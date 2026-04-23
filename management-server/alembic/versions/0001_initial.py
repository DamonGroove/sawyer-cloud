"""initial schema — all 9 tables from MANAGEMENT_SERVER.md §3

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-21 00:00:00

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enum types
    site_mode = postgresql.ENUM("docker", "vm", name="site_mode", create_type=False)
    customer_state = postgresql.ENUM(
        "pending", "healthy", "degraded", "offline", "decommissioned",
        name="customer_state", create_type=False,
    )
    command_state = postgresql.ENUM(
        "queued", "leased", "done", "failed", "canceled",
        name="command_state", create_type=False,
    )
    actor_kind = postgresql.ENUM(
        "user", "service", "agent", "system",
        name="actor_kind", create_type=False,
    )
    audit_result = postgresql.ENUM(
        "success", "failure", name="audit_result", create_type=False,
    )
    feature_provider = postgresql.ENUM(
        "upstream-optional", "community-container", "nc-app", "custom",
        name="feature_provider", create_type=False,
    )
    promotion_stage = postgresql.ENUM(
        "none", "staging-green", "production",
        name="promotion_stage", create_type=False,
    )
    role = postgresql.ENUM(
        "operator", "admin", "engineering", name="role", create_type=False,
    )

    site_mode.create(op.get_bind(), checkfirst=True)
    customer_state.create(op.get_bind(), checkfirst=True)
    command_state.create(op.get_bind(), checkfirst=True)
    actor_kind.create(op.get_bind(), checkfirst=True)
    audit_result.create(op.get_bind(), checkfirst=True)
    feature_provider.create(op.get_bind(), checkfirst=True)
    promotion_stage.create(op.get_bind(), checkfirst=True)
    role.create(op.get_bind(), checkfirst=True)

    # flavors
    op.create_table(
        "flavors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("nextcloud_version_pin", sa.String(32), nullable=True),
        sa.Column("default_apps", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("default_community_containers", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_flavors"),
        sa.UniqueConstraint("slug", name="uq_flavors_slug"),
    )
    op.create_index("ix_flavors_slug", "flavors", ["slug"])

    # customers
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("domain", sa.String(256), nullable=False),
        sa.Column("flavor_slug", sa.String(64), nullable=False),
        sa.Column("site_mode", site_mode, nullable=False),
        sa.Column("deployed_image_tag", sa.String(128), nullable=True),
        sa.Column("state", customer_state, nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("managed_by_team", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_customers"),
        sa.UniqueConstraint("slug", name="uq_customers_slug"),
        sa.ForeignKeyConstraint(
            ["flavor_slug"], ["flavors.slug"],
            name="fk_customers_flavor_slug_flavors", ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_customers_slug", "customers", ["slug"])
    op.create_index("ix_customers_state", "customers", ["state"])
    op.create_index("ix_customers_managed_by_team", "customers", ["managed_by_team"])

    # features
    op.create_table(
        "features",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("provides", feature_provider, nullable=False),
        sa.Column("default_on_flavors", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("conflicts_with", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("min_base_image_tag", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_features"),
        sa.UniqueConstraint("key", name="uq_features_key"),
    )
    op.create_index("ix_features_key", "features", ["key"])

    # feature_bindings
    op.create_table(
        "feature_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_key", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("config_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("enabled_by", sa.String(256), nullable=False, server_default="system"),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_feature_bindings"),
        sa.UniqueConstraint("customer_id", "feature_key", name="customer_feature"),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"],
            name="fk_feature_bindings_customer_id_customers", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["feature_key"], ["features.key"],
            name="fk_feature_bindings_feature_key_features", ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_feature_bindings_customer_id", "feature_bindings", ["customer_id"])
    op.create_index("ix_feature_bindings_feature_key", "feature_bindings", ["feature_key"])

    # agents
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_version", sa.String(32), nullable=True),
        sa.Column("mtls_cert_fingerprint", sa.String(128), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reported_state_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_agents"),
        sa.UniqueConstraint("customer_id", "mtls_cert_fingerprint", name="cust_cert"),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"],
            name="fk_agents_customer_id_customers", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_agents_customer_id", "agents", ["customer_id"])
    op.create_index("ix_agents_mtls_cert_fingerprint", "agents", ["mtls_cert_fingerprint"])

    # commands
    op.create_table(
        "commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("state", command_state, nullable=False),
        sa.Column("enqueued_by", sa.String(256), nullable=False, server_default="system"),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("leased_by_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", postgresql.JSONB, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_commands"),
        sa.UniqueConstraint("customer_id", "idempotency_key", name="idempotency"),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"],
            name="fk_commands_customer_id_customers", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["leased_by_agent_id"], ["agents.id"],
            name="fk_commands_leased_by_agent_id_agents", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_commands_customer_id", "commands", ["customer_id"])
    op.create_index("ix_commands_kind", "commands", ["kind"])
    op.create_index("ix_commands_state", "commands", ["state"])

    # audits
    op.create_table(
        "audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_kind", actor_kind, nullable=False),
        sa.Column("actor_id", sa.String(256), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("parameters_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("result", audit_result, nullable=False),
        sa.Column("error_detail", sa.Text, nullable=True),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_audits"),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"],
            name="fk_audits_customer_id_customers", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_audits_actor_kind", "audits", ["actor_kind"])
    op.create_index("ix_audits_actor_id", "audits", ["actor_id"])
    op.create_index("ix_audits_customer_id", "audits", ["customer_id"])
    op.create_index("ix_audits_action", "audits", ["action"])
    op.create_index("ix_audits_request_id", "audits", ["request_id"])

    # base_images
    op.create_table(
        "base_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag", sa.String(128), nullable=False),
        sa.Column("git_sha", sa.String(64), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_to", promotion_stage, nullable=False, server_default="none"),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_notes", sa.Text, nullable=True),
        sa.Column("rollback_safe_from_tags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_base_images"),
        sa.UniqueConstraint("tag", name="uq_base_images_tag"),
    )
    op.create_index("ix_base_images_tag", "base_images", ["tag"])

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=True),
        sa.Column("api_key_bcrypt", sa.String(128), nullable=True),
        sa.Column("oidc_subject", sa.String(256), nullable=True),
        sa.Column("disabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_oidc_subject", "users", ["oidc_subject"])

    # role_assignments
    op.create_table(
        "role_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", role, nullable=False),
        sa.Column("scope_customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_role_assignments"),
        sa.UniqueConstraint("user_id", "role", "scope_customer_id", name="user_role_scope"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_role_assignments_user_id_users", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scope_customer_id"], ["customers.id"],
            name="fk_role_assignments_scope_customer_id_customers", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_role_assignments_user_id", "role_assignments", ["user_id"])
    op.create_index("ix_role_assignments_scope_customer_id", "role_assignments", ["scope_customer_id"])


def downgrade() -> None:
    op.drop_table("role_assignments")
    op.drop_table("users")
    op.drop_table("base_images")
    op.drop_table("audits")
    op.drop_table("commands")
    op.drop_table("agents")
    op.drop_table("feature_bindings")
    op.drop_table("features")
    op.drop_table("customers")
    op.drop_table("flavors")
    for enum_name in (
        "role", "promotion_stage", "feature_provider", "audit_result",
        "actor_kind", "command_state", "customer_state", "site_mode",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
