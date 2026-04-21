"""Session JWT encode + verify.

HS256 with the session secret. Claims:

    sub           OIDC subject (user's stable identifier at the IdP)
    email         user's email (denormalized; for audit log + UI)
    roles         list[str] of role slugs at issue time
    customer_ids  list[str] of UUIDs; operator scope at issue time
    exp / iat     standard JWT timing

In a later sprint, rotating keys via a JWKS lookup at the IdP replaces
the shared-secret approach. Shape stays the same.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.config import get_settings


def create_session_jwt(
    subject: str,
    email: str,
    roles: list[str],
    customer_ids: list[str],
    *,
    lifetime_seconds: int | None = None,
) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=lifetime_seconds or s.jwt_lifetime_seconds)
    claims: dict[str, Any] = {
        "sub": subject,
        "email": email,
        "roles": roles,
        "customer_ids": customer_ids,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(claims, s.session_secret, algorithm=s.jwt_algorithm)


def verify_session_jwt(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        return jwt.decode(token, s.session_secret, algorithms=[s.jwt_algorithm])
    except JWTError as exc:
        raise ValueError(f"invalid token: {exc}") from exc
