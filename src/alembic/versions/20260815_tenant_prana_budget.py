"""tenant prana budget columns (ADR-036 D3/D7, OP-139)

Herstelt `tenants.prana_budget` en `tenants.prana_spent`. `PranaGuard` leest die twee sinds
maart 2026, maar de migratie die ze aanmaakte (`archive/698adff2b1af`) is uit de keten gehaald.
Gemeten 2026-08-15 tegen een verse PostgreSQL na `alembic upgrade head`: beide kolommen
afwezig, dus elke aanroep van de financiele rem eindigde in een AttributeError.

Types en server-defaults zijn LETTERLIJK overgenomen uit die gearchiveerde migratie
(BigInteger, 100000 en 0), zodat een database waar die ooit op heeft gedraaid na deze migratie
in exact dezelfde toestand staat als een verse.

`server_default` en niet alleen een Python-side default: `src/core/database/seed.py` voegt
tenants toe met raw SQL via `text()`, en daar slaat een Python-side default niet aan -- precies
de fout die in OP-133 drie kolommen op NULL liet lopen tegen een NOT NULL-constraint.

Revision ID: 20260815_tenant_prana_budget
Revises: 20260815_hr_skills_tables
Create Date: 2026-08-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_tenant_prana_budget"
down_revision: str | Sequence[str] | None = "20260815_hr_skills_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("prana_budget", sa.BigInteger(), server_default="100000", nullable=False),
    )
    op.add_column(
        "tenants",
        sa.Column("prana_spent", sa.BigInteger(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tenants", "prana_spent")
    op.drop_column("tenants", "prana_budget")
