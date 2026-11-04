# Backend Feature Specification

## Metadata
- Feature ID: BE-001
- Feature naam: Platform Runtime & Application Factory
- Status: ACTIEF
- Auteur: Rakesh Ramkhelawan
- Reviewer: --
- Datum: 2026-05-25
- Gerelateerde user story / ticket: ADR-010, ADR-011
- Gerelateerde router / module: src/main.py, src/core/app_lifespan.py, src/core/env_loader.py, src/core/config/config_validator.py
- Gerelateerde frontend endpoints: alle (platform-breed)
- Gerelateerde database tabellen: alle (via lifespan init: tenants, users, roles)
- Versie: 1.0

---

## Trainingssamenvatting

### Flow: Backend platform startup (cold boot)

- **Actor:** Operator / Gunicorn supervisor (productie) of `uvicorn --reload` (development)
- **Voorwaarde:** Docker host beschikbaar, `postgres` en `redis` services zijn `healthy`, env vars geladen via `src/core/env_loader.py` (`.env` -> `.env.{ENVIRONMENT}` -> `.env.local`), `DATABASE_URL` is gezet.
- **Actie:** Operator start container of supervisor doet `gunicorn src.main:app -k uvicorn.workers.UvicornWorker --workers N --max-requests 1000 --max-requests-jitter 50` (ADR-010/011).
- **Systeemreactie:** `src/main.py` roept `setup_environment()` aan (env_loader), `validate_config_at_startup()` (guarded met TESTING-check), bouwt FastAPI-app via `create_app()`, registreert middleware-stack (zie BE-003), registreert routers via `router_registry`, voert Alembic-migraties uit (`alembic upgrade head`) en triggert `app_lifespan` startup-hooks (proactive deps wiring SP-WE-21, council cache invalidator, feature flag manager).
- **Succesrespons:** Backend luistert op poort 8000, `/health` en `/status` retourneren 200, eerste `Application startup complete` log-regel verschijnt, Gunicorn workers worden klaargemaakt voor request-verkeer.
- **Foutrespons:** Bij ontbrekende verplichte env var: `validate_config_at_startup()` doet `sys.exit(1)` met expliciete foutmelding. Bij ontbrekende migratie of DB-onbereikbaarheid: Alembic fail-fast, supervisor herstart de worker (`max_requests` of crash-loop). Bij singleton-init failure (LLM provider, Redis): graceful degradation met logger.warning, app blijft beschikbaar zonder die feature.
- **Uitzonderingen:** `TESTING=1` of `PYTEST_CURRENT_TEST` aanwezig -> validator en singletons skip module-level side effects om pytest-collectietijd te beperken (AUDIT-COLL-01/02/03).

