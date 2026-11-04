# BE-EP-016 -- Agent Analytics /ooda Stub Endpoint (SP-WE-09)

**ID:** BE-EP-016
**Sprint:** SP-WE-09
**Datum:** 2026-06-01
**ADR:** ADR-032 (WE-011)

## Samenvatting

Stub endpoint `GET /api/v1/analytics/agents/{agent_id}/ooda` toegevoegd om frontend 404 op te lossen. Retourneert HTTP 501 met duidelijke roadmap-referentie. Volledige implementatie gepland voor SP-C02-B (ADR-032).

## Wijzigingen

- `src/core/api/v1/analytics/agents.py` aangemaakt met stub endpoint
- `src/core/api/router_registry.py`: agent_analytics_router geregistreerd

## Trainingssamenvatting

### Flow 1: Agent OODA metrics request

- **Actor:** AnalyticsService (frontend) via `GET /api/v1/analytics/agents/{id}/ooda`
- **Voorwaarde:** Ingelogde gebruiker; agent dashboard
- **Actie:** `require_tenant_id()` + `get_current_user()` checks; endpoint body raises 501
- **Systeemreactie:** HTTP 501 + `{"success": false, "error": {"code": "NOT_IMPLEMENTED", "message": "..."}}`
- **Succesrespons:** 404 verdwenen; frontend ontvangt 501 (expected, SP-C02-B roadmap)
- **Foutrespons:** HTTP 401/403 bij auth mismatch
- **Uitzonderingen:** SP-C02-B implementeert echte OODA metrics aggregatie
