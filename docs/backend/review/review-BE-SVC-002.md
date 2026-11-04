# Review — BE-SVC-002: LLM complete_json Universal Implementation

**Reviewer:** AI Agent (Laag A + Laag C)  
**Datum:** 2026-05-28  
**Status:** APPROVED WITH MINOR GAPS  

---

## Bevindingen

### Critical: 0
### High: 0
### Medium: 1
### Low: 1

---

## Medium-1: OpenAIClient gebruikt nog system-instruction injection

**Locatie:** `src/core/llm/llm_client.py:618` (`OpenAIClient.complete_json`)

OpenAIClient injecteert een JSON system instruction in plaats van native `response_format={"type": "json_object"}`. Dit is suboptimaal — OpenAI ondersteunt native JSON-mode sinds GPT-4.

**Impact:** Lagere JSON-validiteit rate bij OpenAI calls.  
**Mitigatie:** Niet blocking — OpenAIClient wordt niet door `ProviderRegistry` gebruikt (factory vindt alleen `*Provider` klassen).  
**Aanbeveling:** Verwijder dubbele Client/Provider implementaties in toekomstige refactor.

---

## Low-1: Dubbele implementaties (Client vs Provider)

**Locatie:** `src/core/llm/llm_client.py`

Er zijn twee sets van implementaties:
- `OpenAIClient`, `AnthropicClient`, `GoogleClient`, `OllamaClient`, `DeepSeekClient` in `llm_client.py`
- `DeepSeekProvider`, `GeminiProvider`, `OllamaProvider` in aparte `_provider.py` bestanden

Alleen de `*Provider` klassen worden door `ProviderRegistry.auto_discover()` gevonden.

**Aanbeveling:** Deprecate Client klassen en migreer callers naar Provider klassen.

---

## Testdekking

| Testset | Aantal | Status |
|---------|--------|--------|
| `test_sp_d01_llm_fix.py` | 19 | PASSED |
| `test_complete_json_overrides.py` | 8 | PASSED |
| `test_p0_a1_complete_json.py` | 9 | PASSED |
| `test_p1_a2_ollama_client.py` | 1 | PASSED |
| `copilot unit tests` | 468 | PASSED |

**Totaal: 505 tests passed, 0 regressions.**

---

## Security / Compliance

- Geen hardcoded API keys in wijzigingen
- `tenant_id` komt uit JWT context (geen body extractie)
- ASCII-only in source code
- Geen secrets in logs

---

## Verdict

**APPROVED WITH MINOR GAPS** — Medium-1 en Low-1 zijn geen blockers voor SP-D01. Aangeraden voor technische debt sprint na RC-1.
