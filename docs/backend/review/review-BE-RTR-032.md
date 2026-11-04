# Review BE-RTR-032 — AI Features Domain Migration

## Metadata

| Veld | Waarde |
|------|--------|
| ID | BE-RTR-032 |
| Reviewer | Laag A code-review (Claude Sonnet 4.6) |
| Datum | 2026-06-05 |
| Verdict | **APPROVED WITH MINOR GAPS** |

## Checklist

| Criterium | Status | Notitie |
|-----------|--------|---------|
| tenant_id uit JWT/middleware (BLOCKER) | PASS | Geen tenant_id in body/query; identity via get_current_user() |
| Geen f-strings in logger | PASS | Alle logger calls gebruiken %s formatting |
| exc_info bij except Exception | PASS | logger.exception() gebruikt (automatisch exc_info=True) |
| ADR-033 thin delivery | PASS | Handlers delegeren aan DI-injected engines; geen ORM/business logica |
| Route-volgorde statisch voor parameterpad | PASS | Alle 6 routes zijn statisch (geen path params) |
| Paginering op list-endpoints | MINOR GAP | GET /learning/insights: offset gedeclareerd maar niet forwarded naar engine |
| orphan:exempt op regel 1 van bestanden >200r | PASS | Alle bestanden <200r; orphan:exempt aanwezig voor test-infra |

## Bevindingen

### MINOR GAP: offset niet forwarded naar engine.get_insights()

**Locatie:** `learning_router.py:128`

```python
insights = await engine.get_insights(
    category=category, min_confidence=min_confidence, limit=limit
    # offset ontbreekt hier
)
```

**Impact:** API contract declareert offset maar past het niet toe. Callers die offset=10 meesturen
krijgen dezelfde resultaten als offset=0. Misleidend maar niet security-kritiek.

**Aanbeveling:** TODO(SP-VOLGENDE): `AdaptiveLearningEngine.get_insights()` uitbreiden met
`offset: int = 0` parameter.

## Conclusie

Code is kwalitatief goed. De migratie behoudt alle routes (ADR-031 URL-freeze), verbetert logging
patronen, en volgt ADR-033 drie-laags structuur correct. De minor gap is pre-existing (de originele
flat file had ook geen offset-support).

**APPROVED WITH MINOR GAPS**
