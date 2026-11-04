"""Zes tabellen met een RLS-policy misten een index met tenant_id vooraan.

Revision ID: 20260818_rls_index
Revises: 20260818_rls_expr
Create Date: 2026-08-17

ADR-036 OP-161. Row Level Security voegt aan elke query een `tenant_id = ...`-voorwaarde
toe. Staat die kolom niet als LEIDENDE kolom in een index, dan kan de planner de voorwaarde
niet in een index-scan duwen en valt hij terug op een sequential scan -- op elke query, op
die tabel.

Gemeten 2026-08-17 op een database uit `alembic upgrade head`: 137 tabellen met een policy
en een tenantkolom, waarvan 131 met en zes zonder leidende index. Dit repareert die zes.

**Waarom dit nu moet en niet later.** De applicatie verbindt vandaag als tabeleigenaar, en
PostgreSQL slaat RLS voor de eigenaar over -- de policies doen dus niets en kosten dus
niets. Op de dag dat de applicatie een eigen rol krijgt (OP-151) worden ze allemaal
tegelijk actief. Een tekort dat zich dan aandient als "de applicatie is ineens traag" is
een van de moeilijkst toe te wijzen storingen die er zijn, juist omdat de oorzaak een
wijziging is die niets met prestaties te maken leek te hebben.

`officer_verdicts` is de opvallendste van de zes: die tabel wordt bij elke raadsbeslissing
geschreven en gelezen.

Een enkelkolomsindex op `tenant_id` volstaat voor het RLS-predicaat. Een samengestelde
index met een tweede kolom erbij zou voor specifieke query's sneller zijn, maar dat vraagt
kennis van de daadwerkelijke query-patronen; die is er niet, en gokken levert indexen op
die onderhoud kosten zonder aantoonbaar nut.

`IF NOT EXISTS` omdat een bestaande omgeving de index handmatig kan hebben gekregen.
Geen `CONCURRENTLY`: Alembic draait migraties in een transactie en dat verdraagt zich niet
met `CREATE INDEX CONCURRENTLY`. Op deze zes tabellen is een gewone `CREATE INDEX`
verdedigbaar; wordt een van hen ooit heel groot, dan is dat een eigen afweging.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260818_rls_index"
down_revision = "20260818_rls_expr"
branch_labels = None
depends_on = None

# Tabel -> indexnaam. Expliciet benoemd: een migratie die over een BENOEMDE verzameling
# loopt is in vijf seconden te controleren, en het mutatiebewijs heeft een regel per
# element.
_TABELLEN: dict[str, str] = {
    "ab_tests": "ix_ab_tests_tenant_id",
    "campaign_analytics": "ix_campaign_analytics_tenant_id",
    "campaign_segments": "ix_campaign_segments_tenant_id",
    "deletion_audit": "ix_deletion_audit_tenant_id",
    "focus_builder_accepted_workflows": "ix_fb_accepted_workflows_tenant_id",
    "officer_verdicts": "ix_officer_verdicts_tenant_id",
}


def _is_postgresql() -> bool:
    """De unit-tests draaien op SQLite; daar is dit zonder betekenis."""
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return

    for tabel, index in _TABELLEN.items():
        op.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {index} ON {tabel} (tenant_id)"))


def downgrade() -> None:
    """Exacte inverse: alleen de zes indexen die deze migratie aanmaakt."""
    if not _is_postgresql():
        return

    for index in _TABELLEN.values():
        op.execute(sa.text(f"DROP INDEX IF EXISTS {index}"))
