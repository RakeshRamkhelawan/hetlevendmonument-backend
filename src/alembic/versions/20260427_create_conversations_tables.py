"""create conversations and conversation_messages tables

Revision ID: 20260427_create_conversations
Revises: a45f3cd4bfb3
Create Date: 2026-04-27 09:15:00.000000

"""
from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260427_create_conversations"
down_revision: str | Sequence[str] | None = "a45f3cd4bfb3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create conversations and conversation_messages tables for CVA chat persistence."""
    # conversations table
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("agent_id", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conversations_id"), "conversations", ["id"], unique=False)
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"], unique=False)
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"], unique=False)
    op.create_index(
        "idx_conversations_tenant_user",
        "conversations",
        ["tenant_id", "user_id"],
        unique=False,
    )
    op.create_index(
        "idx_conversations_updated_at", "conversations", ["updated_at"], unique=False
    )

    # conversation_messages table
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversation_messages_id"), "conversation_messages", ["id"], unique=False
    )
    op.create_index(
        "ix_conversation_messages_conversation_id",
        "conversation_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "idx_messages_conversation_timestamp",
        "conversation_messages",
        ["conversation_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_messages_tenant_id", "conversation_messages", ["tenant_id"], unique=False
    )


def downgrade() -> None:
    """Drop conversations and conversation_messages tables."""
    op.drop_index("idx_messages_tenant_id", table_name="conversation_messages")
    op.drop_index("idx_messages_conversation_timestamp", table_name="conversation_messages")
    op.drop_index(
        "ix_conversation_messages_conversation_id", table_name="conversation_messages"
    )
    op.drop_index(op.f("ix_conversation_messages_id"), table_name="conversation_messages")
    op.drop_table("conversation_messages")

    op.drop_index("idx_conversations_updated_at", table_name="conversations")
    op.drop_index("idx_conversations_tenant_user", table_name="conversations")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_index("ix_conversations_tenant_id", table_name="conversations")
    op.drop_index(op.f("ix_conversations_id"), table_name="conversations")
    op.drop_table("conversations")
