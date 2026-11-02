# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""Typeset one manuscript: the command a typesetting step runs.

    python -m typesetter.run --input manuscript.md --output out/ \
        --formats pdf,epub,docx --font eb-garamond --paper 15x23cm \
        --lang es --font-size 11 --chapter-level 2 --toc

Writes one file per format into the output directory, named as FORMATS
declares, and result.json with the PDF's page count and the time taken.
The title, subtitle and author come from the manuscript's YAML front
matter. Exits non-zero when pandoc or Typst fails, with the tool's own
message in the log.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import List, Optional
from zipfile import ZIP_DEFLATED, ZipFile

from typesetter.options import FONTS, FORMATS, LANGUAGES, PAPERS, Font, Layout, parse_formats

TEMPLATE = Path(__file__).with_name("book.typst")
DROPCAP_FILTER = Path(__file__).with_name("dropcap.lua")
SCENES_FILTER = Path(__file__).with_name("scenes.lua")
DASHES_FILTER = Path(__file__).with_name("dashes.lua")
FRONTMATTER_FILTER = Path(__file__).with_name("frontmatter.lua")

# A YAML front matter block at the start, as pandoc reads it.
FRONT_MATTER = re.compile(r"\A---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*\n", re.S)
# The end of a line, then two or more blank lines.
SCENE_BREAK = re.compile(r"\n(?:[ \t]*\n){2,}")

# The Latin theme fonts of pandoc's reference.docx; Word's text styles take
# their face from them.
THEME_LATIN = re.compile(r'(<a:(?:major|minor)Font>\s*<a:latin )typeface="[^"]*"(?: panose="[^"]*")?')


class ToolFailed(Exception):
    pass


def run_tool(command: List[str], cwd: Optional[Path] = None) -> str:
    """Run pandoc or Typst; a failure carries the tool's own message."""
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ToolFailed(f"{command[0]} failed (exit {result.returncode}): {result.stderr.strip()}")
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.stdout


def typst_variables(layout: Layout) -> List[str]:
    """The template variables (book.typst) for this layout, as pandoc -V arguments."""
    paper = PAPERS[layout.paper]
    values = {
        "font": FONTS[layout.font].family,
        "font-size": f"{layout.font_size:g}pt",
        "page-width": f"{paper.width_mm:g}mm",
        "page-height": f"{paper.height_mm:g}mm",
        "margin-inside": f"{paper.inside_mm:g}mm",
        "margin-outside": f"{paper.outside_mm:g}mm",
        "margin-top": f"{paper.top_mm:g}mm",
        "margin-bottom": f"{paper.bottom_mm:g}mm",
        "chapter-level": str(layout.chapter_level),
    }
    args = [f"--variable={k}={v}" for k, v in values.items()]
    if layout.toc:
        args.append("--variable=book-toc=true")
    return args


def pandoc_common(source: Path, layout: Layout) -> List[str]:
    return ["pandoc", str(source), "--from=markdown", f"--metadata=lang={layout.lang}"]


def filter_args(layout: Layout) -> List[str]:
    """The filters: scene spaces, em dashes held to their words, then the dropped capital,
    with the chapter level it reads."""
    return [f"--lua-filter={SCENES_FILTER}", f"--lua-filter={DASHES_FILTER}", f"--lua-filter={DROPCAP_FILTER}",
            f"--metadata=chapter-level={layout.chapter_level}"]


def frontmatter_args(layout: Layout) -> List[str]:
    """The place-and-date page for EPUB and Word (book.typst sets it in the PDF). Its
    space before puts the line at a fifth of the page height: the top margin is
    already there, so it is the rest, in twentieths of a point."""
    paper = PAPERS[layout.paper]
    before = round((0.2 * paper.height_mm - paper.top_mm) * TWIPS_PER_MM)
    return [f"--lua-filter={FRONTMATTER_FILTER}", f"--metadata=place-space-before={before}"]


def mark_scene_breaks(text: str) -> str:
    """Two or more blank lines in a row in the body become a scene-space div (scenes.lua).

    Markdown reads any number of blank lines as one paragraph break; in a
    manuscript the extra ones mark a change of scene. The YAML front matter
    is left as it is."""
    front = ""
    match = FRONT_MATTER.match(text)
    if match:
        front, text = text[:match.end()], text[match.end():]
    return front + SCENE_BREAK.sub("\n\n::: scene-space\n:::\n\n", text)


def pdf_commands(source: Path, work: Path, out: Path, layout: Layout) -> List[List[str]]:
    """pandoc writes the Typst source; Typst sets it, with the face's directory on its font path."""
    font_dir = FONTS[layout.font].directory
    typ = work / "book.typ"
    return [
        pandoc_common(source, layout) + ["--to=typst", f"--template={TEMPLATE}", f"--output={typ}"]
        + filter_args(layout) + typst_variables(layout),
        ["typst", "compile", "--font-path", font_dir, str(typ), str(out)],
    ]


def page_count_command(work: Path, layout: Layout) -> List[str]:
    """Typst reads back the page count the template records under <page-count>."""
    return ["typst", "query", "--font-path", FONTS[layout.font].directory,
            str(work / "book.typ"), "<page-count>", "--field", "value", "--one"]


def epub_css(font: Font) -> str:
    faces = []
    for filename, weight, style in zip(font.files, ("normal", "normal", "bold", "bold"),
                                       ("normal", "italic", "normal", "italic")):
        faces.append(
            "@font-face {\n"
            f'  font-family: "{font.family}";\n'
            f"  font-weight: {weight};\n"
            f"  font-style: {style};\n"
            f'  src: url("../fonts/{filename}");\n'
            "}\n"
        )
    return "".join(faces) + (
        f'body {{ font-family: "{font.family}", serif; text-align: justify; '
        "hyphens: auto; -epub-hyphens: auto; }\n"
        "p { margin: 0; text-indent: 1.2em; }\n"
        "h1, h2, h3 { font-weight: normal; text-align: center; hyphens: none; }\n"
        "h1 + p, h2 + p, h3 + p, hr + p { text-indent: 0; }\n"
        "hr { border: none; margin: 1.2em 0; text-align: center; }\n"
        'hr::after { content: "* * *"; }\n'
        # The chapter's first paragraph, marked by dropcap.lua when it starts with a letter.
        # Two or more blank lines in the manuscript, marked by scenes.lua.
        # The place and date of the front matter (frontmatter.lua), on a page of their own.
        "div.place-date { page-break-before: always; page-break-after: always; margin-top: 20vh; text-align: right; }\n"
        "div.scene-space { height: 1.2em; }\n"
        "div.scene-space + p { text-indent: 0; }\n"
        "div.opening > p { text-indent: 0; }\n"
        "div.opening > p::first-letter { float: left; font-size: 3.3em; line-height: 0.82; "
        "margin: 0.04em 0.08em 0 0; }\n"
    )


def epub_command(source: Path, work: Path, out: Path, layout: Layout) -> List[str]:
    font = FONTS[layout.font]
    css = work / "book.css"
    css.write_text(epub_css(font), encoding="utf-8")
    command = pandoc_common(source, layout) + [
        "--to=epub3", f"--output={out}", f"--css={css}", f"--split-level={layout.chapter_level}",
    ] + frontmatter_args(layout) + filter_args(layout)
    command += [f"--epub-embed-font={font.directory}/{f}" for f in font.files]
    if layout.toc:
        command += ["--toc", f"--toc-depth={layout.chapter_level}"]
    return command


TWIPS_PER_MM = 1440 / 25.4
FOOTER_PART = "word/footer1.xml"
FOOTER_ID = "rIdTkFooter1"
# A centred PAGE field: Word and LibreOffice print the page number in it.
FOOTER_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
    '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    '<w:r><w:t>1</w:t></w:r>'
    '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    '</w:p></w:ftr>'
)


def replace_once(text: str, pattern: str, replacement: str, what: str) -> str:
    """One regex replacement that must match exactly once; reference.docx changing shape stops the run."""
    result, count = re.subn(pattern, replacement, text, flags=re.S)
    if count != 1:
        raise ToolFailed(f"reference.docx: {what} matched {count} times, not once")
    return result


def in_style(styles: str, style_id: str, edit) -> str:
    """Apply edit to one style's XML."""
    pattern = rf'<w:style [^>]*w:styleId="{style_id}".*?</w:style>'
    match = re.search(pattern, styles, re.S)
    if not match:
        raise ToolFailed(f"reference.docx has no style {style_id}")
    return styles[:match.start()] + edit(match.group(0)) + styles[match.end():]


def docx_styles(styles: str, layout: Layout) -> str:
    """Book styles: text size, justified indented paragraphs without space between them,
    parts and chapters on a new page, centred and in the text colour, a lower title."""
    size = round(layout.font_size * 2)
    indent = round(1.2 * layout.font_size * 20)
    styles = replace_once(styles, r'(<w:rPrDefault>.*?)<w:sz w:val="\d+" />\s*<w:szCs w:val="\d+" />',
                          rf'\g<1><w:sz w:val="{size}" /><w:szCs w:val="{size}" />', "the default text size")
    styles = replace_once(styles, r'(<w:pPrDefault>\s*<w:pPr>\s*)<w:spacing w:after="\d+" />',
                          r'\g<1><w:spacing w:after="0" />', "the default paragraph spacing")
    styles = in_style(styles, "BodyText", lambda s: replace_once(
        s, r'<w:spacing w:before="\d+" w:after="\d+" />',
        f'<w:spacing w:before="0" w:after="0" w:line="276" w:lineRule="auto" />'
        f'<w:ind w:firstLine="{indent}" /><w:jc w:val="both" />', "Body Text spacing"))
    styles = in_style(styles, "FirstParagraph", lambda s: replace_once(
        s, r'<w:qFormat />', '<w:qFormat /><w:pPr><w:ind w:firstLine="0" /></w:pPr>', "First Paragraph"))
    styles = in_style(styles, "Title", lambda s: replace_once(
        s, r'<w:spacing w:after="\d+"', '<w:spacing w:before="2880" w:after="480"', "Title spacing"))
    for level in range(1, layout.chapter_level + 1):
        before = 2400 if level == layout.chapter_level else 3600

        def heading(s: str, before: int = before) -> str:
            s = replace_once(s, r'<w:keepNext />', '<w:keepNext /><w:pageBreakBefore />', "heading keepNext")
            s = replace_once(s, r'<w:spacing w:before="\d+" w:after="\d+" />',
                             f'<w:spacing w:before="{before}" w:after="480" /><w:jc w:val="center" />',
                             "heading spacing")
            return replace_once(s, r'<w:color [^>]*/>', '', "heading colour")
        styles = in_style(styles, f"Heading{level}", heading)
    # The table of contents is based on Heading 1 and so starts a page too.
    return styles


def docx_section(document: str, layout: Layout) -> str:
    """The section of the reference document, which pandoc gives the whole book: page
    size, mirrored margins (inside is the binding edge) and the page-number footer,
    left off the title page."""
    paper = PAPERS[layout.paper]
    tw = lambda mm: round(mm * TWIPS_PER_MM)
    section = (
        f'<w:sectPr><w:footerReference w:type="default" r:id="{FOOTER_ID}" />'
        '<w:footnotePr><w:numRestart w:val="eachSect" /></w:footnotePr>'
        f'<w:pgSz w:w="{tw(paper.width_mm)}" w:h="{tw(paper.height_mm)}" />'
        f'<w:pgMar w:top="{tw(paper.top_mm)}" w:right="{tw(paper.outside_mm)}" w:bottom="{tw(paper.bottom_mm)}" '
        f'w:left="{tw(paper.inside_mm)}" w:header="{tw(paper.top_mm / 2)}" w:footer="{tw(paper.bottom_mm / 2)}" '
        'w:gutter="0" />'
        '<w:titlePg /></w:sectPr>'
    )
    document = replace_once(document, r'<w:sectPr>.*?</w:sectPr>', section, "the section properties")
    if 'xmlns:r="' not in document:
        document = replace_once(document, r'<w:document ', '<w:document xmlns:r="http://schemas.openxmlformats.org/'
                                'officeDocument/2006/relationships" ', "the document element")
    return document


def reference_docx(default: bytes, layout: Layout) -> bytes:
    """pandoc's reference.docx set for the book: the face in both Latin theme fonts, the
    book styles, the page and the footer with the page number."""
    family = FONTS[layout.font].family
    source = ZipFile(BytesIO(default))
    target = BytesIO()
    replaced = 0
    with ZipFile(target, "w", ZIP_DEFLATED) as out:
        for item in source.infolist():
            data = source.read(item)
            name = item.filename
            if name == "word/theme/theme1.xml":
                text, replaced = THEME_LATIN.subn(rf'\g<1>typeface="{family}"', data.decode("utf-8"))
                data = text.encode("utf-8")
            elif name == "word/styles.xml":
                data = docx_styles(data.decode("utf-8"), layout).encode("utf-8")
            elif name == "word/document.xml":
                data = docx_section(data.decode("utf-8"), layout).encode("utf-8")
            elif name == "word/settings.xml":
                data = replace_once(data.decode("utf-8"), r'(<w:settings [^>]*>)', r'\g<1><w:mirrorMargins />',
                                    "the settings element").encode("utf-8")
            elif name == "word/_rels/document.xml.rels":
                data = replace_once(
                    data.decode("utf-8"), r'</Relationships>',
                    f'<Relationship Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
                    f'footer" Id="{FOOTER_ID}" Target="footer1.xml" /></Relationships>',
                    "the document relationships").encode("utf-8")
            elif name == "[Content_Types].xml":
                data = replace_once(
                    data.decode("utf-8"), r'</Types>',
                    f'<Override PartName="/{FOOTER_PART}" ContentType="application/vnd.openxmlformats-'
                    'officedocument.wordprocessingml.footer+xml" /></Types>',
                    "the content types").encode("utf-8")
            out.writestr(item, data)
        out.writestr(FOOTER_PART, FOOTER_XML)
    if replaced != 2:
        raise ToolFailed(f"reference.docx has {replaced} Latin theme fonts, not the 2 the face replaces")
    return target.getvalue()


def docx_command(source: Path, work: Path, out: Path, layout: Layout) -> List[str]:
    reference = work / "reference.docx"
    printed = subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"], capture_output=True)
    if printed.returncode != 0:
        raise ToolFailed(f"pandoc could not print its reference.docx: {printed.stderr.decode().strip()}")
    default = printed.stdout
    reference.write_bytes(reference_docx(default, layout))
    return (pandoc_common(source, layout) + docx_options(out, reference, layout)
            + frontmatter_args(layout) + filter_args(layout))


def docx_options(out: Path, reference: Path, layout: Layout) -> List[str]:
    """pandoc's Word options. The contents are a field Word fills in when the document is opened."""
    options = ["--to=docx", f"--output={out}", f"--reference-doc={reference}"]
    if layout.toc:
        options += ["--toc", f"--toc-depth={layout.chapter_level}"]
    return options


def typeset(source: Path, output: Path, layout: Layout) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    pages = None
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        marked = work / "manuscript.md"
        marked.write_text(mark_scene_breaks(source.read_text(encoding="utf-8")), encoding="utf-8")
        source = marked
        for name in layout.formats:
            out = output / FORMATS[name].filename
            if name == "pdf":
                for command in pdf_commands(source, work, out, layout):
                    run_tool(command)
                pages = int(json.loads(run_tool(page_count_command(work, layout))))
            elif name == "epub":
                run_tool(epub_command(source, work, out, layout))
            elif name == "docx":
                run_tool(docx_command(source, work, out, layout))
    return {
        "formats": layout.formats,
        "pages": pages,
        "seconds": round(time.monotonic() - started, 1),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--formats", required=True, type=parse_formats)
    parser.add_argument("--font", required=True, choices=sorted(FONTS))
    parser.add_argument("--paper", required=True, choices=sorted(PAPERS))
    parser.add_argument("--lang", required=True, choices=sorted(LANGUAGES))
    parser.add_argument("--font-size", required=True, type=float)
    parser.add_argument("--chapter-level", required=True, type=int)
    parser.add_argument("--toc", action="store_true")
    args = parser.parse_args(argv)

    layout = Layout(formats=args.formats, font=args.font, paper=args.paper, lang=args.lang,
                    font_size=args.font_size, chapter_level=args.chapter_level, toc=args.toc)
    if layout.error():
        print(layout.error(), file=sys.stderr)
        return 2
    try:
        summary = typeset(args.input, args.output, layout)
    except ToolFailed as e:
        print(str(e), file=sys.stderr)
        return 1
    (args.output / "result.json").write_text(json.dumps(summary), encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
