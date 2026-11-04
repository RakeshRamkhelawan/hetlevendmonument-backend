# BE-DEVOPS-001: pre-deploy-check.sh gewired als CI-gate

**Sprint:** AUDIT-ARCH-2026-07-02 Dag 2 losse P1 (DEVOPS-001)
**Datum:** 2026-07-02
**Status:** APPROVED
**ADR:** ADR-010

## Probleem

`scripts/pre-deploy-check.sh` -- dat Dag 1's FA-001-migratieblocker
reproduceerbaar aantoonde (`sa.inspect(op.get_bind())` crasht bij offline
dry-run) -- werd nergens in `.github/workflows/cd-production.yml` aangeroepen.
Rakesh moest het altijd handmatig draaien; een vergeten handmatige stap is
precies het soort regressie dat dit script had moeten voorkomen.

## Oplossing

Nieuwe job `pre-deploy-check` (needs: `[preflight]`, alleen `actions/checkout` +
`bash scripts/pre-deploy-check.sh`, geen Azure-credentials nodig aangezien het
script zijn eigen `sanskritisetu:migcheck`-image bouwt). `build-backend`/
`build-frontend`/`build-worker` hebben nu `needs: [preflight, pre-deploy-check]`
-- een falende check blokkeert alle 3 builds voordat er dure Docker-builds
starten.

## Trainingssamenvatting

- Actor: CD-pipeline (GitHub Actions), getriggerd door een versietag
- Voorwaarde: tag op `develop`, `preflight`-job geslaagd
- Actie: `pre-deploy-check`-job draait `scripts/pre-deploy-check.sh`
- Systeemreactie: bij falen (kapotte migratie-keten, ongeldige compose-config,
  ontbrekende Dockerfile-bestanden) stopt de pipeline voordat build-backend/
  -frontend/-worker starten
- Succesrespons: alle checks slagen, builds gaan door
- Foutrespons: pipeline faalt met exit 1, deploy wordt geblokkeerd
- Uitzonderingen: geen

## Test bewijs

```
pytest tests/architecture/test_predeploy_check_wired_in_cicd.py -v
2 passed

git show HEAD~1:.github/workflows/cd-production.yml | grep -c pre-deploy-check.sh
0  (bevestigd: was voorheen afwezig -- rode-test-eerst bewijs)
```

## Reviewers

code-reviewer: GO -- `needs:`-semantiek correct, script zelfvoorzienend
(bouwt eigen image, geen afhankelijkheid van build-backend's artifact).
security-reviewer: GO -- geen `secrets:`/`env:`-blok op de nieuwe job, geen
credential-blootstelling voor Azure-login.

## Backlog

Geen.
