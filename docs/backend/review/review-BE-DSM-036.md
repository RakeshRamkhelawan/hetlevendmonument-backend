# Review: BE-DSM-036

**ID:** BE-DSM-036
**Sprint:** SP-DSM-017 Dag 1
**Datum:** 2026-06-26
**Reviewer:** Self-review (< 20 regels, 1 bestand)
**Status:** APPROVED

---

## Oordeel: APPROVED

---

## Bevindingen

### FA-001 (MINOR, opgelost): governance MODULE_MAP aanpak veroorzaakte I regressie

**Bevinding:** `governance.audit` + `governance.services.audit_service` -> shared geprobeerd.
Governance I steeg naar 0.446 (drempel 0.40). Root cause: Ca reductie (3 tenancy->governance
edges worden tenancy->shared, verliezen bijdrage aan governance Ca).

**Oplossing:** Alleen `agents.models -> shared` geimplementeerd. Governance fix uitgesteld naar
latere sprint dag met code-level SecurityEvent verplaatsing.

**Status:** OPGELOST (tenancy->agent_runtime gesloten, governance I < 0.40 behouden).

---

### FA-002 (procesafspraak nageleefd): rode tests in aparte commit

Commit `dea8d239` bevat de rode arch-tests. Fix in separaat commit.

---

## DoD-checklist

- [x] tenancy->agent_runtime = 0 gesloten
- [x] governance I < 0.40 behouden
- [x] shared fan-out = 0 behouden (SOURCE_DIRS["shared"] onaangeroerd)
- [x] Rode test in aparte commit dea8d239 (FA-002)
- [x] Pyright 0 errors (0 errors, 57 warnings)
- [x] Arch-suite 260 passed, 13 xfailed, 0 regressions
- [x] agents.models patroon consistent met auth.models + workflow.models
- [x] tenancy->governance backlog tracking test aangemaakt
- [x] Feature spec BE-DSM-036 aangemaakt
