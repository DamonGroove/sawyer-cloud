"""Security middleware stubs.

CLAUDE.md §5 reserves management-server/app/security/** as a locked path
in operator mode. These stubs establish insertion points so that later
hardening (CSP headers, CSRF tokens, rate limits) lands without needing
to change app/main.py's middleware wiring — the middlewares themselves
change, the assembly does not.

Every middleware here is safe-by-default in its stub form: the CSP
middleware emits a permissive header during bootstrap/dev, the CSRF
middleware no-ops for now, and the rate limiter counts but does not
block. Turning each on hard goes through engineering PR review.
"""

from app.security.csp import CSPMiddleware
from app.security.csrf import CSRFMiddleware
from app.security.ratelimit import RateLimitMiddleware

__all__ = ["CSPMiddleware", "CSRFMiddleware", "RateLimitMiddleware"]
