"""Sync-merge: twee migratiekoppen samenvoegen tot een kop.

Revision ID: 20260924_merge_adr029_tenant_llm_heads
Revises: 20260915_adr029_audit_hardening, 20260920_tenant_llm
Create Date: 2026-09-24

Beide ouders bouwen voort op 20260917_kolomdrift maar takten daarna uiteen:

- Tak A (dit repo, ADR-029 portal): 20260909_adr029_edu_alignment ->
  20260910_adr029_sprint_c_datamodel -> 20260915_adr029_audit_hardening.
- Tak B (upstream sync, ADR-036/LLM): 20260920_tenant_llm
  (tenant_llm_providers + tenants.externe_providers_toegestaan).

De schema-wijzigingen overlappen niet (portal/edu-tabellen versus
tenant-LLM-tabellen), dus een kale merge-migratie volstaat. Zonder deze
revisie meldt elke `alembic upgrade head` "Multiple head revisions are
present".

De ketentest (tests/unit/database/test_agentic_alembic_chain_complete.py)
is in dezelfde commit bijgewerkt naar deze kop -- dat is de enige volgorde
waarin die pin klopt.
"""

from __future__ import annotations

revision = "20260924_merge_adr029_tenant_llm_heads"
down_revision = ("20260915_adr029_audit_hardening", "20260920_tenant_llm")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Kale merge-migratie: geen schema-wijziging, alleen keten-herstel."""


def downgrade() -> None:
    """Kale merge-migratie: downgrade splitst de keten weer in twee koppen."""
