"""commands — the agent's work queue."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CommandState(StrEnum):
    queued = "queued"
    leased = "leased"
    done = "done"
    failed = "failed"
    canceled = "canceled"


class Command(Base):
    __tablename__ = "commands"
    __table_args__ = (
        # Idempotency key must be unique per customer (NULL allowed for
        # system-generated commands that don't need dedup).
        UniqueConstraint(
            "customer_id",
            "idempotency_key",
            name="idempotency",
        ),
    )

    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    state: Mapped[CommandState] = mapped_column(
        SAEnum(CommandState, name="command_state"),
        nullable=False,
        default=CommandState.queued,
        index=True,
    )
    enqueued_by: Mapped[str] = mapped_column(String(256), nullable=False, default="system")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    leased_by_agent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Command id={self.id} kind={self.kind} state={self.state}>"
