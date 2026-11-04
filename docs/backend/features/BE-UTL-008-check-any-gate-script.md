# BE-UTL-008 — check_any_gate.py: Any-Type Linting Gate

**ID:** BE-UTL-008
**Sprint:** SP-TYPE-01 Dag 1
**Type:** Utility Script / CI Gate
**Status:** CLOSED — commit `d2be2efd`
**Bestanden:**
- `scripts/check_any_gate.py` — gate script
- `.pre-commit-config.yaml` — `any-type-gate` hook geregistreerd

---

## Samenvatting

Pre-commit hook en CI gate die Python-bestanden in `src/` afwijst als ze `Any`-annotaties
bevatten zonder `# TODO(TYPE)` of `# type: ignore`. Voorkomt dat nieuwe `Any`-usages
ongedocumenteerd de codebase binnenkomen. Onderdeel van SP-TYPE-01 Type Fortress programma.

---

## Werking

1. Ontvangt via pre-commit/CI een lijst van gewijzigde `.py`-bestanden
2. Roept `scan_file(path)` aan voor elk bestand
3. Rapporteert elke `AnyUsage` met `has_todo=False`
4. Geeft exit code 1 als er violations zijn, exit code 0 bij geen violations
5. Bij exit code 1: commit/CI geblokkeerd

---

## Acceptatiecriteria voor een regel

Een regel is **acceptabel** als één van deze patronen aanwezig is:
- `# TODO(TYPE): ...` — annotatie voor geleidelijke migratie
- `# type: ignore` — expliciete mypy-suppressie
- `*args: Any` / `**kwargs: Any` — legitieme polymorfisme-patronen
- Andere LEGITIMATE_PATTERNS uit `scan_any_usage.py`

---

## Pre-commit configuratie

```yaml
- id: any-type-gate
  name: Any type gate (blocks new Any without TODO(TYPE))
  entry: python scripts/check_any_gate.py
  language: system
  types: [python]
  pass_filenames: true
  files: ^src/
  stages: [pre-commit]
```

---

## CI gebruik

```bash
# Check specifieke bestanden
python scripts/check_any_gate.py src/core/api/main.py

# Check gewijzigde bestanden in CI (GNU xargs -r = skip bij lege input)
git diff --name-only HEAD~1 -- '*.py' | xargs -r python scripts/check_any_gate.py
```

---

## Afhankelijkheden

- Importeert `scan_file` uit `scripts/scan_any_usage.py`
- Geen productie-afhankelijkheden

---

## Trainingssamenvatting

**Flow: Pre-commit gate blokkeert nieuwe Any**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Developer (via git commit) of CI pipeline |
| Voorwaarde | Developer staged Python-bestanden met nieuwe `Any`-annotatie zonder TODO |
| Actie | `git commit` triggert pre-commit hook `any-type-gate` |
| Systeemverwerking | `check_any_gate.py` scant staged `src/*.py` bestanden; rapporteert violations |
| Succesrespons | Exit 0 — commit doorgaat |
| Foutrespons | Exit 1 — `[ANN-ANY GATE FAIL] N Any annotation(s) without TODO(TYPE).` — commit geblokkeerd |
| Uitzonderingen | Geen staged src/ py-bestanden → gate slaat over (exit 0) |
