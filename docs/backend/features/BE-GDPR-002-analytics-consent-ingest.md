# BE-GDPR-002 -- Analytics-consent afgedwongen op ingest (GDPR-004)

- Feature ID: BE-GDPR-002
- Status: Implemented
- Sprint: AGENTIC-COPILOT-TAAKBEHEER-2026-07 Dag 8 (auth-kritiek)
- Branch: `iter/dag8-gdpr-authz`
- Reviewer: code-reviewer + security-reviewer (Gate 2) -- zie `docs/backend/review/review-BE-GDPR-002.md`
- Datum: 2026-07-13
- ADR: ADR-033 (dependencies-facade), ADR-003 (tenant), GDPR art. 6/7

## Doel

`POST /events` (`src/core/api/v1/analytics_ingest/events_router.py`) persisteerde elk `AnalyticsEvent`
zonder consent-check. Nu wordt de opgeslagen `analytics`-consent van de geverifieerde gebruiker
afgedwongen vóór opslag.

## Fix

- Nieuwe dependency `analytics_consent_allowed` in `analytics_ingest/dependencies.py` (ADR-033 facade --
  de router importeert GEEN `src.core.governance` direct). Leest consent met dezelfde sleutel als de writer
  (`privacy/consent_router.py`): `CookieConsentManager.get_consent(str(current_user.id), current_user.tenant_id)`
  -- attribuut-toegang op de geverifieerde-JWT `UserResponse`, nooit `sub`/e-mail of `event.userId` uit de body.
- `submit_events` ontvangt een `analytics_allowed: bool`; events zonder consent worden NIET gepersisteerd,
  geteld als `rejected` binnen het bestaande **202/partial** batch-contract (geen blanket 4xx).
- **Fail-closed:** een consent-leesfout -> `False` (geen tracking), gelogd.
- Pre-existing 500-bug meegefixt: drie `current_user.get("sub")` (faalde op `UserResponse`) -> `current_user.id`.

## Acceptatiecriteria

- Zonder consent -> geen `AnalyticsEvent`-write (rejected in de batch); met consent -> wel.
- Consent gelezen met `str(current_user.id)` + `current_user.tenant_id` (getest met een echt UserResponse-
  achtig object, niet dict); body-`userId` beinvloedt de identiteit niet.
- Fail-closed bij leesfout; tenant-scoped.

## Contract-keuze (gedocumenteerd)

Niet-toegestane events worden overgeslagen en als `rejected` geteld binnen de bestaande 202/partial-respons
(geen 4xx), zodat het batch-contract niet breekt. Kanttekening: `get_consent` maakt via
`_get_or_create_db_record` een default consent-rij aan bij eerste lezing per user -- consistent met de
bestaande consent-GET; op de ingest-hotpath is dat een write bij de eerste event van een nieuwe user.

## Trainingssamenvatting

### Flow 1: Analytics-event met consent-gate

- Actor: geauthenticeerde gebruiker (identiteit uit de JWT `UserResponse`).
- Voorwaarde: batch met events wordt ge-POST naar `/events`.
- Actie: de `analytics_consent_allowed`-dependency leest de opgeslagen `analytics`-consent.
- Systeemreactie: met consent worden events gepersisteerd; zonder consent overgeslagen (rejected).
- Succesrespons: 202 met `eventsProcessed`; zonder consent 202/partial met `eventsRejected`.
- Foutrespons: consent-leesfout -> fail-closed (geen tracking).
- Uitzonderingen: identiteit altijd uit de JWT (`current_user.id`), nooit `event.userId`/body; tenant-scoped.

## Definition of Done

- [x] Consent-gate via ADR-033 facade; import-linter Contract 1 arch-tests groen
- [x] 5 unit tests (submit + dependency-keying + fail-closed); Gate 2 code + security APPROVED
- [x] Gate 3 ruff 0 / pyright 0; ID-REGISTRY bijgewerkt
