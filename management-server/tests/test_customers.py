"""Customer create/list/show + RBAC deny path."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_customer_as_admin(client, admin_token, seeded_flavor) -> None:
    r = await client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "slug": "acme-corp",
            "display_name": "ACME Corporation",
            "domain": "cloud.acme.example.com",
            "flavor": seeded_flavor,
            "site_mode": "docker",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["customer"]["slug"] == "acme-corp"
    assert body["customer"]["state"] == "pending"
    assert body["registration_token"]
    assert "." in body["registration_token"]  # token.<uuid> shape


@pytest.mark.asyncio
async def test_create_customer_as_operator_forbidden(
    client, operator_token, seeded_flavor
) -> None:
    r = await client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "slug": "rejected-corp",
            "display_name": "Should Fail",
            "domain": "x.invalid",
            "flavor": seeded_flavor,
        },
    )
    assert r.status_code == 403, r.text
    assert "admin" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_customers_admin_sees_all(client, admin_token, seeded_flavor) -> None:
    for slug in ("a-corp", "b-corp", "c-corp"):
        await client.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "slug": slug,
                "display_name": slug.upper(),
                "domain": f"{slug}.invalid",
                "flavor": seeded_flavor,
            },
        )
    r = await client.get(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    slugs = {c["slug"] for c in r.json()}
    assert {"a-corp", "b-corp", "c-corp"} <= slugs


@pytest.mark.asyncio
async def test_show_customer(client, admin_token, seeded_flavor) -> None:
    create = await client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "slug": "show-target",
            "display_name": "Show Me",
            "domain": "show.invalid",
            "flavor": seeded_flavor,
        },
    )
    assert create.status_code == 201
    r = await client.get(
        "/api/v1/customers/show-target",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.json()["slug"] == "show-target"


@pytest.mark.asyncio
async def test_customer_404(client, admin_token) -> None:
    r = await client.get(
        "/api/v1/customers/ghost",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 404
