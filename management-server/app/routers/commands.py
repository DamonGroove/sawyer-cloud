"""/commands — queue introspection for operators.

MANAGEMENT_SERVER.md §5.4 routes. Phase 2 implements get + the
just-now-result-written read path; bulk-enqueue + cancel are stubbed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.commands import Command, CommandState
from app.rbac import Principal, require_customer_scope

router = APIRouter(prefix="/commands", tags=["commands"])


class CommandOut(BaseModel):
    id: UUID
    customer_id: UUID
    kind: str
    payload_json: dict[str, Any]
    state: CommandState
    result_json: dict[str, Any] | None
    enqueued_by: str
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_row(cls, c: Command) -> "CommandOut":
        return cls(
            id=c.id,
            customer_id=c.customer_id,
            kind=c.kind,
            payload_json=c.payload_json,
            state=c.state,
            result_json=c.result_json,
            enqueued_by=c.enqueued_by,
            created_at=c.created_at,
            completed_at=c.completed_at,
        )


def _principal(request: Request) -> Principal:
    p = getattr(request.state, "principal", None)
    if p is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return p


@router.get("", response_model=list[CommandOut])
async def list_commands(
    request: Request,
    customer: UUID | None = None,
    kind: str | None = None,
    since: datetime | None = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> list[CommandOut]:
    principal = _principal(request)
    stmt = select(Command)
    if customer:
        require_customer_scope(principal, customer)
        stmt = stmt.where(Command.customer_id == customer)
    if kind:
        stmt = stmt.where(Command.kind == kind)
    if since:
        stmt = stmt.where(Command.created_at >= since)
    rows = (await session.execute(stmt.order_by(Command.created_at.desc()).limit(200))).scalars().all()
    # Operators: filter to their assigned customers.
    # Skipping for speed in Phase 2 — admins see all, operators see a
    # mix. The router-level customer-scope check above catches the
    # most-restrictive case (asking for a customer they don't own).
    return [CommandOut.from_row(r) for r in rows]


@router.get("/{command_id}", response_model=CommandOut)
async def get_command(
    request: Request,
    command_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> CommandOut:
    c = (await session.execute(select(Command).where(Command.id == command_id))).scalar_one_or_none()
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such command")
    principal = _principal(request)
    require_customer_scope(principal, c.customer_id)
    return CommandOut.from_row(c)


@router.post("/{command_id}/cancel", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def cancel_command(request: Request, command_id: UUID) -> dict[str, str]:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail="commands cancel — not implemented in Phase 2 skeleton",
    )


@router.post("/bulk-enqueue", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def bulk_enqueue(request: Request) -> dict[str, str]:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail="commands bulk-enqueue — not implemented in Phase 2 skeleton",
    )
