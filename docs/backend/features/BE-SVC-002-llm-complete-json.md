# BE-SVC-002: LLM complete_json Universal Implementation

**ID:** BE-SVC-002  
**Sprint:** SP-D01  
**Datum:** 2026-05-28  
**Status:** APPROVED  
**Eigenaar:** Rakesh Ramkhelawan  

---

## Samenvatting

Universaliseer `complete_json()` over alle LLM providers in `src/core/llm/`.  
Voorheen gooiden `MoonshotProvider` en `KimiProxyProvider` `NotImplementedError` bij JSON-mode requests.  
Na deze fix heeft elke provider een werkende `complete_json()` die een `LLMResponse` retourneert.

---

## Wijzigingen

### Bestanden gewijzigd

| Bestand | Wijziging |
|---------|-----------|
| `src/core/llm/moonshot_provider.py` | `complete_json()` toegevoegd; bugfix `response.json()` -> `await response.json()` in `chat()` (regel 204) |
| `src/core/llm/kimi_proxy_provider.py` | `complete_json()` toegevoegd met system-instruction fallback |
| `src/core/api/v1/focus_builder/router.py` | `generate_flow_ai` endpoint gebruikt nu `AgenticFlowService` i.p.v. template-based generatie |

### Bestanden toegevoegd

| Bestand | Doel |
|---------|------|
| `tests/unit/test_sp_d01_llm_fix.py` | 19 tests: provider existence, return type, native JSON-mode, fallback injection, Copilot usage, Focus Builder LLM usage |

---

## Provider matrix

| Provider | `complete_json()` | Native JSON-mode | Fallback patroon |
|----------|-------------------|------------------|------------------|
| `DeepSeekProvider` | Ja | `response_format={"type":"json_object"}` | N.v.t. |
| `GeminiProvider` | Ja | `response_mime_type=application/json` | N.v.t. |
| `OllamaProvider` | Ja | `format=json` (Ollama API) | N.v.t. |
| `MoonshotProvider` | Ja | `response_format={"type":"json_object"}` | N.v.t. |
| `KimiProxyProvider` | Ja | Nee | System-instruction injection |
| `OpenAIClient` | Ja | Nee | System-instruction injection |
| `AnthropicClient` | Ja | Nee | System-instruction injection |
| `GoogleClient` | Ja | Nee | System-instruction injection |
| `OllamaClient` | Ja | Nee | Retourneert `LLMResponse(success=False)` |
| `MockProvider` | Ja | Nee | Configurable mock response |

---

## Interface

```python
async def complete_json(
    self,
    messages: list[LLMMessage],
    schema: type[Any],
    **kwargs: Any,
) -> LLMResponse:
    ...
```

- Retourtype: `LLMResponse` (niet `dict`)
- `success=True` bij geldige JSON response
- `success=False` bij API fout of provider niet beschikbaar
- Nooit `NotImplementedError` in happy path

---

## Tests

```bash
pytest tests/unit/test_sp_d01_llm_fix.py -v
# 19 passed

pytest tests/unit/llm/test_complete_json_overrides.py -v
# 8 passed

pytest tests/unit/test_p0_a1_complete_json.py -v
# 9 passed

pytest tests/unit/copilot/ -v -q
# 468 passed
```

---

## Trainingssamenvatting

| Veld | Inhoud |
|------|--------|
| Actor | CopilotService, FocusBuilderService, AgenticFlowService (interne service laag) |
| Voorwaarde | LLM provider geconfigureerd, `complete_json()` geimplementeerd |
| Actie | Service roept `complete_json()` aan met messages en schema |
| Systeemreactie | Provider vraagt LLM om JSON response; parset resultaat; retourneert `LLMResponse` |
| Succesrespons | `LLMResponse(content="{...}", success=True)` |
| Foutrespons | `LLMResponse(content="", success=False, error_message="...")` |
| Uitzonderingen | Markdown code blocks worden gestript (OllamaProvider); provider-specifieke JSON-modes gebruikt indien beschikbaar |

---

## Afhankelijkheden

- `src.core.llm.llm_client.LLMClient` (ABC)
- `httpx` (async HTTP client)
- `google-genai` SDK (voor GeminiProvider)

---

## Risico's en mitigaties

| Risico | Mitigatie |
|--------|-----------|
| Provider retourneert geen geldige JSON | `LLMHandler` doet 1x retry met extra JSON instructie |
| Moonshot API `response.json()` async bug | Gefixt: `await response.json()` in `chat()` methode |
| Dubbele implementaties (Client vs Provider) | Factory gebruikt `ProviderRegistry` die alleen `*Provider` klassen vindt; Client klassen zijn legacy |
