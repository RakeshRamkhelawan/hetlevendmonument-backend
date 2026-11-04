"""add gatekeeper tables

Revision ID: 552d3cb43362
Revises: 20260409c_governance_tables
Create Date: 2026-04-11 21:08:55.340765

"""
from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '552d3cb43362'
down_revision: str | Sequence[str] | None = '20260409c_governance_tables'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create gatekeeper_decisions and hitl_requests tables."""
    # GatekeeperDecision table - SHA-256 hash chain for tamper evidence
    op.create_table(
        'gatekeeper_decisions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('decision_id', sa.String(length=64), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('task_id', sa.String(length=255), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),  # ADR-005: NOT NULL
        sa.Column('decision', sa.String(length=20), nullable=False),  # allow/block/hitl/defer
        sa.Column('risk_category', sa.String(length=20), nullable=False),
        sa.Column('risk_level', sa.String(length=20), nullable=False),
        sa.Column('shadow_ceo_veto', sa.JSON(), nullable=True),
        sa.Column('policy_rules_checked', sa.JSON(), nullable=False),
        sa.Column('policy_rules_failed', sa.JSON(), nullable=False),
        sa.Column('hitl_required', sa.Boolean(), nullable=False, default=False),
        sa.Column('hitl_ticket_ref', sa.String(length=50), nullable=True),
        sa.Column('override_used', sa.Boolean(), nullable=False, default=False),
        sa.Column('decision_hash', sa.String(length=64), nullable=False),  # SHA-256
        sa.Column('previous_hash', sa.String(length=64), nullable=True),  # Chain link
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('decision_id')
    )
    op.create_index(op.f('ix_gatekeeper_decisions_decision_id'), 'gatekeeper_decisions', ['decision_id'], unique=True)
    op.create_index(op.f('ix_gatekeeper_decisions_hitl_ticket_ref'), 'gatekeeper_decisions', ['hitl_ticket_ref'], unique=False)
    op.create_index(op.f('ix_gatekeeper_decisions_task_id'), 'gatekeeper_decisions', ['task_id'], unique=False)
    op.create_index(op.f('ix_gatekeeper_decisions_tenant_id'), 'gatekeeper_decisions', ['tenant_id'], unique=False)

    # HITLRequestModel table - Human-in-the-Loop request persistence
    op.create_table(
        'hitl_requests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),  # ADR-005: NOT NULL
        sa.Column('ticket_ref', sa.String(length=50), nullable=False),
        sa.Column('task_id', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, default='pending'),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by', sa.String(length=100), nullable=True),
        sa.Column('rejected_by', sa.String(length=100), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('decision_id', sa.String(length=64), nullable=True),
        sa.Column('risk_factors', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('request_id'),
        sa.UniqueConstraint('ticket_ref')
    )
    op.create_index(op.f('ix_hitl_requests_request_id'), 'hitl_requests', ['request_id'], unique=True)
    op.create_index(op.f('ix_hitl_requests_task_id'), 'hitl_requests', ['task_id'], unique=False)
    op.create_index(op.f('ix_hitl_requests_tenant_id'), 'hitl_requests', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_hitl_requests_ticket_ref'), 'hitl_requests', ['ticket_ref'], unique=True)


def downgrade() -> None:
    """Drop gatekeeper tables."""
    op.drop_index(op.f('ix_hitl_requests_ticket_ref'), table_name='hitl_requests')
    op.drop_index(op.f('ix_hitl_requests_tenant_id'), table_name='hitl_requests')
    op.drop_index(op.f('ix_hitl_requests_task_id'), table_name='hitl_requests')
    op.drop_index(op.f('ix_hitl_requests_request_id'), table_name='hitl_requests')
    op.drop_table('hitl_requests')
    
    op.drop_index(op.f('ix_gatekeeper_decisions_tenant_id'), table_name='gatekeeper_decisions')
    op.drop_index(op.f('ix_gatekeeper_decisions_task_id'), table_name='gatekeeper_decisions')
    op.drop_index(op.f('ix_gatekeeper_decisions_hitl_ticket_ref'), table_name='gatekeeper_decisions')
    op.drop_index(op.f('ix_gatekeeper_decisions_decision_id'), table_name='gatekeeper_decisions')
    op.drop_table('gatekeeper_decisions')
