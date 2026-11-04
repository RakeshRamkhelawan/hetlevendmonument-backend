"""add_foundation_content_and_tags

Revision ID: 20260524b
Revises: 20260524a
Create Date: 2026-05-24 08:16:00

"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260524b"
down_revision: str | Sequence[str] | None = "20260524a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ["foundation_content"]


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == "postgresql"


def _enable_rls(table: str) -> None:
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"FOR ALL USING ("
            f"tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
            f")"
        )
    )


def _disable_rls(table: str) -> None:
    op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
    op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))


def upgrade() -> None:
    op.create_table(
        "foundation_content",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("uploader_id", sa.Integer(), nullable=True),
        sa.Column(
            "type",
            postgresql.ENUM(
                "STORY",
                "ARTWORK",
                "AUDIO",
                "DOCUMENT",
                "POETRY",
                "LINK",
                name="content_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("title_nl", sa.String(length=255), nullable=False),
        sa.Column("title_en", sa.String(length=255), nullable=True),
        sa.Column("description_nl", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("body_nl", sa.Text(), nullable=True),
        sa.Column("body_en", sa.Text(), nullable=True),
        sa.Column("creator_name", sa.String(length=255), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column(
            "privacy",
            postgresql.ENUM("PUBLIC", "COMMUNITY", name="privacy_enum"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING", "APPROVED", "REJECTED", "REMOVED", name="content_status_enum"
            ),
            nullable=False,
        ),
        sa.Column("rights_confirmed", sa.Boolean(), nullable=False),
        sa.Column("file_url", sa.String(length=1024), nullable=True),
        sa.Column("file_mime", sa.String(length=100), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("external_url", sa.String(length=1024), nullable=True),
        sa.Column("ai_tagging_failed", sa.Boolean(), nullable=False),
        sa.Column("moderation_score", sa.Float(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("takedown_reason", sa.Text(), nullable=True),
        sa.Column("takedown_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["uploader_id"], ["portal_users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_fc_tenant_created", "foundation_content", ["tenant_id", "created_at"], unique=False
    )
    op.create_index(
        "idx_fc_tenant_status", "foundation_content", ["tenant_id", "status"], unique=False
    )
    op.create_index(
        "idx_fc_tenant_type_status",
        "foundation_content",
        ["tenant_id", "type", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_foundation_content_status"),
        "foundation_content",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_foundation_content_tenant_id"),
        "foundation_content",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_foundation_content_uploader_id"),
        "foundation_content",
        ["uploader_id"],
        unique=False,
    )

    op.create_table(
        "content_tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column(
            "tag_type",
            postgresql.ENUM(
                "THEME",
                "LOCATION",
                "PERIOD",
                "SENTIMENT",
                "LANGUAGE",
                name="tag_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("value", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("is_manual", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["content_id"], ["foundation_content.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_tag_content_type", "content_tags", ["content_id", "tag_type"], unique=False
    )
    op.create_index(
        op.f("ix_content_tags_content_id"),
        "content_tags",
        ["content_id"],
        unique=False,
    )

    if _is_postgresql():
        for tbl in _RLS_TABLES:
            _enable_rls(tbl)


def downgrade() -> None:
    op.drop_index(op.f("ix_content_tags_content_id"), table_name="content_tags")
    op.drop_index("idx_tag_content_type", table_name="content_tags")
    op.drop_table("content_tags")

    if _is_postgresql():
        for tbl in reversed(_RLS_TABLES):
            _disable_rls(tbl)

    op.drop_index(
        op.f("ix_foundation_content_uploader_id"), table_name="foundation_content"
    )
    op.drop_index(
        op.f("ix_foundation_content_tenant_id"), table_name="foundation_content"
    )
    op.drop_index(
        op.f("ix_foundation_content_status"), table_name="foundation_content"
    )
    op.drop_index("idx_fc_tenant_type_status", table_name="foundation_content")
    op.drop_index("idx_fc_tenant_status", table_name="foundation_content")
    op.drop_index("idx_fc_tenant_created", table_name="foundation_content")
    op.drop_table("foundation_content")
    op.execute("DROP TYPE IF EXISTS content_status_enum")
    op.execute("DROP TYPE IF EXISTS privacy_enum")
    op.execute("DROP TYPE IF EXISTS content_type_enum")
    op.execute("DROP TYPE IF EXISTS tag_type_enum")
