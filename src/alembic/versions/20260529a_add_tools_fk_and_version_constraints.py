"""add_tools_fk_and_version_constraints

Revision ID: 20260529a
Revises: 76a7b8b016d2
Create Date: 2026-05-29 00:00:00.000000

Add referential integrity and version uniqueness for tools/tool_versions.
"""

from typing import Union

from alembic import op

revision: str = "20260529a"
down_revision: str | None = "76a7b8b016d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_tools_tenant_id_tenants",
        "tools",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_tools_created_by_users",
        "tools",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tool_versions_tenant_id_tenants",
        "tool_versions",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_tool_versions_tool_id_version",
        "tool_versions",
        ["tool_id", "version"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_tool_versions_tool_id_version", "tool_versions", type_="unique")
    op.drop_constraint("fk_tool_versions_tenant_id_tenants", "tool_versions", type_="foreignkey")
    op.drop_constraint("fk_tools_created_by_users", "tools", type_="foreignkey")
    op.drop_constraint("fk_tools_tenant_id_tenants", "tools", type_="foreignkey")
