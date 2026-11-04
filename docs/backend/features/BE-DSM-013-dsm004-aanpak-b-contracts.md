# BE-DSM-013: SP-DSM-004 -- Aanpak B contracts + Contract 5 backlog

**Sprint**: SP-DSM-004 Dag 1
**Datum**: 2026-06-17
**Status**: APPROVED

## Samenvatting

SP-DSM-004 voegt twee targeted `type = forbidden` contracts toe aan `.importlinter`
als eerste stap van de Aanpak B migratie (van `type = layers` naar expliciete `forbidden`
contracts). Het `layers` contract (Contract 3) blijft behouden -- verwijdering zou
stille coverage-regressie veroorzaken (4 invarianten gaan verloren).

Contract 5 hardening (known-violations fixen + `allow_indirect_imports = false`) is
doorgeschoven naar SP-DSM-005: `OfficerVerdict` en `CouncilDecisionRow` hebben >10
callers in `copilot/*`. De verschuiving is gedocumenteerd met een falende architecture
test (`test_contract5_governance_independence_hardened`, xfail strict=True).

## Aanleiding (overgenomen uit SP-DSM-003 Dag 1 review)

SP-DSM-003 Dag 1 backlogged drie Contract 5 items naar SP-DSM-004:
- Contract 5: fix 2 known-violations + `allow_indirect_imports = false`
- Contract 3: herontwerp layers naar Aanpak B (meerdere gerichte forbidden contracts)

SP-DSM-003 Dag 2 loste Contract 3 op met een vereenvoudigde `layers` definitie.
SP-DSM-004 voegt Aanpak B contracts TOE naast `layers`, zodat de geleidelijke migratie
naar expliciete `forbidden` contracts kan beginnen zonder coverage-regressie.

## Wijzigingen

### `.importlinter`

**Contract 8 (`infra-no-api`) -- nieuw:**
- Maakt de `infra -> api` grens expliciet als benoemde `type = forbidden` rule
- Redundant met Contract 3 (`layers`), maar eerste stap Aanpak B migratie
- `allow_indirect_imports = true`: Contract 3 bewaakt al transitieve paden
- 0 violations (verwacht -- layers dekte dit al)

**Contract 9 (`governance-no-workflow-direct`) -- nieuw:**
- Verbiedt directe imports van `governance` naar `workflow`
- NIEUWE invariant, niet gedekt door bestaande contracts
- `allow_indirect_imports = true`: transitief via `src.workers` is een gedeelde
  infraroute (`prana_guard -> rbac_models -> src -> workers -> workflow_worker`)
- 1 known-violation: `dsar_service -> workflow.models` (GDPR DSAR-verwerking,
  lazy imports in 3 functies) -- backlog SP-DSM-005 voor workflow-adapter

**Contract 5 (`governance-independence`) -- comments bijgewerkt:**
- "backlog SP-DSM-004" gewijzigd naar "backlog SP-DSM-005"
- Motivatie voor `allow_indirect_imports = true` uitgebreid: type-move deferred

### `tests/architecture/test_dsm_grade_a_plus.py`

- `test_import_linter_all_contracts_active`: `required_contracts` uitgebreid van 7
  naar 9 items (`infra-no-api` en `governance-no-workflow-direct` toegevoegd).
  Docstring bijgewerkt van "7" naar "9 contracts".
- Nieuwe test `test_contract5_governance_independence_hardened`:
  `@pytest.mark.xfail(strict=True, reason="SP-DSM-005: ...")` -- documenting backlog.
  Test wordt GROEN zodra Contract 5 `allow_indirect_imports = false` krijgt.
  `strict=True`: CI gaat rood als de test onverwacht slaagt zonder xfail te verwijderen.

## Verificatie

```
lint-imports: 9 contracts, 0 broken
pytest tests/architecture/: 13 passed, 4 xfailed, 0 failed
  - test_import_linter_all_contracts_active: PASSED (9 contracts aanwezig)
  - test_contract5_governance_independence_hardened: XFAIL (by design -- SP-DSM-005)
pyright: 0 errors, 55 warnings (baseline ongewijzigd)
ruff check src/: All checks passed
```

## ADR-links

- ADR-033: 3-laags router boundary (Contract 1 en 2)
- ADR-034: agent_runtime facade (Contract 6 en 7)
- ADR-027: copilot-governance samenwerking (Contract 5)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: SP-DSM-004: Aanpak B ADD -- infra-no-api + governance-no-workflow-direct. Contract 5 backlog -> SP-DSM-005. 9 kept, 0 broken. 13 passed, 4 xfailed. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker start of gebruikt SP-DSM-004: Aanpak B ADD -- infra-no-api + governance-no-workflow-direct. Contract 5 backlog -> SP-DSM-005. 9 kept, 0 broken. 13 passed, 4 xfailed..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
