# BE-UTL-013 — Batch current_user Fix + CI Gate Integratie

**ID:** BE-UTL-013
**Sprint:** SP-TYPE-01 Dag 9
**Type:** Utility (type refactoring + CI integratie)
**Status:** CLOSED — commits `f12437f5`, `95c46118`
**Bestanden:** `src/core/api/chat_endpoints.py`, `src/core/api/learning_endpoints.py`, `src/core/api/sandbox_endpoints.py`, `src/core/api/system_endpoints.py`, `src/core/api/v1/als/router.py`, `.github/workflows/ci-feature.yml`

---

## Samenvatting

Batch-vervanging van `current_user: Any = Depends(get_current_user)` in 5 resterende API bestanden (14 occurrences totaal). Toevoeging van de `any-type-gate` informational stap in de CI pipeline.

---

## Wijzigingen

### API bestanden (14 fixes)
- `chat_endpoints.py`: 2× `current_user: Any` → `UserResponse`
- `learning_endpoints.py`: 4× `current_user: Any` → `UserResponse`
- `sandbox_endpoints.py`: 2× `current_user: Any` → `UserResponse`
- `system_endpoints.py`: 4× `current_user: Any` → `UserResponse`
- `v1/als/router.py`: 2× `current_user: Any` → `UserResponse` (patroon: `get_current_user_dependency`)

### .github/workflows/ci-feature.yml
- Stap `any-type-gate` toegevoegd na DI-check
- Vergelijkt gewijzigde `src/*.py` bestanden via `git diff origin/develop...HEAD`
- Rapporteert violations als `::warning::` (non-blocking)
- Review-fix dag 9: `pip install ruff` verwijderd (redundant), import volgorde `chat_endpoints.py` gecorrigeerd

---

## CI Gate specificatie

```yaml
- name: Any-type gate (informational -- tracks new Any without TODO)
  run: |
    VIOLATIONS=$(git diff --name-only origin/develop...HEAD -- '*.py' | grep '^src/' | xargs -r python scripts/check_any_gate.py 2>&1 || true)
    if [ -n "$VIOLATIONS" ]; then
      echo "::warning::New Any annotations without TODO(TYPE) found in changed files:"
      echo "$VIOLATIONS"
    fi
```

**Design keuze:** Non-blocking (`|| true`, `::warning::`) omdat de baseline 8994 TODO-annotaties bevat. Zodra de backlog opgeruimd is, kan de step worden omgezet naar `exit 1` voor volledige enforcement.

---

## Trainingssamenvatting

**Flow: CI gate informational warning activeren**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | CI pipeline (GitHub Actions) |
| Voorwaarde | Developer pusht naar feature branch met nieuwe `Any` zonder `TODO(TYPE)` |
| Actie | `any-type-gate` stap vergelijkt gewijzigde files via git diff |
| Systeemverwerking | `check_any_gate.py` scant gewijzigde `src/*.py` bestanden |
| Succesrespons | "Any-type gate: no new violations in changed src/ files." |
| Foutrespons | `::warning::New Any annotations...` (niet-blokkerend) |
| Uitzonderingen | Directe pushes naar develop: git diff geeft 0 bestanden → gate rapporteert "no violations" |
