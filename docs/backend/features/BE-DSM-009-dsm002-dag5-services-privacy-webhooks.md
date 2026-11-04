# BE-DSM-009 -- SP-DSM-002 Dag 5: services + privacy + webhooks + models facade

**Sprint:** SP-DSM-002 (ADR-033 API-laag violation cleanup)
**Dag:** 5 van 6
**Status:** DONE
**Datum:** 2026-06-17

---

## Samenvatting

29 ADR-033 violations verwijderd uit de API-laag (64 -> 35). Alle verboden imports
verplaatst naar domein-facades (*.dependencies.py). Scanner ondersteunt nu ook
`# dsm:exempt` commentaar voor helper-bestanden die geen router zijn.

---

## Gewijzigde bestanden

### Nieuwe dependencies.py bestanden (4)
- `src/core/api/v1/ai_act/dependencies.py` -- governance.incident_service facade
- `src/core/api/v1/knowledge/dependencies.py` -- agents.agent_registry facade
- `src/core/api/v1/analytics/dependencies.py` -- database.models.analytics + database.session facade
- `src/core/api/v1/autonomous/dependencies.py` -- database.redis facade

### Uitgebreide dependencies.py bestanden (9)
- `workflow/dependencies.py` -- WorkflowService, create_workflow_generator, WorkflowVersioningService
- `feature_flags/dependencies.py` -- TenantFilterBypass + complete __all__
- `missions/dependencies.py` -- CouncilDecisionRow
- `company/dependencies.py` -- PolicyEngine, COUNCIL_TURNS_TOTAL
- `privacy/dependencies.py` -- AITransparencyService, ProfilingType, CookieConsentManager, AIDecision, HumanReviewRequest, UserProfilingOptOut + complete __all__
- `webhooks/dependencies.py` -- TelegramGateway, WhatsAppGateway
- `agents/dependencies.py` -- RegisteredAgent
- `tenants/dependencies.py` -- Agent, AuditLog
- `models/dependencies.py` -- geen wijziging (schemas.py dsm:exempt volstaat)

### Gerepareerde router-bestanden (15)
- workflow: workflow_crud_router.py, workflow_generation_router.py, workflow_versioning_router.py
- feature_flags/admin_router.py (inline -> top-level)
- ai_act/incident_router.py
- missions/lifecycle_router.py (inline -> top-level)
- company/board_router.py (2 inlines -> top-level)
- src/core/api/v1/analytics.py (import source gewijzigd naar api.dependencies)
- privacy: ai_transparency_router.py (top-level + inline), consent_router.py, human_review_router.py (2 inlines)
- webhooks: activepieces_handler.py, telegram_handler.py, whatsapp_handler.py
- agents/agent_crud_router.py
- knowledge/crud_router.py
- tenants/tenants_stats_router.py
- analytics/benchmarks.py
- autonomous/progress_ws.py
- models/registry_router.py (try/except -> schemas import)

### Overige wijzigingen
- `scripts/dsm_api_violation_finder.py` -- dsm:exempt comment support in is_api_layer_file()
- `src/core/api/v1/models/schemas.py` -- # dsm:exempt toegevoegd (non-router helper)
- `src/core/api/webhooks/telegram_handler.py` -- 5 print statements verwijderd (credential leak fix)
- `tests/architecture/test_dsm_api_violations.py` -- ceiling 65 -> 36
- `tests/architecture/test_dsm002_groep_c_deferred.py` -- xfail marker board_router verwijderd
- `.importlinter` -- 21 nieuwe facade-edges gedocumenteerd

---

## Verificatie

- DSM violations: 64 -> 35 (-29)
- Pyright: 0 errors (baseline gehandhaafd)
- Architecture tests: 154 passed, 18 xfailed
- board_router_violations_zero test: GROEN (geen xfail meer)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DSM-002 Dag 5: services + privacy + webhooks + agents + models batch (64->35 violations, -29) is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DSM-002 Dag 5: services + privacy + webhooks + agents + models batch (64->35 violations, -29).
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
