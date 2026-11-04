# Backend Feature Specification

## Metadata

- Feature ID: BE-GOV-004
- Feature naam: RC-003 -- CVA model_id doorsturen naar council + canonical JSON
- Status: APPROVED
- Auteur: SP-GOV-002 Dag 1
- Reviewer: zie docs/backend/review/review-BE-GOV-004.md
- Datum: 2026-06-22
- Gerelateerde user story / ticket: AGENT-CVA-COUNCIL-AUDIT-2026-06-20 RC-003
- Gerelateerde router / module: src/core/services/cva_service.py, src/core/copilot/council/audit_writer.py
- Gerelateerde database tabellen: council_decisions (hash chain, geen schema wijziging)
- Versie: 1.0

---

## Doel en scope

### Doel

RC-003 audit bevinding gesloten: de CVA service stuurde de model identifier niet door naar
de council gate (`model_id` bleef op default "unknown"). Hierdoor ontbrak model-traceerbaarheid
in de audit hash chain (ADR-019/ADR-031 vereiste).

### Scope

- `cva_service.py chat()`: `model_id=getattr(effective_llm, "model", "unknown")` toegevoegd aan `require_council_approval` call (regel ~217)
- `cva_service.py chat_stream()`: `_stream_model_id` berekend voor de council gate (model al beschikbaar via `model` param + `self.llm.model`), doorgegeven als `model_id=_stream_model_id`
- `audit_writer.py compute_canonical_json()`: `model_id` en `model_version` toegevoegd aan hash-invoer dict (regel ~89-90)

---

## Architectuur

### model_id resolutie

```python
# chat():
model_id=getattr(effective_llm, "model", "unknown")

# chat_stream() -- effective_llm nog niet beschikbaar bij council gate:
_stream_model_id = (
    model
    if (model and model in _ALLOWED_CVA_MODELS)
    else getattr(self.llm, "model", "unknown")
)
```

### Canonical JSON hash (audit_writer.py)

Voor de fix ontbrak model metadata in de hash-invoer. Na de fix:
```json
{
  "proposal_id": "...",
  "model_id": "gemini-1.5-pro",
  "model_version": "1.0",
  ...
}
```

Bestaande council_decisions records zijn niet gemigreerd (hash chain is forward-only,
ADR-019). Nieuwe decisions bevatten model metadata.

---

## Tests

| Test | Bestand | Type |
|------|---------|------|
| `test_cva_chat_passes_real_model_id_to_council` | test_governance_gate_model_metadata.py | Happy path (RED->GREEN) |
| `test_cva_chat_falls_back_to_unknown_when_llm_has_no_model_attr` | test_governance_gate_model_metadata.py | Regressiebewaker |
| `test_canonical_json_contains_model_id_key` | test_governance_gate_model_metadata.py | Unhappy path (RED->GREEN) |
| `test_canonical_json_model_id_value_matches_proposal` | test_governance_gate_model_metadata.py | Happy path (RED->GREEN) |

---

## Definition of Done

- [x] model_id != "unknown" doorgegeven aan council (test GROEN)
- [x] Fallback naar "unknown" bewaard bij ontbrekend model attribuut (regressiebewaker GROEN)
- [x] compute_canonical_json bevat model_id + model_version (tests GROEN)
- [x] Pyright 0 errors
- [x] Geen Alembic migratie nodig (CouncilDecisionRow heeft geen model_id kolom)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-GOV-002 Dag 1 RC-003: CVA model_id doorsturen naar council gate + compute_canonical_json. getattr(effective_llm, 'model', 'unknown') in chat() en chat_stream(). model_id+model_version in hash-invoer. 4 tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-GOV-002 Dag 1 RC-003: CVA model_id doorsturen naar council gate + compute_canonical_json. getattr(effective_llm, 'model', 'unknown') in chat() en chat_stream(). model_id+model_version in hash-invoer. 4 tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
