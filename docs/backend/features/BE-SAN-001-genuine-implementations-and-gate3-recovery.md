# BE-SAN-001 -- Eerlijke Contracten, Multi-Tenant Beveiliging en Gate 3 Kwaliteitsherstel

Datum:        2026-09-24
Sprint:       SP-GENUINE-001 (Dagen 1 t/m 5)
Branch:       iter/genuine-implementations
ADR:          ADR-004, ADR-005, ADR-006, ADR-015, ADR-019, ADR-036 (Organisatiemodel & Acceptatieketen)

---

## 1. Waarom dit er is

De codebase bevatte structurele schijnimplementaties, misleidende Gate 3 dekking en testvergiftiging:
1. **Schijnimplementaties:** Supervisors (`BaseSupervisor.act()` en 11 concrete supervisors) retourneerden `{"status": "dispatched", "success": True}` zonder dat er een SignalBus consumer of worker gekoppeld was. `ShardConsumer.start()` zette `self.is_running = True` zonder achtergrondlistener.
2. **Gate 3 Regressies:** 3 NameErrors (`auth.py` logout gaf HTTP 500, `workflow_engine.py` miste logger imports), 11 mypy-fouten over 6 bestanden, en een verouderde Any-ratel.
3. **Multi-Tenant Lekken:** `ExternalAgentService` voerde queries en mutaties uit zonder verplichte `tenant_id` WHERE-filters op het `Task` model. `audit_middleware` en `resolver` misten strikte tenant-isolatie.
4. **Geheugenlekken op Singletons:** Onbegrensde `.append` operaties op module-globale singletons (`PerformanceOptimizer.optimization_history`, `_NoOpHistogram.observations`, `ShardConsumer.recorded_violations`).
5. **Testvergiftiging (OP-254):** `workflow_execution_core_router.py` en `workflow_execution_router.py` bevatten `if os.getenv("TESTING") == "1":` bypasses met embedded stub-klassen (`_FakeLLM`, `_FakeTool`, `_FakeAgent`) die de echte dramatiq worker-infrastructuur omzeilden.
6. **Tool Broker Afbakening:** `CopilotService` las het private attribuut `_agent_profiles` van `ToolPermissionManager` direct uit in plaats van een openbare API aan te roepen, waardoor de harde denylist (ADR-036 D5) werd omzeild.

Met deze sanering zijn alle schijnimplementaties omgebouwd naar eerlijke, traceerbare contracten (`NotImplementedError`), zijn alle tenant-lekken gedicht met SQL WHERE-inspectietests, zijn alle geheugenlekken begrensd, en is Gate 3 100% hersteld.

---

## 2. Wat is gewijzigd (Benoemde Inventarisatie)

### A. Eerlijke Contracten (`NotImplementedError`)
- **`src/core/als/supervisors/base_supervisor.py`**:
  `BaseSupervisor.act()` werpt nu expliciet `NotImplementedError("ALS BaseSupervisor dispatch to SignalBus is not yet implemented; no consumer wired. See ADR-036.")`.
  Alle 11 afgeleide supervisors overerven dit eerlijke contract; geen enkele supervisor liegt meer over succes.
- **`src/core/governance/governance_agent/sharding.py`**:
  `ShardConsumer.start()` werpt nu expliciet `NotImplementedError("ShardConsumer background listener is not yet wired to Redis Pub/Sub. See ADR-006.")`.

### B. Multi-Tenant Beveiliging & SQL Isolatie
- **`src/core/company/external_agent_service.py`**:
  `_get_pending_tasks`, `_reschedule_orphaned_tasks` en `_cancel_pending_tasks` vereisen nu verplicht `tenant_id: int`. Alle SELECT- en UPDATE-queries bevatten `Task.tenant_id == tenant_id` in de gecompileerde WHERE-clausule. `complete_task` retourneert geen loze `True` meer waar `None` verwacht wordt.
- **`src/core/middleware/audit_middleware.py`**:
  `get_audit_logs` dwingt `tenant_id: int` af, past een harde limiet toe van maximaal 100 rijen, ondersteunt offset en redigeert PII-velden (`user_email`, `ip_address`, `user_agent`).
- **`src/core/scheduling/smart/resolver.py`**:
  `_get_participant_email` filtert `UserSchedulingProfile` op `tenant_id`.

### C. Begrensde Singletons (Geheugenlekken Gedicht)
- **`src/core/optimization/performance_optimizer.py`**:
  `PerformanceOptimizer.optimization_history` is geconverteerd van `list` naar `collections.deque(maxlen=1000)`.
- **`src/domains/memory/observability.py`**:
  `_NoOpHistogram.observations` is geconverteerd van `list` naar `collections.deque(maxlen=1000)`.
- **`src/core/governance/governance_agent/sharding.py`**:
  `ShardConsumer.recorded_violations` is geconverteerd naar `collections.deque(maxlen=self.MAX_BUFFER)`. `_handle_violations` logt nu gestructureerde audit warnings met metadata (`shard_id`, `tenant_id`, `event_id`, `reason`).

### D. Eliminatie van Testvergiftiging & Eerlijke Tool Broker
- **`src/core/api/v1/workflow/workflow_execution_core_router.py` & `workflow_execution_router.py`**:
  `if os.getenv("TESTING") == "1":` bypasses verwijderd, inclusief embedded `_FakeLLM`, `_FakeTool` en `_FakeAgent`. Beide routers dispatchen onvoorwaardelijk naar de dramatiq worker via `cast("_DramatiqActor", execute_workflow_task).send(execution_id, tenant_id)`.
- **`src/core/security/security_guard.py`**:
  Statische 2023 CVE-lijst gemarkeerd met `# TODO(SECURITY): replace stub with pip-audit integration or vulnerability API`. `scan_skills` retourneert een duidelijke `audit_notice` waarin staat dat in-process scanning een stub is en officiele audits via `pip-audit` in CI draaien.
- **`src/core/tool_broker/permission_manager.py`**:
  Publieke methode `get_allowed_tools(agent_id)` geimplementeerd met least privilege conform ADR-015:
  1. Default-deny: retourneert `[]` voor onbekende profielen.
  2. Harde denylist (ADR-036 D5): filtert altijd tools die voorkomen in `denied_actions` of `denied_tools`.
- **`src/core/copilot/service.py`**:
  `_get_allowed_tools` aangepast om de openbare methode `ToolPermissionManager.get_allowed_tools("copilot")` aan te roepen in plaats van private attributen te inspecteren.

### E. Eerlijke HR Acceptatieketen Stap 5
- Proefdata mag niet via interne mocks of directe database-injectie van gap-records worden geplaatst.
- Validatietest `tests/integration/tool_broker/test_acceptance_step_5_honest_boundary.py` bewijst:
  1. Stap 5 is fail-closed (ROOD): zonder data levert `analyze_skill_gap` 0 rijen op.
  2. Data wordt uitsluitend via het officiele HTTP-endpoint `POST /api/v1/hr/skills/import` geladen via multipart CSV-uploads (`skill`, `role_requirement`, `employee_assessment`).
  3. Direct na de HTTP-import wordt stap 5 GROEN en levert de echte kloofrijen op uit de PostgreSQL database.

---

## 3. Technische Specificatie & Contracten

### `ToolPermissionManager.get_allowed_tools(agent_id: str) -> list[str]`
- **Preconditie:** `agent_id` is een bekende agent ID (bijv. `"copilot"`).
- **Gedrag:** Zoekt het profiel op in `_agent_profiles`. Indien niet gevonden: retourneert direct `[]` (default-deny).
- **Postconditie:** Retourneert alle tools uit `profile.allowed_tools` waarvoor geldt dat `is_denied(agent_id, tool)` `False` is.

### `SecurityGuard.scan_skills(skills: list[dict[str, Any]]) -> list[dict[str, Any]]`
- **Output:** Elk geretourneerd skill-element bevat het veld `audit_notice`:
  `"Notice: In-process CVE scan is a development stub. Official vulnerability gating is enforced via pip-audit in CI."`.

### Dramatiq Actor Dispatch
- **Router contract:** `cast("_DramatiqActor", execute_workflow_task).send(execution_id, tenant_id)`.
- **Worker broker:** In tests draait `_stub_broker = StubBroker()` om netwerkcrashes te voorkomen.

---

## 4. Gate 3 Verificatiebewijs

| Poort | Commando | Resultaat |
| :--- | :--- | :--- |
| **Ruff** | `python -m ruff check src/` | **0 errors (All checks passed!)** |
| **Mypy** | `python scripts/run_mypy_audit.py --fail-on-increase` | **0 errors over alle 2277 bestanden** |
| **Pyright** | `npx pyright src/` | **0 errors, 11 warnings** |
| **Any-ratel** | `python scripts/check_any_gate.py --mode acknowledged --baseline docs/any_type_baseline.json` | **Exit 0 (7051 = 7051, daling van 7111 naar 7051)** |

---

## 5. Acceptatiecriteria & Review

- [x] Geen enkele functie retourneert `success=True` of gemockte data zonder werkelijke uitvoering.
- [x] Alle 11 supervisors werpen `NotImplementedError` met ADR-036 referentie.
- [x] Alle gewijzigde database queries bevatten verplichte `tenant_id` WHERE-clausules, geverifieerd via compiled SQL tests.
- [x] Alle module-globale metrieken zijn begrensd met `deque(maxlen=1000)`.
- [x] Beide workflow execution routers bevatten geen `os.getenv("TESTING") == "1"` bypasses meer.
- [x] Stap 5 van de acceptatieketen toont fail-closed gedrag en wordt groen via HTTP CSV multipart upload.
- [x] Alle documentatie en historische logs zijn gecorrigeerd en 100% ASCII-clean.

---

## Trainingssamenvatting

- Actor: Systeembeheerder of Platformontwikkelaar
- Voorwaarde: SanskritiSetu core platform services en supervisors zijn geconfigureerd en draaien binnen een multi-tenant context.
- Actie: Ontwikkelaar voert taakdispatch, workflow executie, permissie-inspectie of HR acceptatieketen queries uit.
- Systeemreactie: Het platform dwingt eerlijke contracten af (NotImplementedError bij ontbrekende workers), valideert tenant-isolatie via verplichte WHERE-clausules op queries, begrenst singleton-geheugengebruik, en verifieert de acceptatieketen via ongemockte database-executie.
- Succesrespons: De verzochte operatie slaagt binnen de afgebakende tenant context, of meldt een expliciete, eerlijke foutmelding zonder schijnsucces.
- Foutrespons: Het systeem werpt NotImplementedError (bij onbedrade supervisors/sharding) of weigert ongeauthenticeerde/cross-tenant operaties.
- Uitzonderingen: n.v.t.
