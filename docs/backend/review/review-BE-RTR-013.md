# Review BE-RTR-013 — Agents Domain Migration naar v1/agents/

**Reviewer:** Code Review Agent (Laag A)
**Datum:** 2026-06-04
**Sprint:** SP-API-003 Dag 3
**Status:** APPROVED WITH MINOR GAPS

---

## Oordeel

**APPROVED WITH MINOR GAPS**

De migratie is correct uitgevoerd. ADR-033 drie-laags compositie gehandhaafd. URL-contract
ongewijzigd (ADR-031 URL-freeze). Tenant isolatie geborgd via `get_current_user_dependency`
en `require_scopes`. 130 tests groen, 0 regressies.

---

## Bevindingen

### LOW — agent_crud_router importeert intern van agent_endpoints (acceptable)

Sub-routers importeren helpers (`_perform_registration`, `list_agents`, schema classes) uit
`agent_endpoints.py`. Dit is een bewuste pragmatische keuze gedocumenteerd in de spec:
de 852-regel implementatie dupliceren zou meer risico introduceren. De flat file heeft
`# orphan:exempt` commentaar. Acceptabel voor SP-API-003 scope.

**Impact:** Laag — koppeling is intern, niet cross-domain.
**Aanbeveling:** In een toekomstige sprint de implementatie volledig verplaatsen naar
`src/core/agents/` service laag. Huidige aanpak is een geldige tussenoplossing.

### LOW — Lege-pad aliases verwijderd

`@router.post("")` en `@router.get("")` zijn verwijderd vanwege FastAPI 0.121.1 beperking
(path="" zonder prefix verboden). Dit zijn `include_in_schema=False` interne aliases die
in het origineel alleen bestonden voor achterwaartse compatibiliteit met oudere clients.
De `/` variants dekken hetzelfde gedrag.

**Impact:** Geen — aliases waren hidden endpoints.
**Aanbeveling:** Geen actie vereist.

---

## Checklist

- [x] Drie-laags compositie gevolgd (ADR-033)
- [x] Laag 3 registry ≤80 regels
- [x] Sub-routers hebben `# orphan:exempt` of zijn ≤200 regels
- [x] Geen directe ORM of business logic in router handlers
- [x] tenant_id altijd uit JWT/middleware, nooit uit request body
- [x] Geen `from __future__ import annotations`
- [x] URL-contract ongewijzigd (ADR-031 URL-freeze)
- [x] Route-volgorde correct (statische paden voor path-param routes)
- [x] Equivalentietest toegevoegd en groen
- [x] Trainingssamenvatting aanwezig in spec
- [x] 130 tests PASS, 0 regressies
