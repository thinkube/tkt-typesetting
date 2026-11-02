# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""What a book can ask for: output formats, faces, page sizes, languages.

The backend imports this module to validate a request and the typesetting
step imports it to act on one, so it uses the standard library only.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

# Where the Containerfile installs the faces, one directory per family.
FONT_ROOT = "/usr/local/share/fonts"


@dataclass(frozen=True)
class OutputFormat:
    name: str
    filename: str
    media_type: str
    description: str


@dataclass(frozen=True)
class Font:
    name: str
    family: str
    directory: str
    # Regular, italic, bold and bold italic: the files an EPUB embeds.
    files: tuple
    description: str


@dataclass(frozen=True)
class Paper:
    name: str
    label: str
    width_mm: float
    height_mm: float
    # Inside is the binding edge, so it stays wider than outside.
    inside_mm: float
    outside_mm: float
    top_mm: float
    bottom_mm: float


FORMATS: Dict[str, OutputFormat] = {
    f.name: f
    for f in (
        OutputFormat("pdf", "book.pdf", "application/pdf",
                     "Print-ready PDF, typeset with Typst"),
        OutputFormat("epub", "book.epub", "application/epub+zip",
                     "EPUB 3 e-book with the face embedded"),
        OutputFormat("docx", "book.docx",
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                     "Word document in the chosen face"),
    )
}

FONTS: Dict[str, Font] = {
    f.name: f
    for f in (
        Font("eb-garamond", "EB Garamond", f"{FONT_ROOT}/ebgaramond",
             ("EBGaramond-Regular.otf", "EBGaramond-Italic.otf",
              "EBGaramond-Bold.otf", "EBGaramond-BoldItalic.otf"),
             "Classic Garamond, with small caps and ligatures"),
        Font("crimson-pro", "Crimson Pro", f"{FONT_ROOT}/crimsonpro",
             ("CrimsonPro-Regular.ttf", "CrimsonPro-Italic.ttf",
              "CrimsonPro-Bold.ttf", "CrimsonPro-BoldItalic.ttf"),
             "After old-style book faces, a little darker and very readable"),
        Font("libertinus", "Libertinus Serif", f"{FONT_ROOT}/libertinus",
             ("LibertinusSerif-Regular.otf", "LibertinusSerif-Italic.otf",
              "LibertinusSerif-Bold.otf", "LibertinusSerif-BoldItalic.otf"),
             "Clear and sober, good on screen"),
    )
}

PAPERS: Dict[str, Paper] = {
    p.name: p
    for p in (
        Paper("15x23cm", "15 × 23 cm, trade paperback", 150, 230, 22, 16, 20, 24),
        Paper("a5", "A5, 14.8 × 21 cm", 148, 210, 20, 15, 18, 22),
        Paper("6x9in", "6 × 9 in, US trade", 152.4, 228.6, 22, 16, 20, 24),
        Paper("a4", "A4, 21 × 29.7 cm, manuscript", 210, 297, 30, 25, 25, 30),
    )
}

# Languages Typst hyphenates and pandoc localises; the code goes to both.
LANGUAGES: Dict[str, str] = {
    "es": "Español",
    "ca": "Català",
    "gl": "Galego",
    "eu": "Euskara",
    "pt": "Português",
    "en": "English",
    "fr": "Français",
    "it": "Italiano",
    "de": "Deutsch",
}

FONT_SIZE_MIN = 9.0
FONT_SIZE_MAX = 14.0
CHAPTER_LEVELS = (1, 2, 3)


@dataclass(frozen=True)
class Layout:
    """How one book is set. validate() names every value it refuses."""

    formats: List[str]
    font: str = "eb-garamond"
    paper: str = "15x23cm"
    lang: str = "es"
    font_size: float = 11.0
    chapter_level: int = 1
    toc: bool = False

    def errors(self) -> List[str]:
        found = []
        unknown = [n for n in self.formats if n not in FORMATS]
        if not self.formats or unknown:
            found.append(f"formats must name one or more of {', '.join(FORMATS)}; unknown: {unknown}")
        if self.font not in FONTS:
            found.append(f"Unknown font '{self.font}'. Known: {', '.join(FONTS)}")
        if self.paper not in PAPERS:
            found.append(f"Unknown paper '{self.paper}'. Known: {', '.join(PAPERS)}")
        if self.lang not in LANGUAGES:
            found.append(f"Unknown language '{self.lang}'. Known: {', '.join(LANGUAGES)}")
        if not FONT_SIZE_MIN <= self.font_size <= FONT_SIZE_MAX:
            found.append(f"font_size must be between {FONT_SIZE_MIN} and {FONT_SIZE_MAX} points")
        if self.chapter_level not in CHAPTER_LEVELS:
            found.append(f"chapter_level must be one of {', '.join(map(str, CHAPTER_LEVELS))}")
        return found

    def error(self) -> Optional[str]:
        found = self.errors()
        return "; ".join(found) if found else None


def parse_formats(value: str) -> List[str]:
    """Comma-separated names, in the order FORMATS lists them."""
    names = [n.strip() for n in value.split(",") if n.strip()]
    return [n for n in FORMATS if n in names] + [n for n in names if n not in FORMATS]
