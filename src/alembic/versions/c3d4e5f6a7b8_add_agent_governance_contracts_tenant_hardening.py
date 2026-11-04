"""Add agent_governance_contracts table, tenant_id NOT NULL, RLS

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-03

SP-GOV-ARCH-7 (AUDIT-ARCH-2026-07-02 Dag 3 Groep E): GovernanceContract
(src/core/governance/governance_contract.py) held autonomy_level/risk_category/
evidence purely in-memory, scoped to a single agent instance's lifetime. A
HUMAN_IN_LOOP agent's HITL approval (evidence['approved_actions']) had no
durable backing -- a process restart silently wiped every prior approval, and
record_hitl_approval() had zero production callers (confirmed by
tests/architecture/test_autonomy_ladder_uses_real_agent_capabilities.py::
test_hitl_approval_has_a_production_caller).

This migration adds agent_governance_contracts (tenant_id NOT NULL + RLS,
UNIQUE(tenant_id, agent_id)) so src/core/governance/governance_contract_
repository.py can load/save contract state, giving the gatekeeper HITL
approval endpoint a durable target to call record_hitl_approval() against.

Also adds hitl_requests.agent_id (nullable, existing table): security review
of this same sprint item found that a client-supplied agent_id decoupled from
the HITL ticket being approved would let any caller graft an approval onto an
unrelated agent's contract within their own tenant. Fix: approve_hitl() now
derives agent_id server-side from hitl.agent_id instead of trusting a request-
body field -- this column is what makes that possible.

backend-patterns.md #9: NOOIT sa.inspect(op.get_bind()) in migraties. Uses raw
"CREATE TABLE IF NOT EXISTS" / "DROP TABLE IF EXISTS" SQL, matching the
established pattern in 884d744f6aa9 / a1b2c3d4e5f6 / b2c3d4e5f6a7.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_EXPR = "NULLIF(current_setting('app.current_tenant', true), '')::integer"

_TENANT_SCOPED_TABLES = ["agent_governance_contracts"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_governance_contracts (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            agent_id VARCHAR(255) NOT NULL,
            autonomy_level VARCHAR(50) NOT NULL,
            risk_category VARCHAR(50) NOT NULL,
            evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_agent_governance_contracts_tenant_agent UNIQUE (tenant_id, agent_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_governance_contracts_tenant_id "
        "ON agent_governance_contracts (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_governance_contracts_agent_id "
        "ON agent_governance_contracts (agent_id)"
    )

    for tbl in _TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl}")
        op.execute(f"CREATE POLICY {tbl}_tenant_isolation ON {tbl} USING (tenant_id = {_RLS_EXPR})")

    op.execute("ALTER TABLE hitl_requests ADD COLUMN IF NOT EXISTS agent_id VARCHAR(255)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_hitl_requests_agent_id ON hitl_requests (agent_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_hitl_requests_agent_id")
    op.execute("ALTER TABLE hitl_requests DROP COLUMN IF EXISTS agent_id")

    for tbl in _TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl}")

    op.execute("DROP TABLE IF EXISTS agent_governance_contracts")
