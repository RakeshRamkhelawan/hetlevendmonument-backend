# BE-DSM-032 -- SP-DSM-016 Dag 1: public_registry naar shared (sluit auth<->tenancy)

**Sprint:** SP-DSM-016 Dag 1 (AUDIT-DSM-004)
**Datum:** 2026-06-25
**Status:** APPROVED

---

## Probleem

`src/core/security/security_middleware.py:24` had een top-level runtime-import:

```python
from src.core.middleware.public_registry import PublicEndpointRegistry
```

`src/core/middleware/` is de tenancy-laag. Samen met de legitieme afhankelijkheid van
`tenant_middleware.py` op `auth` (jwt_handler, token_extraction) sloot dit het circulaire
pair `auth <-> tenancy`:

```
security_middleware (security/auth) -> middleware.public_registry (tenancy)
tenant_middleware (tenancy)         -> auth.jwt_handler (auth)
```

---

## Oplossing

`public_registry.py` verplaatst van `src/core/middleware/` naar `src/core/shared/`.

`shared` is de laagste dependency-laag; elk module mag van `shared` importeren zonder
een circulaire koppeling te introduceren.

### Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/shared/public_registry.py` | Nieuw (verplaatst van middleware/) |
| `src/core/middleware/public_registry.py` | Verwijderd |
| `src/core/security/security_middleware.py:24` | Import bijgewerkt naar `src.core.shared.public_registry` |
| `src/core/middleware/tenant_middleware.py:31` | Import bijgewerkt naar `src.core.shared.public_registry` |
| `src/core/api/public_endpoints.py:1,3` | Shim-comment + import bijgewerkt |
| `tests/architecture/test_agent_discovery_auth.py:16` | Import bijgewerkt (RC-001) |

### QR-001 fix: mutable set exposure

`get_public_paths()` en `get_public_prefixes()` gaven directe referenties terug naar de
class-level `set[str]` objecten. Een aanroeper die `registry.get_public_paths().add(...)` deed
zou de singleton-state permanent muteren en authentication bypassen voor dat pad.

Fix: beide methoden geven nu een kopie terug:

```python
# VOOR:
return cls.PUBLIC_PATHS

# NA:
return set(cls.PUBLIC_PATHS)
```

### QR-002 fix: debug-login dead entry verwijderd

`/api/v1/auth/debug-login` stond in `PUBLIC_PATHS` maar geen route met dit pad bestaat
in de codebase. Verwijderd om te voorkomen dat een toekomstig endpoint automatisch
zonder authenticatie draait.

---

## Impact

### Positief
- `auth <-> tenancy` circulair pair gesloten (SP-DSM-016 DoD)
- Mutable set exposure in `get_public_paths/prefixes()` verholpen (latente auth bypass)
- Dead whitelist-entry verwijderd

### Neutraal
- `src/core/api/public_endpoints.py` re-export shim blijft bestaan voor backward compat
- Geen API-contract wijzigingen; `PublicEndpointRegistry` interface ongewijzigd

---

## Verificatie

- Rode test ROOD voor fix: `2 failed`
- Rode test GROEN na fix: `2 passed`
- Arch-suite: 250 passed (was 248 + 2 nieuwe), 0 failed, 13 xfailed
- Gerichte unit-tests: 204 passed, 14 skipped, 9 xfailed (identiek aan baseline)
- Pyright: 22 errors (alle pre-existing in ongewijzigde bestanden)


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-DSM-016 Dag 1: public_registry verplaatst naar shared. auth<->tenancy circulair gesloten. QR-001 mutable set fix + QR-002 dead entry verwijderd. 250 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-DSM-016 Dag 1: public_registry verplaatst naar shared. auth<->tenancy circulair gesloten. QR-001 mutable set fix + QR-002 dead entry verwijderd. 250 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
