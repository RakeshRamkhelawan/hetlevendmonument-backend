# BE-GOV-018: GDPR AI-decision-explainability-router gemount

**Sprint:** AUDIT-ARCH-2026-07-02 Dag 2 losse P1 (SAA-001)
**Datum:** 2026-07-02
**Status:** APPROVED
**ADR:** ADR-033

## Probleem

`src/core/api/v1/gdpr_compliance/explanation_router.py` implementeert het EU AI
Act Art. 13/86-explainability-endpoint (`GET /api/gdpr/decisions/{decision_id}/
explanation`), inclusief correcte tenant-isolatie (JWT-afgeleide `tenant_id`) en
een intra-tenant ownership-check. Het bestand was nooit opgenomen in de
composiet-router (`gdpr_compliance/router.py`, die alleen portability/erasure/
access/utility_router assembleerde) en was dus nooit bereikbaar.

## Oplossing

`router.include_router(explanation_router)` toegevoegd naast de bestaande 4
sub-routers. Geen padoverlap (geverifieerd: `/decisions/{decision_id}/
explanation` is disjunct van de andere routes).

## Trainingssamenvatting

- Actor: geauthenticeerde gebruiker die een AI Act-explainability-verzoek doet
- Voorwaarde: geldige JWT, `decision_id` van een `AIDecision`-record
- Actie: `GET /api/gdpr/decisions/{decision_id}/explanation`
- Systeemreactie: filtert op `tenant_id` (JWT-afgeleid) EN op `user_id`
  (ownership) voordat de explanation wordt geretourneerd
- Succesrespons: 200 met decision-type, confidence-score en rationale
- Foutrespons: 403/404 zonder onderscheid (voorkomt ID-enumeratie), 401 zonder
  geldige JWT
- Uitzonderingen: geen

## Test bewijs

```
pytest tests/unit/api/test_gdpr_compliance_router_mounted.py tests/unit/api/test_gdpr_compliance.py \
  tests/unit/test_gdpr_cva.py -v
26 passed
```

## Reviewers

code-reviewer: GO -- geen padoverlap.
security-reviewer: GO -- bevestigd defense-in-depth (tenant-filter + ownership-
check + generieke 403/404 zonder enumeratie-oracle) al aanwezig in het
ongemounte bestand; mounten introduceert geen nieuw risico.

## Backlog

Geen.
