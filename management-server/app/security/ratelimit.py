"""Rate-limit stub.

Counts-but-does-not-block in Phase 2. Per-identity token-bucket with a
shared Redis backend will replace this in a later sprint.

The counting keeps a per-key running tally in process memory so we can
already surface a `X-RateLimit-Observed-Minute` header for monitoring
pages — useful when tuning the real limits without yet enforcing them.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# Rough sliding-minute counter. Not thread-safe for process-level
# coordination, but FastAPI/uvicorn's default single-process dev mode is
# fine; prod will swap in Redis.
_buckets: dict[tuple[str, int], int] = defaultdict(int)


def _identity(request: Request) -> str:
    principal = getattr(request.state, "principal", None)
    if principal is not None and getattr(principal, "email", None):
        return f"user:{principal.email}"
    client = request.client
    return f"ip:{client.host}" if client else "anon:unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        minute = int(time.time() // 60)
        key = (_identity(request), minute)
        _buckets[key] += 1

        # GC old buckets once per ~60 requests to avoid unbounded growth.
        if len(_buckets) > 1024:
            cutoff = minute - 5
            for k in list(_buckets.keys()):
                if k[1] < cutoff:
                    _buckets.pop(k, None)

        response = await call_next(request)
        response.headers["X-RateLimit-Observed-Minute"] = str(_buckets[key])
        return response
