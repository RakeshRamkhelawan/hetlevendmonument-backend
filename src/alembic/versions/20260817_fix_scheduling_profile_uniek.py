"""cross-tenant unieke index op user_scheduling_profiles rechtzetten (Gate 2-review)

`user_scheduling_profiles` had `unique=True` op `user_id` alleen, op een tabel met
`tenant_id NOT NULL`. Twee gevolgen: tenant B kan geen profiel aanmaken voor een `user_id` die
tenant A al gebruikt, en het verschil tussen "aangemaakt" en "unique violation" verraadt het
BESTAAN van een gebruiker in een andere tenant.

Het model is gerepareerd, en op een VERSE database maakt de baseline de goede vorm al aan
(`20260817_baseline_ontbrekende_tabellen.py`: constraint `uq_scheduling_profile_tenant_user`
plus een NIET-unieke index). Deze migratie bestaat uitsluitend voor BESTAANDE databases, waar
de oude unieke index al staat en `CREATE INDEX IF NOT EXISTS` -- voorwaardelijk op de NAAM --
hem nooit vervangt.

DRIE DINGEN DIE EEN EERDERE VERSIE FOUT DEED, alle drie gemeten door de Gate 2-reviewer:

1. **De volgorde was verkeerd en verzwakte de database.** Hij dropte de bestaande unieke index
   VOOR hij de nieuwe constraint probeerde. Op een database met dubbele
   `(tenant_id, user_id)`-combinaties mislukte de constraint, werd de fout met een `RAISE
   WARNING` weggeslikt die nergens in de alembic-uitvoer terugkomt, en eindigde de migratie met
   exitcode 0 -- met als netto resultaat GEEN uniciteit meer, waar er daarvoor nog wel was.
   Nu: constraint EERST, en pas als die is gelukt wordt de index vervangen. Een reparatie die
   de beveiliging verzwakt mag nooit slagen.

   **En dat maakt het duplicatenscenario zelfs onbereikbaar, niet alleen luidruchtig.** De
   migratie doet alleen iets als `ix_user_scheduling_profiles_user_id` UNIEK is. Is die index
   uniek op `user_id`, dan delen per definitie geen twee rijen een `user_id`, dus delen ze ook
   geen `(tenant_id, user_id)`. `ADD CONSTRAINT UNIQUE (tenant_id, user_id)` kan in dit pad dus
   niet op duplicaten stuklopen. Gemeten: een database met dubbele `(tenant_id, user_id)` heeft
   per definitie GEEN unieke index meer, en daar stapt de migratie meteen uit.

2. **De downgrade was geen inverse.** Hij dropte onvoorwaardelijk de constraint -- ook op een
   verse database, waar de BASELINE hem had aangemaakt -- en legde de cross-tenant unieke index
   terug die de keten nooit produceert. Daarmee herintroduceerde de terugweg exact de
   beveiligingsfout die de heenweg oplost. Nu draait de downgrade alleen terug wat DEZE upgrade
   daadwerkelijk heeft gewijzigd, bijgehouden in `_sched_uniek_20260817`.

3. **Hij deed op een verse database niets, maar zei van wel.** Nu stapt hij expliciet uit
   wanneer de oude index niet uniek is -- de normale toestand na de baseline.

Eigen migratie conform `.claude/rules/database.md` ("Add indexes in their own migration").
Bewust GEEN `sa.inspect(op.get_bind())`: dat crasht offline (OP-148). De voorwaardelijkheid zit
in SQL die offline gewoon meeschrijft.

BEKENDE BEPERKING, eerlijk opgeschreven: als er NA deze upgrade dubbele `user_id`-waarden
ontstaan -- wat de fix juist mogelijk maakt -- kan de downgrade de oude unieke index niet meer
aanleggen en faalt hij. Dat is inherent aan het terugdraaien van deze fix en geen defect: de
oude toestand is dan simpelweg niet meer bereikbaar zonder data weg te gooien.

Revision ID: 20260817_sched_uniek
Revises: 20260817_rls_baseline
Create Date: 2026-08-17

"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260817_sched_uniek"
down_revision: str | Sequence[str] | None = "20260817_rls_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABEL = "user_scheduling_profiles"
_INDEX = "ix_user_scheduling_profiles_user_id"
_CONSTRAINT = "uq_scheduling_profile_tenant_user"
_BOEKHOUDING = "_sched_uniek_20260817"


def upgrade() -> None:
    """Alleen op een database die de oude, cross-tenant unieke index nog heeft."""
    op.execute(
        f"""
        DO $$
        DECLARE was_uniek BOOLEAN;
        BEGIN
            SELECT i.indisunique INTO was_uniek
              FROM pg_index i
              JOIN pg_class c ON c.oid = i.indexrelid
             WHERE c.relname = '{_INDEX}';

            -- Geen index, of al niet-uniek: dit is de toestand na de baseline. Niets te doen,
            -- en met opzet ook niets in de boekhouding -- dan blijft de downgrade een no-op.
            IF was_uniek IS DISTINCT FROM TRUE THEN
                RETURN;
            END IF;

            -- EERST de nieuwe garantie. Bestaan er dubbele (tenant_id, user_id)-combinaties,
            -- dan faalt dit met een unique_violation en breekt de hele migratie af -- luid, en
            -- zonder dat de bestaande uniciteit al is weggehaald.
            ALTER TABLE {_TABEL}
                ADD CONSTRAINT {_CONSTRAINT} UNIQUE (tenant_id, user_id);

            -- Pas nu is het veilig om de te ruime index te vervangen.
            DROP INDEX {_INDEX};
            CREATE INDEX {_INDEX} ON {_TABEL} (user_id);

            -- De boekhouding wordt pas HIER aangemaakt, niet bovenaan. Op een verse
            -- database doet deze migratie niets, en dan hoort er ook geen tabel achter te
            -- blijven -- anders staat er DDL zonder model in de keten, en dat is precies
            -- wat `test_the_chain_creates_nothing_the_models_do_not_know` terecht
            -- afkeurde (CI, 2026-08-17).
            CREATE TABLE IF NOT EXISTS {_BOEKHOUDING} (gewijzigd BOOLEAN PRIMARY KEY);
            INSERT INTO {_BOEKHOUDING} (gewijzigd) VALUES (TRUE) ON CONFLICT DO NOTHING;
        END $$;
        """
    )


def downgrade() -> None:
    """Draait UITSLUITEND terug wat deze upgrade daadwerkelijk heeft gewijzigd."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{_BOEKHOUDING}') IS NULL THEN
                RETURN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM {_BOEKHOUDING} WHERE gewijzigd) THEN
                RETURN;
            END IF;

            ALTER TABLE {_TABEL} DROP CONSTRAINT IF EXISTS {_CONSTRAINT};
            DROP INDEX IF EXISTS {_INDEX};
            -- Kan falen als er inmiddels dubbele user_id-waarden zijn; zie de docstring.
            CREATE UNIQUE INDEX {_INDEX} ON {_TABEL} (user_id);
        END $$;
        """
    )
    op.execute(f"DROP TABLE IF EXISTS {_BOEKHOUDING}")
