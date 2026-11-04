"""Bewaar wat de MENS erbij schreef toen hij een HITL-ticket besloot.

Revision ID: 20260806_hitl_resolution_note
Revises: 20260706_add_agentic_tasks_table
Create Date: 2026-08-06

Bevinding: ADR-036 OP-69, blinde code-review op dag 1 van BE-AGT-045.
ADR: ADR-015 (HITL-gate), AI Act art. 14 (aantoonbaar menselijk toezicht)

`ToolHITLRejection.reason` is verplicht met `min_length=10` en `ToolHITLApproval.notes` is
optioneel. Beide werden gevalideerd en daarna weggegooid, omdat `hitl_tickets` er geen kolom voor
had. Op een endpoint waarvan de hele rechtvaardiging aantoonbaar menselijk toezicht is, was de
motivering van de mens het enige dat NIET werd bewaard.

Nullable, want elk bestaand ticket is besloten zonder dat deze tekst kon worden opgeslagen. Een
`NOT NULL` met een verzonnen default zou beweren dat er een motivering was.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_hitl_resolution_note"
down_revision: str | Sequence[str] | None = "20260706_add_agentic_tasks_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hitl_tickets",
        sa.Column("resolution_note", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hitl_tickets", "resolution_note")
