STATUS: APPROVED
# Backend Feature Review -- BE-CI-007

## Metadata

- Feature ID: BE-CI-007
- Feature naam: De CI op GitHub weer groen
- Review datum: 2026-10-23
- Reviewer: security-reviewer (subagent), een ronde Gate 2 op `scripts/check_non_ascii.py`, de pre-commit en de python-jose-guard; zelfreview op de rest
- Spec locatie: `docs/backend/features/BE-CI-007-ci-op-github-weer-groen.md`

---

## Eindoordeel

**APPROVED** na verwerking van de bevindingen van ronde 1. Een tweede ronde op eigen artefacten was niet nodig (ronde-cap: maximaal twee).

## Bevindingen en afhandeling

| ID | Ernst | Bevinding | Afhandeling |
|---|---|---|---|
| F-001 | HIGH | `str.splitlines()` splitst op U+0085, U+2028 en U+2029 en gooit die tekens weg; een bestand met alleen zo'n teken kwam erdoor (de oude `grep -P` ving het wel) | script splitst op `"\n"`; test `test_een_teken_dat_splitlines_als_regeleinde_ziet_faalt_ook`; mutatie Q1 rood |
| F-002 | MEDIUM | `git ls-files` citeert namen met een accent; het filter op `.py` zag ze niet | `git ls-files -z`; test met een bestand met een accent in de naam in een tijdelijke repo; mutatie Q2 rood |
| F-003 | MEDIUM | de jose-guard zag `from jose.jwt import decode` en `jws/jwk/jwe` niet | guard uitgebreid (commit cb4c69ae); 25 tests, mutaties J1-J3 rood, L2 legitiem groen |
| F-004 | LOW | `STAGED=` in de pre-commit citeert namen met een accent | bewust niet gerepareerd: een hookwijziging maakt de guard `test_de_geinstalleerde_hook_is_de_bron` rood in andere werkkopieen; klaar voor na de gezamenlijke push, op sein van de regie |

## Mutatiebewijs

Gedaan in een wegwerp-worktree (terugzetten met `git checkout --`): S1-S8 (hook, CI, script, bron), R1-R2 (ratel), J1-J3 (jose), Q1-Q2: ROOD. Legitiem L1-L2: GROEN.

## Niet gemeten

De CI op GitHub zelf; migraties, integratietests, coverage, Playwright-E2E en Docker-validatie.
