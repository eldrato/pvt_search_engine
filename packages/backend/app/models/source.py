from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SourceConfig(Base):
    """
    Configuration for an ingestion & search intelligence source.
    Allows enabling/disabling sources and setting default privacy tiers.
    """
    __tablename__ = "source_configs"

    source_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_privacy_tier: Mapped[str] = mapped_column(String(32), default="private", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(64), default="FileText", nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "display_name": self.display_name,
            "enabled": self.enabled,
            "default_privacy_tier": self.default_privacy_tier,
            "description": self.description,
            "icon": self.icon,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
