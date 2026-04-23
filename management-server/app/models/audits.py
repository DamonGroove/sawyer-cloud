"""audits — append-only audit log."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ActorKind(StrEnum):
    user = "user"
    service = "service"
    agent = "agent"
    system = "system"


class AuditResult(StrEnum):
    success = "success"
    failure = "failure"


class Audit(Base):
    __tablename__ = "audits"

    actor_kind: Mapped[ActorKind] = mapped_column(
        SAEnum(ActorKind, name="actor_kind"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    customer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[AuditResult] = mapped_column(
        SAEnum(AuditResult, name="audit_result"),
        nullable=False,
    )
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
