# BE-AGT-022 -- CritiqueStore HITL Escalation

## Metadata

- **Sprint**: SP-AGT-007, Dag 1 van 1
- **Status**: IMPLEMENTED
- **Datum**: 2026-06-27
- **Auteur**: Claude (SP-AGT-007 implementatie-agent)

---

## Samenvatting

Critiques met score < 0.40 triggeren automatisch een HITL-ticket via `HITLTicketRepository`.
De escalatie is best-effort: een DB-fout blokkeert de primaire store niet.
SILENT-mode critiques worden expliciet uitgesloten (telemetrie-only, geen blokkering).

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/critique_store.py` | `_HITL_SCORE_THRESHOLD = 0.40` + `_create_hitl_ticket()` + call in `store()` |
| `tests/unit/agents/test_critique_store_hitl.py` | NIEUW -- 4 unit tests (rood voor, groen na) |

---

## Drempel en gedrag

| Conditie | Actie |
|---|---|
| `score < 0.40` AND `mode != "silent"` | `_create_hitl_ticket()` aangeroepen |
| `score >= 0.40` | Geen HITL-ticket |
| `mode == "silent"` | Geen HITL-ticket (telemetrie-only) |

---

## Implementatiepatroon

```python
_HITL_SCORE_THRESHOLD: float = 0.40

async def _create_hitl_ticket(self, critique: Critique) -> None:
    if critique.mode.lower() == "silent":
        return
    # lazy imports (noqa: PLC0415), best_effort wrapper, explicit db.commit()
```

- `best_effort` omhult de volledige DB-sessie (consistente patroon met `_refresh_mv`).
- `generate_ticket_ref()` wordt aangeroepen en doorgegeven als `ticket_ref`.
- HITL-call staat buiten de `asyncio.Lock` (na MV-refresh).
- Exception in `_create_hitl_ticket` wordt opgevangen in `store()` via try/except.

---

## Testbewijs

```
tests/unit/agents/test_critique_store_hitl.py::test_store_triggers_hitl_when_score_below_threshold PASSED
tests/unit/agents/test_critique_store_hitl.py::test_store_does_not_trigger_hitl_when_score_above_threshold PASSED
tests/unit/agents/test_critique_store_hitl.py::test_hitl_error_does_not_block_primary_store PASSED
tests/unit/agents/test_critique_store_hitl.py::test_hitl_ticket_contains_correct_fields PASSED
```


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: SP-AGT-007 Dag 1: CritiqueStore HITL escalation bij score < 0.40 (_create_hitl_ticket, SILENT-mode guard) is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker start of gebruikt SP-AGT-007 Dag 1: CritiqueStore HITL escalation bij score < 0.40 (_create_hitl_ticket, SILENT-mode guard).
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
