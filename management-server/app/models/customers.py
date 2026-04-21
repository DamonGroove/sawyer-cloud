"""customers — one row per Nextcloud AIO customer instance."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SiteMode(StrEnum):
    docker = "docker"
    vm = "vm"


class CustomerState(StrEnum):
    pending = "pending"
    healthy = "healthy"
    degraded = "degraded"
    offline = "offline"
    decommissioned = "decommissioned"


class Customer(Base):
    __tablename__ = "customers"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    domain: Mapped[str] = mapped_column(String(256), nullable=False)
    flavor_slug: Mapped[str] = mapped_column(
        ForeignKey("flavors.slug", ondelete="RESTRICT"),
        nullable=False,
    )
    site_mode: Mapped[SiteMode] = mapped_column(
        SAEnum(SiteMode, name="site_mode"),
        nullable=False,
        default=SiteMode.docker,
    )
    deployed_image_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[CustomerState] = mapped_column(
        SAEnum(CustomerState, name="customer_state"),
        nullable=False,
        default=CustomerState.pending,
        index=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    managed_by_team: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    def __repr__(self) -> str:
        return f"<Customer slug={self.slug} state={self.state}>"
