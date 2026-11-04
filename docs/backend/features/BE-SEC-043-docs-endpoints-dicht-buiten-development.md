# Backend Feature Specification -- BE-SEC-043

## Metadata

| Veld | Waarde |
| --- | --- |
| ID | BE-SEC-043 |
| Naam | OpenAPI-oppervlakte dicht buiten development |
| Sprint / herkomst | ADR-036 Fase D, OP-124 (+ OP-137 als afsplitsing) |
| Datum | 2026-08-14 |
| Domein | app-configuratie, ops/deploy-scripts, tests |
| ADR | ADR-036 (OP-124), ADR-012 (health-tiers), ADR-035 (on-premise deploy) |
| Status | Geimplementeerd |

## Doel en scope

### Doel

`/docs`, `/redoc` en `/openapi.json` waren onauthenticated bereikbaar in productie. Dat
publiceert de volledige API-oppervlakte inclusief alle schema's. Deze wijziging sluit die drie
endpoints buiten `development`, maakt de fallback fail-secure, en trekt elke plek recht die op
een open schema rekende.

### In scope

- `src/main.py`: `docs_url`/`redoc_url`/`openapi_url` alleen open bij `ENVIRONMENT=development`;
  de default van `ENVIRONMENT` van `development` naar `production`.
- `src/core/app_factory.py` en `src/core/tool_broker/main.py`: dezelfde regel, want beide
  publiceerden hun schema onvoorwaardelijk.
- De CD-smoketests (productie en staging) en vijf on-premise deploy/ops-paden.
- Tests die de omgekeerde invariant vastlegden.
- Twee architecture-guards.

### Out of scope

- `frontend/src/pages/APIDocs.tsx` -- die pagina haalt `/openapi.json` op en toont in productie
  een foutmelding. Productbeslissing van Rakesh; vastgelegd als **OP-137** in ADR-036.
- De ongeveer tien andere modules die `os.getenv("ENVIRONMENT", "development")` gebruiken.
  Alleen `src/main.py`, `app_factory.py` en `tool_broker/main.py` zijn omgezet; de rest raakt
  configuratievalidatie en secret-loading en vraagt een eigen meting.
- `/health/db` geeft 401 zonder token. Dat is correct volgens ADR-012 (Diagnostics-tier) en de
  smoke-check is daarop aangepast, maar `docs/prod-readiness.md` par. 2.9 claimt nog "all 10
  checks pass" -- die checklist is niet bijgewerkt.

## Build summary

| Artefact | Type | Locatie |
| --- | --- | --- |
| Schema-endpoints gated | Config | `src/main.py:118-127` |
| Fail-secure default | Config | `src/main.py:45` |
| Shim gelijkgetrokken | Config | `src/core/app_factory.py` |
| Losse service gelijkgetrokken | Config | `src/core/tool_broker/main.py` |
| Guard: gedrag per omgeving | Test | `tests/architecture/test_docs_disabled_in_prod.py` |
| Guard: elke FastAPI-app | Test | `tests/architecture/test_every_fastapi_app_closes_its_docs.py` |
| Post-deploy verificatie (pytest) | Test | `tests/smoke/test_critical_paths.py` |
| Post-deploy verificatie (PowerShell) | Ops | `scripts/smoke_test.ps1` |

## Detaildocumentatie

### 1. Gedrag per omgeving

Gemeten op de geassembleerde app (`create_app(testing=False)`, volledige routerregistratie):

| ENVIRONMENT | `/docs` | `/redoc` | `/openapi.json` |
| --- | --- | --- | --- |
| `development` | 200 | 200 | 200 |
| `production` | 404 | 404 | 404 |
| `staging` | 404 | 404 | 404 |
| `test` | 404 | 404 | 404 |
| niet gezet | 404 | 404 | 404 |

"Dicht" is niet altijd exact 404: de IP-allowlist in `SecurityMiddleware` kan vanaf een
niet-toegestaan adres eerder een 403 geven. Beide zijn geldig, en daarom eisen de
post-deploy-checks een 4xx en niet exact 404. Een 5xx of geen antwoord is expliciet GEEN
geldige "dicht" -- dat is een storing.

### 2. Waarom de default `production` is

`ENVIRONMENT` was `os.getenv("ENVIRONMENT", "development")`. Bij een ontbrekende variabele
stonden de docs dus open -- fail-open op precies de storing die telt. De default is nu
`production`.

Gevolg dat is meegenomen: `scripts/start_dev.ps1` en `scripts/start_local.ps1` zetten
`DATABASE_URL` maar nooit `ENVIRONMENT`, en `src/core/env_loader.py:30-31` keert vroeg terug
zodra `DATABASE_URL` bestaat -- dan wordt `.env` niet gelezen. Zonder ingrijpen draaide een
lokale `uvicorn` daarmee als productie: docs dicht, audit-logging naar de database en de
productie-eisen aan de redactiesleutel. Beide scripts zetten nu expliciet
`ENVIRONMENT=development`.

### 3. Zichtbaarheids- en toegangsregels

`/docs`, `/redoc` en `/openapi.json` staan in `TenantMiddleware.EXCLUDED_PREFIXES`, dus er komt
geen tokencheck voor. De bescherming is dat de route buiten development niet bestaat.

### 4. Deploy- en ops-paden

| Pad | Voor | Na |
| --- | --- | --- |
| `.github/workflows/cd-production.yml` | eiste 200 op `/docs` | `/health` |
| `.github/workflows/cd-staging.yml` | eiste 200 op `/docs` | `/health` |
| `scripts/smoke_test.ps1` | eiste 200 op `/docs` + schema-veld | eist 4xx op alle drie |
| `scripts/deploy_to_production.sh` | `curl /docs` naar `grep swagger`, anders `return 1` | `/health/ready` + 4xx-eis op `/openapi.json` |
| `scripts/run-tests.sh` | `curl -f /docs` | `/health/ready` |
| `scripts/deploy_day1_backend.sh` | open docs = positief gelogd | dicht = positief |
| `scripts/verify_deployment.sh` | `test_endpoint /docs` | check verwijderd |
| 5 echo-regels in deploy-scripts | printten een docs-URL | melden "alleen in development" |

`scripts/deploy_prod.ps1:145-154` rolt de stack terug bij exitcode != 0 van
`smoke_test.ps1`. Zonder deze wijziging deed die smoke-test dat bij elke geslaagde deploy.

### 5. Guards

`test_docs_disabled_in_prod.py` toetst het gedrag per omgeving met `patch.object` op de
module-global -- geen `importlib.reload`. Dat is bewust: een reload van `src.main` herbindt de
loguru-sink, vervangt `src.main.app` waar 43 testbestanden namen uit vasthouden, en kan
`validate_config_at_startup()` bereiken die `sys.exit(1)` doet. De fail-secure default wordt
structureel op de AST getoetst, want een reload leest `.env.local` en dan hangt de uitkomst af
van een untracked bestand.

`test_every_fastapi_app_closes_its_docs.py` toetst elke `FastAPI(...)`-constructie in `src/` op
de mogelijke WAARDEN van `docs_url` en eist dat `None` erbij zit. Dat onderscheid is nodig:
`app_factory.py` had `"/docs" if not testing else "/docs"`, een conditie waarvan beide takken
open waren. Een guard die alleen op "is het een conditie?" toetst, keurt dat goed.

## Trainingssamenvatting

| Actor | Voorwaarde | Actie | Systeemreactie | Succes | Fout | Uitzondering |
| --- | --- | --- | --- | --- | --- | --- |
| Onauthenticated bezoeker | `ENVIRONMENT=production` | GET `/docs` | Route bestaat niet | 404, geen schema | n.v.t. | 403 als de IP-allowlist eerder weigert |
| Ontwikkelaar | `ENVIRONMENT=development` | GET `/docs` | Swagger UI | 200 | n.v.t. | geen |
| Operator | Na een deploy | `pytest tests/smoke/` met `TEST_BASE_URL` | Readiness-anker plus 4xx-eis op de drie endpoints | Alle checks groen | Faalt bij een 2xx of bij een onbereikbare server | Skipt zonder `TEST_BASE_URL` |
| Operator | On-premise deploy | `deploy_prod.ps1` | `smoke_test.ps1` eist dat de drie dicht zijn | Exitcode 0, geen rollback | Rollback bij een open schema | `/health/db` mag 401 geven |
| Beheerder | `ENVIRONMENT` niet gezet | Start de applicatie | Fail-secure: docs dicht | Geen schema-lek | n.v.t. | Dev-scripts zetten development expliciet |

## Verificatie

- `tests/architecture/test_docs_disabled_in_prod.py` -- 8 tests, mutatie-getest in vier
  richtingen (onvoorwaardelijk open, fail-open voor staging, weiger-alles, default terug).
- `tests/architecture/test_every_fastapi_app_closes_its_docs.py` -- 2 tests, mutatie-getest in
  vier richtingen inclusief de staleness-kant.
- `tests/smoke/test_critical_paths.py` -- aangetoond tegen een echte server in drie richtingen:
  gehardend 6 passed, development 3 failed, geen server 6 skipped.
- `scripts/smoke_test.ps1` -- aangetoond in beide richtingen tegen een echte server.
- **Geen CI.** Het tegoed was op; alle bewijs is lokaal (Windows). Dat is zwakker dan CI.
