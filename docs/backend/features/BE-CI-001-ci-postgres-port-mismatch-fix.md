# Backend Feature Specification

## Metadata

- Feature ID: BE-CI-001
- Feature naam: CI Postgres-servicepoort-mismatch fix (Tenant integration tests)
- Status: ACTIEF
- Auteur: Claude (SP-CI-001 Dag 1)
- Reviewer: self-review (kleine wijziging, <20 regels, 1 bestand -- CLAUDE.md Gate 2-uitzondering)
- Datum: 2026-07-13
- Gerelateerde user story / ticket: SP-CI-001 (CI Pipeline Herstel), Bevinding 1
- Gerelateerde router / module: `.github/workflows/ci-feature.yml`
- Gerelateerde frontend endpoints: n.v.t.
- Gerelateerde database tabellen: n.v.t. (CI-infra, geen schemawijziging)
- Versie: 1.0

---

## Doel en scope

### Doel

De scheduled `main`-CI-run (en elke feature/hotfix-push naar `develop`) faalde consistent op de
stap "Tenant integration tests" in het Python-job. Root-cause: `tests/integration/conftest.py`
probeert bij het opstarten van integratietests een PostgreSQL-verbinding op poort 5435 of 5455
(de vastgelegde lokale/docker-compose-conventie, zie CLAUDE.md), maar de CI-servicecontainer in
`ci-feature.yml` exposeerde alleen poort 5432. De probe faalde daardoor altijd, de gehele
integratietest-module werd geskipt via `pytest.skip(..., allow_module_level=True)`, en de stap
eindigde met exit code 1 ("geen tests verzameld") -- niet omdat er inhoudelijk iets stuk was.

### In scope

- Toevoegen van een tweede poort-mapping (5435 -> 5432) aan de bestaande `postgres`-service in
  `.github/workflows/ci-feature.yml`, zodat dezelfde containerinstantie zowel op 5432
  (bestaande `DATABASE_URL`-referenties in het job) als op 5435 (integratietest-conftest-probe)
  bereikbaar is.

### Out of scope

- Wijzigen van `tests/integration/conftest.py`'s poort-conventie (5435/5455 blijft de
  vastgelegde lokale/dev-standaard, zie `make test-db-up`).
- De migratie-keten-bug (`ALTER TABLE audit_logs ADD COLUMN audit_hash` faalde op de destijds
  gescande `main`-branch omdat de bootstrap-migratie `d4e5f6a7b8c9` daar ontbrak). Onderzoek
  wees uit dat dit AL is opgelost op `develop` (commit `9e65ec3a`, 2026-07-04,
  SP-MIG-ARCH-1/AUDIT-ARCH-2026-07-02 Dag 3) maar nog niet naar `main` is gepromoveerd. Geen
  code-wijziging nodig in deze sprint-dag.

  **Correctie (FA-IND-001/002, onafhankelijke review 2026-07-13):** dit lost zich NIET
  vanzelf op. `main` is de default branch en draait de scheduled CI (`cron`, geen
  branch-filter) tegen zijn eigen workflow-definitie -- niet tegen `develop`. Er bestaat op
  dit moment GEEN PR met `base=main` (laatste main-merge: PR #147, 2026-06-30). PR #148 is
  een `develop`-naar-`develop` fork-sync-PR en heeft niets met een main-promotie te maken --
  die aanname in de eerdere versie van dit document was onjuist. Zowel deze fix als de
  migratie-keten-fix blijven het oorspronkelijk gerapporteerde probleem (scheduled main-CI
  failure) veroorzaken totdat een aparte, Rakesh-goedgekeurde develop-naar-main-merge
  plaatsvindt. Dat is een expliciete beslissing voor Rakesh, geen automatisme van deze sprint.

---

## Build summary

- Gewijzigd: `.github/workflows/ci-feature.yml` -- `services.postgres.ports` uitgebreid met
  `5435:5432` naast de bestaande `5432:5432`.
- Nieuw gebouwd: geen.
- Verwijderd: geen.
- Beinvloede bestaande flows: CI-pipeline "Python" job, stap "Tenant integration tests". Geen
  wijziging aan applicatiecode, geen wijziging aan bestaande 5432-referenties elders in hetzelfde
  workflowbestand (regels met `DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/...`).

---

## Verificatie (i.p.v. API-flows -- dit is geen endpoint-feature)

Lokaal gereproduceerd met Docker (matcht de GitHub Actions services-container-mechaniek 1-op-1):

```bash
docker run -d --name sp_ci_001_pg -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=sanskritisetu -p 5432:5432 -p 5435:5432 pgvector/pgvector:pg15
python -m pytest tests/integration/api/v1/tenants -q --tb=short --timeout=60
# Resultaat: 15 passed in 13.55s (voor de fix: "Skipped: PostgreSQL test database not
# available on port 5435 or 5455")
```

Bevestigd: een enkele Postgres-container met dubbele poort-mapping (5432 + 5435) is
gelijktijdig bereikbaar op beide poorten via zowel directe asyncpg-verbinding als via de
volledige `tests/integration/api/v1/tenants`-testsuite. Dit valideert dat de YAML-wijziging
(zelfde onderliggende Docker-mechaniek als GitHub Actions `services:`) het probleem oplost.

YAML-syntax gevalideerd: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci-feature.yml'))"`.

---

## Open aannames

- GitHub Actions' `services:`-blok ondersteunt meerdere host-poorten naar dezelfde
  containerpoort (bevestigd via lokale Docker-reproductie van hetzelfde onderliggende
  mechanisme; niet 1-op-1 bevestigd in de GitHub-Actions-runneromgeving zelf omdat dit vereist
  dat de workflow daadwerkelijk in CI draait -- aanbevolen als vervolgstap: trigger een
  `workflow_dispatch`-run of wacht de eerstvolgende scheduled run af).

## Open vragen

- Geen.

## Risico's

- Laag: de wijziging voegt alleen een extra poort-mapping toe; de bestaande 5432-mapping en
  alle bestaande `DATABASE_URL`-referenties blijven ongewijzigd.

---

## Trainingssamenvatting

- Actor: CI-pipeline (scheduled/push/PR-run van `.github/workflows/ci-feature.yml`)
- Voorwaarde: de "Tenant integration tests"-stap start, de postgres-servicecontainer draait
- Actie: `tests/integration/api/v1/tenants` wordt uitgevoerd via pytest
- Systeemreactie: `tests/integration/conftest.py` probeert een verbinding op poort 5435 of 5455
- Succesrespons: verbinding lukt op 5435 (via de nieuwe dual-port-mapping), integratietests
  draaien en slagen (15/15)
- Foutrespons (voor de fix): geen van beide poorten bereikbaar -> `pytest.skip(...,
  allow_module_level=True)`, gehele module geskipt, stap eindigt met exit code 1
- Uitzonderingen: n.v.t. (infrastructuur-configuratiefix, geen conditioneel gedrag)

---

## QA-checks

- [x] Lokaal gereproduceerd: probleem bestaat voor de fix (poort-mismatch)
- [x] Lokaal geverifieerd: fix lost het probleem op (dual-port container, 15/15 tests groen)
- [x] YAML-syntax gevalideerd
- [ ] Bevestigd in de daadwerkelijke GitHub Actions-omgeving (aanbevolen vervolgstap, niet
      blokkerend voor deze sprint-dag)
- [x] Geen regressie op bestaande 5432-referenties (ongewijzigd gelaten)

---

## Definition of Done

- [x] Fix is aangebracht (`ci-feature.yml`)
- [x] Root-cause vastgesteld en gedocumenteerd
- [x] Lokaal geverifieerd met een reproductie die het exacte CI-mechanisme nabootst
- [x] Geen nieuwe regressies in `tests/unit/` of `tests/architecture/` (zie final-approver
      brief voor de baseline-vergelijking, inclusief 5 pre-existing architecture-testfailures
      die NIET door deze wijziging zijn veroorzaakt)
- [x] Review: self-review (kleine wijziging, CLAUDE.md Gate 2-uitzondering van toepassing)
