# BE-DSM-012: SP-DSM-003 Dag 2 -- Contract 3 (layers) geactiveerd

**Sprint**: SP-DSM-003 Dag 2
**Datum**: 2026-06-17
**Status**: APPROVED

## Samenvatting

Contract 3 (`layers`) in `.importlinter` was uitgeschakeld na SP-DSM-003 Dag 1 omdat de
oorspronkelijke definitie (api / domein / auth|database) leidde tot >50 violations door
domain-modules die by design elkaars API raakten (ADR-027, ADR-034).

Dag 2 herontwierp de layers-definitie: de domein-laag is weggelaten uit Contract 3.
Andere contracts (1, 2, 5, 6, 7) bewaken de domein-grenzen. Contract 3 bewaakt nu
uitsluitend de infrastructuur-invariant: `database|caching|resilience` mag nooit `auth`
of `api` importeren.

## Wijzigingen

### `.importlinter` (Contract 3 geactiveerd)

Commentaarblok (13 regels, regels 234-246) vervangen door actief contract:

```ini
[importlinter:contract:layers]
name = Infrastructuurlaag mag niet API-laag importeren
type = layers
containers = src.core
layers =
    api
    auth
    database | caching | resilience
ignore_imports =
    src.core.database.import_all_models -> src.core.auth.models.account_lockout
    src.core.database.import_all_models -> src.core.auth.oauth2_service
    src.core.database.import_all_models -> src.core.auth.two_factor_auth
    src.core.database.seed -> src.core.auth.jwt_handler
    src -> src.workers
unmatched_ignore_imports_alerting = warn
```

**Ignore_imports motivatie:**
- `import_all_models -> auth.*`: centrale SQLAlchemy model registry importeert auth-models
  by design (noodzakelijk voor relationship resolution)
- `seed -> auth.jwt_handler`: seed.py hashte initieel wachtwoorden -- by design
- `src -> src.workers`: function-local lazy import in `src/__init__.py::get_workers()`;
  import-linter detecteert dit statisch maar het is nooit een runtime dependency

### `tests/architecture/test_dsm_grade_a_plus.py`

Verwijderd: `@pytest.mark.xfail(reason="Contract 3 (layers) disabled -- SP-DSM-004")`
Test `test_import_linter_all_contracts_active` slaagt nu (was xfail).

## Verificatie

```
lint-imports: 7 contracts, 0 broken
pytest tests/architecture/: 156 passed, 17 xfailed, 0 failed
pyright: 0 errors (baseline ongewijzigd)
ruff check src/: All checks passed
```

## ADR-links

- ADR-033: 3-laags router boundary (Contract 1 en 2)
- ADR-034: agent_runtime facade (Contract 6 en 7)
- ADR-027: copilot-governance samenwerking (Contract 5)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: SP-DSM-003 Dag 2: Contract 3 (layers) geactiveerd. Herontwerp: api/auth/database-infra. 7 kept, 0 broken. xfail marker verwijderd. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker start of gebruikt SP-DSM-003 Dag 2: Contract 3 (layers) geactiveerd. Herontwerp: api/auth/database-infra. 7 kept, 0 broken. xfail marker verwijderd..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
