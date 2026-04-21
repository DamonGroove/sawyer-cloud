"""features — catalog of what can be enabled per customer."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import JSON, Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FeatureProvider(StrEnum):
    upstream_optional = "upstream-optional"
    community_container = "community-container"
    nc_app = "nc-app"
    custom = "custom"


class Feature(Base):
    __tablename__ = "features"

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    provides: Mapped[FeatureProvider] = mapped_column(
        SAEnum(FeatureProvider, name="feature_provider", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    default_on_flavors: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    conflicts_with: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    min_base_image_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)

    def __repr__(self) -> str:
        return f"<Feature key={self.key} provides={self.provides}>"
