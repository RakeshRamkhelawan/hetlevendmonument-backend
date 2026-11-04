# Fase 5 Complete CI/CD Pipeline

## Overzicht

Deze CI/CD pipeline is ontworpen voor de **SanskritiSetu** project en biedt een complete end-to-end oplossing voor geautomatiseerde tests, security scanning, en deployment.

## Features

### 1. Parallelle Job Executie
- Jobs worden parallel uitgevoerd waar mogelijk voor snelle feedback
- Change detection om alleen relevante jobs te draaien
- Concurrency control om duplicate runs te voorkomen

### 2. Complete Test Piramide

```
    /\
   /  \
  / E2E \      <- Playwright E2E tests (Job 7)
 /________\
/          \
/ Integration \  <- Backend integration tests (Job 5)
/______________\
/              \
/     Unit       \ <- Backend & Frontend unit tests (Jobs 4, 6)
/__________________\
```

### 3. Security Scanning
- **Bandit**: Python code security scan
- **Safety**: Dependency vulnerability check
- **Trivy**: Container en filesystem scanning
- **Custom Audit**: Project-specifieke security checks

### 4. Performance Monitoring
- Prometheus metrics validatie
- Performance benchmark tests
- Database query performance checks

### 5. Quality Gates
- Black/Isort formatting checks
- Ruff linting
- MyPy type checking
- ESLint/TypeScript voor frontend

## Workflow Jobs

| Job | Naam | Beschrijving | Condities |
|-----|------|--------------|-----------|
| 1 | Change Detection | Detecteert welke bestanden zijn gewijzigd | Altijd |
| 2 | Backend Quality | Code quality checks voor backend | Backend changes |
| 3 | Frontend Quality | Code quality checks voor frontend | Frontend changes |
| 4 | Backend Unit Tests | Unit tests met coverage | Backend changes |
| 5 | Backend Integration Tests | Integration tests met DB | Backend changes, niet-PR |
| 6 | Frontend Unit Tests | Vitest unit tests | Frontend changes |
| 7 | E2E Tests | Playwright end-to-end tests | Backend of Frontend changes |
| 8 | Security Audit | Security scanning | Scheduled of manual |
| 9 | Performance Check | Performance monitoring | Backend changes |
| 10 | Docker Build Test | Docker image build | Docker/Backend/Frontend changes |
| 11 | Deploy Staging | Deploy naar staging | Develop branch push |
| 12 | Deploy Production | Deploy naar productie | Main branch push |
| 13 | Summary | CI samenvatting | Altijd |

## Triggers

```yaml
on:
  push:
    branches: [main, develop, staging]
  pull_request:
    branches: [main, develop]
  schedule:
    - cron: '0 2 * * *'  # Daily security scan
  workflow_dispatch:
    # Manual trigger met opties:
    # - skip_e2e: boolean
    # - run_security_audit: boolean
```

## Omgevingsvariabelen

| Variable | Standaard | Beschrijving |
|----------|-----------|--------------|
| `PYTHON_VERSION` | `3.11` | Python versie |
| `NODE_VERSION` | `20` | Node.js versie |
| `COVERAGE_THRESHOLD` | `26` | Minimale coverage percentage |
| `TESTING` | `"1"` | Test mode flag |

## Secrets (vereist voor deployment)

```yaml
# GitHub Secrets die geconfigureerd moeten worden:
- SSH_PRIVATE_KEY        # Voor server toegang
- DOCKER_REGISTRY_TOKEN  # Voor Docker registry
- KUBECONFIG            # Voor Kubernetes deployment
- DATABASE_URL          # Production database
- SECRET_KEY            # Application secret
- JWT_SECRET_KEY        # JWT signing secret
```

## Gebruik

### Lokale testing

```bash
# Run alle tests
pytest tests/ -v --cov=src --cov-report=term-missing

# Run E2E tests
npx playwright test

# Run security audit
python scripts/security_audit.py

# Run performance checks
pytest tests/performance/ -v
```

### Manual Workflow Trigger

1. Ga naar **Actions** tab in GitHub
2. Selecteer **Fase 5 Complete CI/CD**
3. Klik **Run workflow**
4. Configureer opties:
   - Skip E2E tests: `true`/`false`
   - Run security audit: `true`/`false`

## Artifacts

Alle jobs uploaden artifacts die bewaard worden:

| Artifact | Retentie | Beschrijving |
|----------|----------|--------------|
| bandit-report | 30 dagen | Security scan results |
| backend-coverage | 7 dagen | Coverage XML reports |
| frontend-test-results | 7 dagen | Frontend test output |
| playwright-report | 30 dagen | E2E test rapporten |
| playwright-results | 30 dagen | E2E test artifacts |
| security-reports | 30 dagen | Alle security scans |

## Troubleshooting

### E2E tests falen
```bash
# Local debug
npx playwright test --headed --debug

# Update snapshots
npx playwright test --update-snapshots
```

### Coverage onder threshold
```bash
# Genereer HTML rapport
pytest tests/ --cov=src --cov-report=html

# Bekijk rapport
open htmlcov/index.html
```

### Security issues
```bash
# Run bandit lokaal
bandit -r src/ -f screen -ll

# Check dependencies
safety check -r requirements.txt
```

## Status Badges

Voeg deze toe aan je README.md:

```markdown
![Fase 5 CI/CD](https://github.com/USERNAME/REPO/workflows/Fase%205%20Complete%20CI/CD/badge.svg)
![Quality Gate](https://github.com/USERNAME/REPO/workflows/Quality%20Gate/badge.svg)
![P0 Critical Tests](https://github.com/USERNAME/REPO/workflows/P0%20Critical%20Tests/badge.svg)
```

## Toekomstige Verbeteringen

- [ ] Parallelle Playwright tests (sharding)
- [ ] Cypress E2E tests als alternatief
- [ ] Load testing met k6
- [ ] Visual regression testing
- [ ] Automated dependency updates (Dependabot)
- [ ] Deploy previews voor PRs

## Ondersteuning

Voor vragen of problemen met de CI/CD pipeline:
1. Check de workflow logs in GitHub Actions
2. Raadpleeg de artifact uploads
3. Zie `AGENTS.md` voor project context
