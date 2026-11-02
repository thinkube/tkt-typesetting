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
    """The filters: scene spaces first, then the dropped capital, with the chapter level it reads."""
    return [f"--lua-filter={SCENES_FILTER}", f"--lua-filter={DROPCAP_FILTER}",
            f"--metadata=chapter-level={layout.chapter_level}"]


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
    ] + filter_args(layout)
    command += [f"--epub-embed-font={font.directory}/{f}" for f in font.files]
    if layout.toc:
        command += ["--toc", f"--toc-depth={layout.chapter_level}"]
    return command


def reference_docx(default: bytes, family: str) -> bytes:
    """pandoc's reference.docx with both Latin theme fonts set to the family."""
    source = ZipFile(BytesIO(default))
    target = BytesIO()
    replaced = 0
    with ZipFile(target, "w", ZIP_DEFLATED) as out:
        for item in source.infolist():
            data = source.read(item)
            if item.filename == "word/theme/theme1.xml":
                text, replaced = THEME_LATIN.subn(rf'\g<1>typeface="{family}"', data.decode("utf-8"))
                data = text.encode("utf-8")
            out.writestr(item, data)
    if replaced != 2:
        raise ToolFailed(f"reference.docx has {replaced} Latin theme fonts, not the 2 the face replaces")
    return target.getvalue()


def docx_command(source: Path, work: Path, out: Path, layout: Layout) -> List[str]:
    reference = work / "reference.docx"
    printed = subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"], capture_output=True)
    if printed.returncode != 0:
        raise ToolFailed(f"pandoc could not print its reference.docx: {printed.stderr.decode().strip()}")
    default = printed.stdout
    reference.write_bytes(reference_docx(default, FONTS[layout.font].family))
    return pandoc_common(source, layout) + docx_options(out, reference, layout) + filter_args(layout)


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
