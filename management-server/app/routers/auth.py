"""/auth — OIDC session issuance endpoints + /users/me.

Phase 2 stubs. Real OIDC flow lands in the next sprint. The shapes match
MANAGEMENT_SERVER.md §5.1 so mgmt-ctl can develop against them.

/users/me is fully wired so mgmt-ctl whoami works once a session token
is in hand (tests set one via the test client's auth headers).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.auth.tokens import create_session_jwt
from app.rbac import Principal

router = APIRouter(tags=["auth"])


class MeOut(BaseModel):
    user_id: UUID | None
    email: str
    roles: list[str]
    assigned_customer_ids: list[UUID]
    is_service: bool


class DevLoginIn(BaseModel):
    """Dev-mode login to avoid needing a real IdP for tests.

    Disabled in production (settings.environment != 'dev').
    """

    email: str
    roles: list[str]
    customer_ids: list[UUID] = []


class DevLoginOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"


@router.get("/users/me", response_model=MeOut)
async def get_me(request: Request) -> MeOut:
    principal: Principal | None = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return MeOut(
        user_id=principal.user_id,
        email=principal.email,
        roles=sorted(r.value for r in principal.roles),
        assigned_customer_ids=sorted(principal.assigned_customer_ids),
        is_service=principal.is_service,
    )


@router.post("/auth/login", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def login() -> dict[str, str]:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail="OIDC login — not implemented in Phase 2 skeleton",
    )


@router.get("/auth/callback", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def callback() -> dict[str, str]:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail="OIDC callback — not implemented in Phase 2 skeleton",
    )


@router.post("/auth/refresh", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def refresh() -> dict[str, str]:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail="token refresh — not implemented in Phase 2 skeleton",
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> None:
    # The client drops its token; nothing to do on the server side yet
    # (no revocation store in Phase 2).
    return None


@router.post("/auth/dev-login", response_model=DevLoginOut)
async def dev_login(request: Request, body: DevLoginIn) -> DevLoginOut:
    """Dev-only: mint a session JWT with the requested roles + scope.

    Disabled outside the `dev` environment.
    """

    from app.config import get_settings

    if get_settings().environment != "dev":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    token = create_session_jwt(
        subject=body.email,
        email=body.email,
        roles=body.roles,
        customer_ids=[str(c) for c in body.customer_ids],
    )
    return DevLoginOut(access_token=token)
