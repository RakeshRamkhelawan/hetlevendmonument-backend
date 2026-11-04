# Fase 10: CI/CD Pipeline Guide

> **Laatst getest:** Maart 2026 via PR #test-ci-cd-pipeline

Deze guide beschrijft de CI/CD pipeline voor de SanskritiSetu Company Layer.

## Overzicht

De CI/CD pipeline omvat:

1. **Backend Lint & Type Check** - Ruff en MyPy
2. **Backend Unit Tests** - Pytest met coverage
3. **Backend Integration Tests** - Met PostgreSQL
4. **Frontend Lint & Build** - ESLint, TypeScript, Vite
5. **Frontend Unit Tests** - Vitest met coverage
6. **E2E Tests** - Playwright met Chromium/Firefox/WebKit
7. **Security Scanning** - Bandit, gitleaks, en npm audit
8. **Config Sync Check** - `.env.example` synchronisatie met Pydantic Settings
9. **Docker Build & Push** - Container images naar GHCR

## GitHub Actions Workflows

### Company Layer CI/CD

**Bestand:** `.github/workflows/company-layer-ci.yml`

**Triggers:**
- Push naar `main` of `develop`
- Pull requests naar `main` of `develop`
- Wijzigingen in:
  - `src/core/company/**`
  - `src/core/api/v1/company/**`
  - `frontend/src/components/company/**`
  - `frontend/src/components/external-agents/**`
  - `frontend/src/components/board/**`
  - `tests/**`
  - `frontend/tests/**`

### Jobs

| Job | Beschrijving | Dependencies |
|-----|--------------|--------------|
| `backend-lint` | Ruff linter + MyPy type check | - |
| `backend-unit-tests` | Pytest unit tests | - |
| `backend-integration-tests` | PostgreSQL integratietests | - |
| `frontend-lint-build` | ESLint + TypeScript + Vite build | - |
| `frontend-unit-tests` | Vitest unit tests | - |
| `e2e-tests` | Playwright E2E tests | backend-integration-tests, frontend-build |
| `security-scan` | Bandit + gitleaks + npm audit | - |
| `config-sync-check` | `.env.example` vs Pydantic Settings validatie | - |
| `docker-build-push` | Build & push naar GHCR | backend-integration-tests, frontend-unit-tests, e2e-tests |

## Lokale E2E Testing

### Met Docker Compose

```bash
# Start de E2E omgeving
docker-compose -f docker-compose.e2e.yml up -d

# Wacht tot alles gestart is
sleep 10

# Run E2E tests
docker-compose -f docker-compose.e2e.yml exec playwright npx playwright test tests/e2e/company/

# Stop de omgeving
docker-compose -f docker-compose.e2e.yml down
```

### Lokaal met bestaande services

```bash
# Terminal 1: Start backend
cd backend
uvicorn src.main:app --reload --port 8000

# Terminal 2: Start frontend
cd frontend
npm run dev

# Terminal 3: Run E2E tests
cd frontend
npx playwright test tests/e2e/company/ --project=company-chromium
```

## Test Rapportage

### GitHub Actions Artifacts

Na elke run worden de volgende artifacts opgeslagen:

- `backend-coverage-report` - HTML coverage rapport
- `integration-test-results` - JSON test resultaten
- `frontend-coverage-report` - Vitest coverage
- `frontend-build` - Gebuild frontend
- `playwright-report` - HTML rapport met screenshots/videos
- `bandit-security-report` - Security scan resultaten

### Lokale Rapporten

```bash
# Backend coverage
pytest --cov=src/core/company --cov-report=html
open htmlcov/index.html

# Frontend coverage
npm run test:coverage
open coverage/index.html

# Playwright rapport
npx playwright test --reporter=html
npx playwright show-report
```

## Omgevingsvariabelen

### CI/CD Environment Variables

| Variable | Beschrijving | Standaard |
|----------|--------------|-----------|
| `PYTHON_VERSION` | Python versie | 3.13 |
| `NODE_VERSION` | Node.js versie | 20 |
| `POSTGRES_DB` | Test database naam | sanskritisetu_test |
| `DATABASE_URL` | Database connection string | - |
| `TESTING` | Test mode flag | 1 |

### Playwright Environment Variables

| Variable | Beschrijving | Standaard |
|----------|--------------|-----------|
| `BASE_URL` | Frontend URL | http://localhost:5173 |
| `API_URL` | Backend URL | http://localhost:8000 |
| `CI` | CI mode flag | - |

## Docker Images

Na succesvolle build op `main` branch:

```bash
# Pull images
docker pull ghcr.io/sanskritisetu/backend:latest
docker pull ghcr.io/sanskritisetu/frontend:latest

# Run locally
docker run -p 8000:8000 ghcr.io/sanskritisetu/backend:latest
docker run -p 5173:5173 ghcr.io/sanskritisetu/frontend:latest
```

## Troubleshooting

### Tests falen in CI maar lokaal niet

1. Check of alle services goed starten:
   ```bash
   docker-compose -f docker-compose.e2e.yml logs
   ```

2. Run tests met headed mode voor debugging:
   ```bash
   npx playwright test --headed
   ```

3. Bekijk Playwright trace:
   ```bash
   npx playwright show-trace test-results/trace.zip
   ```

### Database connectie problemen

1. Controleer of PostgreSQL draait:
   ```bash
   docker-compose -f docker-compose.e2e.yml ps
   ```

2. Check database logs:
   ```bash
   docker-compose -f docker-compose.e2e.yml logs postgres
   ```

### Flaky tests

- Verhoog timeouts in `playwright.config.ts`
- Gebruik `await page.waitForSelector()` voor elementen
- Voeg `retries` toe in CI configuratie

## Config Sync Check

Het `scripts/check_env_example_sync.py` script verifieert dat `.env.example` alle Pydantic Settings velden bevat:

```bash
# Lokaal draaien
python scripts/check_env_example_sync.py

# Output voorbeeld
OK: All Settings fields documented (warnings above for non-Settings keys)
```

**Exit codes:**
- `0` — Alle Settings velden zijn gedocumenteerd in `.env.example`
- `1` — Settings velden ontbreken in `.env.example` (CI faalt)

**Wanneer toevoegen:**
- Nieuw `Settings` veld in `src/core/config.py` of `src/core/config/config.py` → altijd `.env.example` updaten
- Uitzonderingen: voeg toe aan `KNOWN_EXCEPTIONS` in het script

## Best Practices

1. **Schrijf idempotente tests** - Tests moeten meerdere keren kunnen draaien
2. **Gebruik data-testid** - Voeg `data-testid` toe aan componenten voor stabiele selectors
3. **Clean up na tests** - Verwijder aangemaakte resources in `afterEach`
4. **Parallel uitvoering** - Gebruik `fullyParallel: true` waar mogelijk
5. **Screenshot bij falen** - Configureer `screenshot: 'only-on-failure'`

## CI/CD Pipeline Status

![Company Layer CI](https://github.com/sanskritisetu/sanskritisetu.org/workflows/Company%20Layer%20CI/CD/badge.svg)
