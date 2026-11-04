"""create adaptation_rules table

Revision ID: a45f3cd4bfb3
Revises: 20260412_001_create_tool_audit_logs
Create Date: 2026-04-14 09:30:00.000000

"""
from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a45f3cd4bfb3'
down_revision: str | None = '20260412_001_create_tool_audit_logs'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'adaptation_rules',
        sa.Column('id', sa.String(128), nullable=False),
        sa.Column('rule_id', sa.String(128), nullable=False),
        sa.Column('tenant_id', sa.String(128), nullable=False),
        sa.Column('rule_type', sa.String(50), nullable=False, server_default=sa.text("'routing_correction'")),
        sa.Column('source_pattern_id', sa.String(255), nullable=True),
        sa.Column('trigger_keywords', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('trigger_patterns', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('target_supervisor', sa.String(255), nullable=True),
        sa.Column('target_agent', sa.String(255), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False, server_default=sa.text('0.5')),
        sa.Column('priority', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('application_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('success_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('times_applied', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('success_rate', sa.Float(), nullable=False, server_default=sa.text('0.0')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('condition', postgresql.JSONB(), nullable=True),
        sa.Column('action', postgresql.JSONB(), nullable=True),
        sa.Column('parameters', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='adaptation_rules_pkey'),
        sa.UniqueConstraint('rule_id', name='adaptation_rules_rule_id_key'),
    )
    op.create_index('ix_adaptation_rules_tenant', 'adaptation_rules', ['tenant_id'])
    op.create_index('ix_adaptation_rules_active', 'adaptation_rules', ['is_active', 'priority'])
    op.create_index('ix_adaptation_rules_tenant_active', 'adaptation_rules', ['tenant_id', 'is_active'])
    op.create_index('ix_adaptation_rules_rule_id', 'adaptation_rules', ['rule_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_adaptation_rules_rule_id', table_name='adaptation_rules')
    op.drop_index('ix_adaptation_rules_tenant_active', table_name='adaptation_rules')
    op.drop_index('ix_adaptation_rules_active', table_name='adaptation_rules')
    op.drop_index('ix_adaptation_rules_tenant', table_name='adaptation_rules')
    op.drop_table('adaptation_rules')
