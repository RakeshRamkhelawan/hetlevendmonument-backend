"""user_roles krijgt een index die met de klant begint (de enige RLS-tabel zonder leidende tenantindex).

Revision ID: 20261026_user_roles_tenant_index
Revises: 20261025_audit_anonimiseer_functie
Create Date: 2026-10-26

**Het probleem.** `20261009_user_roles_tenant_id` voegde de kolom `tenant_id` toe aan `user_roles` en twee samengestelde
vreemde sleutels (`fk_user_roles_user_tenant`, `fk_user_roles_role_tenant`), maar geen index die met `tenant_id` begint. Elke
query onder RLS op `user_roles` filtert op `tenant_id`, dus zonder zo'n index valt hij terug op een scan zodra de
applicatie met een eigen rol verbindt. De guard `tests/integration/database/test_every_rls_table_has_a_leading_tenant_index.py`
meldt `user_roles` als de enige van 184 tabellen met een policy. Hoe traag dat is, is NIET gemeten.

**De oplossing.** Een index op `(tenant_id, user_id)`. De tweede kolom is `user_id` omdat vrijwel elke query op `user_roles` op de
gebruiker filtert (`git grep "user_roles.c.user_id"`: aanmelden, de rechtencontrole in `rbac_service`, gebruikersbeheer). Zoeken
op alleen `role_id` komt in de code veel minder voor; een index voor die richting is niet gemeten en niet toegevoegd.

**Alleen toevoegend.** Er verandert geen rij en er gaat niets weg. `downgrade()` haalt alleen deze index weg. De tabel is klein
(een rij per gebruiker en rol), dus een gewone `CREATE INDEX` is genoeg; er is geen `CONCURRENTLY` nodig.
"""

from alembic import op

revision = "20261026_user_roles_tenant_index"
down_revision = "20261025_audit_anonimiseer_functie"
branch_labels = None
depends_on = None

_INDEX = "ix_user_roles_tenant_user"


def upgrade() -> None:
    op.create_index(_INDEX, "user_roles", ["tenant_id", "user_id"])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="user_roles")
