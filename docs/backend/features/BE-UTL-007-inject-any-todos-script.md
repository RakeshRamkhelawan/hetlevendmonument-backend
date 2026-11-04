# BE-UTL-007 — inject_any_todos.py: Baseline Any Annotator

**ID:** BE-UTL-007
**Sprint:** SP-TYPE-01 Dag 1-2
**Type:** Utility Script
**Status:** CLOSED — commit `d2be2efd` (dag 1), `0919c43f` (baseline applied dag 2)
**Bestand:** `scripts/inject_any_todos.py`

---

## Samenvatting

Script dat eenmalig `# TODO(TYPE): replace Any with concrete type` injecteert naast
elke `Any`-annotatie in Python-bronbestanden die nog geen TODO of `type: ignore` heeft.
Maakt de `any-type-gate` (BE-UTL-008) effectief: bestaande Any-usages zijn gedocumenteerd,
nieuwe Any zonder TODO worden geblokkeerd.

---

## Functie-overzicht

| Functie | Beschrijving |
|---------|-------------|
| `_python_files(src_dir)` | Recursief alle `.py`-bestanden in `src_dir`, exclusief `__pycache__`, `.venv`, `alembic`, etc. |
| `inject_file(path, apply)` | Voegt TODO-suffix toe aan elke Any-regel zonder annotatie. Idempotent, backslash-guard, TOCTOU-guard. |
| `main()` | CLI entrypoint: `--apply` voor schrijven, default dry-run. `--src` voor doelmap. |

---

## Guards (review findings dag 1 — gefixed voor commit)

| Guard | Beschrijving |
|-------|-------------|
| **Backslash-continuation** | `if stripped.endswith("\\"):` — skip, commentaar na `\` breekt Python-syntax |
| **TOCTOU** | `if "Any" not in stripped:` — verifieer dat de regel nog `Any` bevat na scan-to-write race |
| **Idempotent** | `if TODO_SUFFIX.strip() in stripped:` — skip als TODO al aanwezig |
| **Exclude dirs** | `.pytest_cache`, `.ruff_cache`, `.tmp`, `.mypy_cache`, `__pycache__`, `alembic`, etc. |

---

## Gebruik

```bash
# Dry-run (veilig, geen schrijven)
python scripts/inject_any_todos.py

# Schrijven naar src/
python scripts/inject_any_todos.py --apply

# Specifieke submap
python scripts/inject_any_todos.py --apply --src src/core/api
```

---

## Resultaat baseline run (2026-05-30)

- Bestanden gescand: 1177
- TODO(TYPE) ingespoten: 8994
- Bestanden gewijzigd: 1177

---

## Afhankelijkheden

- Importeert `scan_file` uit `scripts/scan_any_usage.py` (bestaand script)
- Geen productie-afhankelijkheden

---

## Trainingssamenvatting

**Flow: Baseline annotatie uitvoeren**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Developer / CI-pipeline |
| Voorwaarde | `src/` bevat Python-bestanden met Any-annotaties zonder TODO |
| Actie | `python scripts/inject_any_todos.py --apply --src src` |
| Systeemverwerking | Scant alle `.py`-bestanden, voegt TODO-suffix toe per Any-regel zonder annotatie, schrijft bestand terug |
| Succesrespons | `[Applied] N TODO(TYPE) comments across M files.` |
| Foutrespons | `[ERROR] Not a directory: <src>` bij ongeldig pad |
| Uitzonderingen | Backslash-continuation lines worden overgeslagen (TODO zou syntax breken) |
