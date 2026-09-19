import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    DateTime,
    JSON,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.core.db import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Document(Base):
    """
    Authoritative Single Source of Truth (SSOT) record for ingested documents.
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="upload", index=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="text/plain")
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    raw_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doc_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index"
    )

    def to_dict(self, chunk_count: Optional[int] = None) -> dict:
        if chunk_count is None:
            if "chunks" in self.__dict__ and self.__dict__["chunks"] is not None:
                chunk_count = len(self.__dict__["chunks"])
            else:
                chunk_count = 0

        return {
            "id": self.id,
            "title": self.title,
            "source_type": self.source_type,
            "file_path": self.file_path,
            "mime_type": self.mime_type,
            "file_size_bytes": self.file_size_bytes,
            "content_hash": self.content_hash,
            "doc_metadata": self.doc_metadata or {},
            "chunk_count": chunk_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DocumentChunk(Base):
    """
    Searchable granular chunk of a document preserving structural anchors
    (pages, lines, headings) and lexical payload.
    """
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    location_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "token_count": self.token_count,
            "chunk_hash": self.chunk_hash,
            "location_meta": self.location_meta or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


__table_args__ = (
    Index("idx_doc_chunks_doc_idx", DocumentChunk.document_id, DocumentChunk.chunk_index),
)
