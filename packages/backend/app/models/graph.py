import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    String,
    Integer,
    Float,
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


class Entity(Base):
    """
    An extracted semantic entity (Technology, Concept, Organization, Person, Methodology).
    """
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="CONCEPT", index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, default=1)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    out_relations: Mapped[List["Relationship"]] = relationship(
        "Relationship",
        foreign_keys="Relationship.source_id",
        back_populates="source",
        cascade="all, delete-orphan"
    )
    in_relations: Mapped[List["Relationship"]] = relationship(
        "Relationship",
        foreign_keys="Relationship.target_id",
        back_populates="target",
        cascade="all, delete-orphan"
    )
    groundings: Mapped[List["EntityGrounding"]] = relationship(
        "EntityGrounding",
        back_populates="entity",
        cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type,
            "description": self.description,
            "mention_count": self.mention_count,
            "properties": self.properties or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Relationship(Base):
    """
    A typed directed or bidirectional semantic relationship connecting two entities.
    """
    __tablename__ = "relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    target_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    relation_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="ASSOCIATED_WITH",
        index=True
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    source: Mapped["Entity"] = relationship("Entity", foreign_keys=[source_id], back_populates="out_relations")
    target: Mapped["Entity"] = relationship("Entity", foreign_keys=[target_id], back_populates="in_relations")
    groundings: Mapped[List["EntityGrounding"]] = relationship(
        "EntityGrounding",
        back_populates="relationship",
        cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "weight": self.weight,
            "description": self.description,
            "properties": self.properties or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class EntityGrounding(Base):
    """
    Source span grounding linking entities and relationships directly back to
    physical document chunk occurrences, offsets, and surrounding quotes (Phase 7).
    """
    __tablename__ = "entity_groundings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    entity_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    relationship_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("relationships.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    chunk_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    anchor_label: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    span_start: Mapped[int] = mapped_column(Integer, default=0)
    span_end: Mapped[int] = mapped_column(Integer, default=0)
    matched_text: Mapped[str] = mapped_column(String(512), nullable=False)
    context_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    entity: Mapped[Optional["Entity"]] = relationship("Entity", back_populates="groundings")
    relationship: Mapped[Optional["Relationship"]] = relationship("Relationship", back_populates="groundings")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "relationship_id": self.relationship_id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "anchor_label": self.anchor_label,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "matched_text": self.matched_text,
            "context_snippet": self.context_snippet,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


__table_args__ = (
    Index("idx_rel_src_tgt_type", Relationship.source_id, Relationship.target_id, Relationship.relation_type, unique=True),
    Index("idx_ground_doc_chunk", EntityGrounding.document_id, EntityGrounding.chunk_index),
)
