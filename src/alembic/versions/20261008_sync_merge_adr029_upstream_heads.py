"""Sync-merge: kop van het-levend-monument en kop van upstream SanskritiSetu samenvoegen.

Revision ID: 20261008_sync_merge_adr029_upstream_heads
Revises: 20260924_merge_adr029_tenant_llm_heads, 20261007_vier_ogen_bestaande_tenants
Create Date: 2026-10-07

De sync-merge van upstream/develop (301 commits) in het-levend-monument develop
liet twee koppen achter:

- Tak A (dit repo, ADR-029 portal + week-1 security): eindigt op
  20260924_merge_adr029_tenant_llm_heads (zelf al een mergepoint).
- Tak B (upstream, vier-ogen/debiteurenagent): 20260920_tenant_llm ->
  20261004_user_roles_rls -> 20261005_receivables_rls ->
  20261006_outgoing_messages_rls -> 20261006_receivables_checks ->
  20261007_vier_ogen_bestaande_tenants.

De schema-wijzigingen overlappen niet (portal/edu/security-migraties versus
receivables/vier-ogen-migraties; beide takken delen 20260917_kolomdrift en
20260920_tenant_llm als voorouder), dus een kale merge-migratie volstaat.
Zonder deze revisie meldt elke `alembic upgrade head` "Multiple head revisions
are present".

De ketentest (tests/unit/database/test_agentic_alembic_chain_complete.py)
is in dezelfde merge-commit bijgewerkt naar deze kop -- dat is de enige
volgorde waarin die pin klopt.
"""

from __future__ import annotations

revision = "20261008_sync_merge_adr029_upstream_heads"
down_revision = (
    "20260924_merge_adr029_tenant_llm_heads",
    "20261007_vier_ogen_bestaande_tenants",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Kale merge-migratie: geen schema-wijziging, alleen keten-herstel."""


def downgrade() -> None:
    """Kale merge-migratie: downgrade splitst de keten weer in twee koppen."""
