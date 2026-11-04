"""De 35 modelkolommen die nooit een migratie kregen (ADR-036 OP-249).

Revision ID: 20260917_kolomdrift
Revises: 20260915_rls_rest
Create Date: 2026-09-17

WAT HIER MIS WAS
----------------
Het ORM-model en de migratieketen zijn uit elkaar gelopen: VIJFENDERTIG kolommen over
tien tabellen staan wel in `Base.metadata` en worden door geen enkele migratie
aangemaakt. Gemeten 2026-09-17 op een verse keten (head `20260915_rls_rest`) en
onafhankelijk op de staging-database: hetzelfde beeld, dus het gat zit in de MIGRATIES
en niet in een omgeving.

Het is oud. `tenants.stripe_customer_id` staat sinds 2025-12-23 in het model (commit
1c5b96ef) en in geen enkele migratie -- negen maanden. Zichtbaar werd het pas op
2026-09-17, toen registreren op staging een 500 gaf:

    sqlalchemy.exc.ProgrammingError: column tenants.domain does not exist

Dat is de faalvorm: elke query die het VOLLEDIGE model selecteert breekt, ongeacht of
die ene kolom gebruikt wordt. Zestienduizend groene tests zagen het niet, omdat de
unittests hun schema met `Base.metadata.create_all` bouwen en het model dus per
definitie terugzien.

WAAROM TOEVOEGEN EN NIET UIT HET MODEL HALEN
--------------------------------------------
Voor elke kolom zijn er twee geldige uitkomsten: een migratie schrijven, of de kolom uit
het model halen omdat hij dood is. Die tweede is hier NIET gekozen, en dat is een besluit
met een reden en geen gemak.

Voor `tenants` is het aantoonbaar de verkeerde keuze: `api/v1/tenant_management/
crud_router.py` declareert `country_code`, `primary_currency`, `primary_locale`,
`primary_timezone`, `max_users`, `max_agents` en `max_storage_gb` als velden van zijn
eigen verzoek- en antwoordmodellen (regels 76-140). Die kolommen uit het model halen
breekt een API-contract dat de frontend gebruikt (`frontend/src/pages/Settings.tsx`).

Voor de overige negen tabellen is niet per kolom bewezen dat ze gebruikt worden. Ze
toevoegen is daar de VEILIGE kant van de twijfel: een kolom die niemand leest kost een
lege kolom, terwijl een kolom die wel gelezen wordt en ontbreekt de applicatie breekt --
precies zoals `tenants.domain` deed. Blijkt een kolom later aantoonbaar dood, dan is hem
alsnog verwijderen een eigen, kleine wijziging met een eigen bewijs.

DE NOT NULL-KOLOMMEN, EN WAAROM DAAR NIETS WORDT VERZONNEN
-----------------------------------------------------------
Elf van de 35 zijn NOT NULL zonder server-default. Een NOT NULL-kolom toevoegen aan een
tabel MET rijen kan niet zonder een waarde, en een waarde verzinnen is precies de
sentinel-oplossing die dit project eerder duur betaald heeft.

Daarom eerst geteld, op 2026-09-17, op drie plekken (lokale dev op 5435, testdatabase op
5455, en de staging-database als `ssadmin`):

    tenants                    2 / 2 / 1 rijen
    pack_usage_aggregates      0 / 0 / 0
    domain_packs               0 / 0 / 0
    agent_configs              0 / 0 / 0
    audit_report_jobs          0 / 0 / 0
    companies                  0 / 0 / 0
    educational_access         0 / 0 / 0
    study_collections          0 / 0 / 0
    user_roles                 2 / 2 / 0

Gevolg, per geval:

- `tenants` HEEFT rijen, en `max_users`/`max_agents`/`max_storage_gb` zijn NOT NULL. Die
  krijgen tijdelijk een server-default met de waarden die dit project zelf al hanteert --
  10, 50 en 5, letterlijk uit `src/core/database/seed.py:181-187` en uit de
  Field-defaults in `crud_router.py:76-78`. Geen verzonnen getal maar de bestaande
  projectwaarde. Daarna wordt de default weer weggehaald, zodat het model de enige bron
  blijft.
- Alle andere NOT NULL-kolommen zitten in LEGE tabellen en worden direct NOT NULL
  toegevoegd, ZONDER default. Draait deze migratie ooit tegen een omgeving waar zo'n
  tabel wel rijen heeft, dan FAALT hij luid en moet een mens beslissen wat de waarde
  hoort te zijn. Dat is bewust: fail-secure boven een stilzwijgende sentinel. Bij
  `educational_access.code_hash` is dat extra belangrijk -- die kolom is UNIEK, dus een
  constante sentinel zou bij meer dan een rij hoe dan ook stukgaan.

WAT DEZE MIGRATIE NIET DOET
---------------------------
Alleen ONTBREKENDE kolommen. `alembic check` meldde eerder ruim 500 verschillen tussen
model en keten; het overgrote deel daarvan zijn typeverschillen, indexen en
server-defaults op kolommen die WEL bestaan. Dat is een andere bevinding met een andere
meting, en die blijft open onder OP-249. De bewaker die vandaag is toegevoegd
(`test_the_chain_builds_the_whole_schema.py`) dekt de kolom-AANWEZIGHEID, en die is na
deze migratie compleet -- de uitzonderingslijst hoort er leeg uit te komen.

DOWNGRADE
---------
Verwijdert exact dezelfde 35 kolommen, plus de indexen en unieke sleutels die hier zijn
aangemaakt. Omgekeerde volgorde, zodat een index nooit een kolom overleeft.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260917_kolomdrift"
down_revision = "20260915_rls_rest"
branch_labels = None
depends_on = None


# (tabel, kolom, type, nullable, server_default)
#
# Exact overgenomen uit `Base.metadata` op 2026-09-17; geen enkele waarde is hier bedacht.
# De drie `tenants`-quota krijgen een TIJDELIJKE default (zie de docstring); die wordt
# onderaan `upgrade()` weer weggehaald.
_KOLOMMEN: list[tuple[str, str, sa.types.TypeEngine, bool, str | None]] = [
    # -- tenants ------------------------------------------------------------------
    ("tenants", "country_code", sa.String(length=2), True, None),
    ("tenants", "domain", sa.String(length=255), True, None),
    ("tenants", "industry", sa.String(length=100), True, None),
    ("tenants", "max_agents", sa.Integer(), False, "50"),
    ("tenants", "max_storage_gb", sa.Integer(), False, "5"),
    ("tenants", "max_users", sa.Integer(), False, "10"),
    ("tenants", "metadata", sa.JSON(), True, None),
    ("tenants", "primary_currency", sa.String(length=3), True, "'USD'"),
    ("tenants", "primary_locale", sa.String(length=10), True, "'en_US'"),
    ("tenants", "primary_timezone", sa.String(length=50), True, "'UTC'"),
    ("tenants", "region", sa.String(length=20), True, "'eu-west'"),
    ("tenants", "settings", sa.JSON(), True, None),
    ("tenants", "stripe_customer_id", sa.String(length=100), True, None),
    ("tenants", "supported_locales", sa.JSON(), True, None),
    # -- pack_usage_aggregates (leeg op alle drie de gemeten omgevingen) -----------
    ("pack_usage_aggregates", "adoption_rate_pct", sa.Float(), False, None),
    ("pack_usage_aggregates", "avg_usage_per_company", sa.Float(), False, None),
    ("pack_usage_aggregates", "company_type", sa.String(length=20), False, None),
    ("pack_usage_aggregates", "daily_activations", sa.Integer(), False, None),
    ("pack_usage_aggregates", "employee_bucket", sa.String(length=20), False, None),
    ("pack_usage_aggregates", "k_anonymity_met", sa.Boolean(), False, None),
    ("pack_usage_aggregates", "pack_name", sa.String(length=200), True, None),
    ("pack_usage_aggregates", "total_companies", sa.Integer(), False, None),
    # -- domain_packs (leeg) -------------------------------------------------------
    ("domain_packs", "department", sa.String(length=255), False, None),
    ("domain_packs", "error_count", sa.Integer(), False, None),
    ("domain_packs", "health_status", sa.String(length=50), False, None),
    ("domain_packs", "last_health_check", sa.DateTime(timezone=True), True, None),
    ("domain_packs", "last_used_at", sa.DateTime(timezone=True), True, None),
    ("domain_packs", "status", sa.String(length=50), False, None),
    ("domain_packs", "usage_count", sa.Integer(), False, None),
    # -- losse kolommen ------------------------------------------------------------
    ("agent_configs", "department_user_id", sa.Integer(), True, None),
    ("audit_report_jobs", "result_blob", sa.LargeBinary(), True, None),
    ("companies", "template_id", postgresql.UUID(as_uuid=True), True, None),
    ("educational_access", "code_hash", sa.String(length=64), False, None),
    ("study_collections", "educational_access_id", sa.Integer(), False, None),
    ("user_roles", "created_at", sa.DateTime(timezone=True), True, "now()"),
]

# (naam, tabel, kolommen, uniek) -- exact de indexen die het model op deze kolommen zet.
_INDEXEN: list[tuple[str, str, list[str], bool]] = [
    ("ix_tenants_stripe_customer_id", "tenants", ["stripe_customer_id"], True),
    ("ix_pack_usage_aggregates_company_type", "pack_usage_aggregates", ["company_type"], False),
    (
        "ix_pack_usage_aggregates_employee_bucket",
        "pack_usage_aggregates",
        ["employee_bucket"],
        False,
    ),
    ("ix_domain_packs_health_status", "domain_packs", ["health_status"], False),
    ("ix_domain_packs_status", "domain_packs", ["status"], False),
    (
        "ix_study_collections_educational_access_id",
        "study_collections",
        ["educational_access_id"],
        False,
    ),
]

# (naam, tabel, kolommen) -- unieke sleutels die het model eist zonder eigen index.
_UNIEK: list[tuple[str, str, list[str]]] = [
    ("uq_tenants_domain", "tenants", ["domain"]),
    ("uq_educational_access_code_hash", "educational_access", ["code_hash"]),
]

# (naam, bron, kolom, doeltabel, doelkolom)
_FOREIGN_KEYS: list[tuple[str, str, str, str, str]] = [
    ("fk_agent_configs_department_user_id", "agent_configs", "department_user_id", "users", "id"),
    ("fk_companies_template_id", "companies", "template_id", "company_templates", "id"),
    (
        "fk_study_collections_educational_access_id",
        "study_collections",
        "educational_access_id",
        "educational_access",
        "id",
    ),
]

#: De drie kolommen waarvan de default ALLEEN bedoeld is om bestaande rijen te vullen.
#: Na het toevoegen gaat hij er weer af, zodat het model de enige bron blijft.
_TIJDELIJKE_DEFAULTS = [
    ("tenants", "max_agents"),
    ("tenants", "max_storage_gb"),
    ("tenants", "max_users"),
]


def upgrade() -> None:
    for tabel, kolom, kolomtype, nullable, default in _KOLOMMEN:
        op.add_column(
            tabel,
            sa.Column(
                kolom,
                kolomtype,
                nullable=nullable,
                server_default=sa.text(default) if default is not None else None,
            ),
        )

    for naam, tabel, kolommen, uniek in _INDEXEN:
        op.create_index(naam, tabel, kolommen, unique=uniek)

    for naam, tabel, kolommen in _UNIEK:
        op.create_unique_constraint(naam, tabel, kolommen)

    for naam, bron, kolom, doeltabel, doelkolom in _FOREIGN_KEYS:
        op.create_foreign_key(naam, bron, doeltabel, [kolom], [doelkolom])

    # De tijdelijke defaults er weer af: ze waren er om de bestaande tenant-rijen een
    # waarde te geven, niet om voortaan stil nieuwe rijen te vullen.
    for tabel, kolom in _TIJDELIJKE_DEFAULTS:
        op.alter_column(tabel, kolom, server_default=None)


def downgrade() -> None:
    for naam, bron, _kolom, _doeltabel, _doelkolom in reversed(_FOREIGN_KEYS):
        op.drop_constraint(naam, bron, type_="foreignkey")

    for naam, tabel, _kolommen in reversed(_UNIEK):
        op.drop_constraint(naam, tabel, type_="unique")

    for naam, tabel, _kolommen, _uniek in reversed(_INDEXEN):
        op.drop_index(naam, table_name=tabel)

    for tabel, kolom, _kolomtype, _nullable, _default in reversed(_KOLOMMEN):
        op.drop_column(tabel, kolom)
