"""Agent register happy path + tick (requires mTLS header shim)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_agent_register_happy_path(client, admin_token, seeded_flavor) -> None:
    create = await client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "slug": "agent-test",
            "display_name": "Agent Test",
            "domain": "at.invalid",
            "flavor": seeded_flavor,
        },
    )
    assert create.status_code == 201, create.text
    token = create.json()["registration_token"]

    reg = await client.post(
        "/api/v1/agents/register",
        json={
            "registration_token": token,
            "customer_slug": "agent-test",
            "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\nFAKE\n-----END CERTIFICATE REQUEST-----\n",
            "agent_version": "0.1.0",
        },
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()
    assert body["agent_id"]
    assert "BEGIN CERTIFICATE" in body["signed_cert_pem"]


@pytest.mark.asyncio
async def test_agent_register_wrong_slug(client, admin_token, seeded_flavor) -> None:
    create = await client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "slug": "right-slug",
            "display_name": "RS",
            "domain": "rs.invalid",
            "flavor": seeded_flavor,
        },
    )
    token = create.json()["registration_token"]

    reg = await client.post(
        "/api/v1/agents/register",
        json={
            "registration_token": token,
            "customer_slug": "wrong-slug",
            "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\nFAKE\n-----END CERTIFICATE REQUEST-----\n",
            "agent_version": "0.1.0",
        },
    )
    assert reg.status_code == 403


@pytest.mark.asyncio
async def test_agent_register_is_idempotent(client, admin_token, seeded_flavor) -> None:
    create = await client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "slug": "idemp",
            "display_name": "Idemp",
            "domain": "idemp.invalid",
            "flavor": seeded_flavor,
        },
    )
    token = create.json()["registration_token"]

    payload = {
        "registration_token": token,
        "customer_slug": "idemp",
        "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\nSAME\n-----END CERTIFICATE REQUEST-----\n",
        "agent_version": "0.1.0",
    }
    r1 = await client.post("/api/v1/agents/register", json=payload)
    r2 = await client.post("/api/v1/agents/register", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 201
    # Same agent id on both registrations (cert fingerprint matches).
    assert r1.json()["agent_id"] == r2.json()["agent_id"]
