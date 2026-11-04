"""add_activepieces_tables

Revision ID: 20260408_add_activepieces_tables
Revises: 20260407_user_profile_align
Create Date: 2026-04-08 01:00:00.000000

"""
from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260408_add_activepieces_tables'
down_revision: str | Sequence[str] | None = '20260407_user_profile_align'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ActivePieces integration tables."""
    
    # Create activepieces_flows table
    op.create_table(
        'activepieces_flows',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('ap_flow_id', sa.String(length=255), nullable=False),
        sa.Column('project_id', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('flow_definition', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activepieces_flows_ap_flow_id'), 'activepieces_flows', ['ap_flow_id'], unique=False)
    op.create_index(op.f('ix_activepieces_flows_tenant_id'), 'activepieces_flows', ['tenant_id'], unique=False)
    
    # Create activepieces_connections table
    op.create_table(
        'activepieces_connections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('ap_connection_id', sa.String(length=255), nullable=False),
        sa.Column('project_id', sa.String(length=255), nullable=False),
        sa.Column('app_name', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('encrypted_credentials', sa.Text(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('last_error_at', sa.DateTime(), nullable=True),
        sa.Column('last_error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activepieces_connections_ap_connection_id'), 'activepieces_connections', ['ap_connection_id'], unique=False)
    op.create_index(op.f('ix_activepieces_connections_app_name'), 'activepieces_connections', ['app_name'], unique=False)
    op.create_index(op.f('ix_activepieces_connections_tenant_id'), 'activepieces_connections', ['tenant_id'], unique=False)
    
    # Create activepieces_flow_runs table
    op.create_table(
        'activepieces_flow_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('flow_id', sa.UUID(), sa.ForeignKey('activepieces_flows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ap_run_id', sa.String(length=255), nullable=False),
        sa.Column('project_id', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
        sa.Column('output', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activepieces_flow_runs_ap_run_id'), 'activepieces_flow_runs', ['ap_run_id'], unique=False)
    op.create_index(op.f('ix_activepieces_flow_runs_flow_id'), 'activepieces_flow_runs', ['flow_id'], unique=False)
    op.create_index(op.f('ix_activepieces_flow_runs_tenant_id'), 'activepieces_flow_runs', ['tenant_id'], unique=False)
    
    # Create activepieces_sync_logs table
    op.create_table(
        'activepieces_sync_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('sync_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('items_synced', sa.Integer(), nullable=True),
        sa.Column('items_failed', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activepieces_sync_logs_tenant_id'), 'activepieces_sync_logs', ['tenant_id'], unique=False)


def downgrade() -> None:
    """Drop ActivePieces integration tables."""
    op.drop_index(op.f('ix_activepieces_sync_logs_tenant_id'), table_name='activepieces_sync_logs')
    op.drop_table('activepieces_sync_logs')
    
    op.drop_index(op.f('ix_activepieces_flow_runs_tenant_id'), table_name='activepieces_flow_runs')
    op.drop_index(op.f('ix_activepieces_flow_runs_flow_id'), table_name='activepieces_flow_runs')
    op.drop_index(op.f('ix_activepieces_flow_runs_ap_run_id'), table_name='activepieces_flow_runs')
    op.drop_table('activepieces_flow_runs')
    
    op.drop_index(op.f('ix_activepieces_connections_tenant_id'), table_name='activepieces_connections')
    op.drop_index(op.f('ix_activepieces_connections_app_name'), table_name='activepieces_connections')
    op.drop_index(op.f('ix_activepieces_connections_ap_connection_id'), table_name='activepieces_connections')
    op.drop_table('activepieces_connections')
    
    op.drop_index(op.f('ix_activepieces_flows_tenant_id'), table_name='activepieces_flows')
    op.drop_index(op.f('ix_activepieces_flows_ap_flow_id'), table_name='activepieces_flows')
    op.drop_table('activepieces_flows')
