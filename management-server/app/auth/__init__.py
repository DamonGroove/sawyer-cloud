"""OIDC + JWT auth package.

**Phase 2 stubs.** Real IdP wiring lands in a later sprint; this package
provides the shape future code will fit into and a minimum-viable path
for local dev + tests:

    - OIDC login/callback/refresh/logout routes (app/routers/auth.py).
    - JWT issuance + verification (app/auth/tokens.py).
    - A FastAPI middleware that resolves the session JWT (or mTLS for
      agents) into a Principal and attaches it to request.state.principal.

The middleware runs before RBAC decorators. Unauthenticated requests to
anything other than /auth/* and /health get a 401 immediately.
"""

from app.auth.middleware import AuthMiddleware
from app.auth.tokens import create_session_jwt, verify_session_jwt

__all__ = ["AuthMiddleware", "create_session_jwt", "verify_session_jwt"]
