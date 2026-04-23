"""/agents — the agent-facing + operator-facing agent endpoints.

Agent-facing (authenticated via mTLS in prod; via test headers here):
    POST /agents/register         — one-time registration with token.
    POST /agents/tick              — long-poll heartbeat + command fetch.
    POST /agents/commands/{id}/result — command completion report.
    POST /agents/log               — structured log line.

Operator-facing:
    GET  /agents                   — list agents (filter by customer).
    POST /agents/{slug}/rotate     — issue a fresh mTLS cert (stub).
    POST /agents/{slug}/revoke     — revoke the current cert (stub).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.agents import Agent
from app.models.commands import Command, CommandState
from app.models.customers import Customer, CustomerState

router = APIRouter(prefix="/agents", tags=["agents"])


# ---------- schemas --------------------------------------------------------

class RegisterIn(BaseModel):
    registration_token: str = Field(..., min_length=16)
    customer_slug: str = Field(..., min_length=1)
    csr_pem: str = Field(..., min_length=32, description="Agent's CSR in PEM form")
    agent_version: str = Field(..., max_length=32)


class RegisterOut(BaseModel):
    agent_id: UUID
    signed_cert_pem: str
    ca_cert_pem: str


class TickIn(BaseModel):
    heartbeat: dict[str, Any] = Field(default_factory=dict)
    ready_for_commands: bool = True
    max_commands: int = Field(default=5, ge=1, le=20)


class TickCommandOut(BaseModel):
    id: UUID
    kind: str
    payload_json: dict[str, Any]
    idempotency_key: str | None
    lease_deadline: datetime


class TickOut(BaseModel):
    commands: list[TickCommandOut]
    next_tick_hint_seconds: int = 15


class CommandResultIn(BaseModel):
    result_json: dict[str, Any] = Field(default_factory=dict)
    state: CommandState


# ---------- helpers --------------------------------------------------------

async def _get_customer_by_slug(session: AsyncSession, slug: str) -> Customer:
    c = (await session.execute(select(Customer).where(Customer.slug == slug))).scalar_one_or_none()
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no customer with slug {slug}")
    return c


def _cert_fingerprint(csr_pem: str) -> str:
    # Phase 2 stub: we hash the CSR bytes instead of issuing a real cert.
    # The real implementation will use cryptography.x509 to sign with the
    # per-customer CA and compute the signed-cert fingerprint.
    return hashlib.sha256(csr_pem.encode("utf-8")).hexdigest()


def _issue_fake_cert(csr_pem: str) -> tuple[str, str]:
    # Placeholder PEMs — replace when the real CA plumbing lands.
    fp = _cert_fingerprint(csr_pem)
    cert = (
        "-----BEGIN CERTIFICATE-----\n"
        "# sawyer-cloud Phase 2 stub — agent cert, fp=" + fp + "\n"
        "-----END CERTIFICATE-----\n"
    )
    ca = (
        "-----BEGIN CERTIFICATE-----\n"
        "# sawyer-cloud Phase 2 stub — CA cert (per-customer, in real impl)\n"
        "-----END CERTIFICATE-----\n"
    )
    return cert, ca


# ---------- agent-facing routes --------------------------------------------

@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> RegisterOut:
    # Validate customer exists. Registration token -> customer id is encoded
    # as `.<uuid>` suffix in the token (Phase 2 simplification).
    suffix = body.registration_token.rsplit(".", 1)[-1]
    try:
        customer_id = UUID(suffix)
    except ValueError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="malformed registration_token",
        ) from None

    customer = (
        await session.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if customer is None or customer.slug != body.customer_slug:
        # Don't leak which part of the tuple failed.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="registration rejected",
        )

    fp = _cert_fingerprint(body.csr_pem)
    # Idempotency: if an agent with this fingerprint already exists for
    # this customer, return the prior record's id rather than re-creating.
    existing = (
        await session.execute(
            select(Agent).where(
                Agent.customer_id == customer.id,
                Agent.mtls_cert_fingerprint == fp,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        agent = Agent(
            customer_id=customer.id,
            agent_version=body.agent_version,
            mtls_cert_fingerprint=fp,
            registered_at=datetime.now(timezone.utc),
        )
        session.add(agent)
        # Move customer out of pending now that an agent exists.
        if customer.state == CustomerState.pending:
            customer.state = CustomerState.healthy
        await session.commit()
        await session.refresh(agent)
    else:
        agent = existing

    cert_pem, ca_pem = _issue_fake_cert(body.csr_pem)
    return RegisterOut(agent_id=agent.id, signed_cert_pem=cert_pem, ca_cert_pem=ca_pem)


@router.post("/tick", response_model=TickOut)
async def tick(
    request: Request,
    body: TickIn,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> TickOut:
    fp = getattr(request.state, "agent_fingerprint", None)
    slug = getattr(request.state, "agent_customer_slug", None)
    if not fp or not slug:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="tick requires mTLS (X-Client-Cert-Fingerprint header)",
        )

    customer = await _get_customer_by_slug(session, slug)
    agent = (
        await session.execute(
            select(Agent).where(
                Agent.customer_id == customer.id,
                Agent.mtls_cert_fingerprint == fp,
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="unknown agent fingerprint")

    now = datetime.now(timezone.utc)
    agent.last_heartbeat_at = now
    agent.reported_state_json = body.heartbeat

    customer.last_seen_at = now
    if customer.state == CustomerState.offline:
        customer.state = CustomerState.healthy

    commands_out: list[TickCommandOut] = []
    if body.ready_for_commands:
        lease_deadline = now + timedelta(minutes=5)
        stmt = (
            select(Command)
            .where(
                Command.customer_id == customer.id,
                Command.state == CommandState.queued,
            )
            .order_by(Command.created_at.asc())
            .limit(body.max_commands)
        )
        rows = (await session.execute(stmt)).scalars().all()
        for cmd in rows:
            cmd.state = CommandState.leased
            cmd.leased_by_agent_id = agent.id
            cmd.leased_at = now
            cmd.lease_deadline = lease_deadline
            commands_out.append(
                TickCommandOut(
                    id=cmd.id,
                    kind=cmd.kind,
                    payload_json=cmd.payload_json,
                    idempotency_key=cmd.idempotency_key,
                    lease_deadline=lease_deadline,
                )
            )

    await session.commit()
    return TickOut(commands=commands_out)


@router.post("/commands/{command_id}/result")
async def command_result(
    request: Request,
    command_id: UUID,
    body: CommandResultIn,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> dict[str, str]:
    fp = getattr(request.state, "agent_fingerprint", None)
    if not fp:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="result requires mTLS")
    cmd = (await session.execute(select(Command).where(Command.id == command_id))).scalar_one_or_none()
    if cmd is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such command")

    if cmd.state not in (CommandState.leased, CommandState.done, CommandState.failed):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"command in state {cmd.state}")

    cmd.state = body.state
    cmd.result_json = body.result_json
    cmd.completed_at = datetime.now(timezone.utc)
    await session.commit()
    return {"state": cmd.state.value}


@router.post("/log", status_code=status.HTTP_204_NO_CONTENT)
async def agent_log(request: Request) -> None:
    # Rate-limited, structured log ingest. Phase 2 accepts + drops on the
    # floor; a later sprint persists to a dedicated agent_logs table or
    # forwards to the team's log aggregator.
    return None


# ---------- operator-facing -------------------------------------------------

@router.get("")
async def list_agents(customer: str | None = None) -> list[dict[str, str]]:
    # Minimal stub for mgmt-ctl agents list. Phase 2 returns empty; a
    # later sprint joins agents with customers and filters by scope.
    return []


@router.post("/{slug}/rotate", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def rotate(slug: str) -> dict[str, str]:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail="agents rotate — not implemented in Phase 2 skeleton",
    )


@router.post("/{slug}/revoke", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def revoke(slug: str) -> dict[str, str]:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail="agents revoke — not implemented in Phase 2 skeleton",
    )
