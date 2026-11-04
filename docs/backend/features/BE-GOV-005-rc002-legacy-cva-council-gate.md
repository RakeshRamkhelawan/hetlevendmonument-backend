# BE-GOV-005: RC-002 -- Legacy CVA council gate op /chat/legacy

**Sprint:** SP-GOV-002 Dag 2
**Datum:** 2026-06-23
**Status:** APPROVED

## Omschrijving

De `/api/v1/cva/chat/legacy` endpoint bypasste de Agent Council volledig (RC-002 bevinding).
Na deze fix wordt `require_council_approval()` aangeroepen via de `cva/dependencies.py`
facade voordat enige LLM/agent aanroep plaatsvindt (ADR-015/031).

## Wijzigingen

### `src/core/api/v1/cva/dependencies.py`
- `get_cva_council_dependency(session)` toegevoegd: FastAPI Depends factory die een
  request-scoped `AgentCouncil` levert via lazy import van `council.factory.build_council`.
- `execute_cva_council_gate(council, tenant_id, user_id, action_params, reasoning, model_id)`
  toegevoegd: wrapper die `council.governance_gate.require_council_approval` aanroept
  via lazy import (ADR-033 compliant -- `copilot.*` verboden in router files).
- Beide functies toegevoegd aan `__all__`.

### `src/core/api/v1/cva/legacy_router.py`
- `council: Any = Depends(get_cva_council_dependency)` toegevoegd aan handler signature.
- `decision = await execute_cva_council_gate(...)` aanroep VOOR de outer `try` block,
  zodat `HTTPException(403)` correct doorstroomt bij blokkade.
- `decision_id: str | None = None` veld toegevoegd aan `CVAChatResponse`.
- `decision_id=decision_id` meegegeven in beide `CVAChatResponse(...)` returns
  (timeout-pad + happy-pad).
- `db: AsyncSession = Depends(get_db)` verwijderd (was alleen voor council-building).
- `sqlalchemy.ext.asyncio.AsyncSession` import verwijderd (niet meer nodig).

## ADR-033 compliance
- Facade-patroon: `copilot.council.*` imports leven in `dependencies.py` (exempt),
  niet in `legacy_router.py` (zou violation zijn).
- Violation count: 6 (pre-existing dag 1) -- geen nieuwe violations door dag 2.

## Tests
- `tests/unit/api/v1/cva/test_legacy_cva_council_gate.py` -- 4 tests GROEN:
  - `test_legacy_router_calls_require_council_approval` (arch scan)
  - `test_legacy_chat_response_has_decision_id_field` (arch scan)
  - `test_legacy_cva_council_block_returns_403` (gedrag: blokkade = 403)
  - `test_legacy_cva_happy_path_returns_decision_id` (gedrag: decision_id in respons)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-GOV-002 Dag 2 RC-002: council gate op /chat/legacy. execute_cva_council_gate + get_cva_council_dependency facade in cva/dependencies.py (ADR-033). decision_id in CVAChatResponse. 4 tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-GOV-002 Dag 2 RC-002: council gate op /chat/legacy. execute_cva_council_gate + get_cva_council_dependency facade in cva/dependencies.py (ADR-033). decision_id in CVAChatResponse. 4 tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
