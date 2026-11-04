# BE-RTR-021 -- GDPR Compliance Domain Migration naar v1/gdpr_compliance/ (ADR-033)

**Sprint:** SP-API-005 Dag 1
**Datum:** 2026-06-04
**Status:** DONE

---

## Beschrijving

`gdpr_compliance_endpoints.py` (1328r) gemigreerd naar `src/core/api/v1/gdpr_compliance/`
via ADR-033 drie-laags compositie. Strangler Fig stap 1.

**URL prefix bewaard:** `/api/gdpr` (zonder `/v1/`) -- domain_router heeft GEEN extra prefix.

**Registratie verplaatst:** van legacy `setup/router_registry.py` naar `registries/compliance.py` (ADR-033).

**Sub-routers:**

| Bestand | Routes | Regels |
|---|---|---|
| `access_router.py` | GET /audit-trail, GET /status | 129r |
| `erasure_router.py` | POST /delete-all | 264r (`# orphan:exempt` r1) |
| `portability_router.py` | POST /export, GET /export/download/{id} | 367r (`# orphan:exempt` r1) |
| `utility_router.py` | GET /checklist, PUT /checklist/{requirement_id} | 308r (`# orphan:exempt` r1) |

---

## Trainingssamenvatting

### Flow: GDPR data-export aanvragen

**Actor:** Geauthenticeerde gebruiker
**Actie:** POST /api/gdpr/export
**Systeemverwerking:** portability_router delegeert naar GDPRExportService
**Succesrespons:** 202 Accepted met export job ID
**Foutrespons:** 401 zonder auth, 500 bij service-fout
**Uitzonderingen:** audit log in best_effort (export is GDPR-gevoelig)

### Flow: GDPR domein toevoegen aan registries

**Actor:** Backend developer
**Actie:** Import `from src.core.api.v1.gdpr_compliance import domain_router` in registries/compliance.py
**Let op:** domain_router heeft GEEN prefix -- sub-routers bevatten `/api/gdpr` zelf
