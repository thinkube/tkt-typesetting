# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""A typeset book: the manuscript, its layout and the workflow that sets it."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, Float, Integer, String, Text

from app.db.session import Base


class BookStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


TERMINAL = {BookStatus.SUCCEEDED, BookStatus.FAILED}


class Book(Base):
    __tablename__ = "books"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    filename = Column(String(512), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    formats = Column(JSON, nullable=False)
    font = Column(String(32), nullable=False)
    paper = Column(String(32), nullable=False)
    lang = Column(String(8), nullable=False)
    font_size = Column(Float, nullable=False)
    chapter_level = Column(Integer, nullable=False)
    toc = Column(Boolean, nullable=False)
    status = Column(Enum(BookStatus), default=BookStatus.QUEUED, nullable=False)
    workflow_name = Column(String(253), nullable=True)
    error = Column(Text, nullable=True)
    pages = Column(Integer, nullable=True)
    seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Book {self.id}: {self.filename} {self.status}>"
