"""flavors — catalog of deployment flavors (default, law-firm, …)."""

from __future__ import annotations

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Flavor(Base):
    __tablename__ = "flavors"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    nextcloud_version_pin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_apps: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    default_community_containers: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )

    def __repr__(self) -> str:
        return f"<Flavor slug={self.slug}>"
