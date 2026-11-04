# BE-UTL-011 — user_helpers + template_router Type Hardening

**ID:** BE-UTL-011
**Sprint:** SP-TYPE-01 Dag 7
**Type:** Utility (type refactoring)
**Status:** CLOSED — commit `b5f31a72`
**Bestanden:** `src/core/api/user_helpers.py`, `src/core/api/v1/company/template_router.py`

---

## Samenvatting

Lokale variabele-annotaties verbeterd in helper-functies en een inner class.

---

## Wijzigingen

### user_helpers.py
- 8 lokale vars: `user_id/result: Any` → `int | None`, `email/email_result: Any` → `str | None`, `tenant_id/tenant_result: Any` → `int | None`, `role_id/role_result: Any` → `int | None`
- 8 `cast(Optional[X], ...)` → `cast(X | None, ...)` (Python 3.11 stijl)
- `Optional` import verwijderd

### template_router.py (SimpleDBManager inner class)
- `_session: Any` → `AsyncSession`
- `__init__` parameter `session: Any` → `AsyncSession`
- `SessionContext.session: Any` → `AsyncSession`
- `__aenter__` return `Any` → `AsyncSession`
- `get_session()` return `"SessionContext"` → `object` (inner class is niet forward-referentieerbaar)

---

## Trainingssamenvatting

**Flow: lokale variabelen typen in helper-functies**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Type-safety sprint agent |
| Voorwaarde | `user_id: Any = getattr(...)` patroon in user_helpers.py |
| Actie | Annotatie vervangen: `getattr(obj, "id", None)` retourneert `int \| None` |
| Systeemverwerking | AST-gebaseerde TDD test (rood → groen) per functie |
| Succesrespons | 5/5 TDD tests groen |
| Uitzonderingen | `current_user: Any` parameter NIET vervangen — bewust polymorfisch (handles dict en UserResponse) |
