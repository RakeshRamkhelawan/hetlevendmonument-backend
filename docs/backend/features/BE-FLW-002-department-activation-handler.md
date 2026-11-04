# Backend Feature Specification

## Metadata

- Feature ID: BE-FLW-002
- Feature naam: Department Activation Handler
- Status: CLOSED
- Auteur: Sprint Executor Agent
- Reviewer: Auto-review
- Datum: 2026-05-30
- Gerelateerde user story / ticket: AGNT-007 (SP-F)
- Gerelateerde router / module: `src/core/events/department_activation_handler.py`
- Gerelateerde frontend endpoints: Geen
- Gerelateerde database tabellen: agent_configs
- Versie: 1.0

---

## Doel en scope

### Doel

Verwerk een `DepartmentActivatedEvent` door default tools te registreren en een `AgentConfig` aan te maken of te reactiveren.

### In scope

- `DepartmentActivatedEvent` dataclass
- `on_department_activated()` handler functie
- Tool registratie via `ap_mcp_registry`
- AgentConfig creatie / reactivatie

### Out of scope

- Event bus trigger (bestaat al)
- AP MCP Registry zelf (BE-UTL-003)
- AgentConfig repository (BE-SVC-007)

---

## Build summary

- **Nieuw gebouwd:** `src/core/events/department_activation_handler.py`
- **Gewijzigd:** Geen
- **Verwijderd:** Geen
- **Beinvloede bestaande flows:** Department activation flow

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-FLW-002 | Department Activation Handler | Event handler | `src/core/events/department_activation_handler.py` | Nieuw | Department activation |

---

## API-flows

N.v.t. — Event-driven, geen HTTP API.

---

## Detaildocumentatie per artefact

---

## [BE-FLW-002] Department Activation Handler

### 1. Type

Event handler

### 2. Locatie

- Bestandspad: `src/core/events/department_activation_handler.py`
- Klasse / functie: `DepartmentActivatedEvent`, `on_department_activated()`

### 3. Gerelateerde flow

Department activation

### 4. Doel

Wanneer een departement geactiveerd wordt, registreer de default tools en zorg dat er een actieve AgentConfig bestaat.

### 5. Functionele beschrijving

1. Ontvang `DepartmentActivatedEvent` met `tenant_id` en `department`.
2. Haal default tools op voor dit departement uit `ap_mcp_registry`.
3. Log tool registratie (placeholder; echte ToolBroker allowlist call is TODO).
4. Zoek bestaande `AgentConfig` voor deze agent.
5. Als bestaand: reactivate (is_active=True, update topics).
6. Als nieuw: create AgentConfig met departement topics.

### 6. Technische beschrijving

```python
class DepartmentActivatedEvent:
    def __init__(self, tenant_id: int, department: str) -> None

async def on_department_activated(event: DepartmentActivatedEvent, db_session) -> None
```

**Flow:**
```
Event -> ap_mcp_registry.get_default_tools_for_department(department)
      -> log tool_registered
      -> AgentConfigRepository(db_session).get_by_agent_id(agent_id)
      -> if exists: repo.update(id, is_active=True, subscribed_topics=topics)
      -> else: repo.create(tenant_id, agent_type, agent_id, ...)
```

### 7. Zichtbaarheids- en toegangsregels

- Event-driven; geen directe auth.
- `tenant_id` uit event payload (vertrouwd, afkomstig van geautoriseerde event publisher).

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- `tenant_id` moet positief zijn.
- `department` moet bekend zijn in `ap_mcp_registry`.

### 11. Business rules

- BR-001: Departement activatie is idempotent.
- BR-002: Bestaande agent wordt gereactiveerd, niet gedupliceerd.

### 12. Afhankelijkheden

- `src.core.models.agent_config.AgentConfig`
- `src.core.repositories.agent_config_repository.AgentConfigRepository`
- `src.core.events.signal_router.resolve_topics`
- `src.core.tool_broker.ap_mcp_registry.ap_mcp_registry`

### 13. Foutafhandeling

- `ap_mcp_registry` fout -> gelogd, handler gaat door.
- DB fout -> exception propagated.

### 14. Transacties en data-integriteit

- `db_session` wordt doorgegeven vanuit caller.
- `repo.create()` doet `flush()` + `refresh()`.

### 15. Telemetry / logging / tracing

- `logger.info()` bij elke stap (department_activated, tool_registered, agent_config_created, agent_config_reactivated).

### 16. Caching

- Geen.

### 17. Acceptatiecriteria

- [ ] Handler creëert AgentConfig bij eerste activatie
- [ ] Handler reactiveert bestaande AgentConfig
- [ ] Default tools worden gelogd
- [ ] Idempotent bij herhaalde activatie

### 18. Integratoruitleg

- Publish `DepartmentActivatedEvent(tenant_id, department)` naar event bus.
- Handler wordt automatisch aangeroepen.

### 19. Trainingssamenvatting

- **Actor:** Event bus / admin user
- **Voorwaarde:** Departement bestaat in registry
- **Actie:** Publish DepartmentActivatedEvent
- **Systeemverwerking:** Tool registratie + AgentConfig create/update
- **Succesrespons:** AgentConfig actief
- **Foutrespons:** Gelogd, doorgegaan bij tool fout; exception bij DB fout
- **Uitzonderingen:** DB failure -> exception

---

## Integratorhandleiding

N.v.t.

---

## Open aannames

- `ap_mcp_registry` heeft default tools per departement geregistreerd.

## Open vragen

- Wanneer komt de echte ToolBroker allowlist call (nu placeholder log)?

## Risico's

| Risico | Impact | Kans | Mitigatie |
|--------|--------|------|-----------|
| Tool registratie is placeholder | Medium | High | Documenteren als known limitation |

---

## QA-checks

- [x] Eerste activatie -> create getest
- [x] Herhaalde activatie -> reactivate getest
- [x] Idempotentie getest

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Review door reviewer-prompt: APPROVED
