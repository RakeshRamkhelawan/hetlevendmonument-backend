# Backend Feature Specification

## Metadata

- **Feature ID:** BE-DEB-003
- **Feature naam:** Vier ogen voor bestaande ondernemingen -- eenmalige migratie en uitleg bij het inrichten
- **Status:** Geimplementeerd
- **Auteur:** bouwer vier-ogen-bestaand
- **Reviewer:** code-reviewer + security-reviewer (subagents, Gate 2)
- **Datum:** 2026-10-05
- **Gerelateerde user story / ticket:** ADR-039 "Bestaande ondernemingen" (Rakesh 2026-10-05); brief `docs/agent-briefs/generated/2026-10-05-sprint-dag-vier-ogen-bestaande-ondernemingen.md`
- **Gerelateerde router / module:** `src/core/api/v1/tool_broker/four_eyes_router.py`, `src/core/governance/four_eyes.py`, `src/core/models/rbac_models.py`, `src/alembic/versions/20261007_vier_ogen_bestaande_tenants.py`
- **Gerelateerde frontend endpoints:** FE-PGS-033
- **Gerelateerde database tabellen:** `tenants.settings` (sleutels `four_eyes_actions`, `four_eyes_explanation_pending`, `four_eyes_set_by_migration`)
- **Versie:** 1.0

## Doel en scope

### Doel

Bestaande ondernemingen krijgen eenmalig de vier-ogen-standaard, en elke beheerder ziet bij
het inrichten in gewone taal wat de keuzes zijn.

### In scope

- Migratie: tenant zonder `four_eyes_actions` (settings NULL of object) krijgt de standaard,
  de uitlegmarkering en een merkteken; tenants met eigen sleutel of met een niet-object blijven
  ongemoeid. `downgrade()` draait alleen gemarkeerde rijen terug (NULL wordt weer NULL).
- `PUT /four-eyes` laat het merkteken vallen: een eigen keuze overleeft een downgrade.
- Nieuwe tenants krijgen de uitlegmarkering via `with_four_eyes_defaults`.
- `GET /api/v1/tools/hitl/four-eyes` geeft `explanation_pending`.
- `POST /api/v1/tools/hitl/four-eyes/explanation-confirmed`: beheerder, CSRF, 10/min, audit
  `four_eyes_explanation_confirmed`.

### Out of scope

- Andere tenantvelden, copilot, activepieces, debiteuren-flows.

## Technische beschrijving

### Architectuur

Router -> `tool_broker/dependencies.py` -> `governance/four_eyes.py`. Tenant uit de JWT
(`current_user.tenant_id`). De migratie werkt rij voor rij in Python (kolom is `json`).

### Foutafhandeling

403 voor een niet-beheerder, 404 als de tenant niet bestaat. Audit in `best_effort`.

## Acceptatiecriteria

- Migratie upgrade/downgrade/upgrade op Postgres: `tests/migrations/test_vier_ogen_bestaande_tenants_migratie.py` (7 tests).
- API: `tests/unit/api/test_vier_ogen_uitleg_api.py` (11 tests).

## Trainingssamenvatting

### Uitleg bevestigen

- Actor: beheerder van de onderneming
- Voorwaarde: `four_eyes_explanation_pending` staat aan
- Actie: past vinkjes aan en bevestigt
- Systeemreactie: PUT bewaart de keuze, POST haalt de markering weg en schrijft een auditregel
- Succes: de uitleg verschijnt niet meer
- Fout: 403 voor wie geen beheerder is; de markering blijft
- Uitzonderingen: een andere tenant wordt nooit geraakt

## Regressierisico's

- Na alleen bevestigen (zonder eigen wijziging) haalt een downgrade de standaard weer weg; bewust.
- Dev- en seed-tenants krijgen de markering; e2e-flows die op `/dashboard` landen als beheerder
  worden doorgestuurd naar de uitleg (niet gemeten).
