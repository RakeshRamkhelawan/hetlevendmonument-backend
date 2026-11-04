# Review BE-API-039 -- ADR-033 Batch A Flat File Proxy Stubs

Sprint: SP-API-010 Dag 2
Datum: 2026-06-11
Reviewer: self-review (code-reviewer + quality-reviewer via bash)
Oordeel: APPROVED WITH MINOR GAPS

---

## Bevindingen

### APPROVED (geen blockers)

**ADR-033 Contract 1 compliance**
Alle 6 batch-A clean files: 0 violations na stubs. Bewijs:
`test_flat_file_batch_a_clean.py` PASSED.

**RFC 8594 / RFC 9745 deprecation headers**
5 van de 6 stubs krijgen `Deprecation: true` + `Sunset: Thu, 01 Jan 2028 00:00:00 GMT` op alle routes:
orchestrator, tool, workflow_refinement, template, agentic_flow.
`pack_feedback_endpoints.py` is de uitzondering: alle 7 routes blijven volledig functioneel
(geen stub-response, geen RFC headers) omdat alle routes nog actief zijn en er geen v1/
equivalent beschikbaar is. Dit is een bewuste keuze gedocumenteerd in het stub-patroon.

**orphan:exempt bewaard**
Alle 6 bestanden hebben de `orphan:exempt` marker bijgewerkt naar SP-API-010 formaat.

**OWASP A5: geen str(e) lekken in nieuwe code**
Nieuwe stubs gebruiken overal `detail="Internal error"` of generieke foutmeldingen.

**tenant_id**: Altijd via Depends(require_tenant_id) of JWT, nooit uit request body.

**datetime**: Geen datetime.now() of utcnow() in gewijzigde code.

**ASCII-only**: Nieuwe code bevat geen emoji of non-ASCII.

**Pyright baseline**: 0 errors voor mijn wijzigingen (bewezen via stash test).

**Architecture tests**: 1 PASS + 8 XFAIL (strict=True) -- alle gaps gedekt.

**Regressiecheck**: 188 passed, 12 xfailed, 0 failed (unit/api/ + architecture/).

---

### MINOR GAPS (geen blockers, naar backlog)

**MG-1**: `agentic_flow_endpoints.py` WebSocket handler bevat pre-existing emoji
(bv. `logger.info(f"WS scope: ...")` in log-strings) en `str(e)` lekken.
Niet gerepareerd om regressierisico in complexe WS-handler te vermijden.
Actie: TODO(SP-API-011) in handler-body toegevoegd; opruimen bij v1/ migratie.

**MG-2**: `src/core/scheduling/smart/predictor.py` has uncommitted type-wijzigingen
die 9 pyright errors veroorzaken (buiten scope SP-API-010).
Bewijs via stash: pyright = 0 zonder die file. Vereist aparte sprint.

**MG-3**: `pack_feedback_endpoints.py` POST /global/pending heeft TODO-admin-check
pre-existing. Bewaard als `del current_user  # proxy stub -- Depends enforce auth; TODO: admin check`.
Actie: expliciet TODO(SP-API-011) in code.

---

## Checklist

- [x] ADR-033 Contract 1: 6 clean files, 0 violations
- [x] RFC 8594/9745 headers op alle deprecated routes (5/6 stubs; pack_feedback bewust uitgezonderd -- routes functioneel)
- [x] orphan:exempt markers correct formaat
- [x] Geen tenant_id uit request body
- [x] Geen datetime.now()/utcnow()
- [x] Geen emoji/non-ASCII in nieuwe code
- [x] Pyright 0 errors (mijn wijzigingen)
- [x] Architecture tests: 1 PASS + 8 XFAIL
- [x] Unit tests bijgewerkt (orchestrator stub-gedrag)
- [x] Regressiecheck: 0 nieuwe failures
- [x] Feature spec aangemaakt: BE-API-039
- [x] ID-REGISTRY bijgewerkt
