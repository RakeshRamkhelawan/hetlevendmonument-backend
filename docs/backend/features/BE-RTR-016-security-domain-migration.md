---
id: BE-RTR-016
title: Security Domain Migration naar v1/security/ (SP-API-004 Dag 1)
type: BE-RTR
sprint: SP-API-004 Dag 1
date: 2026-06-04
status: APPROVED WITH MINOR GAPS
---

# BE-RTR-016: Security Domain Migration naar v1/security/

## Samenvatting

`src/core/api/security_endpoints.py` (1093r, 14 routes) is gemigreerd naar
`src/core/api/v1/security/` conform ADR-033 §4 Strangler Fig patroon.

## Scope

**Bestand verplaatst:** `security_endpoints.py` → `v1/security/` (5 sub-routers)

**14 routes gemigreerd:**

| Methode | Pad | Sub-router | Auth |
|---------|-----|------------|------|
| POST | /auth/login | auth_router.py | PUBLIC (deprecated) |
| GET | /report | report_router.py | ADMIN_ALL |
| GET | /events | report_router.py | ADMIN_ALL |
| GET | /summary | report_router.py | ADMIN_ALL |
| GET | /rate-limits | management_router.py | ADMIN_ALL |
| POST | /block-ip | management_router.py | ADMIN_ALL |
| POST | /unblock-ip | management_router.py | ADMIN_ALL |
| POST | /cleanup | management_router.py | ADMIN_ALL |
| GET | /health | monitoring_router.py | AGENTS_READ |
| GET | /audit-logs | monitoring_router.py | ADMIN_ALL |
| GET | /verify-integrity | monitoring_router.py | ADMIN_ALL |
| GET | /alerts | alerts_router.py | ADMIN_ALL |
| POST | /alerts/{alert_id}/acknowledge | alerts_router.py | ADMIN_ALL |
| POST | /alerts/{alert_id}/resolve | alerts_router.py | ADMIN_ALL |

## Structuur aangemaakt

```
src/core/api/v1/security/
├── __init__.py          (domain_router, prefix=/api/v1, tags=[Security])
├── router.py            (composite, prefix=/security)
├── dependencies.py      (get_db, get_current_user, require_scopes, etc.)
├── auth_router.py       (POST /auth/login — deprecated=True bewaard)
├── report_router.py     (GET /report, /events, /summary)
├── management_router.py (GET /rate-limits, POST /block-ip, /unblock-ip, /cleanup)
├── monitoring_router.py (GET /health, /audit-logs, /verify-integrity)
└── alerts_router.py     (GET /alerts, POST /acknowledge, /resolve)
```

## Security-specifieke checks

- `POST /auth/login` behoudt `deprecated=True` marker — backward-compat gehandhaafd
- Alle 13 niet-login endpoints bevatten `get_current_user` + `require_scopes` — geen auth-verlies
- `GET /verify-integrity` (ADR-019 hash chain) heeft `require_scopes(ADMIN_ALL)` ✓
- Geen `getattr(user, "tenant_id", None)` zonder fail-secure guard gevonden
- f-strings in logger volledig omgezet naar `%s` formatting

## Wijzigingen in registries

`registries/analytics.py`: `security_endpoints.router` vervangen door
`v1/security.domain_router` (65r, ≤80r limiet gehandhaafd).

`security_endpoints.py`: omgezet naar re-export stub met `# orphan:exempt`.

## Kwaliteitsborging

- `test_security_flat_file_migrated_to_v1` GROEN (1 passed)
- 136 tests PASS (tests/architecture/ + tests/unit/api/)
- analytics.py: 65r ≤ 80r limiet ✓
- Geen directe `src.core.database` imports in router-bestanden ✓

## Trainingssamenvatting

### Flow 1: Admin raadpleegt security rapport

| Stap | Detail |
|------|--------|
| **Actor** | Beheerder met ADMIN rol |
| **Voorwaarde** | Geldig JWT met `scope=admin_all` |
| **Actie** | GET /api/v1/security/report |
| **Systeemverwerking** | `get_security_manager()` → events aggregeren → SecurityReportResponse bouwen |
| **Succesrespons** | 200 + SecurityReportResponse (total_events, blocked_ips, threat_distribution) |
| **Foutrespons** | 500 bij interne fout |
| **Uitzonderingen** | 401 bij ontbrekend token, 403 bij onvoldoende scope |

### Flow 2: Admin verifieert hash chain integriteit

| Stap | Detail |
|------|--------|
| **Actor** | Beheerder met ADMIN rol |
| **Voorwaarde** | Geldig JWT met `scope=admin_all`, PostgreSQL bereikbaar |
| **Actie** | GET /api/v1/security/verify-integrity?limit=1000 |
| **Systeemverwerking** | `get_security_audit_service().verify_log_integrity()` → SHA-256 hash traversal |
| **Succesrespons** | 200 + LogIntegrityResponse (verified, entries_checked, tampered_entries) |
| **Foutrespons** | 500 bij DB-fout |
| **Uitzonderingen** | 401/403 bij auth-fout |

### Flow 3: Admin blokkeert IP-adres

| Stap | Detail |
|------|--------|
| **Actor** | Beheerder met ADMIN rol |
| **Voorwaarde** | Geldig JWT met `scope=admin_all` |
| **Actie** | POST /api/v1/security/block-ip met {ip_address, reason} |
| **Systeemverwerking** | IP valideren → `security_manager.blocked_ips.add()` → security event loggen |
| **Succesrespons** | 200 + {message, reason} |
| **Foutrespons** | 400 bij ongeldig IP, 500 bij interne fout |
| **Uitzonderingen** | 401/403 bij auth-fout |

### Flow 4: Admin lost security alert op

| Stap | Detail |
|------|--------|
| **Actor** | Beheerder met ADMIN rol |
| **Voorwaarde** | Geldig JWT met `scope=admin_all`, alert bestaat in DB |
| **Actie** | POST /api/v1/security/alerts/{alert_id}/resolve met {notes, false_positive} |
| **Systeemverwerking** | `get_security_audit_service().resolve_alert()` → status UPDATE in DB |
| **Succesrespons** | 200 + {message, alert_id} |
| **Foutrespons** | 404 bij onbekende alert_id, 500 bij DB-fout |
| **Uitzonderingen** | 401/403 bij auth-fout |
