# Backend Feature Specification

## Metadata

- Feature ID: BE-ST-002
- Feature naam: Docker Single-Tenant Deployment (ADR-035)
- Status: DONE
- Auteur: Claude (S1 sprint)
- Reviewer: Zie review/review-BE-ST-002.md
- Datum: 2026-07-01
- Gerelateerde user story / ticket: AUDIT-ST-02
- Gerelateerde router / module: N/A (infrastructure)
- Gerelateerde frontend endpoints: N/A
- Gerelateerde database tabellen: N/A
- Versie: 1.0

---

## Doel en scope

### Doel

SanskritiSetu miste deployment-artefacten voor single-tenant (on-premise) installaties. Klanten die de software als dedicated instantie willen draaien hadden geen duidelijke installatieroute. Dit levert een Docker Compose configuratie, environment-template en deployment guide.

### In scope

- `docker-compose.single-tenant.yml` -- complete stack voor single-tenant deployment
- `.env.single-tenant.example` -- environment variabelen template
- `docs/deployment/single-tenant-guide.md` -- installatiehandleiding

### Out of scope

- Kubernetes/Helm charts
- Auto-scaling
- Azure Container Apps single-tenant variant

---

## Build summary

- Nieuw gebouwd: docker-compose.single-tenant.yml, .env.single-tenant.example, docs/deployment/single-tenant-guide.md
- Gewijzigd: N/A
- Verwijderd: N/A
- Beinvloede bestaande flows: Geen (nieuw deployment-pad)

---

## Backend inventory

| ID         | Naam                             | Type                  | Bestandspad                      | Nieuw/Wijziging | Gerelateerde flow |
| ---------- | -------------------------------- | --------------------- | -------------------------------- | --------------- | ----------------- |
| BE-CFG-010 | DEPLOYMENT_MODE env-variabele    | Configuratie          | .env.single-tenant.example       | Nieuw           | BE-FLW-ST-002     |
| BE-CFG-011 | docker-compose.single-tenant.yml | Infrastructure config | docker-compose.single-tenant.yml | Nieuw           | BE-FLW-ST-002     |

---

## API-flows

### Flow ID: BE-FLW-ST-002

- Naam: Single-tenant Docker deployment
- Trigger: `docker compose -f docker-compose.single-tenant.yml up -d`
- Voorwaarden: Docker + Docker Compose geinstalleerd; .env.single-tenant.example gekopieerd naar .env
- Request-pad: docker compose -> backend (DEPLOYMENT_MODE=single_tenant) + frontend + postgres + redis + traefik
- Service-stappen: 1) Alle services starten, 2) Backend leest DEPLOYMENT_MODE=single_tenant, 3) Alembic migraties draaien, 4) Workers gebruiken ensure_single_tenant_context
- DB-operaties: Postgres container; alembic upgrade head bij opstarten
- Successtatus: Alle services healthy; app bereikbaar op geconfigureerde domain
- Foutpaden: DB connection failure, missing env variabelen, port conflict
- Eindtoestand: Single-tenant instantie actief

---

## Detaildocumentatie per artefact

---

## [BE-CFG-010] DEPLOYMENT_MODE configuratievariabele

### 1. Type

- Configuratievariabele

### 2. Locatie

- Bestandspad: .env.single-tenant.example, src/core/workers/tenant_context.py
- Klasse / functie: os.getenv("DEPLOYMENT_MODE", "saas")

### 3. Gerelateerde flow

- BE-FLW-ST-002, BE-FLW-ST-001

### 4. Doel

- Schakelt single-tenant gedrag in voor workers (automatische tenant_id=1 injectie)

### 5. Functionele beschrijving

- Bij DEPLOYMENT_MODE=single_tenant injiceren workers automatisch tenant_id=1 via BE-UTL-010. In SaaS-mode (default) is dit een no-op.

### 6. Technische beschrijving

- Wordt runtime gelezen via os.getenv() (niet import-time) zodat tests monkeypatch.setenv() kunnen gebruiken
- Geldige waarden: "single_tenant", "saas" (default)

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: N/A (infra config)
- Vereiste rol / scope: N/A
- Tenant-isolatie: Forceert tenant_id=1 in single-tenant mode
- Feature flag: Dit IS de feature flag

### 8. Request-specificatie

- Methode: N/A (environment variabele)
- Route: N/A
- Verplichte headers: N/A

### 9. Response-specificatie

- N/A

### 10. Validaties en constraints

- DEPLOYMENT_MODE wordt case-insensitive gecontroleerd
- Onbekende waarden behandeld als "saas"

### 11. Business rules

- single_tenant: tenant_id=1 altijd; geen multi-tenant isolatie nodig
- saas: normale JWT-gebaseerde tenant_id (default)

### 12. Afhankelijkheden

- src/core/workers/tenant_context.py (runtime lezer)

### 13. Foutafhandeling

- Ontbrekende DEPLOYMENT_MODE: default "saas" (veilig)
- Ongeldige waarde: behandeld als "saas"

### 14. Transacties en dataïntegriteit

- N/A

### 15. Telemetry / logging / tracing

- N/A

### 16. Caching

- Gecached: Nee (runtime os.getenv() per aanroep)

### 17. Acceptatiecriteria

- [ ] docker-compose.single-tenant.yml bevat DEPLOYMENT_MODE=single_tenant
- [ ] .env.single-tenant.example bevat alle verplichte variabelen
- [ ] CORS_ALLOWED_ORIGINS is nooit "\*" in de template
- [ ] Architecture test valideert bestaan van compose-bestand, env-template en guide

### 18. Integratoruitleg

- Kopieer .env.single-tenant.example naar .env en vul alle waarden in
- Start met `docker compose -f docker-compose.single-tenant.yml up -d`
- Backend is automatisch geconfigureerd voor single-tenant mode

### 19. Trainingssamenvatting

- Actor: DevOps/installateur
- Voorwaarde: Docker + Compose beschikbaar; .env ingevuld
- Actie (request): docker compose up
- Systeemverwerking: Stack start; DEPLOYMENT_MODE=single_tenant activeert worker-context
- Succesrespons: Alle containers healthy
- Foutrespons: Container exit met error log
- Uitzonderingen: N/A

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Volg docs/deployment/single-tenant-guide.md voor stap-voor-stap installatie
- Gebruik altijd .env.single-tenant.example als startpunt; vul nooit \* in bij CORS
- DEPLOYMENT_MODE=single_tenant is verplicht voor correcte worker-context

---

## Open aannames

- tenant_id=1 bestaat altijd na de eerste alembic upgrade

## Open vragen

- Geen

## Risico's

- Beheerder vergeet DEPLOYMENT_MODE in te stellen; workers draaien dan in SaaS-mode zonder tenant_id injectie

---

## QA-checks

- [x] Architecture test valideert bestaan van artefacten
- [x] .env template bevat geen secrets of wildcard CORS
- [x] Deployment guide beschrijft alle stappen

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Configuratievariabelen geinventariseerd
- [x] Functionele en technische beschrijving aanwezig
- [x] Acceptatiecriteria testbaar
- [x] Integratoruitleg aanwezig
- [x] Trainingssamenvatting aanwezig
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
