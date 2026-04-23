"""/customers — onboarding, list, show, decommission.

MANAGEMENT_SERVER.md §5.2 routes; this Phase 2 skeleton implements list,
show, create fully and stubs the rest with 501 + the correct response
shape so the CLI can exercise error paths now and swap to real impls
later without touching its error-handling.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.customers import Customer, CustomerState, SiteMode
from app.models.users import Role
from app.rbac import Principal, require_customer_scope, require_role

router = APIRouter(prefix="/customers", tags=["customers"])


# ---------- schemas --------------------------------------------------------

class CustomerOut(BaseModel):
    id: UUID
    slug: str
    display_name: str
    domain: str
    flavor_slug: str
    site_mode: SiteMode
    state: CustomerState
    deployed_image_tag: str | None
    last_seen_at: datetime | None

    @classmethod
    def from_row(cls, c: Customer) -> "CustomerOut":
        return cls(
            id=c.id,
            slug=c.slug,
            display_name=c.display_name,
            domain=c.domain,
            flavor_slug=c.flavor_slug,
            site_mode=c.site_mode,
            state=c.state,
            deployed_image_tag=c.deployed_image_tag,
            last_seen_at=c.last_seen_at,
        )


class CustomerCreateIn(BaseModel):
    slug: str = Field(..., pattern=r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
    display_name: str = Field(..., min_length=1, max_length=256)
    domain: str = Field(..., min_length=3, max_length=256)
    flavor: str = Field(..., min_length=1, max_length=64)
    site_mode: SiteMode = SiteMode.docker


class CustomerCreateOut(BaseModel):
    customer: CustomerOut
    registration_token: str


# ---------- helpers --------------------------------------------------------

async def _get_customer_by_slug(session: AsyncSession, slug: str) -> Customer:
    c = (await session.execute(select(Customer).where(Customer.slug == slug))).scalar_one_or_none()
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no customer with slug {slug}")
    return c


def _principal(request: Request) -> Principal:
    p = getattr(request.state, "principal", None)
    if p is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return p


# ---------- routes ---------------------------------------------------------

@router.get("", response_model=list[CustomerOut])
async def list_customers(
    request: Request,
    flavor: str | None = None,
    state: CustomerState | None = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> list[CustomerOut]:
    principal = _principal(request)
    stmt = select(Customer)
    if flavor:
        stmt = stmt.where(Customer.flavor_slug == flavor)
    if state:
        stmt = stmt.where(Customer.state == state)
    rows = (await session.execute(stmt)).scalars().all()
    # Operators only see their assigned customers.
    if Role.admin not in principal.roles and Role.engineering not in principal.roles:
        rows = [r for r in rows if r.id in principal.assigned_customer_ids]
    return [CustomerOut.from_row(r) for r in rows]


@router.get("/{slug}", response_model=CustomerOut)
async def get_customer(
    request: Request,
    slug: str,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> CustomerOut:
    c = await _get_customer_by_slug(session, slug)
    principal = _principal(request)
    require_customer_scope(principal, c.id)
    return CustomerOut.from_row(c)


@router.post(
    "",
    response_model=CustomerCreateOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_role(Role.admin)],
)
async def create_customer(
    request: Request,
    body: CustomerCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> CustomerCreateOut:
    existing = (
        await session.execute(select(Customer).where(Customer.slug == body.slug))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"customer {body.slug} already exists")

    c = Customer(
        slug=body.slug,
        display_name=body.display_name,
        domain=body.domain,
        flavor_slug=body.flavor,
        site_mode=body.site_mode,
        state=CustomerState.pending,
    )
    session.add(c)
    await session.commit()
    await session.refresh(c)

    token = _issue_registration_token(c.id)
    return CustomerCreateOut(customer=CustomerOut.from_row(c), registration_token=token)


@router.post("/{slug}/enroll", dependencies=[require_role(Role.admin)])
async def enroll_new_token(
    request: Request,
    slug: str,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> dict[str, str]:
    c = await _get_customer_by_slug(session, slug)
    token = _issue_registration_token(c.id)
    return {"registration_token": token}


@router.post("/{slug}/decommission", dependencies=[require_role(Role.admin)])
async def decommission(
    request: Request,
    slug: str,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> dict[str, str]:
    c = await _get_customer_by_slug(session, slug)
    c.state = CustomerState.decommissioned
    await session.commit()
    return {"state": c.state.value}


# --- 501 stubs (right shape, not yet wired) --------------------------------

@router.get("/compare", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def compare_customers(a: str, b: str) -> dict[str, str]:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail="customers compare — not implemented in Phase 2 skeleton",
    )


@router.post("/{slug}/apply", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def apply(request: Request, slug: str, section: str | None = None) -> dict[str, str]:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail="customers apply — not implemented in Phase 2 skeleton",
    )


@router.post("/{slug}/rollback", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def rollback(request: Request, slug: str) -> dict[str, str]:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail="customers rollback — not implemented in Phase 2 skeleton",
    )


@router.post("/{slug}/occ", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def occ_passthrough(request: Request, slug: str) -> dict[str, str]:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail="occ passthrough — not implemented in Phase 2 skeleton",
    )


# ---------- internals ------------------------------------------------------

def _issue_registration_token(customer_id: UUID) -> str:
    # One-time token. In Phase 3 this goes into a `registration_tokens`
    # table with a TTL and is consumed on first /agents/register call.
    # For now, return a cryptographically random opaque string.
    return secrets.token_urlsafe(32) + f".{customer_id}"
