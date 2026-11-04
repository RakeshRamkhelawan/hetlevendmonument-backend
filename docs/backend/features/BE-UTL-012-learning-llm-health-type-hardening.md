# BE-UTL-012 — v1/agentic/learning + v1/system/llm_health Type Hardening

**ID:** BE-UTL-012
**Sprint:** SP-TYPE-01 Dag 8
**Type:** Utility (type refactoring)
**Status:** CLOSED — commit `cb4bf459`
**Bestanden:** `src/core/api/v1/agentic/learning.py`, `src/core/api/v1/system/llm_health.py`

---

## Samenvatting

`current_user: Any = Depends(get_current_user)` vervangen door `UserResponse` in 16 endpoints. `LLMProviderType` als lokaal variabele type gezet in llm_health.

---

## Wijzigingen

### v1/agentic/learning.py
- 11× `_current_user: Any` → `UserResponse`
- `from src.core.auth.auth_service import UserResponse` toegevoegd
- `Optional` import verwijderd

### v1/system/llm_health.py
- 5× `current_user: Any` → `UserResponse`
- `target: Any = LLMProviderType(...)` → `LLMProviderType` (lokale variabele annotatie, geen runtime evaluatie voor function-locals)
- `from src.core.auth.auth_service import UserResponse` toegevoegd
- `Optional` import verwijderd

---

## Trainingssamenvatting

**Flow: current_user: Any → UserResponse batch-fix**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Type-safety sprint agent |
| Voorwaarde | `_current_user: Any = Depends(get_current_user)` in meerdere endpoints |
| Actie | Regex-gebaseerde batch-vervanging + import toevoegen |
| Systeemverwerking | TDD (4/4 rood → groen); ruff 0 errors |
| Succesrespons | Alle 16 endpoints getypeerd |
| Uitzonderingen | `LLMProviderType` als function-local annotatie: Python evalueert lokale annotaties niet at runtime, dus inline import in try-blok is voldoende |
