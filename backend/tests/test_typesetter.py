# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""The typesetter's commands and files, without running pandoc or Typst.

The test image has neither tool; what each command asks of them is checked
here, and the typesetting itself is seen in the deployed application.
"""
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from typesetter import run
from typesetter.options import FONTS, PAPERS, Layout, parse_formats

LAYOUT = Layout(formats=["pdf", "epub", "docx"], font="eb-garamond", paper="15x23cm", lang="es",
                font_size=11, chapter_level=2, toc=True)

THEME = (
    '<a:theme><a:fontScheme name="Office">'
    '<a:majorFont>\n  <a:latin typeface="Aptos Display" panose="02110004020202020204"/></a:majorFont>'
    '<a:minorFont>\n  <a:latin typeface="Aptos" panose="02110004020202020204"/></a:minorFont>'
    "</a:fontScheme></a:theme>"
)


STYLES = (
    '<w:styles><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:asciiTheme="minorHAnsi" />'
    '<w:sz w:val="24" /><w:szCs w:val="24" /></w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:spacing w:after="200" /></w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:styleId="BodyText"><w:name w:val="Body Text" />'
    '<w:pPr><w:spacing w:before="180" w:after="180" /></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:customStyle="1" w:styleId="FirstParagraph"><w:name w:val="First Paragraph" />'
    '<w:qFormat /></w:style>'
    '<w:style w:type="paragraph" w:styleId="Title"><w:pPr><w:spacing w:after="80" w:line="240" /></w:pPr></w:style>'
    + "".join(
        f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:pPr><w:keepNext /><w:keepLines />'
        f'<w:spacing w:before="160" w:after="80" /><w:outlineLvl w:val="{n - 1}" /></w:pPr>'
        f'<w:rPr><w:color w:val="0F4761" w:themeColor="accent1" /><w:sz w:val="32" /></w:rPr></w:style>'
        for n in (1, 2, 3))
    + '</w:styles>'
)


def docx_with(theme: str) -> bytes:
    """A reference document with the parts and the shapes pandoc's reference.docx has."""
    buffer = BytesIO()
    with ZipFile(buffer, "w") as z:
        z.writestr("[Content_Types].xml", '<Types><Default Extension="xml" ContentType="application/xml" /></Types>')
        z.writestr("word/document.xml", '<w:document xmlns:w="w"><w:body><w:p />'
                   '<w:sectPr><w:footnotePr><w:numRestart w:val="eachSect" /></w:footnotePr></w:sectPr>'
                   '</w:body></w:document>')
        z.writestr("word/_rels/document.xml.rels", '<Relationships></Relationships>')
        z.writestr("word/settings.xml", '<w:settings xmlns:w="w"><w:zoom w:percent="100" /></w:settings>')
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/theme/theme1.xml", theme)
    return buffer.getvalue()


def test_formats_follow_the_listed_order_and_keep_unknown_names():
    assert parse_formats("docx, pdf") == ["pdf", "docx"]
    assert parse_formats("pdf,mobi") == ["pdf", "mobi"]
    assert Layout(formats=parse_formats("pdf,mobi")).error().startswith("formats must name")


def test_every_template_variable_is_in_the_template():
    template = run.TEMPLATE.read_text(encoding="utf-8")
    names = [arg.removeprefix("--variable=").split("=", 1)[0] for arg in run.typst_variables(LAYOUT)]
    assert names == ["font", "font-size", "page-width", "page-height", "margin-inside", "margin-outside",
                     "margin-top", "margin-bottom", "chapter-level", "book-toc"]
    for name in names:
        assert f"${name}$" in template or f"$if({name})$" in template, name


def test_the_layout_becomes_typst_lengths():
    values = dict(arg.removeprefix("--variable=").split("=", 1) for arg in run.typst_variables(LAYOUT))
    paper = PAPERS["15x23cm"]
    assert values["font"] == "EB Garamond"
    assert values["font-size"] == "11pt"
    assert (values["page-width"], values["page-height"]) == (f"{paper.width_mm:g}mm", f"{paper.height_mm:g}mm")
    assert values["chapter-level"] == "2"
    assert "book-toc" not in dict(
        arg.removeprefix("--variable=").split("=", 1) for arg in run.typst_variables(Layout(formats=["pdf"])))


def test_pdf_is_pandoc_to_typst_then_typst_with_the_face_directory(tmp_path):
    to_typst, compile_pdf = run.pdf_commands(Path("m.md"), tmp_path, Path("out/book.pdf"), LAYOUT)
    assert to_typst[:4] == ["pandoc", "m.md", "--from=markdown", "--metadata=lang=es"]
    assert "--to=typst" in to_typst
    assert f"--template={run.TEMPLATE}" in to_typst
    assert f"--lua-filter={run.DROPCAP_FILTER}" in to_typst
    assert compile_pdf == ["typst", "compile", "--font-path", FONTS["eb-garamond"].directory,
                           str(tmp_path / "book.typ"), "out/book.pdf"]
    query = run.page_count_command(tmp_path, LAYOUT)
    assert query[:2] == ["typst", "query"]
    assert query[-4:] == ["<page-count>", "--field", "value", "--one"]
    assert "<page-count>" in run.TEMPLATE.read_text(encoding="utf-8")


def test_epub_embeds_the_four_styles_and_splits_at_chapters(tmp_path):
    command = run.epub_command(Path("m.md"), tmp_path, Path("out/book.epub"), LAYOUT)
    font = FONTS["eb-garamond"]
    assert "--to=epub3" in command
    assert "--split-level=2" in command
    assert [a for a in command if a.startswith("--epub-embed-font=")] == [
        f"--epub-embed-font={font.directory}/{f}" for f in font.files]
    assert ["--toc", "--toc-depth=2"] == command[-2:]
    assert f"--lua-filter={run.DROPCAP_FILTER}" in command

    css = (tmp_path / "book.css").read_text(encoding="utf-8")
    assert "div.opening > p::first-letter" in css
    assert css.count("@font-face") == 4
    for filename in font.files:
        assert f'url("../fonts/{filename}")' in css
    assert 'font-family: "EB Garamond", serif' in css


def test_word_has_contents_down_to_the_chapter_level_when_asked():
    options = run.docx_options(Path("out/book.docx"), Path("ref.docx"), LAYOUT)
    assert options == ["--to=docx", "--output=out/book.docx", "--reference-doc=ref.docx", "--toc", "--toc-depth=2"]
    assert "--toc" not in run.docx_options(Path("b.docx"), Path("r.docx"), Layout(formats=["docx"]))


def test_place_and_date_go_on_a_recto_in_italics_set_right_at_a_fifth_of_the_page():
    template = run.TEMPLATE.read_text(encoding="utf-8")
    assert "#place(top + right, dy: 0.2 * $page-height$ - $margin-top$)[#emph[$place$$if(date)$, $date$$endif$]]" in template
    assert "$elseif(date)$" in template
    # Title page, its blank back, the place and date, their blank back.
    front = template[template.index("$if(title)$\n#page"):template.index("$if(book-toc)$")]
    assert front.count("#page(numbering: none)[]") == 3


def test_chapters_open_with_a_dropped_capital_from_the_packaged_droplet():
    template = run.TEMPLATE.read_text(encoding="utf-8")
    assert '#import "@preview/droplet:0.3.1": dropcap' in template
    containerfile = (Path(__file__).parents[1] / "Containerfile").read_text(encoding="utf-8")
    assert "ARG DROPLET_VERSION=0.3.1" in containerfile
    lua = run.DROPCAP_FILTER.read_text(encoding="utf-8")
    assert 'dropcap(height: 3' in lua
    # A short opening paragraph is followed beside the capital, not by a gap.
    assert 'local FOLLOWERS = 2' in lua
    assert 'set par(first-line-indent: 0pt)' in lua
    assert '"opening"' in lua
    # The paragraph after the capital is indented by hand with the template's own indent.
    assert '"#h(paragraph-indent)"' in lua
    assert "#let paragraph-indent = " in template
    assert "first-line-indent: paragraph-indent," in template
    assert run.filter_args(LAYOUT) == [f"--lua-filter={run.SCENES_FILTER}", f"--lua-filter={run.DASHES_FILTER}",
                                       f"--lua-filter={run.DROPCAP_FILTER}", "--metadata=chapter-level=2"]


def test_the_contents_title_is_not_a_part_page():
    assert "if not it.outlined" in run.TEMPLATE.read_text(encoding="utf-8")


def patched(layout=LAYOUT, theme=THEME):
    z = ZipFile(BytesIO(run.reference_docx(docx_with(theme), layout)))
    return {name: z.read(name).decode() for name in z.namelist()}


def style(styles, style_id):
    return re.search(rf'<w:style [^>]*w:styleId="{style_id}".*?</w:style>', styles, re.S).group(0)


def test_the_word_reference_takes_the_face_in_both_theme_fonts():
    parts = patched()
    assert re.findall(r'<a:latin typeface="([^"]*)"', parts["word/theme/theme1.xml"]) == ["EB Garamond", "EB Garamond"]
    assert "panose" not in parts["word/theme/theme1.xml"]


def test_a_reference_without_theme_fonts_stops_the_run():
    with pytest.raises(run.ToolFailed, match="0 Latin theme fonts"):
        run.reference_docx(docx_with("<a:theme/>"), LAYOUT)


def test_word_pages_have_the_book_size_mirrored_margins_and_a_page_number():
    parts = patched()
    section = re.search(r"<w:sectPr>.*?</w:sectPr>", parts["word/document.xml"], re.S).group(0)
    paper = PAPERS["15x23cm"]
    assert f'<w:pgSz w:w="{round(paper.width_mm * 1440 / 25.4)}" w:h="{round(paper.height_mm * 1440 / 25.4)}" />' in section
    assert f'w:left="{round(paper.inside_mm * 1440 / 25.4)}"' in section
    assert f'w:right="{round(paper.outside_mm * 1440 / 25.4)}"' in section
    assert f'<w:footerReference w:type="default" r:id="{run.FOOTER_ID}" />' in section
    # No page number on the title page.
    assert "<w:titlePg />" in section
    assert "<w:mirrorMargins />" in parts["word/settings.xml"]
    assert "PAGE" in parts[run.FOOTER_PART]
    assert 'Target="footer1.xml"' in parts["word/_rels/document.xml.rels"]
    assert 'PartName="/word/footer1.xml"' in parts["[Content_Types].xml"]


def test_parts_and_chapters_start_a_page_and_paragraphs_are_set_as_in_a_book():
    styles = patched()["word/styles.xml"]
    for level in (1, 2):
        heading = style(styles, f"Heading{level}")
        assert "<w:pageBreakBefore />" in heading
        assert '<w:jc w:val="center" />' in heading
        assert "w:color" not in heading
    assert "<w:pageBreakBefore />" not in style(styles, "Heading3")
    body = style(styles, "BodyText")
    assert '<w:ind w:firstLine="264" />' in body
    assert '<w:jc w:val="both" />' in body
    assert 'w:before="0" w:after="0"' in body
    assert '<w:ind w:firstLine="0" />' in style(styles, "FirstParagraph")
    assert '<w:sz w:val="22" />' in styles
    assert '<w:spacing w:after="0" />' in styles


def test_a_reference_that_changed_shape_stops_the_run():
    with pytest.raises(run.ToolFailed, match="no style Heading1"):
        run.docx_styles(STYLES.replace('w:styleId="Heading1"', 'w:styleId="Other"'), LAYOUT)


def test_a_refused_layout_stops_before_any_tool(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(run.subprocess, "run", lambda *a, **k: pytest.fail("no tool may run"))
    code = run.main(["--input", "m.md", "--output", str(tmp_path), "--formats", "pdf",
                     "--font", "libertinus", "--paper", "a5", "--lang", "es",
                     "--font-size", "30", "--chapter-level", "1"])
    assert code == 2
    assert "font_size" in capsys.readouterr().err


def test_a_failing_tool_is_reported_in_its_own_words(monkeypatch):
    class Result:
        returncode = 1
        stdout = ""
        stderr = "error: unknown font family: Comic Sans"

    monkeypatch.setattr(run.subprocess, "run", lambda *a, **k: Result())
    with pytest.raises(run.ToolFailed, match="typst failed \\(exit 1\\): error: unknown font family"):
        run.run_tool(["typst", "compile", "book.typ"])


def test_two_or_more_blank_lines_in_the_body_mark_a_scene_space():
    manuscript = "---\ntitle: T\n\n\nauthor: A\n---\n\n# Uno\n\nUno.\nSigue.\n\nDos.\n\n\nTres.\n  \n\n\t\n\nCuatro.\n"
    marked = run.mark_scene_breaks(manuscript)
    # The front matter keeps its blank lines; one blank line is a paragraph break.
    assert marked.startswith("---\ntitle: T\n\n\nauthor: A\n---\n")
    assert "Uno.\nSigue.\n\nDos." in marked
    assert marked.count("::: scene-space\n:::") == 2
    assert "Dos.\n\n::: scene-space\n:::\n\nTres." in marked
    assert "Tres.\n\n::: scene-space\n:::\n\nCuatro." in marked


def test_the_scene_space_is_set_for_each_format():
    lua = run.SCENES_FILTER.read_text(encoding="utf-8")
    assert '"#scene-space"' in lua
    assert '"<w:p/>"' in lua
    assert "#let scene-space = " in run.TEMPLATE.read_text(encoding="utf-8")
    assert "div.scene-space + p { text-indent: 0; }" in run.epub_css(run.FONTS["libertinus"])


def test_every_format_runs_the_filters(tmp_path, monkeypatch):
    class Printed:
        returncode = 0
        stdout = docx_with(THEME)
        stderr = b""

    monkeypatch.setattr(run.subprocess, "run", lambda *a, **k: Printed())
    filters = run.filter_args(LAYOUT)
    to_typst = run.pdf_commands(Path("m.md"), tmp_path, Path("b.pdf"), LAYOUT)[0]
    epub = run.epub_command(Path("m.md"), tmp_path, Path("b.epub"), LAYOUT)
    docx = run.docx_command(Path("m.md"), tmp_path, Path("b.docx"), LAYOUT)
    for command in (to_typst, epub, docx):
        assert all(arg in command for arg in filters)


def test_em_dashes_are_held_to_the_words_they_touch():
    lua = run.DASHES_FILTER.read_text(encoding="utf-8")
    assert 'WORD_JOINER = "\\u{2060}"' in lua
    assert '"([^%s])" .. DASH' in lua
    assert 'DASH .. "([^%s])"' in lua


def test_place_and_date_get_their_own_page_in_epub_and_word_too(tmp_path, monkeypatch):
    paper = PAPERS["15x23cm"]
    before = round((0.2 * paper.height_mm - paper.top_mm) * 1440 / 25.4)
    assert run.frontmatter_args(LAYOUT) == [f"--lua-filter={run.FRONTMATTER_FILTER}",
                                            f"--metadata=place-space-before={before}"]

    class Printed:
        returncode = 0
        stdout = docx_with(THEME)
        stderr = b""

    monkeypatch.setattr(run.subprocess, "run", lambda *a, **k: Printed())
    filter_arg = f"--lua-filter={run.FRONTMATTER_FILTER}"
    assert filter_arg in run.epub_command(Path("m.md"), tmp_path, Path("b.epub"), LAYOUT)
    assert filter_arg in run.docx_command(Path("m.md"), tmp_path, Path("b.docx"), LAYOUT)
    # The PDF's place-and-date page is book.typst's.
    assert filter_arg not in run.pdf_commands(Path("m.md"), tmp_path, Path("b.pdf"), LAYOUT)[0]
    assert "div.place-date" in run.epub_css(run.FONTS["eb-garamond"])

    lua = run.FRONTMATTER_FILTER.read_text(encoding="utf-8")
    assert '"<w:p><w:pPr><w:pageBreakBefore/></w:pPr>"' in lua
    assert '<w:jc w:val=\\"right\\"/>' in lua
    assert '"place-date"' in lua
    assert "doc.meta.date = nil" in lua


def test_word_gets_no_opening_wrapper():
    lua = run.DROPCAP_FILTER.read_text(encoding="utf-8")
    assert 'elseif FORMAT:match("epub") then' in lua


EMBED_KEYS = [f"{{0000000{n}-0000-0000-0000-00000000000{n}}}" for n in range(1, 5)]


def word_document():
    buffer = BytesIO()
    with ZipFile(buffer, "w") as z:
        z.writestr("[Content_Types].xml", '<Types><Default Extension="xml" ContentType="application/xml" /></Types>')
        z.writestr("word/fontTable.xml", '<w:fonts xmlns:r="r" xmlns:w="w"><w:font w:name="Calibri"></w:font>'
                   '<w:font w:name="EB Garamond"><w:charset w:val="00" /></w:font></w:fonts>')
        z.writestr("word/settings.xml", '<w:settings><w:zoom w:percent="100" /><w:embedSystemFonts /></w:settings>')
        z.writestr("word/document.xml", "<w:document />")
    return buffer.getvalue()


def face_with_files(tmp_path):
    files = []
    for n, style in enumerate(("Regular", "Italic", "Bold", "BoldItalic")):
        path = tmp_path / f"Face-{style}.ttf"
        path.write_bytes(bytes([n]) * 64)
        files.append(str(path))
    return run.Font("eb-garamond", "EB Garamond", "/fonts", (), "", tuple(files))


def test_word_documents_carry_their_face(tmp_path):
    font = face_with_files(tmp_path)
    z = ZipFile(BytesIO(run.embed_docx_fonts(word_document(), font, EMBED_KEYS)))
    table = z.read("word/fontTable.xml").decode()
    # One entry for the family, the four styles in the order Word's schema gives them.
    assert table.count('w:name="EB Garamond"') == 1
    assert re.findall(r"<w:(embed\w+) r:id", table) == ["embedRegular", "embedBold", "embedItalic", "embedBoldItalic"]
    assert f'w:fontKey="{EMBED_KEYS[0]}"' in table
    rels = z.read("word/_rels/fontTable.xml.rels").decode()
    assert [f"fonts/font{n}.odttf" for n in range(1, 5)] == re.findall(r'Target="([^"]+)"', rels)
    assert "<w:embedTrueTypeFonts /><w:embedSystemFonts />" in z.read("word/settings.xml").decode()
    assert 'Extension="odttf"' in z.read("[Content_Types].xml").decode()
    # font2 is the bold slot: the Bold file (index 2), obfuscated with the second key.
    stored = z.read("word/fonts/font2.odttf")
    assert stored != bytes([2]) * 64
    assert run.obfuscate_font(stored, EMBED_KEYS[1]) == bytes([2]) * 64


def test_the_obfuscation_follows_the_word_specification():
    key = "{00112233-4455-6677-8899-AABBCCDDEEFF}"
    data = bytes(range(40))
    stored = run.obfuscate_font(data, key)
    # The GUID's bytes in reverse order: the first byte meets 0xFF, the sixteenth 0x00.
    assert stored[0] == 0x00 ^ 0xFF and stored[15] == 0x0F ^ 0x00 and stored[16] == 0x10 ^ 0xFF
    assert stored[32:] == data[32:]
    assert run.obfuscate_font(stored, key) == data


def test_every_face_has_four_truetype_files_to_embed():
    for font in FONTS.values():
        assert len(font.embed) == 4
        assert all(path.endswith(".ttf") for path in font.embed)
