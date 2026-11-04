# BE-SEC-016 -- JWT Verificatie Unificatie (SP-WE-13)

**ID:** BE-SEC-016
**Sprint:** SP-WE-13
**Datum:** 2026-06-01
**Bron:** CG-007 (L3 wiring audit 2026-06-01)
**ADR:** ADR-003

---

## Samenvatting

`SecurityMiddleware` verifieerde JWT tokens via `security_manager.verify_token()` die
`sub` en `tenant_id` claims NIET controleerde. Een token zonder deze verplichte claims
werd geaccepteerd, waardoor auth bypass mogelijk was via dit pad. Fix: beide
aanroepen in `_check_authentication` en `_extract_user_id` vervangen door de canonieke
`jwt_handler.verify_token()` die sub, tenant_id, exp en HS256-only afdwingt (ADR-003).

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/security/security_middleware.py` | Import `_jwt_handler`; 2 aanroepen vervangen; `user_id` -> `sub` claim; `security_level` guard met explicit fallback |
| `src/core/security/security_manager.py` | NOTE docstring aan `generate_token()` toegevoegd |

## Trainingssamenvatting

### Flow 1: SecurityMiddleware JWT verificatie via canoniek jwt_handler pad

- Actor: SecurityMiddleware (`src/core/security/security_middleware.py`)
- Voorwaarde: HTTP request met `Authorization: Bearer <token>` header of `access_token` cookie; voor de fix verificatie via `security_manager.verify_token()` zonder sub/tenant_id check; na de fix via `jwt_handler.verify_token()`
- Actie: `_check_authentication()` extraheert de token en roept `_jwt_handler.verify_token(token)` aan
- Systeemverwerking: jwt_handler decodeert token, controleert exp, controleert aanwezigheid `sub` claim, controleert aanwezigheid `tenant_id` claim, retourneert payload of None; TypeError/ValueError worden gecatched en vertaald naar valid=False
- Succesrespons: `{"valid": True, "message": "Authenticated", "user_id": <sub>}` -- request doorgelaten
- Foutrespons: `{"valid": False, "message": "Invalid or expired token"}` (None van jwt_handler) of `{"valid": False, "message": "Invalid token format"}` (TypeError/ValueError) -- HTTP 401
- Uitzonderingen: (1) Token zonder tenant_id -- afgewezen door jwt_handler, retourneert None; (2) Token zonder sub -- afgewezen, None; (3) Non-string token -- TypeError gecatched, 401; (4) Lege string -- ValueError gecatched, 401; (5) Geen security_level claim -- explicit default AUTHENTICATED, geen silent crash

### Flow 2: TenantMiddleware JWT verificatie (ongewijzigd -- regressietest)

- Actor: TenantMiddleware (`src/core/middleware/tenant_middleware.py`)
- Voorwaarde: Zelfde token langs TenantMiddleware (was al correct)
- Actie: `jwt_handler.verify_token(token)` op regel 146 -- ongewijzigd
- Systeemverwerking: identiek aan Flow 1 na de fix -- beide paden gebruiken nu dezelfde verificatielogica
- Succesrespons: tenant_id en user_id in request scope gezet
- Foutrespons: HTTP 401 met foutmelding
- Uitzonderingen: Ontbrekende tenant_id claim -- HTTP 401 + security event logging
