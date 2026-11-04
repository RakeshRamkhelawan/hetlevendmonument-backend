"""Algoritme-markering per auditregel (ADR-036 OP-120).

`NULL` = legacy SHA-256, `"hmac-sha256-v1"` = gesleuteld met `AUDIT_CHAIN_HMAC_KEY`.

Zonder deze kolom zou een omschakeling naar HMAC elke bestaande rij als gemanipuleerd melden --
`tampering_detected=True` voor iedere tenant, op vier endpoints tegelijk, permanent. Er is geen
backfill mogelijk: omhashen van historische rijen vernietigt juist de bewijswaarde.

De waarde zit ZELF in de preimage van de hash (`hash_chain._hash_volgens_markering`), anders zet
een aanvaller hem terug op `NULL`, valt in de sleutelloze legacy-tak en herberekent de rij.

Revision ID: 20260811_audit_hash_algorithm
Revises: 20260810b_audit_chain_anchors
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_audit_hash_algorithm"
down_revision: str | None = "20260810b_audit_chain_anchors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("hash_algorithm", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audit_logs", "hash_algorithm")
