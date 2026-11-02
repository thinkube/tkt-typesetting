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

    css = (tmp_path / "book.css").read_text(encoding="utf-8")
    assert css.count("@font-face") == 4
    for filename in font.files:
        assert f'url("../fonts/{filename}")' in css
    assert 'font-family: "EB Garamond", serif' in css


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
