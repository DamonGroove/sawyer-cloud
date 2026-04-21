"""RBAC primitives and decorators.

Three roles, clearly nested (MANAGEMENT_SERVER.md §6):

    operator < admin < engineering

Scope:
    operator    role assignments are typically per-customer.
    admin, engineering are typically fleet-wide.

Enforcement runs twice per MANAGEMENT_SERVER.md §6.4:
    1. HTTP middleware — fast-fail on obvious denies.
    2. Service layer — full-context check (customer assignments, feature
       state, command-kind rules). Both log to audits on deny.

This module implements (2) as decorators + helpers. (1) lives in
app/auth/middleware.py.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from app.models.users import Role


# Nesting order. Higher index = more privileged.
_ROLE_ORDER: tuple[Role, ...] = (Role.operator, Role.admin, Role.engineering)


def role_rank(role: Role) -> int:
    try:
        return _ROLE_ORDER.index(role)
    except ValueError as exc:  # pragma: no cover — defensive
        raise ValueError(f"unknown role: {role}") from exc


def role_satisfies(actual: Iterable[Role], required: Role) -> bool:
    """True if any of `actual` has a rank >= required's rank."""

    needed = role_rank(required)
    return any(role_rank(r) >= needed for r in actual)


class Principal:
    """Represents the authenticated caller. Attached to Request.state.principal."""

    def __init__(
        self,
        user_id: UUID | None,
        email: str,
        roles: set[Role],
        assigned_customer_ids: set[UUID],
        is_service: bool = False,
    ) -> None:
        self.user_id = user_id
        self.email = email
        self.roles = roles
        self.assigned_customer_ids = assigned_customer_ids
        self.is_service = is_service

    def can_act_on_customer(self, customer_id: UUID) -> bool:
        # Admin and engineering can act on any customer.
        if role_satisfies(self.roles, Role.admin):
            return True
        # Operators only on assigned customers.
        return customer_id in self.assigned_customer_ids

    def __repr__(self) -> str:
        return f"<Principal email={self.email} roles={sorted(r.value for r in self.roles)}>"


# --- deny helpers ----------------------------------------------------------

_COMMAND_KINDS_ADMIN_ONLY: frozenset[str] = frozenset(
    {
        "aio.image.upgrade",
        "custom.community_containers.set",
    }
)

# Non-default-flavor apps require admin for install. Operators can install
# apps that are on their flavor's default list only.
_APP_INSTALL_REQUIRES_ADMIN = "occ.app.install"


def _require_principal(request: Request) -> Principal:
    principal: Principal | None = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return principal


def require_role(min_role: Role) -> Any:
    """FastAPI dependency: 403s the request if the principal's roles do
    not include one with rank >= min_role.

    Usage:

        @router.post("", dependencies=[require_role(Role.admin)])
        async def create_customer(...):
            ...

    Or in a handler signature:

        async def handler(_: None = require_role(Role.admin)) -> ...:
    """

    async def _dep(request: Request) -> None:
        principal = _require_principal(request)
        if not role_satisfies(principal.roles, min_role):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Required role: {min_role.value}. "
                    f"Your roles: {sorted(r.value for r in principal.roles)}."
                ),
            )

    return Depends(_dep)


def require_command_kind_allowed(principal: Principal, kind: str) -> None:
    """Service-layer check: raise 403 if the principal cannot enqueue `kind`."""

    if kind in _COMMAND_KINDS_ADMIN_ONLY:
        if not role_satisfies(principal.roles, Role.admin):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Command kind {kind} requires admin role. "
                    f"Your roles: {sorted(r.value for r in principal.roles)}."
                ),
            )
    # `occ.app.install` of non-default-flavor apps is admin-only. That
    # second-order check needs flavor context; the routers call
    # require_app_install_allowed(principal, customer, app_id) when they
    # actually service an install.


def require_customer_scope(principal: Principal, customer_id: UUID) -> None:
    """Service-layer check: raise 403 if the principal is not scoped to the customer."""

    if not principal.can_act_on_customer(customer_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this customer.",
        )


