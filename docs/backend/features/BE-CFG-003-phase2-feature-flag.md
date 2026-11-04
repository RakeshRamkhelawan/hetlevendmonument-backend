# BE-CFG-003 — Phase2 Feature Flag (PHASE2_ENABLED)

**ID:** BE-CFG-003
**Sprint:** SP-E07
**Datum:** 2026-05-29
**Bestand:** `src/core/api/setup/router_registry.py`
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

De phase2 router (ethics-gate, multi-LLM orchestration) werd altijd geregistreerd
als de module importeerbaar was. Hierdoor retourneerden endpoints als
`/api/v1/phase2/status` de string `status="stub_implementation"` aan klanten --
misleidend en in strijd met productie-gereedheid (P1-7). Fix: router gated achter
`PHASE2_ENABLED=false` feature flag, zelfde patroon als SP-B03 (RAG_ENABLED).

---

## Wijziging

**Bestand:** `src/core/api/setup/router_registry.py`

```python
# VOOR (altijd gemount als import slaagt):
if phase2_router:
    app.include_router(phase2_router)

# NA (alleen gemount als operator expliciet PHASE2_ENABLED=true zet):
if phase2_router and os.getenv("PHASE2_ENABLED", "false").lower() == "true":
    app.include_router(phase2_router)
```

Tevens: `import os` toegevoegd aan module-level imports (was alleen lokaal beschikbaar).

---

## Architectuurbeslissingen

1. **Registratie-tijd gating:** De phase2 module wordt nog steeds geimporteerd (via
   bestaande try/except) voor ImportError-afhandeling. De feature flag voorkomt alleen
   de registratie. Dit minimaliseert de wijziging en behoudt bestaand gedrag bij ImportError.
2. **`PHASE2_ENABLED` als aparte vlag:** Eigen vlag per CLAUDE.md §9 patroon.
   Default `"false"` is veilig voor productie.
3. **Geen breaking change:** Bestaande deployments (zonder de vlag) gedragen zich als `false`.

---

## Trainingssamenvatting

### Flow: Phase2 endpoints disablen (default productiegedrag)

| Veld | Inhoud |
|------|--------|
| **Actor** | Platform operator / DevOps |
| **Voorwaarde** | `PHASE2_ENABLED` env var niet gezet of `"false"` |
| **Actie** | Client benadert `/api/v1/phase2/*` of `/api/v1/phase2/ethics-gate/status` |
| **Systeemverwerking** | Router niet geregistreerd bij app startup -- FastAPI heeft geen route |
| **Succesrespons** | HTTP 404 Not Found (geen stub misleiding voor client) |
| **Foutrespons** | n.v.t. -- 404 is het correcte en gewenste gedrag |
| **Uitzonderingen** | `PHASE2_ENABLED=true` -- router gemount, endpoints bereikbaar (nog als stub) |

---

## Tests

- `tests/unit/test_sp_e07_phase2_gate.py` -- 11/11 PASS

---

## MINOR GAP

`.env.example` kon niet worden bijgewerkt (bestandsrechten). Handmatig toe te voegen:
```
# Phase 2 endpoints (ethics-gate, multi-LLM orchestration). Default: false (not ready)
PHASE2_ENABLED=false
```
