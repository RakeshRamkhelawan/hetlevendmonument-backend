"""`POST /execute` staat alleen open in ontwikkelomgevingen (ADR-036 OP-125).

**De bevinding, gemeten 2026-08-10.** De poort was een BLOKKEERLIJST op precies een waarde:

    if env == "production" and not enabled:   # dependencies.py:43

De vloot draait ook `staging`, `blue` en `green` (gemeten in `cd-staging.yml` en
`deployment/blue_green/docker-compose.{blue,green}.yml`), en blue/green is een PRODUCTIETECHNIEK
met echte data. Op die drie stond de deur dus open.

Wat daarachter zat: `ALLOWED_COMMANDS` bevatte `env`, `cat`, `python`, `curl` en `wget`, en het
subproces kreeg `**os.environ` mee. Een gewone ingelogde gebruiker -- er is geen rolcontrole,
alleen `Depends(get_current_user)` -- kon met `{"command": "env"}` de pseudonimiseringssleutel,
`DATABASE_URL`, `JWT_SECRET_KEY`, `SECRET_KEY` en de LLM-sleutel uitlezen. `python -c` was
volledige codeuitvoering.

**Waarom de bestaande guard-test dit niet ving:** `test_terminal_production_guard.py` toetst
alleen `development` en `production`. De drie omgevingen waar het misging werden nooit gezet --
de mutatie in de tweede richting ontbrak (`.claude/rules/quality-gates.md`).

**Waarom een TOELAATLIJST en geen blokkeerlijst.** Dit is dezelfde correctie die
`redaction.py:314-320` al had gemaakt, met daar de reden erbij: *"Een allowlist en geen blocklist:
`is_production()` matcht alleen 'production', terwijl de vloot ook `staging`, `blue` en `green`
gebruikt -- en blue/green is een PRODUCTIETECHNIEK."* Een nieuwe omgevingsnaam is dan per
constructie dicht in plaats van per ongeluk open.

**Mutatietest (2026-08-10, beide richtingen):** de toelaatlijst terugveranderd naar
`env == "production"` -> ROOD op de drie omgevingstests. `env` teruggezet in `ALLOWED_COMMANDS`
-> ROOD. `**os.environ` teruggezet -> ROOD. En de andere kant: `development` met de vlag aan
blijft GROEN, anders zou "weiger alles" een geldige oplossing zijn.
"""

from __future__ import annotations

import ast
import importlib
import os
import textwrap
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import HTTPException


@contextmanager
def _guard_met_omgeving(**env: str):
    """Herlaad de module met deze omgeving en houd die omgeving ACTIEF.

    Bewust een contextmanager. Een eerdere versie gaf de module terug en liet de `patch.dict`
    daarbij aflopen -- `_require_terminal_enabled` leest `os.getenv` op AANROEPTIJD, dus de
    assertie draaide dan tegen de herstelde omgeving en de test gaf "DID NOT RAISE" terwijl de
    guard prima werkte. De test mat zichzelf, niet de code.
    """
    with patch.dict(os.environ, env, clear=True):
        yield importlib.reload(
            importlib.import_module("src.core.api.v1.terminal.dependencies")
        )


class TestTheTerminalIsClosedOutsideDevelopment:
    @pytest.mark.parametrize("omgeving", ["staging", "blue", "green"])
    def test_the_terminal_is_closed_in_every_deployed_environment(self, omgeving: str) -> None:
        """De drie omgevingen die de blokkeerlijst miste.

        `blue` en `green` zijn geen testomgevingen: dat is de manier waarop productie wordt
        uitgerold, met echte data en echte secrets.
        """
        with _guard_met_omgeving(ENVIRONMENT=omgeving) as deps:
            with pytest.raises(HTTPException) as fout:
                deps._require_terminal_enabled()

        assert fout.value.status_code == 403, (
            f"De terminal is open in omgeving {omgeving!r}. Daar draaien echte secrets, en het "
            "endpoint laat elke ingelogde gebruiker commando's uitvoeren."
        )

    def test_an_unknown_environment_name_is_closed_by_default(self) -> None:
        """Een toelaatlijst betekent dat een NIEUWE omgevingsnaam dicht is, niet open.

        Dit is de eigenschap die een blokkeerlijst niet heeft, en de reden dat staging/blue/green
        er ooit doorheen glipten.
        """
        with _guard_met_omgeving(ENVIRONMENT="acceptatie-omgeving-die-nog-niet-bestaat") as deps:
            with pytest.raises(HTTPException) as fout:
                deps._require_terminal_enabled()

        assert fout.value.status_code == 403

    def test_development_still_works(self) -> None:
        """De tweede richting: zonder dit zou 'weiger alles' een geldige oplossing zijn."""
        with _guard_met_omgeving(ENVIRONMENT="development") as deps:
            deps._require_terminal_enabled()  # mag niet gooien

    def test_the_environment_dump_commands_are_gone(self) -> None:
        """Geen commando in de lijst mag de omgeving kunnen tonen of code kunnen draaien.

        `env` print alle secrets. `python`/`node` zijn volledige codeuitvoering. `curl`/`wget`
        maken uitgaand verkeer mogelijk en daarmee exfiltratie. `cat` kan `/proc/self/environ`
        lezen -- dat is dezelfde dump langs een andere weg.
        """
        with _guard_met_omgeving(ENVIRONMENT="development") as deps:
            toegestaan = set(deps.ALLOWED_COMMANDS)

        verboden = {"env", "printenv", "python", "python3", "node", "npm", "pip", "curl", "wget"}
        gevonden = verboden & toegestaan

        assert not gevonden, (
            f"Deze commando's staan toegestaan en geven toegang tot de secrets of tot "
            f"codeuitvoering: {sorted(gevonden)}."
        )

    def test_cat_cannot_read_the_process_environment(self) -> None:
        """`cat` mag blijven, maar niet naar `/proc/self/environ` kunnen wijzen."""
        with _guard_met_omgeving(ENVIRONMENT="development") as deps:
            if "cat" not in deps.ALLOWED_COMMANDS:
                pytest.skip("cat staat niet toe; dan is dit pad sowieso dicht")
            toegestaan = deps.is_command_allowed("cat /proc/self/environ")

        assert not toegestaan, (
            "`cat /proc/self/environ` is toegestaan. Dat is dezelfde volledige omgevingsdump als "
            "`env`, alleen langs een andere weg."
        )

    def test_the_subprocess_does_not_inherit_the_secrets(self) -> None:
        """Het subproces mag geen `**os.environ` krijgen.

        Toets de STRUCTUUR en niet de tekst. Een eerdere versie zocht de string `**os.environ`
        in de bron -- en sloeg toen aan op de TOELICHTING die die string noemt. Dat is de
        tekst-in-plaats-van-structuur-val uit `.claude/rules/quality-gates.md`, en hij trad hier
        direct op.

        In de AST is `{**os.environ, ...}` een `ast.Dict` met `None` als sleutel: dat is hoe
        Python uitpakken codeert. Daarop toetsen kan geen enkele comment betrappen.
        """
        import ast
        import inspect

        with _guard_met_omgeving(ENVIRONMENT="development") as deps:
            bron = inspect.getsource(deps.execute_command)

        boom = ast.parse(textwrap.dedent(bron))
        uitpakkingen = [
            knoop
            for knoop in ast.walk(boom)
            if isinstance(knoop, ast.Call)
            for sleutelwoord in knoop.keywords
            if sleutelwoord.arg == "env"
            and isinstance(sleutelwoord.value, ast.Dict)
            and any(sleutel is None for sleutel in sleutelwoord.value.keys)
        ]

        assert not uitpakkingen, (
            "Het subproces krijgt een uitgepakte omgeving mee (`{**os.environ, ...}`) en erft "
            "daarmee elke sleutel. Geef een expliciete minimale omgeving mee."
        )
