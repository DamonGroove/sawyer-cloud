"""Auth middleware — resolves a request's credentials to a Principal.

Two credential paths:

    1. Session JWT in the `Authorization: Bearer ...` header (human users
       after OIDC login). Decoded via verify_session_jwt; the claims
       produce the Principal.
    2. mTLS client cert for agents, surfaced by the TLS terminator as
       `X-Client-Cert-Fingerprint` and `X-Client-Cert-Customer-Slug`
       headers. The fingerprint must match an Agent row; the customer
       slug is a belt-and-suspenders secondary check.

Unauthenticated paths (allow-listed so the IdP and health checks work):

    /health, /auth/*  — always allowed.
    /agents/register  — allowed (token-based, checked inside the route).

Everything else: 401 if no valid credentials.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.auth.tokens import verify_session_jwt
from app.models.users import Role
from app.rbac import Principal

ALLOW_ANON_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/openapi.json",
        "/docs",
        "/redoc",
    }
)
ALLOW_ANON_PREFIXES: tuple[str, ...] = (
    "/api/v1/auth/",
    "/api/v1/agents/register",
)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if path in ALLOW_ANON_PATHS or path.startswith(ALLOW_ANON_PREFIXES):
            return await call_next(request)

        principal: Principal | None = None

        # --- path A: session JWT ---
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            try:
                claims = verify_session_jwt(token)
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "invalid session token"},
                )
            principal = _principal_from_claims(claims)

        # --- path B: agent mTLS ---
        elif request.headers.get("x-client-cert-fingerprint"):
            # Phase 2 stub: we accept the fingerprint header and pin a
            # service-account-like Principal. Resolving the fingerprint
            # against the agents table happens in app/routers/agents.py
            # when agents hit the tick/result endpoints.
            fp = request.headers["x-client-cert-fingerprint"]
            slug = request.headers.get("x-client-cert-customer-slug", "")
            principal = Principal(
                user_id=None,
                email=f"agent:{slug}",
                roles={Role.operator},  # agents are strictly scoped via routers
                assigned_customer_ids=set(),
                is_service=True,
            )
            request.state.agent_fingerprint = fp
            request.state.agent_customer_slug = slug

        if principal is None:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "missing or unsupported credentials"},
            )

        request.state.principal = principal
        return await call_next(request)


def _principal_from_claims(claims: dict) -> Principal:
    roles = {Role(r) for r in claims.get("roles", [])}
    customer_ids = {UUID(s) for s in claims.get("customer_ids", [])}
    return Principal(
        user_id=UUID(claims["sub"]) if _is_uuid(claims.get("sub")) else None,
        email=claims.get("email", "(unknown)"),
        roles=roles,
        assigned_customer_ids=customer_ids,
    )


def _is_uuid(v: object) -> bool:
    if not isinstance(v, str):
        return False
    try:
        UUID(v)
    except (ValueError, TypeError):
        return False
    return True
