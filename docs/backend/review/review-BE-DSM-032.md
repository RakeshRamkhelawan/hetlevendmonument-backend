# Review BE-DSM-032 -- public_registry naar shared

**Sprint:** SP-DSM-016 Dag 1
**Datum:** 2026-06-25
**Status:** APPROVED

---

## Samenvatting

Twee onafhankelijke reviewers (code-reviewer + quality-reviewer) gaven initieel
CHANGES_REQUESTED vanwege 4 bevindingen. Na verwerking van alle bevindingen is de status APPROVED.

---

## Bevindingen

### RC-001 (BLOCKER -- opgelost)

**Bevinding:** `tests/architecture/test_agent_discovery_auth.py:16` had een hardcoded
import naar het te verwijderen module-pad. Na delete van `middleware/public_registry.py`
zou CI falen met `ModuleNotFoundError`.

**Actie:** Import bijgewerkt naar `from src.core.shared.public_registry import PublicEndpointRegistry`.

**Status:** OPGELOST.

---

### RC-002 (BLOCKER -- opgelost)

**Bevinding:** Comment in `src/core/api/public_endpoints.py:1` verwees nog naar de
oude locatie `src/core/middleware/public_registry.py`.

**Actie:** Comment bijgewerkt naar `src/core/shared/public_registry.py`.

**Status:** OPGELOST.

---

### QR-001 (HIGH -- opgelost)

**Bevinding:** `get_public_paths()` en `get_public_prefixes()` gaven directe referenties
terug naar mutable class-level sets. Een aanroeper die `.add()` of `.remove()` aanroept
muteert de singleton-state en bypast authenticatie voor willekeurige paden.

**Actie:** Beide methoden geven nu `set(cls.PUBLIC_PATHS)` en `set(cls.PUBLIC_PREFIXES)` terug.

**Status:** OPGELOST.

---

### QR-002 (MEDIUM -- opgelost)

**Bevinding:** `/api/v1/auth/debug-login` stond in `PUBLIC_PATHS` maar geen route
met dit pad bestaat in de codebase. Dead code met toekomstig risico op onbedoelde bypass.

**Actie:** Entry verwijderd uit `PUBLIC_PATHS`.

**Status:** OPGELOST.

---

### RC-004 (OBSERVATION -- geen actie)

**Bevinding:** `test_dsm016_public_registry_in_shared` checkt alleen bestandsbestaan;
de check of alle importers bijgewerkt zijn zit in een andere test.

**Status:** Geen actie. De twee tests samen dekken beide invarianten.

---

## DoD-checklist

- [x] Rode test ROOD voor de fix (2 failed)
- [x] Rode test GROEN na de fix (2 passed)
- [x] Arch-suite: 250 passed, 0 failed (was 248)
- [x] Gerichte unit-tests: 204 passed, 0 nieuwe failures
- [x] Pyright: 0 nieuwe errors (22 pre-existing in ongewijzigde bestanden)
- [x] RC-001 BLOCKER opgelost voor commit
- [x] RC-002 BLOCKER opgelost voor commit
- [x] QR-001 HIGH opgelost voor commit
- [x] QR-002 MEDIUM opgelost voor commit

---

**Eindoordeel: APPROVED**
