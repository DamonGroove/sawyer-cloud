"""base_images — built aio-base image tags."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum as SAEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PromotionStage(StrEnum):
    none = "none"
    staging_green = "staging-green"
    production = "production"


class BaseImage(Base):
    __tablename__ = "base_images"

    tag: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    git_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    promoted_to: Mapped[PromotionStage] = mapped_column(
        SAEnum(PromotionStage, name="promotion_stage", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=PromotionStage.none,
    )
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_safe_from_tags: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
