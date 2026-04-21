"""/health smoke test — the absolute minimum the API must answer to
confirm the wiring is sane."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_ok(client) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
