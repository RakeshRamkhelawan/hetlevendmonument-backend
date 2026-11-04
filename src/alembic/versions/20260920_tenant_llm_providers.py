"""De LLM-providers van een tenant, plus de schakelaar die extern kan verbieden.

Revision ID: 20260920_tenant_llm
Revises: 20260917_kolomdrift
Create Date: 2026-09-20

Fase 2 van het lokaal-eerst-LLM-plan (besluit Rakesh 2026-09-20): geen vendor lock-in, een
klant geeft bij de inrichting zijn eigen eindpunt, model en sleutel op. De volgorde in deze
tabel WORDT de failoverketen die ADR-026 par. 1.2.1 beschrijft als `tenant.llm_chain` -- een
veld dat tot nu toe niet bestond.

Bewust "wordt" en niet "is": de keten wordt vandaag OPGESLAGEN en door niemand gelezen.
`TenantLLMProviderService.keten()` heeft nul aanroepers; dat verandert pas in fase 2b. Een
docstring die er tegenwoordige tijd van maakt, leest als werkende functionaliteit -- precies
de faalvorm die ADR-036 paragraaf 1 beschrijft. Hier stond "IS" tot 2026-09-21.

**Over Row Level Security in deze migratie.** Hij zet `ENABLE ROW LEVEL SECURITY` plus een
policy, en bewust GEEN `FORCE`. Wat dat betekent verschilt per omgeving, en dat verschil is
gemeten (2026-09-21):

- PostgreSQL past een policy toe op iedereen BEHALVE de tabeleigenaar; `FORCE` trekt de
  eigenaar erbij. Superusers en rollen met BYPASSRLS omzeilen het altijd, ook met `FORCE`.
- Lokaal en in de testdatabase verbindt alles als `postgres` -- eigenaar EN superuser -- dus
  daar beschermt de policy niets. In de testdatabase staat RLS zelfs helemaal uit, omdat het
  schema daar uit `create_all` komt en niet uit deze migratie.
- Op staging verbindt de applicatie als `sanskritisetu_app`, die GEEN eigenaar is. Gemeten
  2026-09-21: alle drie de container apps verwijzen naar het geheim `app-database-url`, en de
  waarde van dat geheim bevat `sanskritisetu_app` (getoetst op aanwezigheid, niet uitgelezen).
  Voor die rol werkt de policy dus, ook zonder `FORCE`.

**Wat `FORCE` hier WEL en NIET doet, en wat ik niet heb kunnen meten.** Een eerdere versie van
deze docstring zei "FORCE toevoegen is geen verbetering van de bescherming". Dat is te stellig
en beide Gate 2-reviewers hebben het terecht afgekeurd:

- Voor het APPLICATIEPAD klopt het: die rol is geen eigenaar, dus `ENABLE` volstaat.
- Voor het EIGENAARSPAD niet: migraties en beheertaken draaien als eigenaar of als een rol met
  BYPASSRLS, en juist die begrenst `FORCE`. ADR-036 OP-151 behandelt `FORCE` dan ook als
  onderdeel van de omschakeling, niet als overbodig.

Wat daarbij hoort en NIET gemeten is: het register noemt dat er op 2026-09-17 met de hand
`FORCE` op 170 staging-tabellen is gezet. Dat heb ik niet kunnen bevestigen -- de
staging-database weigerde twee keer een read-only verbinding omdat hij aan zijn
verbindingsplafond zit (`max_connections = 50`, 40-41 actief). Wat ik WEL kan meten: geen
enkele migratie in deze repo voert `FORCE` uit, en lokaal heeft nul tabel het.

Daarmee is de eerlijke stand: deze tabel krijgt `ENABLE` plus een policy, net als de rest van
de keten. Of staging daarnaast handmatig `FORCE` heeft en of deze tabel daar dan buiten valt,
is een open vraag die alleen op staging te beantwoorden is. `FORCE` in deze migratie zetten
raakt elke omgeving en is daarom een eigen besluit, geen regel die hier stil bijkomt.

**`externe_providers_toegestaan` staat standaard op FALSE.** Dat is de verkoopbelofte "alle
data blijft op eigen server" als schakelaar in plaats van als gewoonte: zolang hij uit staat,
weigert het schrijfpad een extern eindpunt. Een tenant die niets instelt, praat dus met het
lokale model en met niets anders.

De policy zelf volgt het patroon van `20260915_rls_resterende_tabellen.py`. Wat overal geldt,
ook op staging: het expliciete tenantfilter in de repository is de laag die je kunt aanwijzen.
De policy is de tweede laag, en hoe hard die is hangt af van de rol -- zie hierboven.

`to_regclass` en GEEN `sa.inspect(op.get_bind())`: die laatste crasht bij een offline dry-run
(`upgrade head --sql`), backend-patterns regel 9.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260920_tenant_llm"
down_revision = "20260917_kolomdrift"
branch_labels = None
depends_on = None

_TABEL = "tenant_llm_providers"
_POLICY = f"rls_{_TABEL}_tenant_isolation"
_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"


def _is_postgresql() -> bool:
    """RLS bestaat niet in SQLite; een deel van de tests draait daarop."""
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        _TABEL,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("volgorde", sa.Integer(), nullable=False),
        sa.Column("naam", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        # Nooit een leesbare sleutel. Nullable: een lokaal eindpunt heeft er geen nodig, en een
        # verzonnen placeholder zou als geldige sleutel worden aangeboden.
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("actief", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Twee rijen met dezelfde volgorde geven een niet-bepaalde failovervolgorde -- stil, en
        # per query anders.
        sa.UniqueConstraint(
            "tenant_id", "volgorde", name="uq_tenant_llm_providers_tenant_volgorde"
        ),
    )
    op.create_index(f"ix_{_TABEL}_id", _TABEL, ["id"])
    op.create_index(f"ix_{_TABEL}_tenant_id", _TABEL, ["tenant_id"])

    # server_default op false, niet alleen een Python-default: bestaande tenantrijen moeten een
    # waarde krijgen, en de schakelaar hoort UIT te staan voor wie er nooit iets over zei.
    op.add_column(
        "tenants",
        sa.Column(
            "externe_providers_toegestaan",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    if not _is_postgresql():
        return

    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.{_TABEL}') IS NULL THEN
                    RETURN;
                END IF;
                EXECUTE 'ALTER TABLE {_TABEL} ENABLE ROW LEVEL SECURITY';
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public' AND tablename = '{_TABEL}'
                      AND policyname = '{_POLICY}'
                ) THEN
                    -- Dollar-quoting ($q$): de expressie bevat zelf enkele quotes rond
                    -- 'app.current_tenant', en die zouden de EXECUTE-string vroegtijdig
                    -- sluiten (gemeten 2026-09-15 in de zustermigratie).
                    EXECUTE $q$CREATE POLICY {_POLICY} ON {_TABEL} USING ({_EXPRESSIE})$q$;
                END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    if _is_postgresql():
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('public.{_TABEL}') IS NULL THEN
                        RETURN;
                    END IF;
                    EXECUTE 'DROP POLICY IF EXISTS {_POLICY} ON {_TABEL}';
                    EXECUTE 'ALTER TABLE {_TABEL} DISABLE ROW LEVEL SECURITY';
                END $$;
                """
            )
        )

    op.drop_column("tenants", "externe_providers_toegestaan")
    op.drop_index(f"ix_{_TABEL}_tenant_id", table_name=_TABEL)
    op.drop_index(f"ix_{_TABEL}_id", table_name=_TABEL)
    op.drop_table(_TABEL)
