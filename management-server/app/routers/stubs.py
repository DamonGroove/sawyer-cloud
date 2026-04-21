"""Stub routers — 501 Not Implemented with the correct response shape.

Keeps app/main.py's router wiring stable. Each real implementation
replaces one group of stubs without touching the app factory.

Covers these §5 subsections from MANAGEMENT_SERVER.md:
    §5.3 Features           — catalog + enable/disable.
    §5.6 Images, upgrades, backups.
    §5.7 Branding.
    §5.8 Logs & health.
    §5.9 Audits — list + export.
    §5.10 Break-glass.
    §5.11 Provider ops (ollama, litellm).
    §5.12 Containers (operator ops).

Each route returns 501. The response shape is the one the CLI and
mgmt-ctl README.md §5 specify so clients can distinguish "not yet"
from "invalid" reliably.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

features = APIRouter(prefix="/features", tags=["features"])
images = APIRouter(prefix="/images", tags=["images"])
audits = APIRouter(prefix="/audits", tags=["audits"])
break_glass = APIRouter(prefix="/break-glass", tags=["break-glass"])


def _not_implemented(what: str) -> HTTPException:
    return HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"{what} — not implemented in Phase 2 skeleton",
    )


# ------- features catalog --------------------------------------------------
@features.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_features() -> dict[str, str]:
    raise _not_implemented("features list")


# ------- images ------------------------------------------------------------
@images.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_images() -> dict[str, str]:
    raise _not_implemented("images list")


@images.get("/{tag}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def show_image(tag: str) -> dict[str, str]:
    raise _not_implemented("images show")


@images.post("/{tag}/promote", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def promote_image(tag: str) -> dict[str, str]:
    raise _not_implemented("images promote")


# ------- audits ------------------------------------------------------------
@audits.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_audits() -> dict[str, str]:
    raise _not_implemented("audits list")


@audits.get("/export", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def export_audits() -> dict[str, str]:
    raise _not_implemented("audits export")


# ------- break-glass -------------------------------------------------------
@break_glass.post("/request", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def break_glass_request() -> dict[str, str]:
    raise _not_implemented("break-glass request")


@break_glass.post("/{request_id}/approve", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def break_glass_approve(request_id: UUID) -> dict[str, str]:
    raise _not_implemented("break-glass approve")


@break_glass.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def break_glass_list() -> dict[str, str]:
    raise _not_implemented("break-glass list")


# ------- customer-scoped stub helpers re-exported as a router --------------
# Provider ops, containers, branding, backups, logs, health — all customer-
# scoped. Exported as a separate router so main.py can mount them under
# /customers/{slug}/... without clashing with customers.py's implemented
# routes.

per_customer_stubs = APIRouter(prefix="/customers/{slug}", tags=["per-customer-stubs"])


@per_customer_stubs.put("/branding", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def put_branding(slug: str) -> dict[str, str]:
    raise _not_implemented("branding upload")


@per_customer_stubs.post("/upgrade", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def upgrade(slug: str) -> dict[str, str]:
    raise _not_implemented("upgrade")


@per_customer_stubs.get("/backups", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_backups(slug: str) -> dict[str, str]:
    raise _not_implemented("backups list")


@per_customer_stubs.post("/backups", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def run_backup(slug: str) -> dict[str, str]:
    raise _not_implemented("backup now")


@per_customer_stubs.post("/backups/{archive_id}/restore", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def restore_backup(slug: str, archive_id: UUID) -> dict[str, str]:
    raise _not_implemented("backup restore")


@per_customer_stubs.post("/backups/pause", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def pause_backups(slug: str) -> dict[str, str]:
    raise _not_implemented("backups pause")


@per_customer_stubs.post("/backups/resume", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def resume_backups(slug: str) -> dict[str, str]:
    raise _not_implemented("backups resume")


@per_customer_stubs.put("/backups/target", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def set_backup_target(slug: str) -> dict[str, str]:
    raise _not_implemented("backups set-target")


@per_customer_stubs.get("/logs", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_logs(slug: str) -> dict[str, str]:
    raise _not_implemented("logs")


@per_customer_stubs.get("/health", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_health(slug: str) -> dict[str, str]:
    raise _not_implemented("health")


@per_customer_stubs.get("/health/history", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_health_history(slug: str) -> dict[str, str]:
    raise _not_implemented("health history")


@per_customer_stubs.get("/features", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_customer_features(slug: str) -> dict[str, str]:
    raise _not_implemented("customer features list")


@per_customer_stubs.post("/features/{key}/enable", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def enable_feature(slug: str, key: str) -> dict[str, str]:
    raise _not_implemented("feature enable")


@per_customer_stubs.post("/features/{key}/disable", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def disable_feature(slug: str, key: str) -> dict[str, str]:
    raise _not_implemented("feature disable")


@per_customer_stubs.post("/ollama/pull", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def ollama_pull(slug: str) -> dict[str, str]:
    raise _not_implemented("ollama pull")


@per_customer_stubs.get("/ollama/models", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def ollama_list(slug: str) -> dict[str, str]:
    raise _not_implemented("ollama list")


@per_customer_stubs.post("/litellm/rotate", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def litellm_rotate(slug: str) -> dict[str, str]:
    raise _not_implemented("litellm rotate")


@per_customer_stubs.post("/litellm/reload", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def litellm_reload(slug: str) -> dict[str, str]:
    raise _not_implemented("litellm reload")


@per_customer_stubs.post("/containers/{name}/restart", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def container_restart(slug: str, name: str) -> dict[str, str]:
    raise _not_implemented("container restart")


@per_customer_stubs.post("/containers/{name}/start", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def container_start(slug: str, name: str) -> dict[str, str]:
    raise _not_implemented("container start")


@per_customer_stubs.post("/containers/{name}/stop", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def container_stop(slug: str, name: str) -> dict[str, str]:
    raise _not_implemented("container stop")


@per_customer_stubs.post("/restart", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def customer_restart_all(slug: str) -> dict[str, str]:
    raise _not_implemented("customer restart all")
