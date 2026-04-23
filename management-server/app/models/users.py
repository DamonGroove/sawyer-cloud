"""users + roles — RBAC substrate."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Role(StrEnum):
    operator = "operator"
    admin = "admin"
    engineering = "engineering"


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Service-account API keys are stored as bcrypt hashes here; human
    # users authenticate via OIDC and have no local password at all.
    api_key_bcrypt: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Null for service accounts; populated for OIDC-federated human users.
    oidc_subject: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    disabled: Mapped[bool] = mapped_column(default=False, nullable=False)


class RoleAssignment(Base):
    __tablename__ = "role_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "role", "scope_customer_id", name="user_role_scope"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="role"),
        nullable=False,
    )
    # Null = fleet-wide; set = scoped to a single customer (typical for
    # Operator role). Admin / engineering are usually fleet-wide.
    scope_customer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
