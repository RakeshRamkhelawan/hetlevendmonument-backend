# BE-INFRA-001: detect_db_imports CI-gate

**Sprint:** AUDIT-SINGLE-TENANT-DB01 S6
**Datum:** 2026-07-01
**Status:** DONE

## Doel

`scripts/detect_db_imports.py` upgrade naar een volwaardige CI-gate die exit code 1 geeft
bij ADR-033-violations. Hiermee wordt voorkomen dat toekomstige commits directe DB-imports
in router.py-bestanden introduceren.

## Implementatie

Het script had al de exit-code logica (regels 128-132):
```python
return 0 if not offenders else 1
# ...
sys.exit(main())
```

De CI-gate was daarmee al volledig aanwezig na S1-S5. Verificatie:
- `python scripts/detect_db_imports.py` geeft exit code 0 (69 bestanden, 0 violations).

## Architecture test

`tests/architecture/test_detect_db_imports_zero.py`:
- `test_detect_db_imports_returns_zero_offenders`: exit code 0 vereist.
- `test_detect_db_imports_script_exists`: script aanwezig vereist.

## ADR-conformiteit

| ADR | Regel | Status |
|-----|-------|--------|
| ADR-033 | router.py geen directe DB-imports | COMPLIANT: 69/69 bestanden schoon |

## Trainingssamenvatting

- Actor: CI-pipeline of ontwikkelaar die `python scripts/detect_db_imports.py` uitvoert.
- Voorwaarde: Project root bevat `src/core/api/v1/**/router*.py`; script is Python 3 uitvoerbaar.
- Actie (request): Voer `python scripts/detect_db_imports.py [--output <pad>] [--verbose]` uit vanuit de project root.
- Systeemverwerking: Script doorloopt router-bestanden, parset AST per bestand en detecteert verboden symbolen (`get_db`, `AsyncSession`, `select`, `func`, `insert`, `update`, `delete`, `text`) en modules (`sqlalchemy`, `src.core.database.database`). Resultaat wordt als JSON afgedrukt.
- Succesrespons: Exit code 0 met JSON `{"scanned": 69, "offenders": [], "clean": 69}`.
- Foutrespons: Exit code 1 met JSON waarbij `offenders` een lijst is van `{ "file": "...", "forbidden_imports": [...] }`.
- Uitzonderingen: Bij een `SyntaxError` in een router-bestand wordt dat bestand overgeslagen (lege hitlijst); ongeldige argumenten geven een argparse-fout.
