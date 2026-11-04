# Final Approver Brief -- SP-API-011-backlog Dag 2

Sprint:     SP-API-011-backlog
Dag:        2 van 3
Datum:      2026-06-22
Branch:     develop
Commit:     8193bf02 + 3c37b207 (FA minors fix)
Reviewtype: onafhankelijke beoordeling (6 lagen)

---

## Scope van deze dag

19 ADR-033 violations in het `cva/` domein verwijderd via Depends factory pattern.

**Gewijzigde bestanden:**

| Bestand | Wijziging |
| ------- | --------- |
| `src/core/api/v1/cva/dependencies.py` | Volledige uitbreiding: alle factory functions toegevoegd (get_cva_service_dependency, get_llm_service_dependency, build_cva_service, probe_llm_health, get_optional_conversation_memory, get_cva_agent_registry_dependency, get_cva_agent_registry_repository_dependency, create_cva_agent_factory) |
| `src/core/api/v1/cva/chat_router.py` | 6 violations: LLMService + system_prompt + 3x CVAService lazy imports + lokale get_llm_service_dependency verwijderd |
| `src/core/api/v1/cva/conversations_router.py` | 5 violations: 4x CVAService lazy imports -> Depends(get_cva_service_dependency) |
| `src/core/api/v1/cva/legacy_router.py` | 2 violations: ConversationMemory lazy import -> Depends(get_optional_conversation_memory) |
| `src/core/api/v1/cva/management_router.py` | 2 violations: LLMService lazy import -> probe_llm_health() uit dependencies |
| `src/core/api/v1/cva/public_router.py` | 2 violations: AgentRegistryRepository lazy imports -> Depends(get_cva_agent_registry_repository_dependency) |
| `src/core/api/v1/cva/state.py` | 2 violations: create_ultimate_cva_agent lazy import -> create_cva_agent_factory() uit dependencies |

---

## Bewijs per deliverable

### Violation count: 13 (was 32, -19)

```
python scripts/dsm_api_violation_finder.py
Files with violations: 6
Total violation imports: 13
```

cva/ domein volledig schoon -- 0 violations resterend in cva/ bestanden.
Resterende 13 violations zijn alle in focus_builder/ (dag 3).

### Gerichte tests: 201 passed, 6 failed (pre-existing)

```
python -m pytest tests/unit/api/v1/cva/ tests/architecture/ -q --tb=short --timeout=60
6 failed, 201 passed, 13 xfailed
```

Pre-existing failures (ongewijzigd t.o.v. baseline):
- `test_streaming_value_error_handler_logs_with_exc_info` -- statische analyse test, multi-line logger format niet herkend (pre-existing)
- `test_risk_register_adapter_fail_safe_on_missing_tenant` -- SP-CVA-P1 deferred item
- `test_prompt_injection_error_does_not_leak_tenant_id_in_details` -- SP-CVA-P1 deferred item
- `test_proactive_endpoint_documents_no_prompt_guard_scan` -- SP-CVA-P1 deferred item
- `test_all_v1_violations_resolved` -- architecture gate, ROOD verwacht tot dag 3 klaar is
- `test_api_layer_violations_regression_ceiling` -- architecture gate, ROOD verwacht tot dag 3 klaar is

### Pyright: 0 errors

```
python -m pyright
0 errors, 56 warnings, 0 informations
```

Baseline ongewijzigd (warnings zijn pre-existing missing stubs voor aiosmtplib / tensorflow_hub).

### Architecture tests: 2 FAIL (verwacht)

```
FAILED test_api_layer_violations_regression_ceiling  -- 13 violations > 0 ceiling
FAILED test_all_v1_violations_resolved               -- 13 resterend
```

Tests blijven ROOD totdat dag 3 (focus_builder/) voltooid is en count 0 bereikt.

---

## Laag 1 -- Code (CLAUDE.md patronen)

| Check | Status |
| ----- | ------ |
| Geen tenant_id uit request body | PASS -- geen logica gewijzigd |
| Geen datetime.now() | PASS |
| Geen emoji of non-ASCII | PASS |
| Geen hardcoded secrets | PASS |
| ADR-033 router boundary | PASS -- alle forbidden imports verwijderd uit cva/ |
| Geen nieuwe abstracties | PASS -- Depends-factory patroon consistent met dag 1 |
| from __future__ import annotations | PASS -- aanwezig in alle gewijzigde bestanden |

**Fix-patronen toegepast:**
- **TYPE_CHECKING imports**: forbidden module -> eigen domein `src.core.api.v1.cva.dependencies`
- **Lazy imports in handler body**: verwijderd, vervangen door `Depends(factory)` in handler signature
- **Lokale factory functies**: verwijderd uit router (get_llm_service_dependency, get_agent_registry_dependency), centrale versie in dependencies.py gebruikt
- **build_cva_service**: sync helper voor CVAService+LLMService combo (db_factory closure kan niet als pure Depends chain)
- **probe_llm_health**: async probe voor management health check -- nooit raises, soft failure semantics bewaard

---

## Laag 2 -- Security (OWASP + ADR)

| Check | Status |
| ----- | ------ |
| Tenant isolatie | PASS -- CVAService(db_session=session) ongewijzigd; user_id+tenant_id nog steeds uit JWT |
| Injection | PASS -- PromptGuard.sanitize() aanwezig in chat endpoints |
| Auth | PASS -- geen auth code gewijzigd |
| any-types | PASS -- geen Any toegevoegd aan request-handling paden |
| AgentRegistryRepository.get_registered_agent_by_agent_id(agent_id, tenant_id) | PASS -- tenant filter behouden |

---

## Laag 3 -- Tests

| Check | Status |
| ----- | ------ |
| Baseline VOOR fix | PASS -- 11 pre-existing failures gedocumenteerd in Taak 0 |
| Regressie NA fix | PASS -- 6 failures, alle pre-existing |
| Architecture tests rood als gate | PASS -- 2 FAIL verwacht en aanwezig |
| Bonus: test_chat_router_system_prompt_import_via_facade | PASS -- ROOD -> GROEN door fix chat_router.py line 24 |

---

## Laag 4 -- Architectuur

| Check | Status |
| ----- | ------ |
| ADR-033 Laag 1 | PASS -- cva/ compliant (0 violations) |
| Import linter scope | PASS -- TYPE_CHECKING imports via own-domain; runtime lazy imports in dependencies.py (exempt) |
| FastAPI DI patroon | PASS -- Depends(factory) in alle handlers |
| dependencies.py is exempt | PASS -- scanner slaat dependencies.py over per ontwerp |
| Geen nieuwe violations | PASS |

---

## Laag 5 -- PR-checklist

| Check | Status |
| ----- | ------ |
| Geen merge naar main | PASS -- alleen develop |
| Geen git-tag | PASS |
| Geen --no-verify | PASS |
| Commit bericht correct | PASS -- fix(api): SP-API-011-backlog dag 2 |
| pyright 0e baseline | PASS -- 0 errors |

---

## Laag 6 -- Pre-existing

| Categorie | Wat | Status |
| --------- | --- | ------ |
| 13 violations in focus_builder/ | Dag 3 | Ongewijzigd |
| 2 RED architecture gates | test_all_v1_violations_resolved + ceiling | Verwacht ROOD tot dag 3 |
| 3 SP-CVA-P1 deferred tests | test_cva_p1_dag1_deferred_findings | Ongewijzigd |
| 1 static analysis test | test_streaming_value_error_handler_logs_with_exc_info | Pre-existing, multi-line logger |
| 56 pyright warnings missing stubs | aiosmtplib / tensorflow_hub | Ongewijzigd |

---

## FA-minors gefixed (commit 3c37b207)

| ID | Bevinding | Fix |
|----|-----------|-----|
| FA-002 | Dead code `isinstance(e, (ImportError, ModuleNotFoundError))` in `handle_cva_value_error` | Branch verwijderd |
| FA-003 | Bare `except Exception:` in `build_cva_service` + `get_optional_conversation_memory` | `logger.warning(..., exc_info=True)` toegevoegd |
| FA-004 | Unused `db: AsyncSession = Depends(get_db)` in `get_cva_health` + `get_cva_status_detail` | Parameter + imports verwijderd |

---

## Eindoordeel

**GO**

19 violations in `cva/` opgelost. Violation count: 32 -> 13. pyright 0e.
Gerichte tests: 201 pass, 6 pre-existing failures ongewijzigd.
Architecture bonus: test_chat_router_system_prompt_import_via_facade GROEN.
3 FA-minors direct gefixed in commit 3c37b207.

---

## Volgende stap: dag 3 (focus_builder/ domein, 13 violations)

SP-API-011-backlog dag 2 klaar. Commit: 8193bf02
Brief: docs/agent-briefs/generated/2026-06-22-final-approver-SP-API-011-backlog-dag2.md

cva/ domein: 19 violations verwijderd. Resterend: 13 (focus_builder/).
Volgende actie: zeg "review dag 2" -- Claude leest de brief en geeft GO/NO-GO.
Bij GO: dag 3 brief (focus_builder/ domein) wordt direct gegenereerd.

---

*Brief-type: final-approver | Sprint: SP-API-011-backlog | Dag 2 van 3 | Commit: 8193bf02*


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-API-011-backlog Dag 2: cva/ domein 19 ADR-033 violations -> 0. dependencies.py herschreven (8 factory functions: LLMService, CVAService, ConversationMemory, AgentRegistry, probe_llm_health). FA-minors gefixed. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-API-011-backlog Dag 2: cva/ domein 19 ADR-033 violations -> 0. dependencies.py herschreven (8 factory functions: LLMService, CVAService, ConversationMemory, AgentRegistry, probe_llm_health). FA-minors gefixed..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
