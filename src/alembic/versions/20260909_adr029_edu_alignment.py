"""ADR-029 Foundation Portal v1 -- educatieve tabellen en enums aligneren op de ORM-modellen.

Revision ID: 20260909_adr029_edu_alignment
Revises: 20260917_kolomdrift
Create Date: 2026-09-09

Achtergrond: migratie 20260824_adr029_portal_v1 maakte twee tabellen en twee
enum-types aan die niet overeenkomen met de SQLAlchemy-modellen in
src/core/models/foundation_content.py. Elke ORM-insert op deze tabellen faalde:

1. educational_access.kolom `code` String(20) != model `code_hash` String(64)
   (het model bewaart SHA-256 hashes, nooit plaintext).
2. study_collections.kolom `access_code` String(20) != model
   `educational_access_id` (FK naar educational_access.id, NOT NULL) plus
   composite index `idx_sc_tenant_code` op (tenant_id, educational_access_id).
3. portal_role_enum / educational_role_enum werden met lowercase waarden
   gemaakt, terwijl SQLAlchemy zonder values_callable de member-NAMEN
   (hoofdletters) serialiseert. De modellen kregen values_callable zodat ze
   de .value's (lowercase) schrijven -- dat matcht dit type.
4. newsletter_status_enum kreeg in 20260824 een dode dubbele waarde
   'bounced' (lowercase) naast de bestaande 'BOUNCED' (hoofdletters, model
   serialiseert member-namen). PostgreSQL kan enum-waarden niet droppen
   zonder type-recreatie; die recreatie gebeurt hier expliciet omdat het
   type klein is en maar door een kolom gebruikt wordt.

Data-veiligheid: omdat de ORM nooit met deze kolommen kon schrijven, is elke
bestaande rij in educational_access / study_collections een onbruikbaar
plaintext-restant (ongehaste codes / vrije access_codes zonder FK-doel).
De veiligste route is die rijen expliciet te verwijderen voor de NOT NULL /
FK-wijzigingen; downstream referenties bestonden nooit (geen werkende ORM-flow).

DEFENSIEF Sinds 2026-09-24 (BE-MIG-015)
---------------------------------------
Deze migratie stond tot 2026-09-18 onder 20260716_backfill_prana_budgets en
werd toen herkoppeld onder 20260917_kolomdrift (zie de notitie bij
down_revision). Kolomdrift voegt educational_access.code_hash (+
uq_educational_access_code_hash), study_collections.educational_access_id
(+ fk_study_collections_educational_access_id en
ix_study_collections_educational_access_id) zelf al onvoorwaardelijk toe.
Deze migratie deed daarna een ONVOORWAARDELIJKE `RENAME code TO code_hash`
en `ADD COLUMN educational_access_id` -- en faalde daarmee op elke database
die de keten in deze volgorde draait:

    psycopg2.errors.DuplicateColumn: column "code_hash" of relation
    "educational_access" already exists

Gemeten 2026-09-24 op een verse PostgreSQL 15 (wegwerp-database op de
testserver): de keten sterft hier, op weg naar head. In deze ketenpositie
heeft deze migratie dus NOOIT ergens succesvol gedraaid: niet op een verse
database (bewezen), niet op staging (kolomdrift's eigen docstring meet
2026-09-17 dat staging code_hash miste, dus edu_alignment had daar nog niet
gedraaid; na de herkoppeling kan hij daar alleen maar falen), en productie is
sinds 2026-05-11 niet ingericht. Een database die hem in de OUDE positie
(voor 2026-09-18) wel heeft toegepast, draagt de revisie-id al in
alembic_version en voert hem nooit opnieuw uit. Daarom mag de migratie
zelf aangepast worden -- .claude/rules/database.md's "never modify" beschermt
omgevingen die de migratie al hebben gedraaid, en een NIEUWE migratie bovenop
de keten kan een mid-chain DuplicateColumn onmogelijk repareren (de keten
bereikt die kop nooit).

De upgrade inspecteert daarom eerst welke kolommen er staan:

- beide `code` EN `code_hash` aanwezig (de werkelijke keten, post-kolomdrift):
  het plaintext-restant `code` uit 20260824 gaat WEG met zijn unieke sleutel
  en indexen; kolomdrift's code_hash-objecten blijven staan (ook onder
  kolomdrift's namen -- diens downgrade verwacht ze zo terug).
- alleen `code` aanwezig (kolomdrift-objecten ontbreken; kan in deze keten
  niet voorkomen, maar de migratie blijft er correct onder): het
  oorspronkelijke rename-pad.
- alleen `code_hash`: al aligned; alleen ontbrekende sleutels/indexen
  aanvullen.
- offline (`--sql`): geen inspectie mogelijk; het oorspronkelijke script wordt
  blind gegenereerd. Dat dekt tests/unit/test_be_mig_013_offline_sql.py en
  volgt de bestaande conventie van dit bestand (offline = blind, defensief
  genoeg voor review-doeleinden).

De eindtoestand is in alle paden identiek aan wat het model eist:
educational_access heeft alleen code_hash String(64) NOT NULL met precies een
unieke sleutel en de composite unique index idx_ea_tenant_code op
(tenant_id, code_hash); study_collections heeft alleen educational_access_id
NOT NULL met FK naar educational_access.id, de model-index
ix_study_collections_educational_access_id en idx_sc_tenant_code op
(tenant_id, educational_access_id). Welke CONSTRAINT-namen daarbij staan
verschilt per pad (kolomdrift's uq_/fk_-namen of dit bestand's _key/_fkey);
dat is bewust -- hernoemen zou kolomdrift's downgrade breken.

Downgrade zet de toestand van VOOR deze migratie terug, en dat is sinds de
herkoppeling de toestand NA kolomdrift: `code` en `access_code` komen terug
met hun sleutels/indexen, terwijl kolomdrift's objecten (code_hash,
educational_access_id, uq_, fk_, ix_) met rust gelaten worden -- kolomdrift's
eigen downgrade ruimt ze op. Daarmee werkt de roundtrip naar base weer.
De downgrade is structureel maar kan verwijderde rijen niet herstellen en is
alleen uitvoerbaar op lege tabellen (anders eerst TRUNCATE; zie downgrade()).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260909_adr029_edu_alignment"
# Herkoppeld 2026-09-18 bij het syncen van upstream/develop (SanskritiSetu.org):
# upstream voegde 20260915_bypass_rol, 20260915_rls_rest en 20260917_kolomdrift toe.
# Door deze migratie onder 20260917_kolomdrift te hangen blijft de keten lineair
# en heeft alembic heads exact 1 head.
down_revision = "20260917_kolomdrift"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _is_offline() -> bool:
    # Offline mode (`alembic ... --sql`): geen live connectie, dus geen
    # inspectie mogelijk; de blinde paden hieronder dekken dat. Detectie via
    # MockConnection -- zelfde patroon als 20260810b_audit_chain_anchors
    # (MigrationContext.is_offline_mode bestaat niet; gemeten 2026-09-24 als
    # AttributeError op alembic 1.13.1).
    import sqlalchemy.engine.mock as mock_mod

    return isinstance(op.get_bind(), mock_mod.MockConnection)


def _kolommen(tabel: str) -> set[str]:
    """Kolomnamen van `tabel` -- alleen ONLINE aanroepen.

    Ruwe SQL op information_schema, niet sa.inspect(op.get_bind()): die crasht op
    een offline dry-run (backend-patterns.md #9) en wordt bewaakt door
    tests/architecture/test_no_sa_inspect_in_migrations.py. Zelfde catalogus-
    patroon als _constraint_bestaat/_index_bestaat hieronder.
    """
    result = op.get_bind().execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": tabel},
    )
    if result is None:
        return set()
    return {rij[0] for rij in result.fetchall()}


def _constraint_bestaat(tabel: str, naam: str) -> bool:
    """Online-only. Geen ::cast naast :bind in dezelfde text() -- SQLAlchemy
    tokeniseert die mix onbetrouwbaar (zie _enum_has_value); daarom een join
    op pg_class.relname."""
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = :t AND c.conname = :n"
        ),
        {"t": tabel, "n": naam},
    )
    return result is not None and result.fetchone() is not None


def _index_bestaat(tabel: str, naam: str) -> bool:
    """Online-only."""
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = :t AND indexname = :n"
        ),
        {"t": tabel, "n": naam},
    )
    return result is not None and result.fetchone() is not None


def _fk_op_kolom(tabel: str, kolom: str) -> str | None:
    """Naam van een FK op `tabel`.`kolom` (welke naam dan ook), of None.

    Online-only. Kolomdrift noemde de FK fk_study_collections_educational_access_id,
    dit bestand study_collections_educational_access_id_fkey; voor "bestaat er
    een FK" is de naam irrelevant.
    """
    result = op.get_bind().execute(
        sa.text(
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = :t AND c.contype = 'f' "
            "AND (SELECT attname FROM pg_attribute "
            "     WHERE attrelid = c.conrelid AND attnum = c.conkey[1]) = :k"
        ),
        {"t": tabel, "k": kolom},
    )
    if result is None:
        return None
    rij = result.fetchone()
    return rij[0] if rij is not None else None


def _unieke_constraints_op_kolom(tabel: str, kolom: str) -> list[str]:
    """Namen van unieke constraints op `tabel`.`kolom` -- online-only."""
    result = op.get_bind().execute(
        sa.text(
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = :t AND c.contype = 'u' "
            "AND (SELECT attname FROM pg_attribute "
            "     WHERE attrelid = c.conrelid AND attnum = c.conkey[1]) = :k"
        ),
        {"t": tabel, "k": kolom},
    )
    if result is None:
        return []
    return [rij[0] for rij in result.fetchall()]


def _enum_has_value(type_name: str, value: str) -> bool:
    # NB: geen ::cast in deze query -- SQLAlchemy text() tokeniseert een mix van
    # :bind en ::cast onbetrouwbaar (laten een letterlijke ':t' naar Postgres
    # gaan; gemeten 2026-09-09 als SyntaxError op een echte database). Join op
    # pg_type.typname i.p.v. enumtypid = :t::regtype.
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = :t AND e.enumlabel = :v"
        ),
        {"t": type_name, "v": value},
    )
    if result is None:
        # Offline mode (`alembic ... --sql`): geen live connectie, blind
        # genereren; de recreatie+case-cast is defensief genoeg.
        return True
    return result.fetchone() is not None


# ----------------------------------------------------------------------------
# educational_access -- twee paden plus een gedeelde "verzeker de eindsleutels"
# ----------------------------------------------------------------------------


def _educational_access_rename_pad() -> None:
    """Het oorspronkelijke pad: `code` hernoemen naar code_hash.

    Correct als code_hash nog niet bestaat (kolomdrift-objecten ontbreken) en
    het enige dat offline (--sql) gegenereerd kan worden -- daar is geen
    inspectie mogelijk. Op een database waar code_hash al bestaat geeft dit
    DuplicateColumn; die toestand vangt `_educational_access_verwijder_code`
    af en komt hier nooit terecht.
    """
    if _is_postgresql():
        # Unnamed unique constraint van 20260824 heet in Postgres
        # educational_access_code_key. Eerst blind IF EXISTS droppen (werkt
        # ook in offline mode); daarna in online mode defensief opzoeken of
        # er onder een afwijkende naam nog een unieke constraint op `code` zit.
        op.execute(
            sa.text(
                "ALTER TABLE educational_access "
                "DROP CONSTRAINT IF EXISTS educational_access_code_key"
            )
        )
        if not _is_offline():
            for naam in _unieke_constraints_op_kolom("educational_access", "code"):
                op.drop_constraint(naam, "educational_access", type_="unique")
    op.drop_index("idx_ea_tenant_code", table_name="educational_access")
    op.alter_column(
        "educational_access",
        "code",
        new_column_name="code_hash",
        type_=sa.String(64),
        existing_type=sa.String(20),
        existing_nullable=False,
    )
    op.create_unique_constraint(
        "educational_access_code_hash_key", "educational_access", ["code_hash"]
    )
    op.create_index(
        "idx_ea_tenant_code",
        "educational_access",
        ["tenant_id", "code_hash"],
        unique=True,
    )


def _educational_access_verwijder_code() -> None:
    """Post-kolomdrift pad: `code` is een plaintext-restant, code_hash bestaat
    al. Renamen zou DuplicateColumn geven -- het restant gaat weg.

    Alleen online aanroepen (inspecteert). De unieke sleutel
    (educational_access_code_key) en de composite index idx_ea_tenant_code op
    (tenant_id, code) uit 20260824 staan op de kolom en gaan expliciet mee weg;
    PostgreSQL zou ze bij DROP COLUMN ook zelf laten vallen, maar expliciet is
    hier leesbaarder dan het impliciete cascade-gedrag.
    """
    op.execute(
        sa.text(
            "ALTER TABLE educational_access "
            "DROP CONSTRAINT IF EXISTS educational_access_code_key"
        )
    )
    for naam in _unieke_constraints_op_kolom("educational_access", "code"):
        op.drop_constraint(naam, "educational_access", type_="unique")
    op.execute(sa.text("DROP INDEX IF EXISTS idx_ea_tenant_code"))
    op.drop_column("educational_access", "code")


def _educational_access_eindsleutels_verzekeren() -> None:
    """Unieke sleutel op code_hash + composite unique index, als ze ontbreken.

    Alleen online aanroepen. Hernoemt bewust NIETS: kolomdrift's
    uq_educational_access_code_hash blijft onder die naam staan omdat
    kolomdrift's downgrade zijn eigen objecten onder zijn eigen namen verwacht.
    """
    if not (
        _constraint_bestaat("educational_access", "uq_educational_access_code_hash")
        or _constraint_bestaat("educational_access", "educational_access_code_hash_key")
    ):
        op.create_unique_constraint(
            "educational_access_code_hash_key", "educational_access", ["code_hash"]
        )
    if not _index_bestaat("educational_access", "idx_ea_tenant_code"):
        op.create_index(
            "idx_ea_tenant_code",
            "educational_access",
            ["tenant_id", "code_hash"],
            unique=True,
        )


# ----------------------------------------------------------------------------
# study_collections -- idem
# ----------------------------------------------------------------------------


def _study_collections_fk_pad() -> None:
    """Het oorspronkelijke pad: access_code eruit, educational_access_id erin.

    Correct als educational_access_id nog niet bestaat; het enige pad dat
    offline gegenereerd kan worden. Post-kolomdrift bestaan de kolom, de FK en
    de model-index al en zou dit pad op DuplicateColumn resp. dubbele index
    lopen -- die toestand vangt de online tak in upgrade() af.
    """
    op.drop_index("idx_sc_tenant_code", table_name="study_collections")
    op.drop_index("ix_study_collections_access_code", table_name="study_collections")
    op.drop_column("study_collections", "access_code")
    op.add_column(
        "study_collections",
        sa.Column(
            "educational_access_id",
            sa.Integer(),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "study_collections_educational_access_id_fkey",
        "study_collections",
        "educational_access",
        ["educational_access_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_study_collections_educational_access_id",
        "study_collections",
        ["educational_access_id"],
    )
    op.create_index(
        "idx_sc_tenant_code",
        "study_collections",
        ["tenant_id", "educational_access_id"],
    )


def _study_collections_online(sc_kolommen: set[str]) -> None:
    """Defensieve online-variant van _study_collections_fk_pad.

    Voert elke stap alleen uit als de bron er is en het doel nog niet;
    kolomdrift's FK en index (onder kolomdrift's namen) blijven staan.
    """
    if "access_code" in sc_kolommen:
        op.execute(sa.text("DROP INDEX IF EXISTS idx_sc_tenant_code"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_study_collections_access_code"))
        op.drop_column("study_collections", "access_code")
    if "educational_access_id" not in sc_kolommen:
        # NOT NULL zonder default: alleen veilig op een lege tabel -- de
        # count-check in upgrade() stap 2 heeft dat al afgedwongen.
        op.add_column(
            "study_collections",
            sa.Column(
                "educational_access_id",
                sa.Integer(),
                nullable=False,
            ),
        )
    if _fk_op_kolom("study_collections", "educational_access_id") is None:
        op.create_foreign_key(
            "study_collections_educational_access_id_fkey",
            "study_collections",
            "educational_access",
            ["educational_access_id"],
            ["id"],
            ondelete="CASCADE",
        )
    if not _index_bestaat("study_collections", "ix_study_collections_educational_access_id"):
        op.create_index(
            "ix_study_collections_educational_access_id",
            "study_collections",
            ["educational_access_id"],
        )
    if not _index_bestaat("study_collections", "idx_sc_tenant_code"):
        op.create_index(
            "idx_sc_tenant_code",
            "study_collections",
            ["tenant_id", "educational_access_id"],
        )


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Dode dubbele enum-waarde 'bounced' verwijderen uit
    #    newsletter_status_enum via type-recreatie (PostgreSQL kan enum-
    #    waarden niet droppen zonder het type opnieuw aan te maken).
    # ------------------------------------------------------------------
    if _is_postgresql() and _enum_has_value("newsletter_status_enum", "bounced"):
        op.execute(sa.text("ALTER TYPE newsletter_status_enum RENAME TO newsletter_status_enum_old"))
        op.execute(
            sa.text(
                "CREATE TYPE newsletter_status_enum AS ENUM "
                "('PENDING_OPT_IN', 'SUBSCRIBED', 'UNSUBSCRIBED', 'BOUNCED')"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE newsletter_subscriptions "
                "ALTER COLUMN status TYPE newsletter_status_enum "
                # Defensief: rijen met de dode lowercase 'bounced' (geldig sinds
                # 20260824) mappen naar 'BOUNCED', anders faalt de cast en rolt de
                # hele migratie terug.
                "USING (CASE WHEN status::text = 'bounced' THEN 'BOUNCED' "
                "ELSE status::text END)::newsletter_status_enum"
            )
        )
        op.execute(sa.text("DROP TYPE newsletter_status_enum_old"))

    # ------------------------------------------------------------------
    # 2. Onbruikbare rest-data verwijderen (zie module-docstring).
    #    EIGENAAR-VEREISTE: deze DELETE's moeten als tabel-eigenaar (of een
    #    rol die RLS bypass't) draaien. Onder niet-eigenaar + RLS kunnen de
    #    DELETE's stille no-ops zijn; de count-checks hieronder maken dat
    #    een harde migratie-fout in plaats van stille corruptie.
    # ------------------------------------------------------------------
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM study_collections"))
    bind.execute(sa.text("DELETE FROM educational_access"))
    # Rowcount-verificatie (alleen met live connectie): onder niet-eigenaar +
    # RLS kunnen de DELETE's stille no-ops zijn; dan faalt de migratie hier
    # hard i.p.v. stil door te gaan met resterende plaintext-codes.
    for table in ("study_collections", "educational_access"):
        result = bind.execute(sa.text(f"SELECT count(*) FROM {table}"))
        if result is None:
            break  # offline mode: geen verificatie mogelijk
        remaining = result.scalar_one()
        if remaining != 0:
            raise RuntimeError(
                f"{table} is na DELETE niet leeg ({remaining} rijen) -- "
                "migratie moet als tabel-eigenaar draaien (RLS-bypass vereist)"
            )

    # ------------------------------------------------------------------
    # 3. educational_access: eindtoestand is code_hash String(64) volgens het
    #    model. Welke actie dat vraagt hangt af van wat er al staat (zie de
    #    module-docstring, "DEFENSIEF sinds 2026-09-24").
    # ------------------------------------------------------------------
    if _is_offline():
        _educational_access_rename_pad()
    else:
        ea_kolommen = _kolommen("educational_access")
        if "code" in ea_kolommen and "code_hash" in ea_kolommen:
            # De werkelijke keten sinds 2026-09-18: kolomdrift voegde
            # code_hash al toe; `code` is het plaintext-restant uit 20260824.
            _educational_access_verwijder_code()
        elif "code" in ea_kolommen:
            # code_hash ontbreekt: kolomdrift-objecten zijn er niet; het
            # oorspronkelijke rename-pad is de juiste transformatie.
            _educational_access_rename_pad()
        # else: alleen code_hash -- al aligned, hier valt niets te doen.
        _educational_access_eindsleutels_verzekeren()

    # ------------------------------------------------------------------
    # 4. study_collections: access_code -> educational_access_id FK volgens
    #    het model (index=True op de kolom + composite idx_sc_tenant_code).
    # ------------------------------------------------------------------
    if _is_offline():
        _study_collections_fk_pad()
    else:
        _study_collections_online(_kolommen("study_collections"))


def downgrade() -> None:
    # Zet de toestand van VOOR deze migratie terug. Sinds de herkoppeling van
    # 2026-09-18 is dat de toestand NA kolomdrift: code_hash,
    # educational_access_id, uq_educational_access_code_hash,
    # fk_study_collections_educational_access_id en
    # ix_study_collections_educational_access_id zijn van kolomdrift en blijven
    # hier bewust staan -- kolomdrift's eigen downgrade verwacht ze onder die
    # namen aan te treffen en ruimt ze zelf op. Alleen wat DEZE migratie
    # weghaalde komt terug: `code` en `access_code` met hun sleutels/indexen.
    #
    # Alleen uitvoerbaar op LEGE tabellen. De upgrade heeft alle rijen uit
    # study_collections / educational_access verwijderd; draait deze downgrade
    # op een gevulde database, draai dan eerst zelf:
    #   TRUNCATE study_collections, educational_access;
    # Reden: access_code en code worden nullable=False toegevoegd zonder
    # default (faalt op elke rij). Verwijderde rijen uit de upgrade zijn
    # onomkeerbaar (plaintext-restanten, nooit door de ORM bruikbaar).

    online = not _is_offline()

    # ------------------------------------------------------------------
    # 4. study_collections: access_code terug (kolomdrift's FK-kolom blijft)
    # ------------------------------------------------------------------
    if not online or _index_bestaat("study_collections", "idx_sc_tenant_code"):
        # idx_sc_tenant_code staat op (tenant_id, educational_access_id) en is
        # van deze migratie; de oude variant op access_code komt hieronder
        # onder dezelfde naam terug.
        op.drop_index("idx_sc_tenant_code", table_name="study_collections")
    if not online or "access_code" not in _kolommen("study_collections"):
        op.add_column(
            "study_collections",
            sa.Column("access_code", sa.String(20), nullable=False),
        )
    if not online or not _index_bestaat("study_collections", "ix_study_collections_access_code"):
        op.create_index(
            "ix_study_collections_access_code", "study_collections", ["access_code"]
        )
    op.create_index(
        "idx_sc_tenant_code", "study_collections", ["tenant_id", "access_code"]
    )

    # ------------------------------------------------------------------
    # 3. educational_access: code String(20) terug (code_hash blijft van
    #    kolomdrift)
    # ------------------------------------------------------------------
    if not online or _index_bestaat("educational_access", "idx_ea_tenant_code"):
        op.drop_index("idx_ea_tenant_code", table_name="educational_access")
    if not online or "code" not in _kolommen("educational_access"):
        op.add_column(
            "educational_access",
            sa.Column("code", sa.String(20), nullable=False),
        )
    if not online or not _constraint_bestaat("educational_access", "educational_access_code_key"):
        op.create_unique_constraint(
            "educational_access_code_key", "educational_access", ["code"]
        )
    op.create_index(
        "idx_ea_tenant_code", "educational_access", ["tenant_id", "code"], unique=True
    )

    # ------------------------------------------------------------------
    # 1. Dode dubbele waarde 'bounced' terugzetten (structureel, geen data)
    # ------------------------------------------------------------------
    if _is_postgresql():
        op.execute(
            sa.text("ALTER TYPE newsletter_status_enum ADD VALUE IF NOT EXISTS 'bounced'")
        )
