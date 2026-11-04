# BE-AGT-008 -- AIContextEngine

**Sprint:** SP-AGT-003 Dag 3
**Datum:** 2026-06-10
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

Aanmaken van `AIContextEngine` in `src/core/agents/context_engine.py`. De engine consumeert de
bestaande `ContextPackerService` (ADR-025) en produceert een `EnrichedContext` met een
`twin_profile` dict die profiel-attributen van `AgentMemoryProfile` bevat.

Dit is de context-enrichment laag die Dag 4's `CopilotService` twin_service injectie gaat gebruiken.

---

## Gewijzigde bestanden

| Bestand | Type | Omschrijving |
|---------|------|-------------|
| `src/core/agents/context_engine.py` | Nieuw | AIContextEngine + EnrichedContext |
| `tests/unit/agents/test_context_engine.py` | Nieuw | 6 unit tests |
| `src/domains/memory/services/context_packer_service.py` | Fix | Pre-existing non-ASCII `≈` → `~=` (CR-004) |

---

## Interfaces

### EnrichedContext (dataclass)

```python
@dataclass
class EnrichedContext:
    context: dict[str, Any] = field(default_factory=dict)
    twin_profile: dict[str, Any] = field(default_factory=dict)
    surface: str = ""
    query: str = ""
```

`context` bevat de serialiseerbare sleutels uit `ContextPackerService.build()`:
`agent_id` en `estimated_tokens`. De volgende sleutels worden altijd uitgesloten:

| Sleutel | Reden |
|---------|-------|
| `profile` | SQLAlchemy ORM-object (niet JSON-serialiseerbaar) |
| `tenant_id` | Mag niet lekken buiten ContextVar-grens (ADR-003) |
| `built_at` | `datetime`-object (niet JSON-serialiseerbaar zonder encoder) |
| `recent_episodes` | `list[MemoryItem]` ORM-objecten |
| `top_facts` | `list[MemoryItem]` ORM-objecten |
| `top_preferences` | `list[MemoryItem]` ORM-objecten |

`twin_profile` bevat de volgende velden van `AgentMemoryProfile` (bij afwezige profile: `{}`):
`persona_name`, `persona_description`, `active_goals`, `operating_rules`, `domain_expertise`, `agent_type`

### AIContextEngine

```python
class AIContextEngine:
    def __init__(self, db: AsyncSession, tenant_id: int) -> None: ...

    async def enrich(
        self,
        agent_id: str,
        query: str,
        surface: str,
    ) -> EnrichedContext: ...
```

`agent_id` moet een agent-identifier zijn (bijv. `"cva"`, `"copilot"`) -- niet een user-ID.
Dit correspondeert met `AgentMemoryProfile.agent_id` in de database.

---

## Gedrag

1. `ContextPackerService(db, tenant_id).build(agent_id=agent_id)` wordt aangeroepen
2. Het `profile` veld (AgentMemoryProfile ORM-object) wordt omgezet naar `twin_profile` dict
3. Niet-serialiseerbare sleutels worden uitgesloten uit `context`
4. Bij elke fout in `ContextPackerService.build()`: graceful degradatie naar lege `EnrichedContext`
   met `surface` en `query` correct doorgegeven; fout gelogd met `exc_info=True`

---

## ADR-034 compliance

`context_engine.py` staat in `src/core/agents/` en importeert NIET `src.core.database.database` direct.
De import van `ContextPackerService` uit `src.domains.memory` is een bestaand patroon in de codebase
(`base_agent.py` importeert dezelfde module). Contract 3 in `.importlinter` is nog uitgecommentarieerd
(SP-AGT-004). Wanneer Contract 3 actief wordt, moet `context_engine.py` worden toegevoegd aan de
SP-AGT-004 migratielijst.

---

## Tests

Bestand: `tests/unit/agents/test_context_engine.py` -- 6 tests

| Test | Type | Beschrijving |
|------|------|-------------|
| `test_ai_context_engine_stores_tenant_id` | behavioral | `__init__` slaat tenant_id op |
| `test_enriched_context_defaults_are_empty` | behavioral | defaults zijn leeg |
| `test_enrich_returns_enriched_context` | happy path | retourneert EnrichedContext instantie |
| `test_enriched_context_has_twin_profile_from_agent_memory_profile` | behavioral | profiel-attrs in twin_profile |
| `test_enrich_calls_context_packer_service` | behavioral | ContextPackerService aangeroepen met juiste args |
| `test_enrich_graceful_on_packer_failure` | unhappy path | lege context, surface/query bewaard |

Resultaat: 6/6 GROEN

---

## Backlog (gedocumenteerd, geen actie in deze sprint)

- **SP-AGT-004**: voeg `context_engine.py` toe aan Contract 3 migratielijst wanneer import-linter Contract 3 actief wordt
- `MemoryItem.to_dict()` helper voor volledige serialisatie van `recent_episodes`/`top_facts`/`top_preferences` in toekomstige sprint wanneer downstream consumers die data nodig hebben

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
