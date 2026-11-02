# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""Books: upload a manuscript, follow its typesetting, download, delete.

Every route takes a Thinkube Identity token or one of this application's API
tokens, so scripts call the same API as the web page.
"""
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.api_tokens import get_current_user_dual_auth
from app.core.config import settings
from app.db.session import get_db
from app.models.book import TERMINAL, Book, BookStatus
from app.services import storage, workflows
from typesetter.options import (
    CHAPTER_LEVELS,
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    FONTS,
    FORMATS,
    LANGUAGES,
    PAPERS,
    Layout,
    parse_formats,
)

router = APIRouter()

PHASES = {
    "Pending": BookStatus.QUEUED,
    "Running": BookStatus.RUNNING,
    "Succeeded": BookStatus.SUCCEEDED,
    "Failed": BookStatus.FAILED,
    "Error": BookStatus.FAILED,
}

MANUSCRIPT_SUFFIXES = (".md", ".markdown", ".txt")
DEFAULTS = Layout(formats=list(FORMATS))


class FormatInfo(BaseModel):
    name: str
    filename: str
    description: str


class FontInfo(BaseModel):
    name: str
    family: str
    description: str


class PaperInfo(BaseModel):
    name: str
    label: str
    width_mm: float
    height_mm: float


class LayoutDefaults(BaseModel):
    formats: List[str]
    font: str
    paper: str
    lang: str
    font_size: float
    chapter_level: int
    toc: bool


class Options(BaseModel):
    formats: List[FormatInfo]
    fonts: List[FontInfo]
    papers: List[PaperInfo]
    languages: Dict[str, str]
    font_size_min: float
    font_size_max: float
    chapter_levels: List[int]
    defaults: LayoutDefaults
    max_upload_mb: int


class BookOut(BaseModel):
    id: str
    filename: str
    size_bytes: int
    formats: List[str]
    font: str
    paper: str
    lang: str
    font_size: float
    chapter_level: int
    toc: bool
    status: BookStatus
    error: Optional[str] = None
    pages: Optional[int] = None
    seconds: Optional[float] = None
    workflow_name: Optional[str] = None
    logs_url: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None

    @classmethod
    def of(cls, b: Book) -> "BookOut":
        return cls(
            id=b.id, filename=b.filename, size_bytes=b.size_bytes, formats=b.formats, font=b.font,
            paper=b.paper, lang=b.lang, font_size=b.font_size, chapter_level=b.chapter_level, toc=b.toc,
            status=b.status, error=b.error, pages=b.pages, seconds=b.seconds, workflow_name=b.workflow_name,
            logs_url=workflows.logs_url(b.workflow_name) if b.workflow_name else None,
            created_at=b.created_at, finished_at=b.finished_at,
        )


@router.get("/options", response_model=Options)
async def options(current_user: dict = Depends(get_current_user_dual_auth)):
    """The formats, faces, page sizes and languages a book can ask for, and the defaults."""
    return Options(
        formats=[FormatInfo(name=f.name, filename=f.filename, description=f.description) for f in FORMATS.values()],
        fonts=[FontInfo(name=f.name, family=f.family, description=f.description) for f in FONTS.values()],
        papers=[PaperInfo(name=p.name, label=p.label, width_mm=p.width_mm, height_mm=p.height_mm)
                for p in PAPERS.values()],
        languages=LANGUAGES,
        font_size_min=FONT_SIZE_MIN,
        font_size_max=FONT_SIZE_MAX,
        chapter_levels=list(CHAPTER_LEVELS),
        defaults=LayoutDefaults(
            formats=DEFAULTS.formats, font=DEFAULTS.font, paper=DEFAULTS.paper, lang=DEFAULTS.lang,
            font_size=DEFAULTS.font_size, chapter_level=DEFAULTS.chapter_level, toc=DEFAULTS.toc,
        ),
        max_upload_mb=settings.MAX_UPLOAD_MB,
    )


@router.post("", response_model=BookOut, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=BookOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_book(
    file: UploadFile = File(..., description="The manuscript: Markdown in UTF-8, with optional YAML front matter"),
    formats: str = Form(..., description="Comma-separated format names: pdf, epub, docx"),
    font: str = Form(DEFAULTS.font),
    paper: str = Form(DEFAULTS.paper),
    lang: str = Form(DEFAULTS.lang),
    font_size: float = Form(DEFAULTS.font_size, description="Body text size in points"),
    chapter_level: int = Form(DEFAULTS.chapter_level, description="The heading level that starts a chapter"),
    toc: bool = Form(DEFAULTS.toc, description="Add a table of contents"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_dual_auth),
):
    """Upload a manuscript and start typesetting it."""
    layout = Layout(formats=parse_formats(formats), font=font, paper=paper, lang=lang,
                    font_size=font_size, chapter_level=chapter_level, toc=toc)
    if layout.error():
        raise HTTPException(422, layout.error())

    if not file.filename:
        raise HTTPException(422, "The upload has no file name")
    if not file.filename.lower().endswith(MANUSCRIPT_SUFFIXES):
        raise HTTPException(422, f"'{file.filename}' is not a manuscript: send {', '.join(MANUSCRIPT_SUFFIXES)}")
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"'{file.filename}' is larger than {settings.MAX_UPLOAD_MB} MB")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(422, f"'{file.filename}' is not UTF-8 text (byte {e.start})")

    book = Book(
        user_id=current_user["sub"],
        filename=file.filename,
        size_bytes=len(data),
        formats=layout.formats,
        font=layout.font,
        paper=layout.paper,
        lang=layout.lang,
        font_size=layout.font_size,
        chapter_level=layout.chapter_level,
        toc=layout.toc,
    )
    db.add(book)
    db.flush()

    storage.put_source(book.id, data)
    book.workflow_name = workflows.submit(book.id, layout)
    db.commit()
    db.refresh(book)
    return BookOut.of(book)


def _refresh(book: Book, db: Session) -> Book:
    """Bring a running book up to date with its workflow."""
    if book.status in TERMINAL or not book.workflow_name:
        return book
    state = workflows.state(book.workflow_name)
    if state is None:
        # Finished runs are removed after a day; what the run left in storage
        # says how it ended.
        state = workflows.WorkflowState(
            phase="Succeeded" if storage.read_result(book.id) is not None else "Failed",
            message=f"Workflow {book.workflow_name} was removed before its result was read",
        )
    if state.phase not in PHASES:
        raise HTTPException(502, f"Workflow {book.workflow_name} reports an unknown phase '{state.phase}'")
    new_status = PHASES[state.phase]
    if new_status == BookStatus.SUCCEEDED:
        result = storage.read_result(book.id)
        if result is None:
            new_status = BookStatus.FAILED
            book.error = "The workflow succeeded but wrote no result.json"
        else:
            book.pages = result["pages"]
            book.seconds = result["seconds"]
    elif new_status == BookStatus.FAILED:
        book.error = state.message or f"Workflow {state.phase}"
    if new_status != book.status:
        book.status = new_status
        if new_status in TERMINAL:
            book.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(book)
    return book


def _owned(book_id: str, db: Session, user: dict) -> Book:
    book = db.query(Book).filter(Book.id == book_id, Book.user_id == user["sub"]).first()
    if not book:
        raise HTTPException(404, "Book not found")
    return book


@router.get("", response_model=List[BookOut])
@router.get("/", response_model=List[BookOut], include_in_schema=False)
async def list_books(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_dual_auth),
):
    """The caller's books, newest first."""
    rows = db.query(Book).filter(Book.user_id == current_user["sub"]).order_by(Book.created_at.desc()).all()
    return [BookOut.of(_refresh(b, db)) for b in rows]


@router.get("/{book_id}", response_model=BookOut)
async def get_book(
    book_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_dual_auth),
):
    return BookOut.of(_refresh(_owned(book_id, db, current_user), db))


@router.get("/{book_id}/outputs/{format_name}")
async def download_output(
    book_id: str,
    format_name: str,
    download: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_dual_auth),
):
    """One output of a typeset book."""
    book = _refresh(_owned(book_id, db, current_user), db)
    if format_name not in book.formats:
        raise HTTPException(404, f"This book was not typeset as '{format_name}'")
    if book.status != BookStatus.SUCCEEDED:
        raise HTTPException(409, f"The book is {book.status.value}")
    fmt = FORMATS[format_name]
    chunks = storage.open_output(book.id, fmt.filename)
    if chunks is None:
        raise HTTPException(404, f"{fmt.filename} is not in storage")
    return StreamingResponse(
        chunks,
        media_type=fmt.media_type,
        headers={"Content-Disposition": content_disposition(book.filename, fmt.filename, download)},
    )


def content_disposition(manuscript: str, output: str, download: bool) -> str:
    """The manuscript's name with the output's extension. Headers are Latin-1, so a
    name outside ASCII goes in filename* (RFC 6266) with an ASCII filename beside it."""
    name = f"{manuscript.rsplit('.', 1)[0]}.{output.rsplit('.', 1)[1]}"
    disposition = "attachment" if download else "inline"
    ascii_name = name.encode("ascii", "replace").decode("ascii").replace('"', "'")
    if ascii_name == name:
        return f'{disposition}; filename="{name}"'
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(
    book_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_dual_auth),
):
    """Delete the book, its manuscript and its outputs."""
    book = _owned(book_id, db, current_user)
    storage.delete_book(book.id)
    db.delete(book)
    db.commit()
