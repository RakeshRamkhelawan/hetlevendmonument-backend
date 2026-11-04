# CI/CD Pipeline Documentatie — SanskritiSetu.org

> **Laatste update:** 2026-04-07
> **Huidige branch:** develop (feature/cicd-hardening)
> **Versie:** 3.2 — na pipeline hardening sprint

---

## Inhoud

1. [Architectuuroverzicht](#1-architectuuroverzicht)
2. [CI workflow (feature branches)](#2-ci-workflow-feature-branches)
3. [CD Staging pipeline](#3-cd-staging-pipeline)
4. [CD Productie pipeline](#4-cd-productie-pipeline)
5. [Rollback workflow](#5-rollback-workflow)
6. [Activepieces integratie](#6-activepieces-integratie)
7. [GitHub Secrets](#7-github-secrets)
8. [Lokale kwaliteitsbewakers](#8-lokale-kwaliteitsbewakers)
9. [Azure-infrastructuur](#9-azure-infrastructuur)
10. [Opgeloste problemen](#10-opgeloste-problemen)
11. [Bekende onvolkomenheden](#11-bekende-onvolkomenheden)
12. [Deploy-procedure](#12-deploy-procedure)
13. [CI workflow detail](#13-ci-workflow-detail)

---

## 1. Architectuuroverzicht

| Workflow | Bestand | Trigger | Doel |
|----------|---------|---------|------|
| **CI** | `.github/workflows/ci-feature.yml` | Push op `feature/**`, `hotfix/**`; PR naar `develop` | Lint, tests, Docker validatie, security scan |
| **CD Staging** | `.github/workflows/cd-staging.yml` | Push op `develop` | Build, valideer, deploy naar staging |
| **CD Productie** | `.github/workflows/cd-production.yml` | Tag `v*.*.*` op develop; `workflow_dispatch` | Build, valideer, deploy naar productie |
| **Rollback** | `.github/workflows/rollback.yml` | `workflow_dispatch` (handmatig) | Terugdraaien naar een eerdere image tag |

### Branchstrategie

```
feature/** ──PR──> develop ──push──> CD Staging
                       │
                       └── tag v*.*.* ──> CD Productie ──> merge naar main
```

- `main`: stabiele productie-code, wordt automatisch bijgewerkt na productie-deploy
- `develop`: staging-branch, elke push triggert CD Staging
- `feature/**`: ontwikkeling, PR naar develop triggert CI

---

## 2. CI workflow (feature branches)

**Bestand:** `.github/workflows/ci-feature.yml`
**Trigger:** Push op `feature/**` en `hotfix/**` branches; PR naar `develop`

De CI workflow draait 4 parallelle jobs:

| Job | Naam | Timeout | Wat het doet |
|-----|------|---------|-------------|
| `python` | Python | (default) | Ruff lint + pytest unit tests (exclusief postgres/redis/ollama) |
| `frontend` | Frontend | 15 min | npm ci, unit tests, production build |
| `docker-validate` | Docker Build Validation | 20 min | Backend build, migratie-keten validatie, single head check, frontend build |
| `security` | Security Scan | 10 min | Bandit security scan (HIGH severity + HIGH confidence blokkeren merge) |

Zie [Sectie 13](#13-ci-workflow-detail) voor gedetailleerde stappen.

---

## 3. CD Staging pipeline

**Bestand:** `.github/workflows/cd-staging.yml`
**Trigger:** Push op `develop`
**Concurrency:** `cd-staging`, cancel-in-progress: **true**
**Timeout:** 45 minuten
**Environment:** `staging`

### Stappen

| # | Stap | Beschrijving |
|---|------|-------------|
| 0 | Checkout | Code ophalen |
| 1 | Azure login + ACR login | Authenticatie bij Azure en Container Registry |
| 2 | Set up Docker Buildx | BuildKit configureren voor multi-platform builds |
| 3 | Cache Docker layers | GitHub Actions cache voor Docker layer hergebruik |
| **Build & Validatie** | | |
| 4a | Build backend | `docker buildx build --target production-api --load` met cache |
| 4b | Validate migration chain | Offline dry-run: chain compile + single head check |
| 4c | Push backend | Naar ACR (alleen na geslaagde validatie) |
| 5a | Build frontend | `docker build --load` met dynamische `VITE_API_URL` uit Container App FQDN |
| 5b | Validate frontend image | `nginx -t` + controle of `index.html` aanwezig is |
| 5c | Push frontend | Naar ACR |
| 6a | Build worker | `docker build --target production-worker --load` |
| 6b | Validate worker imports | `import src.workers.workflow_worker; import src.workers.actors` |
| 6c | Push worker | Naar ACR |
| **Secrets & Migraties** | | |
| 7 | Push secrets to Key Vault | `database-url`, `secret-key`, `jwt-secret-key` naar `sanskriti-kv-stg` |
| 8a | Update migration-job image | Patch Container App Job via `az rest` (image + secrets + env) |
| 8b | Run migrations | `az containerapp job start` + poll loop (30x, 10s interval, exit 1 bij failure/timeout) |
| **Deploy** | | |
| 9 | Deploy backend-staging | `az containerapp update` met env vars |
| 10 | Deploy frontend-staging | `az containerapp update` |
| 11 | Deploy worker-staging | `az containerapp update` (of `create` als eerste keer) |
| 12 | Deploy Activepieces | Optioneel — alleen als `STAGING_AP_ENCRYPTION_KEY` is ingesteld |
| **Verificatie** | | |
| 13 | Health check | Retry loop: 5 pogingen, 20s interval, continue-on-error |
| 14 | Smoke tests | `/health` detail + `/docs` endpoint check, continue-on-error |
| 15 | Build summary | Overzicht van gedeployde images |
| **Opruiming** | | |
| 16 | ACR tag cleanup | Verwijdert oude `develop-*` tags, behoudt de laatste 10 per repository |

### Tags

Elke build push twee tags per component:
- `<component>:staging` — huidige staging versie
- `<component>:develop-<sha>` — specifieke commit voor rollback

---

## 4. CD Productie pipeline

**Bestand:** `.github/workflows/cd-production.yml`
**Trigger:** Tag `v*.*.*` op develop; `workflow_dispatch`
**Concurrency:** `cd-production`, cancel-in-progress: **false**
**Timeout:** 45 minuten
**Environment:** `production` (URL: https://www.sanskritisetu.org)

### Stappen

| # | Stap | Beschrijving |
|---|------|-------------|
| 0 | Checkout | Met `fetch-depth: 0` voor tag-verificatie |
| 1 | Verificeer tag op develop | Controleert dat de tag op een develop-commit staat |
| 2 | Azure login + ACR login | Authenticatie |
| 3 | Set up Docker Buildx + Cache | BuildKit + layer cache |
| **Secrets** | | |
| 4 | Push secrets to Key Vault | `database-url`, `secret-key`, `jwt-secret-key` naar `sanskriti-kv-prd` |
| **Build & Validatie** | | |
| 5a | Build backend | `docker buildx build --target production-api --load` met cache |
| 5b | Validate migration chain | Offline dry-run: chain compile + single head check |
| 5c | Push backend | Tags: `<tag>` + `latest` |
| 6a | Build frontend | `docker build --load` met hardcoded productie-URL's |
| 6b | Validate frontend image | `nginx -t` + `index.html` check |
| 6c | Push frontend | Tags: `<tag>` + `latest` |
| 7a | Build worker | `docker build --target production-worker --load` |
| 7b | Validate worker imports | Import check op workflow_worker + actors |
| 7c | Push worker | Tags: `<tag>` + `latest` |
| **Migraties** | | |
| 8a | Update migration-job image | Patch via `az rest` met Key Vault secrets |
| 8b | Run migrations | `az containerapp job start` + poll (30x, 10s interval, exit 1 bij failure/timeout) |
| **Deploy** | | |
| 9 | Deploy backend | `az containerapp update` met `${{ secrets.PROD_BACKEND_APP }}` |
| 10 | Deploy frontend | `az containerapp update` met `${{ secrets.PROD_FRONTEND_APP }}` |
| 11 | Deploy worker | `az containerapp update` met `${{ secrets.PROD_WORKER_APP }}` |
| 12 | Deploy Activepieces | Optioneel — alleen als `PROD_AP_ENCRYPTION_KEY` is ingesteld |
| **Verificatie** | | |
| 13 | Health check | Retry loop: 5 pogingen, 20s interval, **faalt pipeline** (geen continue-on-error) |
| 14 | Smoke tests | `/health` detail + `/docs` endpoint, continue-on-error |
| **Post-deploy** | | |
| 15 | Update main branch | Merge naar main via `GH_PAT_MAIN_MERGE`, continue-on-error |
| 16 | Warn if main merge failed | `::warning::` annotatie als merge mislukt — handmatige actie vereist |
| 17 | GitHub Release aanmaken | Automatisch met `gh release create --generate-notes` |

### Tags

Elke build push twee tags per component:
- `<component>:<versietag>` — bijv. `backend:v1.2.3`
- `<component>:latest` — huidige productie versie

### Verschil met staging

| Aspect | Staging | Productie |
|--------|---------|-----------|
| Tag-verificatie | Nee | Ja (tag moet op develop staan) |
| Concurrency | cancel-in-progress: true | cancel-in-progress: false |
| Frontend URL | Dynamisch (FQDN lookup) | Hardcoded (`api.sanskritisetu.org`) |
| Health check | continue-on-error | **Blokkerend** |
| Worker deploy | Create-or-update | Update (via `${{ secrets.PROD_WORKER_APP }}`) |
| Main merge | Nee | Ja (met warning bij falen) |
| GitHub Release | Nee | Ja |
| ACR cleanup | Ja (develop-* tags) | Nee |

---

## 5. Rollback workflow

**Bestand:** `.github/workflows/rollback.yml`
**Trigger:** `workflow_dispatch` (handmatig via GitHub Actions UI)
**Timeout:** 15 minuten

### Invoerparameters

| Parameter | Type | Verplicht | Beschrijving |
|-----------|------|-----------|-------------|
| `environment` | choice | Ja | `staging` of `production` |
| `target_tag` | string | Ja | Image tag om naar terug te draaien (bijv. `v1.2.3` of `develop-abc1234`) |
| `components` | string | Ja | Komma-gescheiden componenten: `backend,frontend,worker` |

### Stappen

1. **Azure login** — authenticatie
2. **Determine resource group** — automatisch op basis van environment
3. **Determine app names** — haalt Container App namen op uit secrets
4. **Verify images exist** — controleert dat alle gevraagde images bestaan in ACR
5. **Rollback components** — `az containerapp update --image` per component
6. **Health check** — retry loop (5 pogingen, 15s interval)

### Gebruik

```bash
# Via GitHub CLI
gh workflow run rollback.yml \
  -f environment=production \
  -f target_tag=v1.2.3 \
  -f components="backend,frontend,worker"
```

Of via de GitHub Actions UI: Actions > Rollback > Run workflow.

---

## 6. Activepieces integratie

Activepieces is een optioneel workflow-automatiseringsplatform dat in zowel staging als productie wordt gedeployd.

### Voorwaarden

De deploy wordt **overgeslagen** als de encryptie-sleutel niet is ingesteld:
- Staging: `STAGING_AP_ENCRYPTION_KEY`
- Productie: `PROD_AP_ENCRYPTION_KEY`

### Configuratie

| Secret | Beschrijving |
|--------|-------------|
| `*_AP_ENCRYPTION_KEY` | 32-char encryptiesleutel (`openssl rand -hex 16`) |
| `*_AP_JWT_SECRET` | JWT secret (`openssl rand -hex 32`) |
| `*_REDIS_HOST` | Azure Cache for Redis hostname |
| `*_AP_URL` | Publieke URL van Activepieces |

### Image versie

De Activepieces image tag wordt beheerd via de `AP_IMAGE_TAG` environment variable in beide workflow bestanden (momenteel `0.81.4`). Bij wijziging ook `activepieces/Dockerfile` updaten.

---

## 7. GitHub Secrets

### Verplichte secrets

| Secret | Beschrijving |
|--------|-------------|
| `AZURE_CREDENTIALS` | JSON met clientId, clientSecret, subscriptionId, tenantId |
| `ACR_PASSWORD` | Azure Container Registry wachtwoord |
| `GH_PAT_MAIN_MERGE` | GitHub PAT voor main branch merge + release creation |

### Staging secrets

| Secret | Beschrijving |
|--------|-------------|
| `STAGING_RESOURCE_GROUP` | Azure resource group naam voor staging |
| `STAGING_BACKEND_APP` | Container App naam voor staging backend |
| `STAGING_FRONTEND_APP` | Container App naam voor staging frontend |
| `STAGING_DATABASE_URL` | PostgreSQL connection string |
| `STAGING_SECRET_KEY` | Applicatie secret key |
| `STAGING_JWT_SECRET_KEY` | Separate JWT signing secret voor staging |

### Productie secrets

| Secret | Beschrijving |
|--------|-------------|
| `PROD_BACKEND_APP` | Container App naam voor productie backend |
| `PROD_FRONTEND_APP` | Container App naam voor productie frontend |
| `PROD_WORKER_APP` | Container App naam voor productie worker |
| `PROD_DATABASE_URL` | PostgreSQL connection string |
| `PROD_SECRET_KEY` | Applicatie secret key |
| `PROD_JWT_SECRET_KEY` | Separate JWT signing secret voor productie |

### Nieuwe secrets aanmaken (eenmalig)

Na de pipeline hardening sprint moeten deze 3 secrets aangemaakt worden:

```bash
# JWT signing secrets (gescheiden van applicatie secret)
gh secret set PROD_JWT_SECRET_KEY --body "$(openssl rand -hex 32)"
gh secret set STAGING_JWT_SECRET_KEY --body "$(openssl rand -hex 32)"

# Worker Container App naam
gh secret set PROD_WORKER_APP --body "worker"
```

Als de secrets environment-scoped moeten zijn (i.p.v. repository-breed):

```bash
gh secret set PROD_JWT_SECRET_KEY --env production --body "$(openssl rand -hex 32)"
gh secret set STAGING_JWT_SECRET_KEY --env staging --body "$(openssl rand -hex 32)"
gh secret set PROD_WORKER_APP --env production --body "worker"
```

**Let op:** Het aanmaken van `PROD_JWT_SECRET_KEY` en `STAGING_JWT_SECRET_KEY` maakt alle bestaande JWT-tokens ongeldig. Gebruikers moeten opnieuw inloggen na de volgende deploy.

### Activepieces secrets (optioneel)

| Secret | Beschrijving |
|--------|-------------|
| `STAGING_AP_ENCRYPTION_KEY` | 32-char encryptiesleutel |
| `STAGING_AP_JWT_SECRET` | JWT secret |
| `STAGING_REDIS_HOST` | Redis hostname (staging) |
| `STAGING_AP_URL` | Publieke URL Activepieces (staging) |
| `PROD_AP_ENCRYPTION_KEY` | 32-char encryptiesleutel |
| `PROD_AP_JWT_SECRET` | JWT secret |
| `PROD_REDIS_HOST` | Redis hostname (productie) |
| `PROD_AP_URL` | Publieke URL Activepieces (productie) |

---

## 8. Lokale kwaliteitsbewakers

### pre-deploy-check.sh

**Locatie:** `scripts/pre-deploy-check.sh`

Dit script MOET draaien voor elke deploy. Het valideert:

| Check | Beschrijving |
|-------|-------------|
| 1. Docker-bestanden in git | Controleert dat alle `COPY`-bronnen in de Dockerfile ook in git zitten |
| 2. Docker build backend | `docker build --target production-api` |
| 3. Docker build frontend | `docker build frontend/` |
| 3b. Migratie-keten validatie | Chain compile (`alembic upgrade head --sql`) + single head check |
| 4. GitHub Secrets | Controleert verplichte secrets via `gh secret list` |
| 5. Azure SP toegang | Controleert roltoewijzingen van de service principal |

**Stap 3b** (migratie-keten) werd toegevoegd tijdens de hardening sprint. Het draait dezelfde validatie als de CI en CD pipelines: de migratie-keten wordt offline gecompileerd en er wordt gecontroleerd dat er precies 1 head is. Dit vangt import-fouten en gebroken ketens lokaal op, voordat ze de pipeline bereiken.

### Gebruik

```bash
bash scripts/pre-deploy-check.sh
```

Als het script faalt: fix het probleem, draai het script opnieuw, en pas dan deployen.

---

## 9. Azure-infrastructuur

| Wat | Waar |
|-----|------|
| Productie | West Europe -- **NIET INGERICHT** sinds 2026-05-11, zie `docs/infra/AZURE_OMGEVINGEN.md` |
| Staging | Resource group via `STAGING_RESOURCE_GROUP` secret, North Europe |
| Container Registry | `sanskritisetuacr.azurecr.io`, UK South |
| Key Vault staging | `sanskriti-kv-stg` |
| Key Vault productie | `sanskriti-kv-prd` |
| Service principal | `sanskritisetu-github-actions` (App ID: `34923a6f-3f24-47f1-bb56-ce8416bc850f`) |
| Subscription ID | `<azure-subscription-id>` |

### Container Apps

| Component | Staging | Productie |
|-----------|---------|-----------|
| Backend | `${{ secrets.STAGING_BACKEND_APP }}` | `${{ secrets.PROD_BACKEND_APP }}` |
| Frontend | `${{ secrets.STAGING_FRONTEND_APP }}` | `${{ secrets.PROD_FRONTEND_APP }}` |
| Worker | `worker-staging` (hardcoded) | `${{ secrets.PROD_WORKER_APP }}` |
| Migration Job | `migration-job` | `migration-job` |
| Activepieces | `activepieces-staging` | `activepieces` |

---

## 10. Opgeloste problemen

| # | Probleem | Oorzaak | Fix |
|---|----------|---------|-----|
| P1 | Pipeline faalt met "No subscriptions found" | AZURE_CREDENTIALS onvolledig | subscriptionId + tenantId toegevoegd; Contributor-rol toegewezen |
| P2 | Docker build "No such file or directory" | Bestand niet in git | `git ls-files --error-unmatch` check in pre-deploy |
| P3 | Docker build applicatie-import errors | RUN-stap in Dockerfile importeert applicatiecode | Verwijderd; validatie via pytest |
| P4 | Frontend test heap OOM | Windows: npx vitest zonder memory limit | `npm run test:unit` met cross-env NODE_OPTIONS |
| P5 | Activepieces deploy faalt | Secrets niet ingesteld | Graceful skip als encryptiesleutel ontbreekt |
| P6 | Activepieces env vars array expansion | Bash array niet correct ge-expandeerd | `"${AP_ENVVARS[@]}"` met juiste quoting |
| P7 | Migration timeout zonder exit code | Poll loop eindigde zonder `exit 1` | `exit 1` na timeout loop toegevoegd |
| P8 | Health check single attempt | Enkele curl zonder retry | Retry loop: 5 pogingen, 20s interval |
| P9 | JWT secret gedeeld tussen omgevingen | Zelfde `SECRET_KEY` voor app + JWT signing | Aparte `STAGING_JWT_SECRET_KEY` en `PROD_JWT_SECRET_KEY` secrets |
| P10 | Worker app naam hardcoded in productie | `worker` hardcoded i.p.v. configureerbaar | Geparametriseerd via `${{ secrets.PROD_WORKER_APP }}` |
| P11 | Activepieces array expansion fix | Bash array niet correct doorgegeven aan `az containerapp` | Correcte `"${AP_ENVVARS[@]}"` syntax |
| P12 | Geen concurrency control of timeout | Meerdere deploys tegelijk mogelijk | `concurrency` group + `timeout-minutes: 45` toegevoegd |
| P13 | Migration CLI inconsistent | Mix van `az rest` en `az containerapp job` | Gestandaardiseerd: `az containerapp job start/execution show` voor run/poll |
| P14 | Worker image niet gevalideerd | Push zonder import-controle | Validate stap: `import src.workers.workflow_worker; import src.workers.actors` |
| P15 | Frontend image niet gevalideerd | Push zonder nginx/content check | Validate stap: `nginx -t` + `index.html` check |
| P16 | Main merge failure stopt deploy | Harde error bij merge-probleem | `continue-on-error: true` + `::warning::` annotatie |

---

## 11. Bekende onvolkomenheden

| # | Probleem | Prioriteit | Toelichting |
|---|----------|-----------|-------------|
| C11 | ACR_PASSWORD als plain-text in migration-job | Laag | De `acr-password` secret in het migration-job patch JSON wordt als plain-text value doorgegeven i.p.v. Key Vault referentie. Dit is een beperking van de Container App Jobs API. Risico is beperkt omdat het alleen tijdens de migration-job uitvoering zichtbaar is. |
| C12 | Geen database backup voor migratie | Laag | Er wordt geen automatische database backup gemaakt voor migraties worden uitgevoerd. Bij een falende migratie moet handmatig worden teruggedraaid. Azure heeft point-in-time restore, maar dit is niet geautomatiseerd in de pipeline. |

---

## 12. Deploy-procedure

### Standaard deploy (staging + productie)

```bash
# 1. Pre-deploy validatie
bash scripts/pre-deploy-check.sh

# 2. Merge naar develop (triggert CD Staging)
git checkout develop
git merge feature/mijn-feature --no-edit
git push origin develop

# 3. Verifieer staging deploy
#    Controleer GitHub Actions: cd-staging workflow
#    Controleer staging: https://<staging-backend>/health

# 4. Tag aanmaken (triggert CD Productie)
git tag v1.2.3
git push origin v1.2.3

# 5. Verifieer productie deploy
#    Controleer GitHub Actions: cd-production workflow
#    Controleer productie: https://api.sanskritisetu.org/health
```

### Rollback procedure

Bij problemen na een deploy kan snel worden teruggedraaid via de rollback workflow:

```bash
# Via GitHub CLI
gh workflow run rollback.yml \
  -f environment=production \
  -f target_tag=v1.2.2 \
  -f components="backend,frontend,worker"

# Of via GitHub Actions UI:
# Actions > Rollback > Run workflow
```

**Belangrijk:**
- De rollback workflow draait alleen `az containerapp update` — het voert GEEN migraties terug.
- Bij een falende migratie: gebruik Azure point-in-time restore of handmatige rollback.
- Controleer eerst welke tags beschikbaar zijn in ACR.

### Noodprocedure

1. **Rollback** via bovenstaande workflow
2. **Logs bekijken:** `az containerapp logs show --name <app> --resource-group <rg> --tail 50`
3. **Pipeline logs:** `gh run view <run-id> --log-failed`

---

## 13. CI workflow detail

**Bestand:** `.github/workflows/ci-feature.yml`

### Job: Python

| Stap | Beschrijving |
|------|-------------|
| Checkout | Code ophalen |
| Setup Python 3.11 | Met pip cache |
| Install dependencies | `requirements.txt` + `requirements-test.txt` |
| Ruff lint | `ruff check src/ --exclude src/alembic` |
| Unit tests | pytest met exclusies voor postgres/redis/ollama-afhankelijke tests |

### Job: Frontend

| Stap | Beschrijving |
|------|-------------|
| Checkout | Code ophalen |
| Setup Node 20 | Met npm cache |
| Install dependencies | `npm ci` |
| Unit tests | `npm run test:unit` met verbose reporter |
| Build check | `npm run build` |

**Timeout:** 15 minuten

### Job: Docker Build Validation

| Stap | Beschrijving |
|------|-------------|
| Checkout | Code ophalen |
| Build backend | `docker build --target production-api --load` |
| Validate migration chain | `alembic upgrade head --sql` (offline, geen database nodig) |
| Single head check | Controleert dat er precies 1 migratie-head is |
| Build frontend | `docker build` met test `VITE_API_URL` |

**Timeout:** 20 minuten

### Job: Security Scan

| Stap | Beschrijving |
|------|-------------|
| Checkout | Code ophalen |
| Setup Python 3.11 | Met pip cache |
| Install bandit | Security scanner |
| Bandit scan | Scant `src/` (excl. tests en alembic) |
| Check critical findings | Faalt als er HIGH severity + HIGH confidence issues zijn |

**Timeout:** 10 minuten
