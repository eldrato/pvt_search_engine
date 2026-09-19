import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.core.db import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class CrawlDomain(Base):
    """
    Allowlisted domain record for strictly bounded personal crawling.
    """
    __tablename__ = "crawl_domains"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    max_depth: Mapped[int] = mapped_column(Integer, default=2)
    rate_limit_delay: Mapped[float] = mapped_column(Float, default=1.0)
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0)
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "domain": self.domain,
            "description": self.description,
            "enabled": self.enabled,
            "max_depth": self.max_depth,
            "rate_limit_delay": self.rate_limit_delay,
            "pages_crawled": self.pages_crawled,
            "last_crawled_at": self.last_crawled_at.isoformat() if self.last_crawled_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CrawlJob(Base):
    """
    Asynchronous crawl job execution record and frontier telemetry.
    """
    __tablename__ = "crawl_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    seed_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)  # queued, running, completed, failed, cancelled
    max_depth: Mapped[int] = mapped_column(Integer, default=2)
    max_pages: Mapped[int] = mapped_column(Integer, default=20)
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    current_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True
    )

    pages: Mapped[List["CrawlPage"]] = relationship(
        "CrawlPage",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="CrawlPage.crawled_at.desc()"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "seed_url": self.seed_url,
            "domain": self.domain,
            "status": self.status,
            "max_depth": self.max_depth,
            "max_pages": self.max_pages,
            "pages_crawled": self.pages_crawled,
            "pages_failed": self.pages_failed,
            "current_url": self.current_url,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CrawlPage(Base):
    """
    Log of individual visited page within a crawl job.
    """
    __tablename__ = "crawl_pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    document_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    depth: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True
    )

    job: Mapped["CrawlJob"] = relationship("CrawlJob", back_populates="pages")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "status_code": self.status_code,
            "title": self.title,
            "content_hash": self.content_hash,
            "document_id": self.document_id,
            "depth": self.depth,
            "error_message": self.error_message,
            "crawled_at": self.crawled_at.isoformat() if self.crawled_at else None,
        }
