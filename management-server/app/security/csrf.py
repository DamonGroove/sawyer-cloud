"""CSRF protection stub.

The API today is Authorization-Bearer-only, which is not cookie-based
and therefore not CSRF-vulnerable in the classic sense. The /auth/login
and /auth/callback routes ARE cookie-based (OIDC state + session); those
need a double-submit CSRF token in a future sprint.

This module ships as a no-op so the wiring in app/main.py does not need
to change when the real implementation lands.
"""

from __future__ import annotations

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # No-op for now. A future implementation will:
        #   1. On GET of an HTML page under /auth/*, set a HttpOnly cookie
        #      with a random token AND render the token into the page as
        #      a meta tag.
        #   2. On POST, require the token header to match the cookie.
        return await call_next(request)
