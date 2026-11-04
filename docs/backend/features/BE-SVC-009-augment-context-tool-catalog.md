# BE-SVC-009 -- _augment_context Tool Catalog (B-001)

**ID:** BE-SVC-009
**Sprint:** SP-C01-B
**Datum:** 2026-05-30
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

Vervangt de TODO-stub in `CopilotService._augment_context` door een echte implementatie
die de beschikbare agents en tools injecteert in de LLM-context. Voorkomt LLM-hallucinatie
van niet-bestaande tools (CLAUDE.md valkuil: "LLM system prompt mist capability catalog").

---

## Root Cause (B-001)

`_augment_context` bevatte uitsluitend een TODO-comment. De LLM ontving geen informatie
over welke agents en tools beschikbaar zijn op het platform, waardoor het acties kon
"hallusineren" die niet bestaan of niet zijn toegestaan (ADR-015 ToolBroker).

---

## Implementatie

```python
async def _get_available_agents(self, tenant_id: int) -> list[dict[str, Any]]:
    from src.core.agents.subagent_loader import get_loader
    loader = get_loader()  # global singleton
    return loader.list_available_agents()

async def _get_allowed_tools(self, tenant_id: int) -> list[dict[str, Any]]:
    # IToolBroker heeft alleen execute_tool -- catalog API nog niet in Protocol.
    # TODO: extend IToolBroker Protocol met list_tools() in toekomstige sprint.
    return []

async def _augment_context(self, tenant_id: int, context: dict[str, Any]) -> dict[str, Any]:
    # ... agents en tools ophalen met graceful degradation op fout ...
    augmented["_platform_capabilities"] = {
        "tenant_id": tenant_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents": agents,   # SubagentLoader global singleton
        "tools": tools,     # leeg tot IToolBroker Protocol uitgebreid is
    }
```

---

## Open punten (bewust uitgesteld)

| Item | Ernst | Reden |
|------|-------|-------|
| `_get_allowed_tools` retourneert altijd `[]` | MEDIUM | `IToolBroker` Protocol heeft geen catalog-methode. Uitbreiden in aparte sprint. |
| `_get_available_agents` is `async def` maar roept sync code aan | LOW | Werkt correct; misleidende handtekening. Acceptabel voor nu. |

---

## Trainingssamenvatting

**Flow: Copilot turn met capability-snapshot**

| Veld | Waarde |
|------|--------|
| **Actor** | CopilotService.handle_turn (per gebruikersverzoek) |
| **Voorwaarde** | POST /api/v1/copilot/turn aangeroepen |
| **Actie** | `_augment_context` wordt aangeroepen met tenant_id en context-dict |
| **Systeemreactie** | SubagentLoader geladen (global singleton); agents-lijst + lege tools-lijst toegevoegd aan capabilities |
| **Succesrespons** | `_platform_capabilities` dict bevat `agents`, `tools`, `tenant_id`, `timestamp` |
| **Foutrespons** | Bij SubagentLoader-fout: WARNING gelogd, lege agents-lijst doorgegeven (geen crash) |
| **Uitzonderingen** | `tools` altijd leeg totdat IToolBroker Protocol uitgebreid is |

---

## DoD

- [x] TODO-comment verwijderd uit `_augment_context`
- [x] `_platform_capabilities` bevat `agents` en `tools` keys
- [x] `get_loader()` module-functie gebruikt (niet `SubagentLoader()` direct)
- [x] Graceful degradation: lege catalog bij exception, geen crash
- [x] 5 unit tests groen (source-inspectie + behavioral)
- [x] 501 regressietests groen
