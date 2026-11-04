# BE-SEC-DLP-001 -- DLP/PII-masking LLM Intercept

**Feature-ID:** BE-SEC-DLP-001
**Sprint:** SP-DLP-001 Dag 1
**Status:** ONTWERP
**Datum:** 2026-06-25
**Basis:** Audit ADR-DLP-2026-06-25 (bevindingen SEC-001, SEC-002, GDPR-001 t/m GDPR-012, DLP-gap)

---

## 1. Achtergrond en aanleiding

Audit 2026-06-25 bevestigt een volledige afwezigheid van PII-masking in het LLM-aanroeppad:

- `src/core/governance/gdpr_enforcer.py:119` heeft `detect_pii()` maar **geen** `redact_pii()`.
- `src/core/llm/llm_client.py` stuurt ongemaskeerde gebruikersinvoer naar externe providers
  (Google GenAI, DeepSeek, Anthropic, Ollama) via `chat_completion()`, `generate_response()`
  en `complete_json()` -- zonder enige interceptie.
- Gebruikersinvoer wordt verbatim gelogd op INFO-niveau in `ultimate_cva/agent.py:150`
  en `ultimate_cva/nlp.py:127` (SEC-002).
- Email-adressen worden verbatim gelogd in `frontend/auth.py:61,68,78` (SEC-001).

Gevolg: PII (namen, e-mailadressen, IBAN, BSN) bereikt externe LLM-providers en logbundels
zonder beveiliging. Dit is een GDPR Art. 5(1)(f) schending en een M&A due diligence blocker.

---

## 2. Scope

**WEL in scope:**
- `redact_pii(text)` implementeren in `src/core/governance/gdpr_enforcer.py`
- DLP-interceptie in `src/core/llm/llm_client.py` (alle drie entry points)
- Detokenisatie na LLM-response (herstel voor eindgebruiker)
- PII-log fixes SEC-001 en SEC-002
- Architecture tests `test_pii_log_leakage.py` groen krijgen

**NIET in scope:**
- GDPR-004 forget-me cascade (apart: SP-DLP-001 P3)
- EU AI Act frontend fixes (apart: SP-DLP-002)
- GDPR-001 LawfulBasisRegistry wiring (apart: SP-DLP-001 P3)

---

## 3. Technisch ontwerp

### 3.1 `redact_pii()` in `gdpr_enforcer.py`

```python
from contextvars import ContextVar
from typing import Any

_pii_token_map: ContextVar[dict[str, str]] = ContextVar(
    "_pii_token_map", default={}
)

def redact_pii(self, text: str) -> tuple[str, dict[str, str]]:
    """Maskeert PII in text en retourneert gemaskeerde tekst + token-map.

    De token-map is request-scoped via ContextVar -- thread-safe, niet
    deelbaar over requests of Dramatiq-workers.

    Returns:
        (gemaskeerde_tekst, token_map)
        token_map: {TOKEN_PII_0: originele_waarde, ...}
    """
    token_map: dict[str, str] = {}
    detected = self.detect_pii({"text": text})
    result = text
    for idx, pii_type in enumerate(detected):
        placeholder = f"[TOKEN_PII_{idx}]"
        # Hergebruik bestaande regex-patronen per pii_type
        result, original = self._replace_first_match(result, pii_type, placeholder)
        if original:
            token_map[placeholder] = original
    return result, token_map


def detokenize(self, text: str, token_map: dict[str, str]) -> str:
    """Herstelt originele waarden in een gemaskeerde tekst."""
    result = text
    for placeholder, original in token_map.items():
        result = result.replace(placeholder, original)
    return result
```

**Waarom ContextVar en niet een global dict:**
Een global dict voor de token-map is thread-unsafe en lekt data over requests heen.
`ContextVar` is per-asyncio-task gesoleerd: elke FastAPI-request en elke Dramatiq-worker
heeft zijn eigen kopie. Dit is het enige correcte patroon.

### 3.2 `_sanitize_messages()` in `llm_client.py`

```python
async def _sanitize_messages(
    self,
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Maskeert PII in 'user' role messages voor verzending naar externe provider.

    'system' en 'assistant' berichten worden niet gemaskeerd -- die zijn
    door de applicatie gegenereerd en bevatten geen eindgebruikersinvoer.

    Returns:
        (gesanitiseerde_messages, gecombineerde_token_map)
    """
    combined_map: dict[str, str] = {}
    sanitized = []
    for msg in messages:
        if msg.get("role") == "user":
            clean_content, token_map = self._gdpr_enforcer.redact_pii(
                msg.get("content", "")
            )
            combined_map.update(token_map)
            sanitized.append({**msg, "content": clean_content})
        else:
            sanitized.append(msg)
    return sanitized, combined_map
```

### 3.3 Integratie in alle drie entry points

```python
# In chat_completion():
sanitized_messages, token_map = await self._sanitize_messages(messages)
raw_response = await self._provider.chat_completion(sanitized_messages, **kwargs)
return self._gdpr_enforcer.detokenize(raw_response, token_map)

# Idem voor generate_response() en complete_json()
```

### 3.4 Gestreamde responses

Bij streaming retourneert `chat_completion()` een async generator. Detokenisatie
moet over de volledige samengestelde response plaatsvinden, niet per chunk
(een PII-placeholder kan gesplitst zijn over twee chunks):

```python
async def _collect_and_detokenize(
    stream: AsyncIterator[str],
    token_map: dict[str, str],
    gdpr_enforcer: GDPREnforcer,
) -> AsyncIterator[str]:
    full_text = ""
    async for chunk in stream:
        full_text += chunk
    yield gdpr_enforcer.detokenize(full_text, token_map)
```

### 3.5 PII-log fixes

**SEC-001** (`frontend/auth.py:61,68,78`):
```python
# VOOR (fout):
logger.info("Successful login for user: %s", email)

# NA (goed):
import hashlib
_masked = hashlib.sha256(email.encode()).hexdigest()[:12]
logger.info("Successful login for user: %s", _masked)
```

**SEC-002** (`ultimate_cva/agent.py:150`):
```python
# VOOR (fout):
logger.info(f"Processing command: '{user_input}'")

# NA (goed):
logger.info("Processing command: len=%d", len(user_input))
```

---

## 4. Implementatiestappen (TDD)

### Stap 1 -- Falende tests schrijven voor `redact_pii()`

```python
# tests/unit/test_gdpr_enforcer_redact.py
def test_redact_pii_replaces_email_with_placeholder():
    enforcer = GDPREnforcer()
    masked, token_map = enforcer.redact_pii("Stuur naar jan@example.com graag")
    assert "jan@example.com" not in masked
    assert len(token_map) == 1
    original_email = list(token_map.values())[0]
    assert original_email == "jan@example.com"

def test_detokenize_restores_original_value():
    enforcer = GDPREnforcer()
    masked, token_map = enforcer.redact_pii("jan@example.com")
    restored = enforcer.detokenize(masked, token_map)
    assert restored == "jan@example.com"

def test_redact_pii_contextvar_is_isolated():
    # Twee gelijktijdige redact-aanroepen mogen elkaars token_maps niet mengen.
    import asyncio
    from src.core.governance.gdpr_enforcer import _pii_token_map
    async def task_a():
        _pii_token_map.set({"[TOKEN_PII_0]": "a@a.nl"})
        await asyncio.sleep(0)
        return _pii_token_map.get()
    async def task_b():
        _pii_token_map.set({"[TOKEN_PII_0]": "b@b.nl"})
        await asyncio.sleep(0)
        return _pii_token_map.get()
    results = asyncio.run(asyncio.gather(task_a(), task_b()))
    assert results[0] != results[1]
```

Voer uit: `pytest tests/unit/test_gdpr_enforcer_redact.py -v`
Verwacht: FAIL (redact_pii niet geimplementeerd)

### Stap 2 -- `redact_pii()` implementeren in `gdpr_enforcer.py`

Zie sectie 3.1. Voer tests opnieuw uit: alle groen.

### Stap 3 -- Falende test voor `llm_client._sanitize_messages()`

```python
# tests/unit/test_llm_client_dlp.py
async def test_chat_completion_does_not_send_email_to_provider(mock_provider):
    client = LLMClient(provider=mock_provider)
    await client.chat_completion([
        {"role": "user", "content": "Stuur naar jan@example.com"}
    ])
    sent_messages = mock_provider.last_messages
    assert "jan@example.com" not in sent_messages[0]["content"]
```

Voer uit: `pytest tests/unit/test_llm_client_dlp.py -v`
Verwacht: FAIL

### Stap 4 -- `_sanitize_messages()` implementeren + integreren

Zie sectie 3.2/3.3. Voer test opnieuw uit: groen.

### Stap 5 -- PII-log fixes doorvoeren

Fix `frontend/auth.py` (SEC-001) en `ultimate_cva/agent.py` (SEC-002) per sectie 3.5.

### Stap 6 -- Architecture tests verifieren

```bash
pytest tests/architecture/test_pii_log_leakage.py -v
```

Verwacht na stap 5: alle 4 tests GROEN.
Verwacht nu (voor fix): ROOD op SEC-001 en SEC-002.

### Stap 7 -- Gate 3

```bash
python -m pyright
ruff check src/core/governance/gdpr_enforcer.py src/core/llm/llm_client.py
python -m pytest tests/unit/test_gdpr_enforcer_redact.py tests/unit/test_llm_client_dlp.py -v
```

---

## 5. Risico's en mitigaties

| Risico | Kans | Impact | Mitigatie |
|--------|------|--------|-----------|
| Detokenisatie-fout bij gestreamde responses | Middel | Hoog | Chunks samenvoegen voor detokenisatie (zie 3.4) |
| Performance overhead grote prompts | Laag | Middel | detect_pii() is O(n) regex; acceptabel voor <10KB; benchmark bij implementatie |
| Valse positieven (code die op email lijkt) | Laag | Laag | Whitelist voor bekende niet-PII patronen in gdpr_enforcer config |
| ContextVar leeg in Dramatiq worker | Middel | Hoog | Dramatiq workers moeten _pii_token_map.set({}) aanroepen bij start; clear in finally |
| Bestaande tests falen door gemaskeerde responses | Middel | Middel | Test-mocks geven geen PII terug -- geen impact verwacht |

---

## 6. Acceptatiecriteria

- [ ] `redact_pii()` maskeert email, IBAN, BSN, naam in testcases
- [ ] `detokenize()` herstelt originele waarden volledig
- [ ] `llm_client.chat_completion()` stuurt geen email verbatim naar externe provider
- [ ] `llm_client.generate_response()` idem
- [ ] `llm_client.complete_json()` idem
- [ ] `frontend/auth.py` logs bevatten geen email (SHA-256 hash ipv plaintext)
- [ ] `ultimate_cva/agent.py` logs bevatten geen `user_input` verbatim
- [ ] `tests/architecture/test_pii_log_leakage.py` -- alle 4 tests GROEN
- [ ] `python -m pyright` -- 0 errors (baseline bewaard)
- [ ] `python -m pytest tests/unit/ -n 8 --timeout=60 -q` -- 0 failures
