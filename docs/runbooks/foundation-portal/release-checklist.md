# Runbook: Release Checklist

**Doel**: kwaliteitsgate vóór elke release naar productie.
**Eigenaar**: Release manager (rotatie).

Gebaseerd op CLAUDE.md PR-checklist + deploy-richtlijnen.

## Pre-release (development branch)

### Code-kwaliteit

- [ ] Kwaliteitsloop doorlopen per task (CLAUDE.md "Vóór elke code wegschrijven"):
  - [ ] Code review subagent
  - [ ] Quality review subagent (lint, secrets, OWASP)
  - [ ] Happy + unhappy path tests
  - [ ] User behavioral test
  - [ ] Integration tests tegen echte backend
- [ ] Geen `any` types in TypeScript
- [ ] Geen `print()` of `console.log()` in productie-paden
- [ ] Geen hardcoded secrets / URLs / poorten
- [ ] Geen `datetime.now()` of `datetime.utcnow()` zonder tz
- [ ] Geen `tenant_id` in request body
- [ ] Alle list-endpoints hebben `limit/offset` paginering
- [ ] Alle Audit-log writes via `best_effort()`
- [ ] Alle nieuwe repository-methodes hebben `tenant_id` filter + isolatietest
- [ ] Elke `useEffect` met timer/listener heeft cleanup
- [ ] Elke nieuwe WS-hook heeft `mountedRef` guard
- [ ] ASCII-only in source code

### Tests

- [ ] `pytest --stepwise` slaagt (geen failures)
- [ ] Coverage >= 95% (`pytest --cov=src --cov-fail-under=95`)
- [ ] `pytest -m security` slaagt
- [ ] `pytest -m integration` slaagt tegen echte DB (poort 5455)
- [ ] `pytest -m gdpr` slaagt
- [ ] Frontend `npm run test:unit` slaagt
- [ ] Frontend `npm run type-check` zonder errors
- [ ] Frontend `npm run lint` zonder errors
- [ ] Frontend `npm run test:e2e` (Playwright) slaagt
- [ ] WCAG axe-core scan: 0 critical violations
- [ ] Lighthouse a11y score >= 95

### Database

- [ ] Nieuwe Alembic-migratie heeft werkende `downgrade()` (geen `pass`)
- [ ] `alembic -c src/alembic.ini upgrade head --sql` slaagt offline
- [ ] `alembic heads` toont precies 1 head
- [ ] `alembic check` toont geen drift
- [ ] Migratie heeft `_is_offline()` guard waar nodig
- [ ] Test in `tests/integration/test_alembic_chain.py` voor nieuwe migratie

### Security

- [ ] `bandit -r src/` zonder high-severity findings
- [ ] `pip-audit` zonder kritieke CVE's
- [ ] `npm audit` zonder high-severity vulns
- [ ] PUBLIC_PREFIXES gereviewed bij nieuwe endpoints
- [ ] Rate-limit decorators op nieuwe endpoints
- [ ] JWT scope-check op nieuwe admin-endpoints

### Documentatie

- [ ] CHANGELOG.md bijgewerkt
- [ ] CLAUDE.md "Wat IS gebouwd" tabel bijgewerkt
- [ ] SPRINT-TRACKER.md bijgewerkt
- [ ] AGENTS.md bijgewerkt indien relevant
- [ ] Runbook bijgewerkt indien proces-impact
- [ ] ADR aangemaakt indien architectuur-keuze

## CI gate

Push naar `develop` triggert:
- [ ] CI-feature workflow groen op GitHub Actions
- [ ] Container build succes
- [ ] Smoke tests staging slagen

## Pre-deploy (productie tag)

```bash
# Verplicht vóór tag (CLAUDE.md "Vóór elke deploy"):
bash scripts/pre-deploy-check.sh
```

Het script controleert:
1. Alle Dockerfile-bestanden in git
2. `docker build --target production-api .` slaagt lokaal
3. `docker build frontend/` slaagt lokaal
4. GitHub Secrets aanwezig
5. Azure SP heeft roltoewijzingen

- [ ] Script slaagt zonder errors
- [ ] Geen breaking-changes zonder migratie-pad
- [ ] Stakeholders geinformeerd (release-notes)
- [ ] Maintenance-window aangekondigd indien downtime > 1 min

## Tag & deploy

```bash
git checkout develop
git pull
git tag -a v{x.y.z} -m "Release v{x.y.z}: {korte omschrijving}"
git push origin v{x.y.z}
```

Pipeline triggert CD-prod automatisch.

## Post-deploy verificatie

Binnen 15 min:

- [ ] Health endpoints groen op productie:
  - [ ] `GET https://api.sanskritisetu.org/health`
  - [ ] `GET https://api.sanskritisetu.org/health/ready`
- [ ] Smoke tests slagen tegen prod-URL
- [ ] Status-page groen
- [ ] Sentry toont geen nieuwe errors
- [ ] Grafana dashboards blijven groen 30 min
- [ ] Eerste cureren-actie werkt (test met test-tenant)
- [ ] Eerste upload-flow werkt (test met test-tenant)

## Rollback-criterium

Direct rollback bij:
- Health endpoint faalt > 5 min
- Error rate > 5%
- Data-corruptie gemeld
- Security-vulnerability ontdekt

Rollback-procedure:
```bash
# Re-tag previous werkende version
git tag -a v{x.y.z+hotfix} -m "Rollback to v{x.y.previous}"
git push origin v{x.y.z+hotfix}
```

Nooit `git push --force` op tag.

## Communicatie

| Wanneer | Wat | Kanaal |
| --- | --- | --- |
| 24u vóór release | Aankondiging | Slack #releases + e-mail curators |
| Bij start deploy | "Deploy gestart" | Slack #releases |
| Bij succes | "Deploy klaar, verificatie loopt" | Slack #releases |
| 30 min na deploy | "Verificatie OK" of rollback | Slack #releases + status-page |
| Bij rollback | Public statement | status-page + e-mail |

## Audit
Elke release loggen in `docs/operations/releases.md`:
- Tag, datum, uitvoerder
- Wijzigingen (CHANGELOG-link)
- Issues post-release
- Rollback ja/nee + reden
