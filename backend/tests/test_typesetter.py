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


def docx_with(theme: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as z:
        z.writestr("word/document.xml", "<w:document/>")
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
    assert '"#dropcap(' in lua
    assert '"opening"' in lua
    # The paragraph after the capital is indented by hand with the template's own indent.
    assert '"#h(paragraph-indent)"' in lua
    assert "#let paragraph-indent = " in template
    assert "first-line-indent: paragraph-indent," in template
    assert run.filter_args(LAYOUT) == [f"--lua-filter={run.SCENES_FILTER}", f"--lua-filter={run.DROPCAP_FILTER}",
                                       "--metadata=chapter-level=2"]


def test_the_contents_title_is_not_a_part_page():
    assert "if not it.outlined" in run.TEMPLATE.read_text(encoding="utf-8")


def test_the_word_reference_takes_the_face_in_both_theme_fonts():
    patched = run.reference_docx(docx_with(THEME), "Crimson Pro")
    with ZipFile(BytesIO(patched)) as z:
        theme = z.read("word/theme/theme1.xml").decode()
        assert z.read("word/document.xml") == b"<w:document/>"
    assert re.findall(r'<a:latin typeface="([^"]*)"', theme) == ["Crimson Pro", "Crimson Pro"]
    assert "panose" not in theme


def test_a_reference_without_theme_fonts_stops_the_run():
    with pytest.raises(run.ToolFailed, match="0 Latin theme fonts"):
        run.reference_docx(docx_with("<a:theme/>"), "Crimson Pro")


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
