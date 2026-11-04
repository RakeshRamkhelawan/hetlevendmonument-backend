"""Het JSON-testrapport mag niet opnieuw elke logregel opnemen (ADR-036 OP-132).

**Wat er gebeurde.** `addopts` in `pyproject.toml` zette `--json-report` aan zonder
`--json-report-omit`. Daardoor nam het rapport ELKE logregel van ELKE test op, met volledige
metadata (`pathname`, `module`, `exc_info`, ...). Gemeten op de volle suite: **1338,8 MB**.

`pytest-json-report` bouwt dat rapport in geheugen op en serialiseert het in `pytest_sessionfinish`
-- dus NA de samenvatting. CI toonde `15528 passed ... in 1118.05s` en werd 26 minuten later door de
45-minutenlimiet gedood. De tests slaagden dus al die tijd; de POORT stond rood op het wegschrijven
van een rapport dat niemand leest.

Op `main` timede dezelfde stap al af, maar daar heet hij "Full unit tests (informational)" met
`continue-on-error`, dus hij rapporteerde `success`. Precies waar `.claude/rules/quality-gates.md`
voor waarschuwt: een gate met `continue-on-error` is theater, en hier verborg het wekenlang een
echte blokkade.

**Waarom deze guard en geen grotere.** De omvang zelf toetsen zou een volledige suite-run vragen.
De CONFIGURATIE toetsen kost niets en dekt de oorzaak: zonder `omit=log` komt het gigabyte-rapport
terug, ongeacht hoe groot de suite is.

**Mutatietest (2026-08-11, beide richtingen):**

1. `--json-report-omit=log` uit `addopts` halen -> ROOD, met de gemeten omvang in de melding.
   Vervangen door `--json-report-omit=keywords` (dus wel een omit, maar niet die van `log`) ->
   nog steeds ROOD; de guard toetst de WAARDE en niet het bestaan van de vlag.
2. De andere kant: ongewijzigd -> GROEN. En `test_the_json_report_is_still_enabled` bewaakt dat het
   rapport niet stilletjes helemaal is uitgezet -- "zet `--json-report` uit" zou anders een geldige
   oplossing zijn, en dan verdwijnt met het probleem ook de dekking van gefaalde tests.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _addopts() -> list[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    opts = data["tool"]["pytest"]["ini_options"]["addopts"]
    return list(opts) if isinstance(opts, list) else str(opts).split()


def test_the_json_report_omits_captured_logs() -> None:
    """Zonder `omit=log` groeit het rapport naar meer dan een gigabyte en sterft de CI-poort."""
    omits = [o.split("=", 1)[1] for o in _addopts() if o.startswith("--json-report-omit=")]
    gevraagd = {deel.strip() for waarde in omits for deel in waarde.split(",")}

    assert "log" in gevraagd, (
        "`--json-report-omit=log` ontbreekt in de pytest-addopts. Zonder die vlag neemt "
        "`pytest-json-report` elke logregel van elke test op: gemeten 2026-08-11 op de volle suite "
        "1338,8 MB, geserialiseerd NA de samenvatting. CI meldde toen `15528 passed` en werd 26 "
        f"minuten later door de 45-minutenlimiet gedood. Gevonden omits: {sorted(gevraagd) or 'geen'}."
    )


def test_the_json_report_is_still_enabled() -> None:
    """De tweede richting: het rapport helemaal uitzetten is geen geldige oplossing.

    Dan verdwijnt met de omvang ook de vastlegging van gefaalde tests, en die is het doel.
    Nagemeten dat `omit=log` de `longrepr` van een failure intact laat.
    """
    opts = _addopts()

    assert "--json-report" in opts, (
        "`--json-report` staat niet meer aan. De omvang is dan opgelost door de dekking weg te "
        "gooien; gefaalde tests worden dan nergens meer met hun traceback vastgelegd."
    )
