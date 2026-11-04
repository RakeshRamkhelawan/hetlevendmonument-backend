# BE-DSM-014: SP-DSM-005 Dag 1 -- Contract 5 Hardening

**Sprint**: SP-DSM-005 Dag 1
**Datum**: 2026-06-17
**Status**: APPROVED

## Probleemstelling

Contract 5 (`governance-independence`) stond op `allow_indirect_imports = true` met
2 known-violations:
- `src.core.governance.hash_chain -> src.core.copilot.council.types` (OfficerVerdict)
- `src.core.governance.retention_cleanup -> src.core.copilot.council.models` (CouncilDecisionRow)

Per ADR-027: governance -> copilot is VERBODEN. copilot -> governance is by design.

## Oplossing

Type-move naar `governance.models` + re-exports in copilot (backward compat) +
Contract 5 tighten naar `allow_indirect_imports = false`.

### Bestanden gewijzigd

| Bestand | Wijziging |
|---------|-----------|
| `src/core/governance/models.py` | `VerdictType`, `OfficerVerdict`, `CouncilDecisionRow`, `OfficerVerdictRow` toegevoegd |
| `src/core/copilot/council/types.py` | `VerdictType` + `OfficerVerdict` definities vervangen door re-exports |
| `src/core/copilot/council/models.py` | `CouncilDecisionRow` + `OfficerVerdictRow` definities vervangen door re-exports |
| `src/core/governance/hash_chain.py` | Import van `governance.models` i.p.v. `copilot.council.types` |
| `src/core/governance/retention_cleanup.py` | Import van `governance.models` i.p.v. `copilot.council.models` |
| `.importlinter` | Contract 5: `allow_indirect_imports = false`, ignore_imports leeggemaakt + `src -> src.workers` |
| `tests/architecture/test_dsm_grade_a_plus.py` | xfail-marker verwijderd; regex bug `$` -> `\Z` gefixed |

### ADR-027 rationale

`copilot -> governance` is by design (copilot.council.models re-exporteert vanuit governance.models).
`governance -> copilot` is VERBODEN. Na de type-move: geen enkele governance-module importeert
meer rechtstreeks uit copilot.

### Backward compat

Alle callers van `copilot.council.types.VerdictType`, `.OfficerVerdict` en
`copilot.council.models.CouncilDecisionRow`, `.OfficerVerdictRow` werken ongewijzigd:
de re-exports behouden de originele module-paden. Type-identiteit geverifieerd:
```python
assert VerdictType is VT2  # True
assert OfficerVerdict is OV2  # True
assert CouncilDecisionRow is CDR2  # True
assert OfficerVerdictRow is OVR2  # True
```

### Bijkomende bevinding: Contract 5 `src -> src.workers`

Na `allow_indirect_imports = false` detecteert import-linter een transitieve keten via
`rbac_models -> src -> src.workers -> copilot.api.contest_service`. Dit is hetzelfde
statische-analyse-artefact als in Contract 3 (layers): `src/__init__.py::get_workers()`
heeft een function-local lazy import. Geen runtime governance->copilot koppeling.
Suppress via `ignore_imports = src -> src.workers` (zelfde patroon als Contract 3).

### Bijkomende bugfix: test regex

De test gebruikte `re.MULTILINE | re.DOTALL` + `(?=...|$)`. Met MULTILINE matcht `$`
op elke regeleinде, waardoor `group(1)` leeg was. Fix: `$` -> `\Z` (end-of-string).

## Verificatie

```
lint-imports: 9 contracts, 0 broken
pytest tests/architecture/test_dsm_grade_a_plus.py: 14 passed, 3 xfailed, 0 failed
test_contract5_governance_independence_hardened: PASSED (was xfail)
python -m pyright: 0 errors (baseline ongewijzigd)
ruff check src/: All checks passed
Gerichte regressie (79 tests): 0 failures
```


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: SP-DSM-005 Dag 1: Contract 5 hardening. VerdictType+OfficerVerdict+CouncilDecisionRow+OfficerVerdictRow type-move naar governance.models. allow_indirect_imports=false. 9 kept, 0 broken. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker start of gebruikt SP-DSM-005 Dag 1: Contract 5 hardening. VerdictType+OfficerVerdict+CouncilDecisionRow+OfficerVerdictRow type-move naar governance.models. allow_indirect_imports=false. 9 kept, 0 broken..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
