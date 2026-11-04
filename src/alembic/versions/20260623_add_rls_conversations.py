"""Add RLS to conversations and conversation_messages tables (RC-005d).

Revision ID: 20260623_add_rls_conversations
Revises: e4f5c648cf94
Create Date: 2026-06-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260623_add_rls_conversations"
down_revision: str | Sequence[str] | None = "e4f5c648cf94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgresql():
        op.execute("ALTER TABLE conversations ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY conversations_tenant_isolation ON conversations
            FOR ALL USING (
                tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER
            )
            """
        )
        op.execute("ALTER TABLE conversation_messages ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY conversation_messages_tenant_isolation ON conversation_messages
            FOR ALL USING (
                tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER
            )
            """
        )


def downgrade() -> None:
    if _is_postgresql():
        op.execute("DROP POLICY IF EXISTS conversations_tenant_isolation ON conversations")
        op.execute("ALTER TABLE conversations DISABLE ROW LEVEL SECURITY")
        op.execute(
            "DROP POLICY IF EXISTS conversation_messages_tenant_isolation ON conversation_messages"
        )
        op.execute("ALTER TABLE conversation_messages DISABLE ROW LEVEL SECURITY")
