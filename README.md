# tkt-typesetting

A Thinkube app template that typesets a Markdown manuscript as a book: a print-ready PDF set with [Typst](https://typst.app), and an EPUB e-book and a Word document written with [pandoc](https://pandoc.org).

## What it does

Upload a manuscript, choose the formats and the layout, and download the results from the web page or through the REST API.

| Format | File | How it is made |
|---|---|---|
| `pdf` | `book.pdf` | pandoc writes Typst source through `backend/typesetter/book.typst`; Typst sets it |
| `epub` | `book.epub` | pandoc's EPUB 3 writer, with the face embedded and one file per chapter |
| `docx` | `book.docx` | pandoc's Word writer, with a reference document set for the book: the chosen face and size, the page size with mirrored margins, page numbers in the footer, parts and chapters on a new page, justified and indented paragraphs |

| Option | Values | Default |
|---|---|---|
| `font` | `eb-garamond` (EB Garamond), `crimson-pro` (Crimson Pro), `libertinus` (Libertinus Serif) | `eb-garamond` |
| `paper` | `15x23cm`, `a5`, `6x9in`, `a4` | `15x23cm` |
| `lang` | `es`, `ca`, `gl`, `eu`, `pt`, `en`, `fr`, `it`, `de` | `es` |
| `font_size` | 9 to 14 points | 11 |
| `chapter_level` | 1, 2 or 3: the heading level that starts a chapter | 1 |
| `toc` | a table of contents | `false` |

The language sets hyphenation, the quotation marks Typst prints for straight quotes (« » in Spanish and Catalan) and the title of the contents.

## The manuscript

Markdown in UTF-8, as pandoc reads it. The title page comes from the YAML front matter:

```markdown
---
title: "The title"
subtitle: "An optional subtitle"
author: "The author"
place: "Vielha"
date: "2026"
---

## Chapter 1

—Dialogue with em dashes —she says—, italics with *asterisks*.

***

A scene break: three asterisks on a line of their own.


Two or more blank lines: a change of scene set as a blank line's space.
```

An em dash stays with the word it touches: a closing dash ("—dice Marisa—.") never starts a line, and an opening one never ends a line. A dash with a space on one side still breaks at the space.

One blank line is a paragraph break, as in any Markdown. Two or more blank lines in a row mark a change of scene: the PDF and the EPUB leave a blank line's space and start the next paragraph without an indent; Word gets an empty paragraph. Next to a heading such a space is dropped.

In the PDF, the title page is a recto with a blank back. `place` and `date` ("Vielha, 2026") go on the next recto, in italics, set right at a fifth of the page's height, also with a blank back, so the contents or the first part start on a recto. The Word document has the same pages; the EPUB gives the line a page of its own. None of the three repeats the date on the title page.

Each chapter opens with a dropped capital three lines high: in the PDF with the [droplet](https://typst.app/universe/package/droplet) package, which the image carries, and in the EPUB with the stylesheet. A chapter whose first paragraph starts with a dialogue dash or quotation marks gets none. Word documents have no dropped capitals. With `toc`, the PDF has a contents page after it, the EPUB a contents page, and the Word document a contents field that Word fills in when the file is opened.

In the PDF, a heading at `chapter_level` starts a new page; a heading above it (fewer `#`) is a part title on a page of its own; a heading below it is set in the text. The EPUB starts a new file at each chapter. Paragraphs are justified, indented and set without space between them, and Typst avoids widows and orphans.

## How it reaches a user

A person deploys it from the Templates page in thinkube-control, part of
[Thinkube](https://github.com/thinkube/thinkube), or asks Claude Code:
*"deploy the typesetting template, call it typesetting"*. The deploy creates
the person's own repository from this template, then builds and deploys the
app. It is not installed on its own.

## How it fits together

- **Web app template.** React on thinkube-style, FastAPI, PostgreSQL, sign-in through Thinkube Identity, API tokens.
- **Argo Workflows** (`services: [workflows]`). Each book is one workflow step that runs `python -m typesetter.run` in the backend's own image, which carries pandoc, Typst and the three faces.
- **Thinkube Storage.** The manuscript and the outputs are artifacts under `argo-artifacts/<app>/books/<id>/`. The step reads and writes them by key.

## API

All routes are under `/api/v1/books` and take a Thinkube Identity token or an API token from this app's **API Tokens** page.

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/books/options` | the formats, faces, page sizes and languages on offer, and the defaults |
| POST | `/api/v1/books` | upload a manuscript (`file`, `formats`, and any of the options above) and start typesetting it |
| GET | `/api/v1/books` | list books |
| GET | `/api/v1/books/<id>` | one book and its state |
| GET | `/api/v1/books/<id>/outputs/<format>` | download one output |
| DELETE | `/api/v1/books/<id>` | delete a book and its files |

```bash
curl -H "Authorization: Bearer $TOKEN" \
     -F file=@novel.md -F formats=pdf,epub,docx \
     -F font=eb-garamond -F paper=15x23cm -F lang=es -F chapter_level=2 \
     https://<app>.<domain>/api/v1/books
```

The OpenAPI page is at `/api/v1/docs`.

## Working on it

Each container has a `run_tests.sh`. Without arguments it runs the whole
suite, as CI does before every build. With a file argument it runs that one
test file:

```bash
cd backend && ./run_tests.sh tests/test_typesetter.py
cd frontend && ./run_tests.sh src/pages/__tests__/BooksPage.test.tsx
```

The book's look is `backend/typesetter/book.typst`; the faces, page sizes and
languages on offer are `backend/typesetter/options.py`. A new face is a
directory under `/usr/local/share/fonts` in `backend/Containerfile` and an
entry in `FONTS`.

## License

MIT. Code generated from this template is yours: no attribution required, and you may license the app you build however you choose. See [LICENSE](LICENSE). pandoc is GPL-2.0 and Typst is Apache 2.0; both run as separate programs in the image. EB Garamond, Crimson Pro and Libertinus are under the SIL Open Font License 1.1.

Copyright Alejandro Martínez Corriá and the Thinkube contributors
