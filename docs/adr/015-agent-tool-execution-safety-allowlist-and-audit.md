# ADR-015: Agent Safety - Tool Allowlist & Audit Trail

## Status
Accepted

## Context
Autonome AI-agenten in SanskritiSetu kunnen "tools" aanroepen (bijv. zoeken in bronnen, data exporteren). Als een agent "hallucineert" of wordt gemanipuleerd via prompt injection, kan hij schadelijke acties uitvoeren binnen de context van een tenant.

## Decision
We implementeren een "Zero-Trust" architectuur voor agent-acties.

### 1. Expliciete Tool Allowlist
Een agent kan **alleen** tools aanroepen die expliciet voor zijn profiel zijn vrijgegeven in de configuratie.
- **Check**: De `ToolBroker` verifieert bij elke aanroep of de `tool_name` op de allowlist staat van de huidige agent-sessie.
- **Sandboxing**: Tools die het bestandssysteem of netwerk raken, draaien in een geïsoleerde wrapper met beperkte privileges.

### 2. Onwijzigbare Audit Trail
Elke tool-aanroep wordt vastgelegd in een dedicated `audit_logs` tabel (ADR-005 compliant):
```json
{
  "event": "TOOL_EXECUTION",
  "agent_id": "...",
  "tool_name": "db_query",
  "input": "...",
  "output_hash": "...",
  "status": "SUCCESS",
  "tenant_id": "..."
}
```

### 3. Human-in-the-Loop (HITL) Gate
Voor "high-risk" tools (bijv. `delete_resource`, `send_email`) is een **manual approval** vereist:
| Tool Risico | Actie |
| :--- | :--- |
| **Low** (Search, Read) | Directe uitvoering |
| **Medium** (Write, Update) | Loggen + post-action alert |
| **High** (Delete, Admin) | HITL (Wachten op gebruiker in UI) |

## Consequences
- **Positive**:
    - Beschermt tegen de zwaarste vormen van AI-misbruik en manipulatie.
    - Voldoet aan compliance-eisen voor "explainability" en "accountability" van AI systemen.
- **Negative**:
    - HITL onderbreekt de flow van een autonome agent; vereist UI support voor approvals.
- **Notes**:
    - Audit logs worden nooit verwijderd; ze worden na 30 dagen gearchiveerd naar cold storage.

## AI Act Governance Mapping (ADR-031)

Dit ADR levert aantoonbaar bewijs voor de volgende AI Act vereisten:

| Vereiste | Artikel | Hoe dit ADR voldoet |
|----------|---------|---------------------|
| Tool execution safety for AI systems | ADR-031 §1, §3 | ToolBroker allowlist is a mandatory policy check in the canonical governance pipeline; every tool-capable AI action must pass allowlist verification |
| Human oversight for high-risk AI actions | ADR-031 §2, §3 | HITL gate maps to L3/L4 autonomy ladder controls; high-risk tools require explicit approval before execution |
| Audit trail for AI tool usage | ADR-031 §5 | Every tool execution is logged with SHA-256 hash chain, linking to Council decisions and officer verdicts |

## SOC 2 Mapping

Dit ADR levert aantoonbaar bewijs voor de volgende SOC 2 Security Criteria:

| Criterium | Subcriteria | Hoe dit ADR voldoet |
| --------- | ----------- | ------------------- |
| CC5.2 | Control activities | HITL gate voor high-risk tools (delete, admin) vereist menselijke goedkeuring vóór uitvoering; workflow-gated approval is een aantoonbare control activity die vastgelegd wordt in de audit trail |
| CC6.3 | Access restricted to authorized individuals | Tool allowlist per agent-profiel; `ToolBroker` verifieert bij elke aanroep of `tool_name` op de allowlist staat; niet-geautoriseerde tools worden geblokkeerd voordat uitvoering plaatsvindt |
| CC6.8 | Malicious software prevention | Sandboxing voor tools die het bestandssysteem of netwerk raken; beperkte privileges in geïsoleerde wrapper; AP_EXECUTION_MODE=SANDBOXED+THREAD (ADR-030) beperkt de blast radius bij een gecompromitteerde agent |
| CC7.2 | Monitoring tools implemented | Elke tool-aanroep wordt vastgelegd in de `tool_audit_logs` tabel met tenant_id, agent_id, tool_name, input, output_hash en status; onwijzigbaar door RLS (ADR-005) |
| CC7.3 | Security incidents identified | `AUTHORIZATION_DENIED` events in de audit trail zijn detecteerbaar als security incident; HITL rejections zijn gelogd en koppelbaar aan een specifieke agent-sessie |
| CC7.4 | Security events assessed | `output_hash` in de audit log maakt forensisch onderzoek mogelijk zonder gevoelige output op te slaan; hash chain (ADR-019) borgt dat de audit trail niet achteraf is gewijzigd |

### 4. Capability Discovery Interface (toegevoegd 2026-05-27)

De Context Engine (ADR-027 §11-12) moet weten welke tools beschikbaar zijn om accurate voorstellen te genereren. De ToolBroker exposeert daarom een **read-only capability discovery interface** naast de executie interface:

```python
class IToolBroker(Protocol):
    # bestaand
    async def execute_tool(self, tool_name: str, payload: dict) -> ToolResult: ...
    async def is_allowed(self, tool_name: str, agent_id: str) -> bool: ...
    
    # nieuw — capability discovery
    async def list_tools(self, tenant_id: int) -> list[ToolMeta]
    async def get_tool_schema(self, tool_name: str, tenant_id: int) -> ToolSchema
    async def get_allowlist_snapshot(self, tenant_id: int) -> set[str]
```

**Security boundary**: `list_tools` en `get_tool_schema` zijn **read-only**; ze verifiëren tenant isolatie maar voeren geen acties uit. De Unified Capability Registry (ADR-027 §12) consumeert deze interface voor de ToolCatalog.

**Caching**: Tool metadata wordt 60s in Redis gecached per tenant. Allowlist wijzigingen triggeren cache invalidatie via `toolbroker.allowlist_updated` event.

### Open gaps richting volledige SOC 2 Type I readiness

- Geen geautomatiseerde alerting op hoge frequentie `AUTHORIZATION_DENIED` events (potentieel misbruiksignaal); drempel en kanaal zijn nog niet geconfigureerd
- Tool allowlist configuratie is niet versie-beheerd als auditeerbaar document; de configuratie staat in de database en is niet als git-artifact raadpleegbaar door auditors

## Implementatie-bevinding -- L3 Wiring Audit 2026-06-01

### CG-004b [HIGH] ToolBrokerService: HITLTicketRepository lazy-import, geen constructor-injectie

**Situatie:** ADR-015 beschrijft `HITLTicketRepository` als een vereiste dependency van `ToolBrokerService`.
**Werkelijkheid:** `HITLTicketRepository` wordt lazy-geimporteerd *binnen* een uitvoeringsmethode
(`service.py` regel 212), niet via constructor-injectie. Dit maakt de dependency onzichtbaar voor
dependency injection en onmogelijk te mocken in unittests zonder monkey-patching.
Daarnaast gebruikt `ToolBrokerService` `ToolRiskClassifier` in plaats van de ADR-beschreven allowlist,
wat afwijkt van ADR-015 §3 (static allowlist als eerste gate).
**Bewijs:** `src/core/tool_broker/service.py:212` (lazy import in methode body).
**Fix:** Injecteer `HITLTicketRepository` via de constructor van `ToolBrokerService`.
Voeg een formele allowlist-check toe als eerste gate vóór `ToolRiskClassifier`.
**Sprint:** SP-WE-15 (onderdeel van HITL unificatie)

---

## Implementatie-bevinding -- Architectuur Audit 2026-05-31

### WE-018 [MEDIUM] HITL in-memory store en DB repository zijn volledig losgekoppeld

**Situatie:** ADR-015 beschrijft een HITL-gate waarbij de ToolBroker wacht op menselijke goedkeuring.
**Werkelijkheid:** Twee volledig onafhankelijke stores bestaan naast elkaar:

- `tool_broker/hitl_store.py`: in-memory dict `_hitl_tickets`, gelezen door `execute_tool()`
- `tool_broker/hitl_repository.py`: ORM-backed DB repository, aangesproken door REST API endpoints

Wanneer een operator een HITL-ticket goedkeurt via de REST API (schrijft naar DB), ziet
`execute_tool()` die goedkeuring NOOIT (leest uit in-memory dict).

**Bewijs:** `src/core/tool_broker/service.py execute_tool()`: `hitl_store._hitl_tickets.get(ticket_ref)`.
`src/core/tool_broker/hitl_repository.py`: schrijft naar ORM. Geen synchronisatie tussen beide.
**Impact:** HITL-gate is effectief gebroken. Operators kunnen tickets goedkeuren via de UI,
maar tools worden nooit vrijgegeven omdat de gate de DB-goedkeuring niet ziet.
**Fix:** `hitl_store.py` vervangen door DB-backed implementatie die leest uit `HITLTicketRepository`.
**Sprint:** SP-WE-04

---

## Implementatiestatus Frontend

Geimplementeerd in SP-FE-2E (Dag 1, 2026-06-28).

| Component | Bestand | Route | Status |
| --- | --- | --- | --- |
| `ToolBrokerRegistry` pagina | `frontend/src/pages/redesign/ToolBrokerRegistry.tsx` | `/tools` | Geimplementeerd |
| `HITLQueue` pagina (redesign) | `frontend/src/pages/redesign/HITLQueue.tsx` | `/hitl` | Geimplementeerd (swap van HITLPage) |
| `ToolAuditLogs` pagina | `frontend/src/pages/redesign/ToolAuditLogs.tsx` | `/tool-audit-logs` | Geimplementeerd |
| `ToolBrokerCard` component | `frontend/src/components/integrations/ToolBrokerCard.tsx` | -- | PermissionGate agents:manage op Switch |
| `HITLDecisionForm` component | `frontend/src/components/compliance/HITLDecisionForm.tsx` | -- | ClassificationWrapper confidential op counter-proposal |

Tests: ToolBrokerRegistry 31, HITLQueue 30, ToolAuditLogs 20 (totaal 81 tests, 0 failures).
Specs: FE-PGS-021 (ToolBrokerRegistry), FE-PGS-022 (HITLQueue), FE-PGS-023 (ToolAuditLogs) -- APPROVED.

Opmerking: HITL in-memory vs. DB mismatch (WE-018) is een bestaand backend-probleem dat los staat van de frontend implementatie. De frontend toont de DB-state via REST API; de executie-kant (SP-WE-04) blijft een open backend-bevinding.

---

## Changelog

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | Initial | Tool allowlist, audit trail, HITL gate |
| **1.1** | **2026-05-27** | **§4 Capability Discovery Interface toegevoegd; read-only tool metadata voor Context Engine; cache invalidatie contract.** |
| **1.2** | **2026-05-31** | **WE-018 gedocumenteerd: HITL in-memory store en DB repository zijn losgekoppeld; HITL-gate effectief gebroken; fix in SP-WE-04.** |
| **1.3** | **2026-06-28** | **SP-FE-2E: ToolBrokerRegistry `/tools` (PermissionGate agents:manage, 31 tests), HITLQueue `/hitl` redesign-swap (30 tests), ToolAuditLogs `/tool-audit-logs` (20 tests). Frontend implementatiestatus sectie toegevoegd.** |
