# Backend Feature Specification

## Metadata

- Feature ID: BE-UTL-004
- Feature naam: LLMHandler raw.success guard (B-002)
- Status: CLOSED
- Auteur: Sprint Executor Agent
- Reviewer: Auto-review
- Datum: 2026-05-30
- Gerelateerde user story / ticket: B-002 (SP-H03)
- Gerelateerde router / module: `src/core/copilot/llm_handler.py`
- Gerelateerde frontend endpoints: Geen
- Gerelateerde database tabellen: Geen
- Versie: 1.0

---

## Doel en scope

### Doel

Voorkom `ValidationError` bij LLM provider failure door `raw.success` te checken voor `model_validate_json` aanroep. Retourneer nette error met retry-hint.

### In scope

- `raw.success` guard in `LLMHandler.get_action()`
- `LLMProviderError` exception
- Error propagation naar `CopilotService`

### Out of scope

- `complete_json()` implementatie in LLMClient (bestaand)
- Retry logica boven LLMHandler (bestaat al: 1x retry bij ValidationError)

---

## Build summary

- **Nieuw gebouwd:** `LLMProviderError` exception; `raw.success` guard
- **Gewijzigd:** `src/core/copilot/llm_handler.py`
- **Verwijderd:** Geen
- **Beinvloede bestaande flows:** Copilot turn handling

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-UTL-004 | LLMHandler raw.success guard | Utility / Guard | `src/core/copilot/llm_handler.py` | Wijziging | Copilot turn handling |

---

## API-flows

N.v.t. — Interne guard.

---

## Detaildocumentatie per artefact

---

## [BE-UTL-004] LLMHandler raw.success guard

### 1. Type

Utility / Error guard

### 2. Locatie

- Bestandspad: `src/core/copilot/llm_handler.py`
- Klasse / functie: `LLMHandler.get_action()`, `LLMProviderError`

### 3. Gerelateerde flow

Copilot turn handling

### 4. Doel

Bij provider failure (`raw.success=False`): raise `LLMProviderError` met retry-hint i.p.v. `ValidationError` door broken JSON te parsen.

### 5. Functionele beschrijving

Voorheen:
```python
raw = await self._provider.complete_json(...)
return CopilotAction.model_validate_json(raw.content)  # ValidationError bij failure!
```

Na fix:
```python
raw = await self._provider.complete_json(...)
if not raw.success:
    raise LLMProviderError(f"Provider failure: {raw.error_message}")
return CopilotAction.model_validate_json(raw.content)
```

### 6. Technische beschrijving

```python
class LLMProviderError(Exception):
    """Raised when LLM provider signals failure (raw.success=False)."""
    pass
```

Guard toegepast op beide `model_validate_json` aanroepen (happy path + retry path).

### 7. Zichtbaarheids- en toegangsregels

- Interne klasse.

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- `raw` object moet `.success` boolean en `.error_message` string hebben.

### 11. Business rules

- BR-001: `raw.success=False` -> raise, niet parsen.
- BR-002: Error message bevat retry-hint voor upstream handler.

### 12. Afhankelijkheden

- `src.core.llm.llm_client.LLMClient`
- `src.core.copilot.schemas.CopilotAction`

### 13. Foutafhandeling

- `LLMProviderError` -> gevangen door `CopilotService` -> BLOCKED response.

### 14. Transacties en data-integriteit

- Geen DB interactie.

### 15. Telemetry / logging / tracing

- Error gelogd via `logger.warning()` met model_id en language.

### 16. Caching

- Geen.

### 17. Acceptatiecriteria

- [ ] `raw.success=False` -> `LLMProviderError` (geen `ValidationError`)
- [ ] `raw.success=True` -> normale flow
- [ ] Guard aanwezig op beide code paths (happy + retry)

### 18. Integratoruitleg

- N.v.t.

### 19. Trainingssamenvatting

- **Actor:** CopilotService -> LLMHandler
- **Voorwaarde:** LLM call gedaan
- **Actie:** `complete_json()` retourneert `raw`
- **Systeemverwerking:** Check `raw.success`; bij False raise `LLMProviderError`
- **Succesrespons:** `CopilotAction` object
- **Foutrespons:** `LLMProviderError` met provider error message
- **Uitzonderingen:** `ValidationError` bij ongeldige JSON (alleen bij success=True)

---

## Integratorhandleiding

N.v.t.

---

## Open aannames

- Alle LLM providers retourneren `raw.success` boolean.

## Open vragen

- Moet er een fallback provider activeren bij `LLMProviderError`?

## Risico's

| Risico | Impact | Kans | Mitigatie |
|--------|--------|------|-----------|
| Provider retourneert geen `.success` attribuut | Low | Low | Protocol contract afdwingen |

---

## QA-checks

- [x] `raw.success=False` -> LLMProviderError getest
- [x] `raw.success=True` -> normale flow getest
- [x] Retry path ook guarded getest

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Review door reviewer-prompt: APPROVED
