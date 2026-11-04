# Review BE-AGT-003 -- FocusBuilderToolAgent _dispatch_tools Graceful Fallback

**Sprint:** SP-WE-22
**Datum:** 2026-06-01
**Status:** APPROVED

## Scope

- `src/core/agents/focus_builder_tool_agent.py` (regel 134-146)
- `tests/unit/test_sp_we_22_focus_builder_not_implemented.py`

## Bevindingen

### CRITICAL
Geen.

### HIGH
Geen.

### MEDIUM
Geen.

### LOW / INFO

- INFO-1: De `try/except Exception` in `handle_message()` blijft staan als veiligheidsnet
  voor toekomstige scenarios waar `_fallback.handle_message()` zelf faalt. Bewust behouden.
- INFO-2: `_fallback` wordt in `__init__` direct geinstantieerd; kan nooit `None` zijn op
  het moment van aanroep door `_dispatch_tools()`. Stopvoorwaarde uit de brief niet
  geactiveerd.

## Checklist

- [x] Geen tenant_id uit request body -- gebruikt `self.tenant_id` (JWT-derived)
- [x] Geen hardcoded URLs of secrets
- [x] ASCII-only in nieuwe code en log-strings (em-dash uit oude string verwijderd)
- [x] `logger.warning` met `extra={"tenant_id": ...}` per CLAUDE.md regel 11
- [x] Geen exception geslikt -- expliciete delegation
- [x] `_dispatch_tools()` gooit geen exception meer (kerndoel van de fix)
- [x] 5/5 unit tests groen
- [x] `ruff check` clean op gewijzigd bestand
- [x] `mypy` clean op gewijzigd bestand (1 onverwante syntax-error in
  `src/workers/actors.py` valt buiten scope -- parallel SP-WE-21 sprint)
- [x] Fix < 30 regels (~13 regels gewijzigd)
- [x] Geen Alembic migraties nodig
- [x] Geen frontend wijzigingen

## Conclusie

**APPROVED.** De fix lost NEW-WIRE-006 volledig op met minimale wijziging. Tests dekken
happy path, regressie (geen `NotImplementedError`), warning-emissie en fallback-delegatie.
Geen open CRITICAL of HIGH bevindingen.
