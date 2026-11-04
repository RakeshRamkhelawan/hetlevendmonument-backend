# BE-RTR-027 -- CVA Domain Consolidatie (SP-API-006 Dag 2)

**Sprint:** SP-API-006 Dag 2
**Datum:** 2026-06-05
**Status:** DONE

---

## Beschrijving

Drie pre-ADR-033 flat files zijn geconsolideerd naar de bestaande `v1/cva/` structuur:

| Flat bestand | Omgezet naar | Routes |
|---|---|---|
| `cva_chat.py` (322r) | re-export shim | POST /chat, POST /chat/stream, POST /chat/legacy |
| `cva_admin.py` (409r) | re-export shim | GET /status, /health, /status-detail, /analytics, POST /optimize, /shutdown |
| `cva_conversations.py` (220r) | re-export shim | GET /conversations, GET /conversations/{id}, DELETE /conversations/{id}, DELETE /conversations/{id}/messages |

**Nieuw toegevoegd:** `DELETE /conversations/{id}/messages` in `conversations_router.py` (ontbrak in SP-API-004 migratie).

**main.py:** `"src.core.api.cva_admin"` verwijderd uit `wire_container()` modules lijst.

---

## Trainingssamenvatting

### Flow: CVA flat files consolideren

**Actor:** Backend developer
**Voorwaarde:** v1/cva/ bestaat al (SP-API-004), routes zijn al gemigreerd
**Actie:** Controleer via scan of alle routes aanwezig zijn in v1/cva/ sub-routers
**Systeemverwerking:** Flat file wordt 2-3 regels re-export shim met `# orphan:exempt` op r1
**Succesrespons:** Equivalentietest GROEN, 0 regressions
**Foutrespons:** Route ontbreekt in v1/cva/ → eerst toevoegen aan sub-router
