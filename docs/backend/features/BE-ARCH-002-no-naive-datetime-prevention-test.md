# BE-ARCH-002: Geen naive datetime preventietest

**Sprint:** AUDIT-SINGLE-TENANT-DB01 S7
**Datum:** 2026-07-02
**ADR:** CLAUDE.md NOOIT-lijst

## Probleem

CLAUDE.md verbiedt `datetime.now()` en `datetime.utcnow()` zonder
`timezone.utc` in `src/` -- naive datetimes veroorzaken inconsistente
audit-timestamps en TZ-vergelijkingsbugs. Er was geen geautomatiseerde
architecture-test die dit verbod afdwingt.

## Oplossing

`tests/architecture/test_no_naive_datetime.py` scant elk `.py`-bestand onder
`src/` regel voor regel op het patroon
`\bdatetime\.(?:datetime\.)?(now\(\)|utcnow\(\))`, met een negative-match voor
regels die al een argument bevatten (bijv. `datetime.now(timezone.utc)`).

De regex dekt zowel `from datetime import datetime; datetime.now()` als
`import datetime; datetime.datetime.now()` (S7 code-review bevinding --
oorspronkelijke regex miste de laatste importstijl).

## Test bewijs

```
python -m pytest tests/architecture/test_no_naive_datetime.py -v
1 passed
```

Huidige staat van `src/`: 0 violations (alle datetime-aanroepen zijn reeds
timezone-aware conform CLAUDE.md).

## Reviewers

code-reviewer: GO (regex-gap gevonden en direct gefixed in dezelfde sprint).
quality-reviewer: GO (pyright 0 errors, ruff clean, ASCII-only).


## Trainingssamenvatting

- Actor: Een CI/architecture test runner of ontwikkelaar die `tests/architecture/test_no_naive_datetime.py` uitvoert.
- Voorwaarde: De source tree is beschikbaar; Python bronbestanden staan onder `src/`.
- Actie (request): Voer `pytest tests/architecture/test_no_naive_datetime.py` uit.
- Systeemverwerking: De test scant recursief alle `.py` bestanden onder `src/`. Per bestand wordt een AST opgebouwd, worden import-aliassen voor `datetime` verzameld (`import datetime`, `import datetime as dt`, `from datetime import datetime` inclusief aliassen), en worden `Call` nodes gecontroleerd op `<alias>.now()` of `<alias>.datetime.now()` / `<alias>.utcnow()` zonder argumenten. Bestanden in `_EXEMPT_FILES` worden overgeslagen.
- Succesrespons: De test rapporteert `1 passed` wanneer er geen naive aanroepen worden gevonden.
- Foutrespons: `AssertionError` met een lijst van bestandsnamen en regelnummers waar een naive `datetime.now()` of `datetime.utcnow()` is aangetroffen.
- Uitzonderingen: De scan is statisch en dekt geen dynamische reflectie zoals `getattr(datetime, "now")()`; alleen `src/` wordt gecontroleerd, niet `tests/` of dependencies.
