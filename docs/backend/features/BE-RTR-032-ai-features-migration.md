# BE-RTR-032 — AI Features Domain Migration naar v1/ai_features/

## Metadata

| Veld | Waarde |
|------|--------|
| ID | BE-RTR-032 |
| Sprint | SP-API-007 Dag 2 |
| Datum | 2026-06-05 |
| Commit | 681ca809 |
| Status | APPROVED WITH MINOR GAPS |

## Samenvatting

`ai_features_endpoints.py` (509r, 6 endpoints) is gemigreerd naar het drie-laags ADR-033 domeinpakket
`src/core/api/v1/ai_features/`. De legacy flat file is vervangen door een re-export shim.
Beide registries zijn bijgewerkt: `setup/router_registry.py` commentarieert de oude import uit,
`registries/analytics.py` registreert de nieuwe `domain_router` via lazy import.

## Geraakte bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/v1/ai_features/__init__.py` | Nieuw — Laag 2 domain package |
| `src/core/api/v1/ai_features/router.py` | Nieuw — Laag 1 composite router |
| `src/core/api/v1/ai_features/learning_router.py` | Nieuw — POST /learning/event + GET /learning/insights |
| `src/core/api/v1/ai_features/routing_router.py` | Nieuw — POST /routing/route |
| `src/core/api/v1/ai_features/analytics_router.py` | Nieuw — POST /analytics/predict |
| `src/core/api/v1/ai_features/system_router.py` | Nieuw — GET /system/status + GET /capabilities |
| `src/core/api/v1/ai_features/dependencies.py` | Nieuw — domein-level dependencies (placeholder) |
| `src/core/api/ai_features_endpoints.py` | Re-export shim (orphan:exempt) |
| `src/core/api/setup/router_registry.py` | Legacy import uitgecommentarieerd |
| `src/core/api/registries/analytics.py` | domain_router lazy import toegevoegd (77r <= 80r) |
| `tests/architecture/test_registry_equivalence.py` | test_ai_features_flat_file_migrated_to_v1 toegevoegd |

## Routes (ongewijzigd — ADR-031 URL-freeze)

| Method | Path | Auth |
|--------|------|------|
| POST | /api/v1/ai/learning/event | AGENTS_WRITE |
| GET | /api/v1/ai/learning/insights | AGENTS_READ |
| POST | /api/v1/ai/routing/route | AGENTS_WRITE |
| POST | /api/v1/ai/analytics/predict | AGENTS_READ |
| GET | /api/v1/ai/system/status | AGENTS_READ |
| GET | /api/v1/ai/capabilities | AGENTS_READ |

## Verbeteringen ten opzichte van de flat file

1. Geen f-strings in logger calls (was wel in origineel)
2. `detail=` bevat geen stack trace meer (was `str(e)` in origineel)
3. `raise ... from e` toegevoegd voor cause-chaining
4. `offset` parameter toegevoegd aan GET /learning/insights (MINOR GAP: niet forwarded naar engine)
5. ASCII-only logging patterns

## Bekende beperkingen

- `offset` in GET /learning/insights is gedeclareerd maar niet doorgegeven aan
  `engine.get_insights()`. De engine accepteert alleen `limit`. Dit is een pre-existing beperking
  van de engine interface. TODO(SP-VOLGENDE): `get_insights()` uitbreiden met offset-support.

## Trainingssamenvatting

### Flow 1: POST /api/v1/ai/learning/event

| Stap | Detail |
|------|--------|
| Actor | Ingelogde gebruiker met AGENTS_WRITE scope |
| Voorwaarde | Geldig JWT + event_type + context vereist |
| Actie | POST /api/v1/ai/learning/event met LearningEventRequest body |
| Systeemverwerking | JWT validatie -> scope check -> LearningEvent aanmaken -> engine.process_event() |
| Succesrespons | 200 {"success": true, "event_type": "...", "recorded_by": ..., "timestamp": "..."} |
| Foutrespons | 422 bij validatiefout; 500 bij engine failure |
| Uitzonderingen | user_id uit JWT als request.user_id niet opgegeven |

### Flow 2: GET /api/v1/ai/learning/insights

| Stap | Detail |
|------|--------|
| Actor | Ingelogde gebruiker met AGENTS_READ scope |
| Voorwaarde | Geldig JWT; optionele query params: category, min_confidence, limit, offset |
| Actie | GET /api/v1/ai/learning/insights?limit=50&offset=0 |
| Systeemverwerking | JWT validatie -> scope check -> engine.get_insights(category, min_confidence, limit) |
| Succesrespons | 200 LearningInsightResponse met insights list + summary |
| Foutrespons | 500 bij engine failure |
| Uitzonderingen | offset parameter gedeclareerd maar niet forwarded (MINOR GAP) |

### Flow 3: POST /api/v1/ai/routing/route

| Stap | Detail |
|------|--------|
| Actor | Ingelogde gebruiker met AGENTS_WRITE scope |
| Voorwaarde | Geldig JWT + request_id + request_type vereist |
| Actie | POST /api/v1/ai/routing/route met RoutingRequest body |
| Systeemverwerking | JWT -> scope -> RequestContext aanmaken -> router_instance.route() |
| Succesrespons | 200 RoutingDecisionResponse met selected_route, confidence, reasoning |
| Foutrespons | 503 als router None retourneert; 500 bij onverwachte fout |
| Uitzonderingen | user_id uit JWT als niet opgegeven in body |

### Flow 4: GET /api/v1/ai/system/status

| Stap | Detail |
|------|--------|
| Actor | Ingelogde gebruiker met AGENTS_READ scope |
| Voorwaarde | Geldig JWT; alle 3 DI-engines beschikbaar |
| Actie | GET /api/v1/ai/system/status |
| Systeemverwerking | Parallel status opvragen bij adaptive_learning, intelligent_routing, predictive_analytics engines |
| Succesrespons | 200 met components dict (status, event counts, model counts) |
| Foutrespons | 500 als een engine faalt |
| Uitzonderingen | Geen graceful degradation per component (alles-of-niets) |
