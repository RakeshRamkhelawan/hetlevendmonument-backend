# BE-RTR-030 -- Synthesis Domain Migration naar v1/synthesis/ (SP-API-006 Dag 5)

**Sprint:** SP-API-006 Dag 5
**Datum:** 2026-06-05
**Status:** DONE

---

## Beschrijving

`synthesis_endpoints.py` (518r) gemigreerd naar `src/core/api/v1/synthesis/` via ADR-033 drie-laags compositie. Strangler Fig stap 1.

**1 route:** POST /api/v1/synthesis

**Sub-routers:**
| Bestand | Routes | Regels |
|---|---|---|
| `synthesis_router.py` | POST /synthesis | 138r |
| `synthesis_service.py` | Service-laag (helper) | 358r |

**domain_router:** GEEN prefix -- sub-router bevat `/api/v1` als prefix.

---

## Trainingssamenvatting

### Flow: synthesis endpoint aanroepen

**Actor:** Geauthenticeerde gebruiker
**Actie:** POST /api/v1/synthesis met synthesis payload
**Systeemverwerking:** synthesis_router delegeert naar synthesis_service
**Succesrespons:** 200 met synthesis resultaat
**Foutrespons:** 401 zonder auth, 500 bij service-fout
