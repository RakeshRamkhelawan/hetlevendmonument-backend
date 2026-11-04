"""DATA-001/DB-AUDIT-001 -- agentic-domain tables must be in the LIVE Alembic chain
(Sprint Dag 1 Groep 4, AUDIT-ARCH-2026-07-02).

Previously, the 9 agentic-domain tables (prompt_templates, features, tool_definitions,
prompt_metrics, user_personas, agent_sessions, session_messages, prompt_experiments,
prompt_experiment_variants) existed only in a stale, schema-mismatched migration under
src/alembic/versions/archive/ that was never part of the live chain (confirmed: no live
migration referenced them; tests bootstrapped schema via Base.metadata.create_all(),
bypassing Alembic entirely). Migration 884d744f6aa9 adds them to the live chain.
"""

import ast
import re
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_ALEMBIC_INI = Path("src/alembic.ini")
_NEW_MIGRATION = Path(
    "src/alembic/versions/884d744f6aa9_add_agentic_domain_tables_tenant_hardening.py"
)

_EXPECTED_TABLES = [
    "prompt_templates",
    "features",
    "tool_definitions",
    "prompt_metrics",
    "user_personas",
    "agent_sessions",
    "session_messages",
    "prompt_experiments",
    "prompt_experiment_variants",
]


def test_alembic_chain_has_exactly_one_head() -> None:
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", "src/alembic")
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 alembic head, found {len(heads)}: {heads}"


def test_new_migration_is_the_current_head() -> None:
    """De kop van de migratieketen, expliciet vastgepind.

    Deze test MOET meebewegen met elke nieuwe migratie -- dat is opzet: hij dwingt af dat een
    toegevoegde migratie bewust op de bestaande kop is gezet en niet per ongeluk een tweede tak
    opent. `test_exactly_one_head` vangt de tweede tak; deze vangt een stille HERouting.

    Historie: b2c3d4e5f6a7 -> c3d4e5f6a7b8 (SP-GOV-ARCH-7, agent_governance_contracts)
    -> 20260706_add_agentic_tasks_table (AGENTIC-COPILOT-TAAKBEHEER-2026-07 dag 2)
    -> 20260806_hitl_resolution_note (ADR-036 OP-69: de motivering van de mens bij een
    HITL-beslissing werd gevalideerd en daarna weggegooid)
    -> 20260811_audit_hash_algorithm (ADR-036 OP-120: algoritme-markering per auditregel)
    -> 20260815_hr_skills_tables (ADR-036 OP-26: vaardigheden, functie-eisen en
    beoordelingen -- de piloot kon zonder die drie tabellen geen kloof berekenen)
    -> 20260815_tenant_prana_budget (ADR-036 D3/D7: de twee kolommen die `PranaGuard` al
    sinds maart 2026 leest maar die in geen enkele migratie in de keten stonden)
    -> 20260817_baseline_tabellen (ADR-036 OP-140: de 71 tabellen die de keten niet
    aanmaakte -- een verse database kwam op 120 tabellen terwijl de applicatie er 186
    verwacht)
    -> 20260817_rls_baseline (ADR-005: die 71 tabellen kwamen zonder Row Level Security
    de keten in, terwijl 41 andere migraties dat wel zetten -- Gate 2-review)
    -> 20260817_sched_uniek (Gate 2-review ronde 2: de cross-tenant unieke index op
    user_scheduling_profiles bereikte geen enkele BESTAANDE database, want
    `CREATE INDEX IF NOT EXISTS` is voorwaardelijk op de naam)
    -> 20260818_app_rol (ADR-036 OP-151: de applicatierol `sanskritisetu_app` --
    niet-eigenaar, NOLOGIN, zodat Row Level Security uberhaupt kan gaan werken)
    -> 20260818_rls_expr (ADR-036 OP-151: veertien policies gaven een foutmelding in
    plaats van nul rijen zodra de tenantcontext leeg was)
    -> 20260818_rls_index (ADR-036 OP-161: zes tabellen met een policy misten een index
    met tenant_id vooraan; zonder leidende kolom valt de planner terug op een sequential
    scan zodra de policies actief worden)
    -> 20260822_hr_trainings_tables (BE-AGT-058, Fase 3, vervolg op ADR-036 OP-26:
    trainings-catalogus en medewerker-koppeling, analoog aan 20260815_hr_skills_tables --
    gevonden door Gate 2 (security-reviewer): deze pin bewoog niet automatisch mee en
    stond na de nieuwe migratie ROOD)
    -> 20260824_adr029_portal_v1 (ADR-029 Foundation Portal: content/curatie-tabellen --
    dezelfde pin-onderhoudsplicht als hierboven, nu bijgewerkt na een verse
    `alembic heads`-controle: exact 1 head, down_revision-keten intact, downgrade() geen
    kale `pass`).
    -> fc090c9d7267, GEWEEST EN WEER VERWIJDERD (2026-09-03). Beweerde "vier ontbrekende
    portal-tabellen" (portal_users, magic_link_tokens, takedown_requests,
    newsletter_subscriptions) te vullen. De pin is op 2026-09-02 hierheen bijgewerkt na de
    drie STRUCTURELE controles (1 head, down_revision-keten, downgrade() geen `pass`) --
    maar niet tegen een ECHTE database gedraaid. `alembic upgrade head` tegen een verse
    Postgres (lokaal, poort 5455) faalde met `psycopg2.errors.DuplicateTable: relation
    "portal_users" already exists`, en dezelfde fout trof PR #163's CI-stap "Run migrations".
    Alle vier tabellen bleken kolom-voor-kolom identiek AL te bestaan sinds
    20260524a_add_portal_users_and_magic_links.py / 20260524d_add_takedown_requests.py /
    20260524e_add_newsletter_subscriptions.py -- portal_users' kolommen in fc090c9d7267 waren
    letterlijk de UNIE van 20260524a's basiskolommen en de kolommen die
    20260824_adr029_portal_v1 er via `add_column` bovenop zette. De migratie voegde dus NIETS
    toe; het was een complete dubbeling, ontstaan uit een gap-analyse die de tabellen als
    "ontbrekend" beoordeelde zonder de keten daadwerkelijk uit te voeren. Bestand verwijderd
    (nooit gemerged naar develop, dus veilig); 20260824_adr029_portal_v1 is weer head. LES:
    de drie structurele controles in deze docstring zijn NOODZAKELIJK maar niet VOLDOENDE --
    "bouwt de keten zonder fout" vereist een echte database, niet alleen keten-structuur (zie
    ook OP-148 elders in deze codebase over dezelfde valkuil bij offline dry-runs).
    -> 20260715_add_prana_economy_tables -> 20260716_backfill_prana_budgets (samenvoegen van
    `iter/prana-economy`, Cluster F, 2026-09-08). Deze twee migraties bestonden al op de
    branch maar wezen nog op `20260706_add_agentic_tasks_table` (de kop van juli, toen de
    branch werd afgesplitst) -- `alembic heads` toonde er 2 en `upgrade head --sql` faalde met
    "Multiple head revisions are present". Herkoppeld op `20260824_adr029_portal_v1`. Dit keer
    WEL tegen een echte database gedraaid (niet alleen de drie structurele controles, zie de
    les hierboven): `docker start sanskritisetu_test_db`, `alembic_version` teruggezet naar
    `20260824_adr029_portal_v1` (de vorige stand van dit bestand was door een mislukte eigen
    `stamp`-aanroep gecorrumpeerd tot de letterlijke string "head", geen echte revisie-id --
    zelf ontdekt met een rechtstreekse SQL-query, niet aangenomen), en toen `alembic upgrade
    head` opnieuw gedraaid: `prana_department_budget` en `prana_transaction` ontstaan, backfill
    gaf 20 rijen (10 kanonieke departementen x 2 tenants) met `total_prana=10000`/
    `spent_prana=0` per rij, exact ADR-021's default.
    -> adr036_op81_requested_by (ADR-036 OP-81: `hitl_requests.requested_by_user_id`,
    zodat de zelf-goedkeuringscheck op het gatekeeper-pad de OORSPRONKELIJKE menselijke
    opdrachtgever kan vergelijken met de goedkeurder, niet alleen de agent die namens hem
    handelde). Deze pin zelf is de fout uit deze docstring, opnieuw opgetreden: de
    migratie is toegevoegd in commit 5a0f781c op de toen nog losstaande branch
    `iter/op81-hertoets` (2026-09-01) zonder deze pin bij te werken, en dat bleef zo
    staan door de hele reviewronde heen tot de merge naar develop (7bbc230e,
    2026-09-09). De daaropvolgende OP-40-merge (75ed2e6b) raakte dit bestand niet en
    liet de rode pin dus ook staan. CI stond daardoor twee pushes achter elkaar rood op
    exact deze assertie (runs 34393183853 en 34400271052, "Full unit tests" ->
    AssertionError). Structureel gecontroleerd voor deze fix: `alembic heads` geeft
    precies 1 kop (`adr036_op81_requested_by`), de down_revision-keten is intact naar
    `20260716_backfill_prana_budgets`, en `downgrade()` verwijdert kolom en index (geen
    "Run migrations"-stap op deze exacte migratieketen, dus dit is niet alleen de
    offline structurele controle uit de les hierboven.
    -> 20260915_bypass_rol -> 20260915_rls_rest (ADR-036 OP-154 stap 1 en OP-155: de rol
    `sanskritisetu_bypass` voor de opzoeking voor het inloggen, en 29 afschermingsregels
    op de resterende tabellen met een `tenant_id`).
    -> 20260917_kolomdrift (ADR-036 OP-249: de 35 modelkolommen over tien tabellen die
    nooit een migratie kregen, waaronder `tenants.domain` -- dat gaf op staging een 500 bij
    registreren -- en `tenants.stripe_customer_id`, dat sinds 2025-12-23 in het model stond
    en in geen enkele migratie). Tegen een ECHTE database getest: upgrade/downgrade/upgrade,
    een bestaande tenant-rij overleefde de drie NOT NULL-quota via een tijdelijke default,
    en met een rij in `domain_packs` faalt de migratie LUID met `NotNullViolation` op kolom
    `department` -- fail-secure in plaats van een verzonnen sentinel.
    Tak A (ADR-029, dit repo):
    -> 20260909_adr029_edu_alignment (ADR-029 edu-alignment, BE-MIG-013).
    -> 20260910_adr029_sprint_c_datamodel (ADR-029 Sprint C datamodel, BE-MIG-014).
    -> 20260915_adr029_audit_hardening (ADR-029 audit hardening RLS, contact & donaties).
    Tak B (upstream sync, ADR-036/LLM):
    -> 20260920_tenant_llm (BE-LLM-003, fase 2a: `tenant_llm_providers` plus de kolom
    `tenants.externe_providers_toegestaan`, zodat een klant zijn eigen LLM-eindpunt en sleutel
    kan laten inrichten).
    -> 20260924_merge_adr029_tenant_llm_heads (sync-merge: de twee takken die beide op
    20260917_kolomdrift voortbouwen -- de ADR-029-portal-tak en de upstream tenant-LLM-tak --
    lopen hier weer samen tot een kop; kale merge-migratie, geen schema-wijziging).
    Tak B liep bij upstream door (ADR-036/ADR-039, sync 2026-10-07):
    -> 20261004_user_roles_rls (OP-190: RLS-policy op `user_roles`).
    -> 20261005_receivables_rls -> 20261006_outgoing_messages_rls -> 20261006_receivables_checks
    (debiteurenagent dag 1 en 2). Dag 1 zette zijn migratie erop zonder deze pin bij te werken;
    gemeten 2026-10-05 stond hij op `fcdbdc7f` daardoor rood. Bijgewerkt in DEZELFDE commit als
    de twee dag-2-migraties. De drie controles: `alembic heads` geeft een kop
    (`20261006_receivables_checks`), de keten is intact (elke migratie is de enige met haar
    `down_revision`), en beide `downgrade()`s doen echt iets (tabel weg, resp. twee CHECKs weg).
    Tegen een wegwerpdatabase (`wegwerp_deb_dag2`, netwerkpoort 5455): upgrade head, twee keer
    downgrade -1 en weer upgrade head, met `to_regclass`, `pg_policies` en `pg_constraint`.
    -> 20261007_vier_ogen_bestaande_tenants (ADR-039). Die commit bewoog de pin niet mee;
    bijgewerkt 2026-10-05. De drie controles: `alembic heads` geeft een kop
    (`20261007_vier_ogen_bestaande_tenants`), de keten is intact (zij is de enige met
    `down_revision = 20261006_receivables_checks`), en `downgrade()` is geen kale `pass` (haalt
    de gemerkte standaard per tenant weer weg). Niet tegen een echte database gedraaid.
    -> 20261008_debiteuren_verzenden_en_opvolgen (debiteuren Keten B dag 1). Pin bijgewerkt in
    DEZELFDE commit als de migratie. De drie controles: `alembic heads` geeft een kop, de keten is
    intact (enige met `down_revision = 20261007_vier_ogen_bestaande_tenants`), `downgrade()` is
    geen kale `pass`. Tegen een echte database: zie de commitboodschap.
    -> 20261009_user_roles_tenant_id (OP-190 deel 2). Bijgewerkt 2026-10-09 na de volledige
    testronde op de samenvoeging. De drie controles: `alembic heads` geeft een kop, de keten is
    intact (enige met `down_revision = 20261008_debiteuren_verzenden_en_opvolgen`) en
    `downgrade()` is geen kale `pass` (haalt trigger, functie, twee sleutels, unieke sleutel en
    kolom weg). Tegen de wegwerpdatabase op netwerkpoort 5455: upgrade, downgrade -1, upgrade.
    -> 20261010_roi_tabellen (ROI eerlijk gemeten). Pin bijgewerkt in DEZELFDE commit als de migratie.
    `alembic heads` geeft een kop, de keten is intact (enige met `down_revision =
    20261009_user_roles_tenant_id`) en `downgrade()` is geen kale `pass` (laat precies de twee
    nieuwe tabellen vallen). Tegen een wegwerpdatabase op poort 5455: upgrade, downgrade -1,
    upgrade, `alembic check` zonder drift.
    -> 20261011_training_proposals (HR-pilot dag 2: opleidingsvoorstel als rij). Pin bijgewerkt in
    DEZELFDE commit als de migratie hoorde te gebeuren; dat is bij de samenvoeging gemist. Enige
    met `down_revision = 20261010_roi_tabellen`, `downgrade()` laat precies die ene tabel vallen.
    -> 20261012_hr_deadlines (HR-pilot dag 3: termijnen). Enige met `down_revision =
    20261011_training_proposals`; `downgrade()` laat precies die ene tabel vallen. Beide tegen een
    wegwerpdatabase op poort 5455: upgrade, downgrade -1, upgrade.
    -> 20261014_pack_activations (pakket aanzetten dag 1: welk pakket staat voor welke klant aan).
    Enige met `down_revision = 20261012_audit_geen_tenant_fk`; `downgrade()` laat precies die ene
    tabel vallen. Tegen een wegwerpdatabase op poort 5455: upgrade (tabel, RLS aan, policy), downgrade
    -1 (tabel weg, versie terug), upgrade; `alembic check` noemt de tabel niet.
    -> 20261020_tenant_noodstop (noodstop per klant, ADR-036 OP-03). Ronde 4: staat NA
    `20261020_tenant_ap_verbindingen` (`down_revision` daarop gezet bij het samenvoegen met
    `origin/develop` `d054a114`; beide hingen aan `20261014_pack_activations` en gaven twee koppen);
    `downgrade()` laat precies die ene tabel vallen. Tegen een
    wegwerpdatabase (niet 5455): upgrade (tabel, RLS aan, policy), downgrade -1, upgrade. De pin is
    in ronde 3 bijgewerkt: ronde 1 voegde de migratie toe en liet deze pin ongewijzigd.
    -> 20261020_tenant_ap_verbindingen (ActivePieces per klant dag 2: het adres en de inloggegevens
    van de eigen ActivePieces per tenant, het wachtwoord versleuteld). Pin bijgewerkt op 2026-10-22,
    nadat de pre-push-ronde op de samenvoeging (`ddcccdfe`) hem rood meldde: de migratie kwam in
    `93b6b2b6`/`9b0a1ae5` zonder deze pin te verplaatsen. De drie controles, gemeten op `ddcccdfe`:
    `alembic heads` geeft precies een kop (`20261020_tenant_ap_verbindingen`), de keten is intact
    (zij is de enige migratie met `down_revision = 20261014_pack_activations`) en `downgrade()` is
    geen kale `pass` (haalt de twee indexen en de tabel weg; de policy en de unieke sleutels gaan
    met de tabel mee). De migratie is getrackt (`git ls-files`). Tegen een wegwerpdatabase op poort
    5455 gedraaid in `tests/migrations/test_tenant_ap_verbindingen_migratie.py`: upgrade, RLS aan,
    downgrade, upgrade.
    -> 20261023_schemadrift_schadelijk (schemadrift: `tenants.slug` naar 100 tekens, NOT NULL laten
    vallen op drie kolommen die het model niet kent). Pin bijgewerkt op 2026-10-24, in dezelfde
    commitreeks als de migratie, nadat de volledige ronde hem rood meldde. De drie controles:
    `alembic heads` geeft precies een kop, de keten is intact (enige migratie met
    `down_revision = 20261020_tenant_ap_verbindingen`) en `downgrade()` is geen kale `pass` (zet de
    kolommen terug en weigert met een melding als dat data zou kosten). De migratie is getrackt.
    Tegen een wegwerpdatabase gedraaid in
    `tests/integration/database/test_schemadrift_schadelijke_gevallen.py`.
    -> 20261024_payables_rls (crediteuren dag 1: `suppliers` en `payables`, beide met RLS en een samengestelde sleutel).
    Pin bijgewerkt in DEZELFDE commit als de migratie. De drie controles: `alembic heads` geeft precies een kop
    (`20261024_payables_rls`), de keten is intact (zij hangt aan 20261023_schemadrift_schadelijk) en `downgrade()` is geen kale `pass` (laat precies die twee tabellen vallen, eerst
    `payables`). Tegen een wegwerpdatabase: `tests/migrations/test_payables_migratie.py` (upgrade, RLS aan, downgrade, upgrade).
    -> 20261020_tenant_noodstop (opnieuw de kop). `down_revision` is op 2026-10-24 van
    `20261020_tenant_ap_verbindingen` naar `20261024_payables_rls` gezet bij het samenvoegen met
    `ce0e395a` (dat `origin/develop` `69f433cc` en `iter/schemadrift` `b10b20eb` bevat); anders gaf de
    samenvoeging twee koppen. Interlock 1: alleen de VOLGORDE, de tabel en `downgrade()` zijn
    ongewijzigd. De drie controles: `alembic heads` geeft precies een kop, de keten is intact (enige
    met `down_revision = 20261024_payables_rls`) en `downgrade()` is geen kale `pass`.
    -> 20261024_audit_leesregel (ADR-036 OP-246: RLS op `audit_logs`, lezen per klant) -> 20261025_audit_anonimiseer_functie
    (de anonimiseerfunctie voor auditregels). Rehang 2026-10-25: `20261024_audit_leesregel` had
    `down_revision = 20261020_tenant_ap_verbindingen` en gaf daarmee een tweede tak naast
    `20261020_tenant_noodstop`; die staat nu op `20261020_tenant_noodstop`. De rechte lijn is:
    20261020_tenant_ap_verbindingen -> 20261023_schemadrift_schadelijk -> 20261024_payables_rls ->
    20261020_tenant_noodstop -> 20261024_audit_leesregel -> 20261025_audit_anonimiseer_functie. Alleen de
    VOLGORDE is aangepast (interlock 1), de tabellen en `downgrade()` zijn ongewijzigd. De drie controles:
    `alembic heads` geeft precies een kop (`20261025_audit_anonimiseer_functie`), de keten is intact en
    `downgrade()` is geen kale `pass`.
    -> 20261026_user_roles_tenant_index (alleen toevoegend: een index op `user_roles (tenant_id, user_id)`, de enige RLS-tabel
    zonder leidende tenantindex; `downgrade()` haalt alleen die index weg). Nieuwe kop; de keten blijft een rechte lijn.
    -> 20261008_sync_merge_adr029_upstream_heads (sync-merge 2026-10-07: onze kop
    20260924_merge_adr029_tenant_llm_heads en upstreams kop
    20261007_vier_ogen_bestaande_tenants lopen hier samen tot een kop; kale
    merge-migratie, geen schema-wijziging; beide takken delen 20260917_kolomdrift en
    20260920_tenant_llm als voorouder, dus er is geen schema-overlap).
    -> 20261101_sync_merge_adr029_upstream_heads (sync-merge 2026-11-01: onze kop
    20261008_sync_merge_adr029_upstream_heads en upstreams kop 20261026_user_roles_tenant_index
    lopen hier samen tot een kop; kale merge-migratie, geen schema-wijziging. Onze tak heeft
    sinds 20261008 geen eigen migratie, dus er is geen schema-overlap).
    -> 20261102_adr029_archief_exports (BE-EP-054: tabel foundation_archive_exports voor de
    BagIt-archiefexport, op de sync-merge-kop van 2026-11-01)
    -> 20261103_adr029_docentenomgeving (BE-EP-055: tabellen voor docentaanvragen, lessen per
    klas en leerlingantwoorden, plus twee nullable kolommen op study_collections; puur
    toevoegend, met RLS)
    -> 20261103b_adr029_content_bestanden (BE-EP-057: tabel foundation_content_bestanden
    voor extra bestanden per verhaal; puur toevoegend, met RLS)
    """
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", "src/alembic")
    script = ScriptDirectory.from_config(config)
    (head,) = script.get_heads()
    assert head == "20261103b_adr029_content_bestanden", (
        f"Expected 20261103b_adr029_content_bestanden to be the current head, found {head} -- is er "
        "een nieuwere migratie bovenop gezet zonder deze test bij te werken, of is er een "
        "tweede tak ontstaan? "
        "CONTROLEER EERST OF DIE NIEUWERE MIGRATIE GETRACKT IS, met "
        "`git status --short src/alembic/versions/`. Is hij ONGETRACKT, dan is deze failure een "
        "LOKAAL artefact van ongecommit werk en staat CI GROEN -- die doet een verse checkout en "
        "ziet dat bestand niet. De pin dan bijwerken BREEKT CI, want daar is de oude migratie "
        "nog de head. Gemeten 2026-09-09: deze exacte fout gebeurde LIVE op develop, niet alleen "
        "in een hypothetische worktree -- de OP-81-mergecommit voegde de migratie toe maar liet "
        "deze pin ongewijzigd, en twee opeenvolgende CI-runs op develop stonden daardoor rood. "
        "De pin hoort in DEZELFDE commit mee te bewegen als de migratie zelf, na de drie "
        "controles uit de docstring hierboven: exact 1 head, down_revision-keten intact, en "
        "downgrade() geen kale pass."
    )


def _raw_sql_table_ddl(source: str) -> dict[str, str]:
    """Extract 'CREATE TABLE IF NOT EXISTS <name> (...)' blocks from op.execute()
    raw-SQL string literals (backend-patterns.md #9: migrations use raw SQL, not
    sa.inspect()/op.create_table(), to stay offline-dry-run-safe)."""
    ddl_by_table: dict[str, str] = {}
    for match in re.finditer(
        r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\s*\)",
        source,
        re.DOTALL,
    ):
        ddl_by_table[match.group(1)] = match.group(2)
    return ddl_by_table


def test_new_migration_creates_all_nine_agentic_tables() -> None:
    """The live migration file must create all 9 tables (source of truth:
    src/domains/agentic/models.py) via raw SQL, not depend on the archived
    migration or on sa.inspect()-based op.create_table() (offline-dry-run-unsafe)."""
    assert _NEW_MIGRATION.exists(), f"{_NEW_MIGRATION} not found"
    source = _NEW_MIGRATION.read_text(encoding="utf-8")

    created_tables = set(_raw_sql_table_ddl(source))
    missing = set(_EXPECTED_TABLES) - created_tables
    assert not missing, f"Migration does not create expected tables: {missing}"


def test_new_migration_does_not_import_from_archive() -> None:
    """Checks actual import statements, not prose -- the migration's own docstring
    legitimately mentions "archive" when explaining why it exists."""
    tree = ast.parse(_NEW_MIGRATION.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        module = None
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
        elif isinstance(node, ast.Import):
            module = ",".join(alias.name for alias in node.names)
        if module and "archive" in module:
            raise AssertionError(
                f"Migration imports from archive/: {module} -- that migration's schema "
                "no longer matches src/domains/agentic/models.py."
            )


def test_new_migration_creates_tenant_id_not_null() -> None:
    """Every tenant-scoped table's tenant_id column must be declared NOT NULL in the
    raw SQL DDL (prompt_experiment_variants has no tenant_id column by design)."""
    source = _NEW_MIGRATION.read_text(encoding="utf-8")
    tenant_scoped_tables = set(_EXPECTED_TABLES) - {"prompt_experiment_variants"}
    ddl_by_table = _raw_sql_table_ddl(source)

    violations = []
    for table_name in tenant_scoped_tables:
        ddl = ddl_by_table.get(table_name, "")
        tenant_id_line = next((line for line in ddl.splitlines() if "tenant_id" in line), "")
        if "NOT NULL" not in tenant_id_line:
            violations.append(table_name)

    assert not violations, f"tenant_id is not created NOT NULL for: {violations}"
