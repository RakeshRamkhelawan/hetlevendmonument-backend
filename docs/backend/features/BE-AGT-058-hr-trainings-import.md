# BE-AGT-058 -- HR-skills/trainings data-import + trainingscatalogus (Fase 3, dag 1-4)

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-058 (dag 1), BE-AGT-059 (dag 2), BE-AGT-060 (dag 3), BE-AGT-061 (dag 4) |
| Datum | 2026-08-22 (dag 1-3), 2026-08-24 (dag 4) |
| ADR | ADR-033 (3-laags router), ADR-036 OP-26 (het gat dat deze sprint dicht) |
| Sprint | Fase 3 -- HR data-import & kennislaag, dag 1-4 van 4 |
| Scope | Datamodel + migratie (dag 1), repository-upserts (dag 2), API-laag (dag 3), integratiebewijs (dag 4) |

---

## 1. Probleem

`analyze_skill_gap` (`src/core/tool_broker/hr_registry.py`, sinds 2026-08-15) leest
`skills`/`role_required_skills`/`employee_skills` en berekent per rol een
vaardighedenkloof. Een fact-check-sessie (2026-08-22) op een extern statusrapport legde
bloot dat dit ALTIJD een leeg resultaat gaf voor een echte tenant: de drie tabellen
bestonden, maar er was geen enkel pad om er data in te krijgen. Deze sprint dicht precies
dat gat -- een echt, tenant-gescoopt import-pad, plus een `trainings`-catalogus +
`employee_trainings`-koppeltabel voor een toekomstige cursuskoppeling.

## 2. Dag 1 -- datamodel + migratie (BE-AGT-058, commit `c5bbe67d`)

`src/core/models/hr_training_models.py` (nieuw): `Training` (`trainings`: id, tenant_id
NOT NULL CASCADE, name, description, skill_id FK `skills.id` ON DELETE SET NULL,
created_at; unique `(tenant_id, name)`) en `EmployeeTraining` (`employee_trainings`: id,
tenant_id NOT NULL CASCADE, user_id FK `users.id` CASCADE, training_id FK `trainings.id`
CASCADE, status CHECK IN `('assigned', 'in_progress', 'completed')`, completed_at,
created_at; unique `(tenant_id, user_id, training_id)`). Migratie
`20260822_hr_trainings_tables.py`, `down_revision = "20260818_rls_index"`.

**Bewust NIET gefixt, gedocumenteerd en bewaakt met een gedateerde uitzondering +
staleness-test:** ADR-005 par. 5 (composite `(tenant_id, id)` FK's) geldt niet voor deze
twee nieuwe tabellen -- ze volgen het BESTAANDE single-FK-patroon van de drie zusje-
tabellen uit 2026-08-15, na expliciete afweging met Rakesh. Repo-brede fix is een
toekomstige Hardening Sprint. Bewaakt door
`tests/architecture/test_hr_junction_tables_composite_fk_gap.py` (5 tests, mutatie-getest
in beide richtingen).

## 3. Dag 2 -- repositories (BE-AGT-059, commit `31c048d7`)

`HRSkillsImportRepository` (`upsert_skills`, `upsert_role_requirements`,
`upsert_employee_assessments`, `list_skills`) en `HRTrainingsRepository`
(`upsert_trainings`, `upsert_employee_trainings`, `list_trainings`). Upsert i.p.v.
reject-on-duplicate: 1 gebundelde SELECT per batch (geen N+1, empirisch bewezen via een
SQLAlchemy `before_cursor_execute`-event), dan `add()`/attribuutwijziging, 1 `flush()`.
Rijtypen leven op de repository-laag (`hr_import_types.py`), niet de API-laag -- de
correcte ADR-033-afhankelijkheidsrichting (API mag van data afhangen, niet omgekeerd).

Gate 2 vond en fixte: 3 van de 5 upsert-methoden laadden de VOLLEDIGE tenant-tabel voor hun
"bestaat dit al"-lookup i.p.v. gescoopt op de rol-/skill-/gebruiker-ids van de batch;
ontbrekende Python-lengtecontrole naast de DB-`VARCHAR`-grens (SQLite handhaaft dat niet);
`list_skills`/`list_trainings` zonder bovengrens op `limit`.

## 4. Dag 3 -- API-laag (BE-AGT-060, commits `7eb8da8e`, `7097ce6c`, `b0b23c18`)

Vier endpoints, ADR-033 3-laags (`router.py` -> `dependencies.py`-facade ->
`registries/hr.py`), admin-gate, tenant-uit-JWT, rate limits, best_effort-audit (aantallen
alleen). Contract-tabellen: zie sectie 6.

Gate 2 (twee onafhankelijke reviewers, meerdere rondes) vond en fixte: `row_index` voor
CSV-uploads was 1 te laag (header niet meegeteld); case-insensitieve naam-/e-mailmatching
ontbrak volledig; een gelijktijdige-import-race gaf een onafgevangen `IntegrityError`/500
(nu `IntegrityError` -> `ConflictError`/409); PII in een foutmelding; twee onafgevangen
parse-exceptions (`RecursionError` bij diep-geneste JSON, `csv.Error` bij een te groot
CSV-veld). Twee scope-uitbreidingen na Rakesh's GO: een nieuwe globale
`MaxRequestBodySizeMiddleware` (FastAPI leest de multipart-body VOOR elke auth-check --
elke ingelogde gebruiker kon zo geheugen/schijf-druk veroorzaken voor de 403 kwam; dekt ook
het pre-existing `documents/upload_router.py`) en repository-toegang via
`dependencies.py`-`Depends()`-providers i.p.v. directe instantiatie in de routers. Een
post-commit onafhankelijke verificatie (nodig na een procesonderbreking die de
completion-record van de oorspronkelijke code-review kwijtmaakte) vond en fixte een echte
mypy-syntaxfout (`# type: ignore[misc]`-comment zonder tweede `#`) die pyright/ruff/ASCII/de
gerichte testsuite niet vingen.

## 5. Dag 4 -- integratiebewijs (BE-AGT-061, dit gesprek, ongecommit op moment van schrijven)

Twee nieuwe integratietesten tegen een ECHTE Postgres-database (poort 5455), niet SQLite:

- `tests/integration/api/test_hr_import_tenant_isolation.py` -- een skill/training die
  tenant 1 importeert is aantoonbaar onzichtbaar voor tenant 2 (een verse, zelf-gezaaide
  admin-gebruiker voor tenant 2). **Mutatie-getest:** de `Skill.tenant_id == tenant_id`-
  filter in `list_skills` tijdelijk verwijderd -> test ging ROOD (tenant 2 zag tenant 1's
  skill); filter herstellen -> test GROEN. Bewijst dat de test een echte regressie vangt,
  niet vacuous is.
- `tests/integration/tool_broker/test_hr_skill_gap_after_import.py` -- drie echte POSTs
  naar de dag-3-endpoints (skill "IFRS", rolvereiste "Accountant heeft IFRS niveau 3
  nodig", beoordeling "niveau 4 voor een bestaande gebruiker"), gevolgd door een directe
  aanroep van `analyze_skill_gap`. Resultaat: `gap_count=1`, `holders=1`,
  `meeting_requirement=1`, `below_requirement=0`, `unassessed=0` -- het EXACTE gat dat
  OP-26 open liet is hiermee aantoonbaar gedicht.

**Belangrijke afwijking van het sprint-plan:** het import-pad maakt bewust NOOIT
automatisch een `Role` aan (Ontwerpbeslissing 3, dag 1-3). De E2E-test zaait daarom vooraf
een "Accountant"-rol via een directe ORM-insert (niet via de import-API) en koppelt de
al-gezaaide tenant-1-testgebruiker daaraan -- dit is een noodzakelijke testvoorbereiding,
geen omzeiling van wat de test beweert te bewijzen (de rolvereiste-IMPORT zelf gaat wel
via de echte API).

**Procesobstakel, niet mijn code:** beide integratietests konden niet rechtstreeks in de
hoofdwerkmap draaien, omdat een ONGERELATEERDE wijziging van een andere parallelle sessie
aan `src/core/models/foundation_content.py` (een `metadata`-attribuut dat botst met
SQLAlchemy's gereserveerde `Base.metadata`) de conftest-importketen van
`tests/integration/` breekt -- eerst als oncommitte wijziging, later ALS ONDERDEEL VAN EEN
COMMIT op `develop` (`63d0d94d`, "Foundation Portal v1"). Opgelost door telkens een
isolerende `git worktree` te gebruiken (eerst vanaf `b0b23c18`, mijn eigen dag-3-tip; later
opnieuw vanaf de nieuwe `develop`-tip om te bevestigen dat het probleem daar ook nog
aanwezig was) voor de testrun, zonder het andere sessie's bestanden aan te raken -- conform
CLAUDE.md's eigen regel dat parallelle iteraties nooit rechtstreeks in dezelfde werkmap
mogen ingrijpen. De bestanden die de andere sessie tegelijk wijzigt
(`docs/agent-briefs/generated/2026-08-24-sprint-dag-1-revisie.md` e.d.) suggereren dat dit
al onderdeel is van hun eigen, actieve revisiecyclus -- geen stille, vergeten regressie.

**Waargenomen, niet dag-4-specifiek, NIET een bevinding op deze feature:** een `WARNING
BYPASS: Tenant filter DISABLED`-logregel vuurt op elke GET-aanvraag. Getraceerd tot
`TenantFilterBypass`, legitiem gebruikt binnen de auth-resolutieketen (`get_current_user`
moet een gebruikers tenant_id opzoeken VOORDAT enige tenant-context bestaat -- exact het
scenario dat `TenantFilterBypass`'s eigen docstring als geldig gebruik noemt, onafhankelijk
bevestigd door twee Gate-2-reviewers op dag 4). De mutatietest hierboven bewijst dat de
EXPLICIETE `tenant_id`-filter in de repository de daadwerkelijk werkende veiligheidslaag is,
onafhankelijk van de ADR-004 ORM-hook -- niet de bypass-logregel. Om deze conclusie niet
alleen als proza te laten staan (doc-review BE-AGT-058, bevinding High: elke niet-gefixte
FA-bevinding vereist een falende architecture-test conform `.claude/rules/quality-gates.md`)
is de eenmalige, handmatige mutatietest omgezet in een permanente, geautomatiseerde guard:
`tests/architecture/test_hr_repositories_explicit_tenant_filter.py` (mutatie-getest in beide
richtingen -- zie de guard's eigen module-docstring). Die guard bewaakt de ECHTE
veiligheidslaag; een guard op de logregel zelf zou een vals signaal bewaken.

## 6. Contract per endpoint

| Aspect | `POST /skills/import` | `POST /trainings/import` | `GET /skills` | `GET /trainings` |
| --- | --- | --- | --- | --- |
| Auth | `Depends(require_admin_role)` | idem | idem | idem |
| `tenant_id` | `_resolve_tenant_id(current_user)`, NOOIT uit body/bestand | idem | idem | idem |
| Body | `multipart/form-data`: `entity_type` (skill/role_requirement/employee_assessment) + `file` (CSV/JSON) | `entity_type` (training/employee_training) + `file` | -- | -- |
| Query | -- | -- | `limit` (default 50, ge=1, le=1000), `offset` (default 0, ge=0) | idem |
| Caps | 5 MiB bestand, 500 rijen per batch (400 bij overschrijding, nooit stil afgekapt) | idem | -- | -- |
| Rate limit | `hr_import_write_limit` (10/min) | idem | `hr_import_read_limit` (60/min) | idem |
| Succes | 200, `{"success": true, "data": {"inserted", "updated", "errors": [...]}}` | idem | 200, `{"success": true, "data": [...]}` | idem |
| 400 | onleesbaar bestand, 0 rijen, >500 rijen, onbekend content-type | idem | -- | -- |
| 401/403 | geen/ongeldig token, geen admin-rol | idem | idem | idem |
| 409 | gelijktijdige import met overlappende sleutel (`IntegrityError` -> `ConflictError`) | idem | -- | -- |
| 422 | ontbrekend/ongeldig `entity_type` (Literal) of ontbrekend `file`-veld -- FastAPI's eigen Pydantic-validatie, VOORDAT enige repository- of parse-laag bereikt wordt | idem | -- | -- |
| 429 | > 10 aanvragen/min | idem | > 60 aanvragen/min | idem |
| 500 | onverwachte DB-fout buiten de rij-niveau try/except -- geen eigen afhandeling, leunt op de globale exception-handler (generieke melding, geen stacktrace, conform `.claude/rules/error-handling.md`) | idem | idem | idem |
| Audit | `AuditService.log_event` via `best_effort`, AANTALLEN alleen (nooit rij-inhoud/e-mails) | idem | -- | -- |
| Rij-fout (geen 4xx) | individuele rij komt in `errors[]` met het ORIGINELE bestandsrijnummer (1-based, header meegeteld voor CSV); blokkeert de rest van de batch niet | idem | -- | -- |

## 7. Trainingssamenvatting

**Flow 1 -- tenant-admin importeert skills met een deel-fout**

- Actor: tenant-admin (JWT met `roles` bevat `admin`/`system_admin`)
- Voorwaarde: CSV/JSON-bestand onder 5 MiB en 500 rijen
- Actie: `POST /api/v1/hr/skills/import` met `entity_type=employee_assessment`, rij 1
  geldig, rij 2 verwijst naar een onbekende gebruiker
- Systeemverwerking: rij 1 wordt geupsert en gecommit; rij 2 komt in `row_errors` met
  bericht "onbekende gebruiker" (geen e-mailadres erin, PII-bescherming); audit-log
  registreert `{"inserted": 1, "rejected": 1}`, geen rij-inhoud
- Succesrespons: 200, `data.inserted=1`, `data.errors=[{"row_index": 2, "message":
  "onbekende gebruiker"}]`
- Foutrespons: n.v.t. (deel-fout is geen 4xx)
- Uitzonderingen: >500 rijen of >5 MiB wijst de HELE batch af (400), geen deel-verwerking

**Flow 2 -- een andere tenant probeert de geimporteerde data te zien**

- Actor: admin van tenant 2
- Voorwaarde: tenant 1 heeft net een skill geimporteerd
- Actie: `GET /api/v1/hr/skills` met tenant 2's eigen, geldige admin-token
- Systeemverwerking: `list_skills(tenant_id=2, ...)` filtert op `Skill.tenant_id == 2`
- Succesrespons: 200, lege of alleen-tenant-2-lijst; tenant 1's skill zit er NOOIT in
- Foutrespons: n.v.t.
- Uitzonderingen: geen -- mutatie-getest (zie sectie 5)

**Flow 3 -- een echte import maakt `analyze_skill_gap` bruikbaar**

- Actor: tenant-admin (import), daarna een adviserende skill/tool-aanroeper
  (`analyze_skill_gap`)
- Voorwaarde: een rol met naam X bestaat al (import maakt NOOIT automatisch een `Role`
  aan)
- Actie: import skill Y, rolvereiste "X heeft Y nodig op niveau N", beoordeling "gebruiker
  Z heeft Y op niveau M"; daarna `analyze_skill_gap(tenant_id=1)`
- Systeemverwerking: drie upserts, dan een geaggregeerde SQL-query over
  `role_required_skills`/`employee_skills`/`users`/`roles`, tenant-gescoopt via een
  ambient ContextVar EN expliciete `tenant_id`-joins
  (dubbele laag, zie `hr_registry.py`'s eigen docstring)
- Succesrespons: `{"success": true, "gaps": [{"role": "X", "skill": "Y",
  "required_level": N, "holders": 1, "meeting_requirement": 1 of 0, "below_requirement":
  ..., "unassessed": 0}], "gap_count": >= 1}`. De dag-4-test asserteert `gap_count > 0`
  (niet een exacte waarde) plus de exacte inhoud van de "X"/"Y"-rij zelf -- in dat precieze
  scenario (1 geimporteerde rolvereiste) is `gap_count` toevallig 1, maar dat is geen
  apart-getest contract
- Foutrespons: `{"success": false, "error": "HR-query mislukt door een interne fout"}` bij
  een `SQLAlchemyError` -- nooit de ruwe exception-tekst (zou gebonden SQL-parameters in
  de LLM-context/leerlaag lekken)
- Uitzonderingen: `M >= N` geeft `meeting_requirement=1`/`below_requirement=0`; een
  onbeoordeelde houder van de rol telt als `unassessed`, NIET als `below_requirement`

## 8. Wat NIET is gedaan (bewust, buiten deze sprint)

- `analyze_skill_gap`'s output koppelen aan `trainings` ("stuur deze mensen naar training
  X") -- volgt in een latere sprint, nu de tabellen bestaan.
- ADR-005 par. 5 composite-FK-fix voor de nieuwe junction-tabellen -- toekomstige
  Hardening Sprint (zie dag 1).
- Per-proces (niet Redis-backed) rate limiting voor `hr_import_read_limit`/
  `hr_import_write_limit` -- matcht het bestaande, niet-gemigreerde patroon van de meeste
  `privacy_rate_limit`-decorators in dit bestand.
- 4xx-envelop-contract-mismatch (`error_code` i.p.v. `code`, geen top-level `success` bij
  een afgewezen aanvraag) -- pre-existing, repo-breed in `src/core/exceptions/
  handlers.py`, niet door deze feature veroorzaakt.
- D11 (generieke document-RAG/pgvector) -- eigen sprintplanning.

## 9. Gewijzigde/nieuwe bestanden (alle 4 dagen)

| Bestand | Wijziging |
| --- | --- |
| `src/core/models/hr_training_models.py` | nieuw (dag 1) |
| `src/alembic/versions/20260822_hr_trainings_tables.py` | nieuw (dag 1) |
| `src/core/database/import_all_models.py` | dag 1: registratie |
| `src/core/repositories/hr_import_types.py` | nieuw (dag 2) |
| `src/core/repositories/hr_skills_import_repository.py` | nieuw (dag 2), fixes dag 3 |
| `src/core/repositories/hr_trainings_repository.py` | nieuw (dag 2), fixes dag 3 |
| `src/core/api/v1/hr/*.py` (7 bestanden) | nieuw (dag 3) |
| `src/core/api/registries/hr.py` | nieuw (dag 3) |
| `src/core/api/router_registry.py` | dag 3: hr-registry toegevoegd |
| `src/core/governance/rate_limiter.py` | dag 3: `hr_import_read/write_limit` |
| `src/core/middleware/max_body_size_middleware.py` | nieuw (dag 3, scope-uitbreiding) |
| `src/core/api/setup/middleware_config.py` | dag 3: middleware geregistreerd |
| `src/core/shared/config.py` | dag 3: dubbele-rol-comment op `max_upload_size_bytes` |
| `tests/unit/models/test_hr_training_models.py` | nieuw (dag 1) |
| `tests/integration/database/test_hr_training_models_cascade.py` | nieuw (dag 1) |
| `tests/architecture/test_hr_junction_tables_composite_fk_gap.py` | nieuw (dag 1) |
| `tests/unit/repositories/test_hr_*_repository.py` (2 bestanden) | nieuw (dag 2), uitgebreid dag 3 |
| `tests/unit/api/v1/hr/*.py` (3 bestanden) | nieuw (dag 3) |
| `tests/unit/middleware/test_max_body_size_middleware.py` | nieuw (dag 3, scope-uitbreiding) |
| `tests/integration/api/test_hr_import_tenant_isolation.py` | nieuw (dag 4) |
| `tests/integration/tool_broker/test_hr_skill_gap_after_import.py` | nieuw (dag 4) |
