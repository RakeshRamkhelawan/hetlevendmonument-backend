"""Sync-merge 2026-11-01: kop van het-levend-monument en kop van upstream SanskritiSetu samenvoegen.

Revision ID: 20261101_sync_merge_adr029_upstream_heads
Revises: 20261008_sync_merge_adr029_upstream_heads, 20261026_user_roles_tenant_index
Create Date: 2026-11-01

De sync-merge van upstream/develop (8da3ba206, 689 commits) liet twee koppen achter:
onze kop 20261008_sync_merge_adr029_upstream_heads en upstreams kop
20261026_user_roles_tenant_index. Onze tak heeft sinds 20261008 geen eigen migratie;
upstream bouwde verder op 20261007_vier_ogen_bestaande_tenants, een voorouder van onze
kop. Er is dus geen schema-overlap en een kale merge-migratie volstaat.
"""

from __future__ import annotations

revision = "20261101_sync_merge_adr029_upstream_heads"
down_revision = (
    "20261008_sync_merge_adr029_upstream_heads",
    "20261026_user_roles_tenant_index",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Kale merge-migratie: geen schema-wijziging, alleen keten-herstel."""


def downgrade() -> None:
    """Kale merge-migratie: downgrade splitst de keten weer in twee koppen."""
