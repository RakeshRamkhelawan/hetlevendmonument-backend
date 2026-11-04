# BE-EP-008 — Canvas Export Access Check + WS Auth Fix

**ID:** BE-EP-008  
**Sprint:** SP-E03  
**Datum:** 2026-05-29  
**Status:** APPROVED  
**Type:** Security fix (BE-EP — endpoint hardening)

---

## Samenvatting

Two security fixes applied to canvas-related API code:

**Fix A (`export_import.py`):** The `export_canvas` endpoint previously called a
non-existent module-level `canvas_service` singleton and had a TODO placeholder
instead of access control. This is replaced by `CanvasService` per-request
instantiation, which internally calls `_check_canvas_access()`. Unauthorized access
now returns HTTP 403; non-existent canvases return HTTP 404.

**Fix B (`agent_blocks.py`):** The WebSocket execution stream handler used
`UUID(int=0)` (null sentinel) as `user_id` in the audit trail.
`get_current_user_ws` (cookie-first, query-param fallback) is now a Depends
parameter; the real `user_id=UUID(int=current_user.id)` is passed to `execute_block`.

---

## Betrokken bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/v1/canvas/export_import.py` | Fix A: CanvasService + 403/404, datetime.utcnow fixes, response_model=None |
| `src/core/api/v1/canvas/agent_blocks.py` | Fix B: get_current_user_ws dependency + UUID(int=current_user.id) |
| `src/domains/canvas/agent_block_registry.py` | New: thin wrapper exporting get_agent_block_registry() |
| `tests/unit/test_sp_e03_canvas_access.py` | 9 source-level TDD tests (4 Fix A + 5 Fix B) |

---

## Architectuurbeslissingen

- `CanvasService` is een per-request instantie (`db`, `tenant_id`, `user_id` in constructor).
  `_check_canvas_access()` wordt intern aangeroepen bij `get_canvas()` — de API-laag
  hoeft de access-check-logica niet zelf te implementeren.
- `PermissionDeniedError` -> HTTP 403, `NotFoundError` -> HTTP 404.
  Andere exceptions propageren naar FastAPI (HTTP 500) zodat stacktraces niet verloren gaan.
- `UUID(int=current_user.id)` converteert de integer user-PK naar UUID formaat voor
  `execute_block`. Dit is een bestaand patroon in de codebase (type mismatch tussen
  `UserResponse.id: int` en `Canvas.owner_id: UUID`).
- De `export_import.py` router is niet geregistreerd; dode code. De fix garandeert
  dat de module importeerbaar is en dat `export_canvas` correct toegangsbeheer afdwingt
  zodra de router wél geregistreerd wordt.

---

## Trainingssamenvatting

### Flow 1 — Export canvas (geauthenticeerde eigenaar)

| Stap | Detail |
|------|--------|
| **Actor** | Ingelogde gebruiker (canvas eigenaar of collaborator) |
| **Voorwaarde** | Geldig JWT-token, canvas bestaat, gebruiker heeft toegang |
| **Actie** | `GET /canvas/{canvas_id}/export?format=json` |
| **Systeemverwerking** | `CanvasService(db, tenant_id, cast(UUID, user.id)).get_canvas(canvas_id)` → `_check_canvas_access()` |
| **Succesrespons** | HTTP 200 + exportdata (JSON/Markdown/HTML/SVG) |
| **Foutrespons** | HTTP 403 (`PermissionDeniedError`) of HTTP 404 (`NotFoundError`) |
| **Uitzonderingen** | Overige exceptions propageren als HTTP 500 |

### Flow 2 — Export canvas (ongeautoriseerde gebruiker)

| Stap | Detail |
|------|--------|
| **Actor** | Ingelogde gebruiker (andere tenant of geen collaborator-rol) |
| **Voorwaarde** | Canvas bestaat maar gebruiker heeft geen toegang |
| **Actie** | `GET /canvas/{canvas_id}/export?format=json` |
| **Systeemverwerking** | `CanvasService.get_canvas()` → `_check_canvas_access()` → `raise PermissionDeniedError` |
| **Foutrespons** | HTTP 403 `{"detail": "Access denied"}` |
| **Uitzonderingen** | — |

### Flow 3 — WebSocket executie-stream (geauthenticeerd)

| Stap | Detail |
|------|--------|
| **Actor** | Browser-client (via WebSocket) |
| **Voorwaarde** | Cookie `access_token` aanwezig of `?token=` query-param |
| **Actie** | WS connect + `{"action": "start"}` bericht |
| **Systeemverwerking** | `get_current_user_ws` valideert JWT voor accept(); `execute_block(user_id=UUID(int=current_user.id))` |
| **Succesrespons** | Streaming output van block-executie |
| **Foutrespons** | HTTP 401 als token ontbreekt (door `get_current_user_ws`) |
| **Uitzonderingen** | `WebSocketDisconnect` wordt gevangen; audittrail bevat real user_id |

---

## Tests

| Testbestand | Tests | Markers |
|-------------|-------|---------|
| `tests/unit/test_sp_e03_canvas_access.py` | 9 | `unit`, `security` |

**Fix A tests (source-level):**
- `test_todo_access_check_removed_from_export_import`
- `test_export_import_does_not_use_broken_canvas_service_call`
- `test_export_canvas_uses_canvas_service_for_access`
- `test_http_403_present_in_export_import`

**Fix B tests (source-level):**
- `test_null_uuid_int_0_removed_from_agent_blocks`
- `test_agent_blocks_ws_handler_uses_get_current_user_ws`
- `test_agent_blocks_todo_get_from_auth_removed`
- `test_execution_stream_websocket_has_current_user_parameter`
- `test_audit_log_receives_real_user_id_not_zero`
