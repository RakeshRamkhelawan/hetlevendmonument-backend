# BE-SVC-040: CVA Council Gate + Shadow CEO (AIACT-003 + AIACT-004 + ARCH-014)

**Sprint:** SP-CVA-SEC dag 1
**Status:** APPROVED
**Datum:** 2026-06-20
**ADRs:** ADR-031 (AI Act governance), ADR-016 (Shadow CEO), ADR-033 (router boundary)

---

## Samenvatting

EU AI Act Art. 9 (risk management) en Art. 14 (human oversight) vereisen dat elke
AI-chatrespons langs een governance gate gaat. CVAService.chat() en CVAService.chat_stream()
roepen nu require_council_approval() aan voordat LLMService.generate() wordt aangeroepen.
Shadow CEO is al ingebakken in build_council() via _ShadowCEOAdapter (factory.py:331).

## Grondslag

- EU AI Act Art. 9: Risk management system voor high-impact AI
- EU AI Act Art. 14: Human oversight via council deliberation
- ADR-016: Shadow CEO veto-model (4-level)
- ADR-031: AI Act governance contract + autonomy ladder
- ADR-033: router.py mag nooit direct council importeren

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/services/cva_service.py` | Council gate in chat() en chat_stream() |
| `src/core/schemas/cva_schemas.py` | decision_id: str \| None = None aan ChatResponse |
| `src/core/api/v1/cva/chat_router.py` | TODO(SP-VOLGENDE) verwijderd (ARCH-014) |

## Architectuur

```
chat_router.py
  |-> CVAService.chat()
        |-> build_council(db)           # factory.py -- ShadowCEO ingebakken
        |-> require_council_approval()  # governance_gate.py
              |-> HTTPException(403)    # veto: propageert naar client
              |-> HTTPException(500)    # crash: degraded mode, decision_id=None
              |-> CouncilDecision       # approved: decision_id in response
        |-> LLMService.generate()       # alleen na council approval
```

## Degraded mode (ADR-031 §3)

Als council niet beschikbaar is (Redis down, DB timeout):
- Chat gaat door met decision_id=None
- Best-effort audit log emitted (event_type=council_degraded_mode)
- HTTP 403 (governance veto) propageert altijd -- nooit degraded mode voor veto

## Beslissing: HTTPException in service layer

De service layer importeert HTTPException uit fastapi. Dit is een pragmatisch
compromis: governance_gate.py (copilot package) maakt zelf al gebruik van FastAPI.
Toekomstig refactor (GovernanceVetoError domain exception) staat in backlog.

## Tests

- `tests/architecture/test_cva_council_wiring.py` (3 tests)
- `tests/unit/test_sp_cva_sec_council_gate.py` (3 tests)
- `tests/unit/test_sp_cva_sec_decision_id_schema.py` (2 tests)

Alle 8 tests PASSED na implementatie.


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-CVA-SEC Dag 1: Council gate + Shadow CEO voor CVAService.chat() en chat_stream(). require_council_approval() VOOR LLMService.generate(). decision_id in ChatResponse. AIACT-003+004+002+ARCH-014 gesloten. 8 nieuwe tests PASS. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-CVA-SEC Dag 1: Council gate + Shadow CEO voor CVAService.chat() en chat_stream(). require_council_approval() VOOR LLMService.generate(). decision_id in ChatResponse. AIACT-003+004+002+ARCH-014 gesloten. 8 nieuwe tests PASS..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
