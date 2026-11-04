# BE-SEC-027: Fail-closed compose-defaults + AP sandboxed-regressie hersteld

**Sprint:** AUDIT-ARCH-2026-07-02 Dag 2 Groep 5
**Datum:** 2026-07-02
**Status:** APPROVED
**ADR:** ADR-009, ADR-010

## Probleem

`docker-compose.yml`/`.dev.yml`/`.prod.yml` gebruikten `:-postgres` /
`:-changeme_in_production` / `:-change-me-in-production`-fallbacks voor
credentials (Postgres/Redis-wachtwoorden, ActivePieces-secrets,
Grafana-admin-wachtwoord, DATABASE_URL/REDIS_URL/DRAMATIQ_BROKER_URL in
productie-workers). `docker-compose.single-tenant.yml` (een reeel self-hosted
productie-pad, zie `docs/deployment/single-tenant-guide.md`) bond Postgres/Redis
op alle interfaces i.p.v. 127.0.0.1, en Redis had daarin helemaal geen
`--requirepass` -- erger dan de audit beschreef. `.github/workflows/
cd-production.yml`/`cd-staging.yml` zetten `AP_EXECUTION_MODE=UNSANDBOXED`, een
bevestigde regressie van F-09 (commit 27a9bbf0, teruggedraaid door e6c67529).

## Oplossing

- Alle credential-fallbacks vervangen door `${VAR:?<naam> is verplicht}`
  (fail-closed: ontbrekende env-var laat de container-start hard falen i.p.v.
  een onveilige default te gebruiken).
- `docker-compose.single-tenant.yml`: Postgres/Redis-poorten gebonden op
  `127.0.0.1`, Redis vereist nu `--requirepass ${DB_PASSWORD:?...}` (hergebruikt
  hetzelfde secret als Postgres -- 1 operator-credential voor deze
  single-host-deployment).
- `AP_EXECUTION_MODE=SANDBOXED` + `AP_WORKER_TYPE=THREAD` hersteld in beide
  CD-workflows.
- 4 nieuwe architecture-tests als permanente CI-gate.

## Trainingssamenvatting

- Actor: operator die `docker compose up` draait (lokaal, staging, of een
  self-hosted single-tenant-klant)
- Voorwaarde: `.env`/omgevingsvariabelen voor credential-velden
- Actie: container-opstart zonder de vereiste credential-env-var
- Systeemreactie: Docker Compose weigert de service te starten met een expliciete
  foutmelding (`required variable X is missing a value: <bericht>`)
- Succesrespons: met alle vereiste vars gezet start de stack normaal
- Foutrespons: `docker compose config`/`up` faalt hard, geen impliciete
  onveilige default meer
- Uitzonderingen: `POSTGRES_USER`/`GRAFANA_ADMIN_USER` behouden hun default
  (username is geen secret, alleen wachtwoord-achtige velden zijn verplicht)

## Test bewijs

```
pytest tests/architecture/test_activepieces_sandboxed_ci_gate.py \
  tests/architecture/test_single_tenant_network_binding.py \
  tests/architecture/test_prod_compose_no_hardcoded_credentials.py \
  tests/architecture/test_compose_fail_closed_defaults.py -v
9 passed

docker compose -f docker-compose.yml config --quiet  (met alle vars gezet) -- geslaagd
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet -- geslaagd
docker compose -f docker-compose.single-tenant.yml config --quiet -- geslaagd
docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet -- geslaagd
```

## Reviewers

code-reviewer: GO WITH MINOR ISSUES -- vond dat `backend`-service's eigen
REDIS_URL/DRAMATIQ_BROKER_URL ontbrak in de oorspronkelijke scope, en dat
`docker-compose.dev.yml` een split-brain-fallback zou achterlaten. Beide direct
meegenomen in de implementatie.
security-reviewer: GO -- bevestigde single-tenant.yml als reeel self-hosted
productie-pad (niet alleen dev), bevestigde geen DoS-regressie via fail-closed
(deze compose-bestanden worden niet door CI/CD aangeroepen, alleen door
operators/klanten handmatig).

## Backlog

Geen -- alle 7 Groep-5-bevindingen zijn vandaag gesloten.
