# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-023
- Feature naam: SP-DLP-001 Dag 2: DLP kern -- redact_pii() + _sanitize_messages() LLM intercept
- Status: APPROVED
- Auteur: Rakesh Ramkhelawan
- Reviewer: Zie `docs/backend/review/review-BE-SEC-DLP-002.md`
- Datum: 2026-06-26
- Gerelateerde user story / ticket: SP-DLP-001 Dag 2 (DLP-gap audit bevinding)
- Gerelateerde router / module: src/core/governance/gdpr_enforcer.py, src/core/llm/llm_client.py
- Gerelateerde database tabellen: geen (pure logica)
- Versie: 1.0

---

## Doel en scope

### Doel

PII-masking voordat gebruikersinvoer naar externe LLM-providers (Google GenAI, DeepSeek, Anthropic,
Ollama) verzonden wordt. Zonder deze interceptie bereikte PII (emailadressen, telefoonnummers,
BSN, creditcardnummers) externe providers verbatim -- een GDPR Art. 5(1)(f) schending.

### In scope

- `GDPREnforcer.redact_pii(text)` -- maskeert PII en retourneert (masked_text, token_map)
- `GDPREnforcer.detokenize(text, token_map)` -- herstelt originele waarden na LLM-response
- `GDPREnforcer._replace_first_match()` -- private helper, eerste PII-occurrence vervangen
- Module-level `_PII_PATTERNS` en `_pii_token_map` ContextVar (thread-safe, request-scoped)
- `LLMClient._sanitize_messages()` -- sanitiseert user-role berichten voor provider-aanroep
- `LLMClient.generate_response()` interceptie -- chat + text pad beide gesanitiseerd
- Hergebruik van bestaande `detect_pii()` regex-patronen (geen duplicatie)

### Out of scope

- complete_json() provider-level intercept (vereist subclass-aanpassingen, post-dag 2)
- Streaming response detokenisatie (post-dag 2)
- GDPR-004 forget-me cascade, GDPR-001 LawfulBasisRegistry wiring

---

## Build summary

- Nieuw gebouwd: 0 nieuwe productiebestanden
- Gewijzigd: 2 productiebestanden + 2 testbestanden
- Verwijderd: geen

| Bestand | Wijziging |
|---------|-----------|
| `src/core/governance/gdpr_enforcer.py` | redact_pii() + detokenize() + _replace_first_match() + module constants |
| `src/core/llm/llm_client.py` | GDPREnforcer import + __init__ wiring + _sanitize_messages() + generate_response() intercept |
| `tests/unit/test_gdpr_enforcer_redact.py` | 6 unit tests (TDD, alle GROEN) |
| `tests/unit/test_llm_client_dlp.py` | 5 unit tests (TDD, alle GROEN) |

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging |
| --- | --- | --- | --- | --- |
| BE-SEC-023a | redact_pii() | BE-SVC | `src/core/governance/gdpr_enforcer.py:161` | Wijziging |
| BE-SEC-023b | detokenize() | BE-SVC | `src/core/governance/gdpr_enforcer.py:177` | Wijziging |
| BE-SEC-023c | _replace_first_match() | BE-SVC | `src/core/governance/gdpr_enforcer.py:184` | Wijziging |
| BE-SEC-023d | _PII_PATTERNS module constant | BE-SVC | `src/core/governance/gdpr_enforcer.py:14` | Wijziging |
| BE-SEC-023e | _pii_token_map ContextVar | BE-SVC | `src/core/governance/gdpr_enforcer.py:21` | Wijziging |
| BE-SEC-023f | LLMClient._sanitize_messages() | BE-SVC | `src/core/llm/llm_client.py:303` | Wijziging |
| BE-SEC-023g | LLMClient.generate_response() DLP intercept | BE-SVC | `src/core/llm/llm_client.py:277` | Wijziging |

---

## Technische beschrijving

### redact_pii()

```python
def redact_pii(self, text: str) -> tuple[str, dict[str, str]]:
```

- Roept `detect_pii({"text": text})` aan om PII-typen te detecteren
- Voor elk type: vervangt eerste occurrence via `_replace_first_match()` met `[TOKEN_PII_N]`
- Retourneert (gemaskeerde_tekst, token_map) -- token_map bevat {placeholder: origineel}

### detokenize()

```python
def detokenize(self, text: str, token_map: dict[str, str]) -> str:
```

- String-replace van alle placeholders naar originele waarden
- Idempotent bij lege token_map

### _pii_token_map ContextVar

```python
_pii_token_map: ContextVar[dict[str, str] | None] = ContextVar("_pii_token_map", default=None)
```

- Thread-safe, asyncio-task scoped
- Exporteerbaar voor optioneel request-scoped opslaan van token_map
- Geverifieerd gesoleerd via `test_redact_pii_contextvar_is_isolated`

### _sanitize_messages()

```python
def _sanitize_messages(
    self, messages: list[LLMMessage]
) -> tuple[list[LLMMessage], dict[str, str]]:
```

- Sanitiseert alleen `role == "user"` berichten
- `role == "system"` en `role == "assistant"` worden ongewijzigd doorgegeven
- Retourneert (sanitized_messages, combined_token_map)

### generate_response() interceptie

Beide paden (chat + text) zijn beveiligd:
- Chat-pad: `_sanitize_messages()` voor `chat_completion()` + `detokenize()` na response
- Text-pad: `redact_pii()` op prompt voor `text_completion()` + `detokenize()` na response

---

## Acceptatiecriteria

- [x] `redact_pii()` maskeert emailadres in testcases (6 tests GROEN)
- [x] `detokenize()` herstelt originele waarden (test_detokenize_restores_original_email)
- [x] `_pii_token_map` ContextVar is request-gesoleerd (test_redact_pii_contextvar_is_isolated)
- [x] `_sanitize_messages()` sanitiseert alleen user-role (5 tests GROEN)
- [x] System- en assistant-berichten worden niet gemaskeerd
- [x] `python -m pyright` -- 0 errors (baseline bewaard)
- [x] `ruff check src/core/governance/gdpr_enforcer.py src/core/llm/llm_client.py` -- clean

## Bekende beperkingen (post-dag 2 backlog)

- `complete_json()` provider-overrides sanitiseren niet -- vereist subclass-aanpassingen
- Streaming responses: detokenisatie werkt niet per-chunk (chunk kan placeholder splitsen)
- Alleen eerste PII-occurrence per type wordt gemaskeerd (meerdere emailadressen in 1 bericht)


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-DLP-001 Dag 2: DLP kern -- `redact_pii()` + `detokenize()` in gdpr\_enforcer.py + `_sanitize_messages()` + `generate_response()` intercept in llm\_client.py. 11 TDD tests GROEN. pyright 0 errors. is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-DLP-001 Dag 2: DLP kern -- `redact_pii()` + `detokenize()` in gdpr\_enforcer.py + `_sanitize_messages()` + `generate_response()` intercept in llm\_client.py. 11 TDD tests GROEN. pyright 0 errors..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
