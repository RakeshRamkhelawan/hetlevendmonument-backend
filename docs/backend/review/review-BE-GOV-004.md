# Review BE-GOV-004

- Feature: RC-003 -- CVA model_id doorsturen naar council + canonical JSON
- Reviewer: code-reviewer + quality-reviewer (Taak 2 SP-GOV-002 dag 1)
- Datum: 2026-06-22
- Verdict: APPROVED

## Bevindingen

Geen CRITICAL of HIGH bevindingen.

Opmerking (niet blocker): `compute_canonical_json` hash chain is forward-only -- bestaande
records worden niet gemigreerd. Bewust besluit per ADR-019 (post-fix records bevatten model_id).

## DoD check

- [x] model_id != "unknown" doorgegeven aan council
- [x] Fallback naar "unknown" bewaard
- [x] compute_canonical_json bevat model_id + model_version
- [x] Pyright 0 errors
- [x] Geen Alembic migratie nodig
