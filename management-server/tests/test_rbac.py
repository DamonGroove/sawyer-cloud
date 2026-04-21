"""RBAC deny paths."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client) -> None:
    r = await client.get("/api/v1/customers")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_role_ordering() -> None:
    from app.models.users import Role
    from app.rbac import role_satisfies

    assert role_satisfies({Role.engineering}, Role.admin)
    assert role_satisfies({Role.admin}, Role.operator)
    assert not role_satisfies({Role.operator}, Role.admin)
    assert not role_satisfies({Role.operator}, Role.engineering)


@pytest.mark.asyncio
async def test_operator_cannot_create_customer(client, operator_token, seeded_flavor) -> None:
    r = await client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "slug": "op-fail",
            "display_name": "x",
            "domain": "x.invalid",
            "flavor": seeded_flavor,
        },
    )
    assert r.status_code == 403
