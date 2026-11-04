# Review BE-GOV-005: RC-002 Legacy CVA council gate

**Reviewer:** code-reviewer (SP-GOV-002 dag 2)
**Datum:** 2026-06-23
**Verdict:** APPROVED

## Bevindingen

Geen CRITICAL of HIGH bevindingen.

### PASS: Council gate volgorde correct
`execute_cva_council_gate` wordt aangeroepen VOOR de outer `try` block, zodat
`HTTPException(403)` niet wordt gevangen door de generieke error handler.

### PASS: ADR-033 compliance
`copilot.council.*` imports leven uitsluitend in `cva/dependencies.py` (exempt).
`legacy_router.py` importeert alleen van `src.core.api.v1.cva.dependencies` (own-domain, allowed).
Violation count: 6 (pre-existing dag 1) -- geen nieuwe violations.

### PASS: tenant_id correct
`current_user.tenant_id` en `current_user.id` uit JWT, niet uit request body.

### PASS: decision_id correct doorgestuurd
`str(decision.decision_id)` coercion aanwezig (UUID -> str). Meegegeven in beide returns.

### PASS: Tests cover unhappy + happy path
403-blokkade test + decision_id happy-path test aanwezig en GROEN.

### PASS: Pyright 0 errors
`council: Any` type is correct (runtime object via lazy import, niet statisch getypeerd).
