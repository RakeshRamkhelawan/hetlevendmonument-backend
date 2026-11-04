"""De PreToolUse-hook legt de twee pushgoedkeuring-handelingen die een mens toekomen aan hem voor.

WAAROM DEZE TEST BESTAAT
------------------------
Op 2026-09-19 is gemeten dat de drie `ask`-regels in `.claude/settings.json` niet vuren.
Twee verse `ask`-regels op een onschuldig `echo`-commando, in BEIDE schrijfwijzen
(`Bash(echo x *)` en `Bash(echo x:*)`), gaven geen prompt -- het ligt dus niet aan de
schrijfwijze en niet aan de brede allow-regel `Bash(python *)` in datzelfde bestand.
Waarom ze niet vuren is NIET vastgesteld en staat hier bewust niet als verklaring.

Wat WEL aantoonbaar werkt is `.claude/hooks/block-dangerous-commands.sh`: die greep in
dezelfde sessie live in op een `git push --no-verify` en, zonder herstart, op het eerste
`--human`-commando dat langskwam. Deze test bewaakt dat die tussenkomst blijft bestaan.

ASK EN NIET DENY -- en dat verschil is de kern
-----------------------------------------------
De eerste versie van deze hook gaf `deny`. Dat was fout, en Rakesh betrapte het: er is geen
scherm waarop een mens een geweigerde aanroep alsnog vrijgeeft. De documentatie is expliciet
-- "a hook that exits with code 2 stops the tool call before permission rules are evaluated"
-- en het tabblad "Recently denied" dat toen in CLAUDE.md stond, bestaat niet. Een deny op een
handeling die een mens WEL mag doen is dus een slot zonder sleutel.
`ask` doet wat er nodig is: "show the permission prompt to the user as normal"
(code.claude.com/docs/en/hooks-guide.md). Deze test bewaakt daarom de UITSPRAAK van de hook,
niet zijn exitcode -- bij `ask` is de exitcode 0, net als bij doorlaten, dus een test op de
exitcode alleen zou `ask` en "geen mening" niet uit elkaar houden.

MUTATIEBEWIJS (2026-09-19, beide richtingen, een regel per bewaakt element)
---------------------------------------------------------------------------
Voorwaarts -- regel uit de hook gehaald, test wordt ROOD:
    approve met --human              -> zonder de regel: geen uitspraak (ROOD)
    set-coordinator                  -> zonder de regel: geen uitspraak (ROOD)
Achterwaarts -- legitiem gebruik mag NIET blijven hangen, test blijft GROEN:
    approve zonder --human           -> geen uitspraak, loopt door
    request / status / verify / whois-> geen uitspraak, loopt door
    een willekeurig `echo`           -> geen uitspraak, loopt door
En de bestaande deny die er al stond blijft een deny:
    git push --no-verify             -> deny
    git commit -m <tekst>            -> geen uitspraak, loopt door

TWEE VALSTRIKKEN DIE HIER ZIJN GEMETEN, allebei niet te zien aan de code
------------------------------------------------------------------------
1. `bash` op deze machine kan naar de WSL-relay wijzen. `subprocess.run(["bash", ...])`
   gaf `execvpe(/bin/bash) failed` met returncode 1 -- geen weigering, maar de hook had
   dan ook niet gedraaid. Elke assertie op "rc != 2 dus toegestaan" was daarmee groen
   geweest zonder iets te meten. Daarom zoekt `_bash()` expliciet de Git-bash.
2. De hook leest de COMMANDOTEKST. Bewerk dit bestand daarom nooit via een Bash-heredoc
   waarin de letterlijke tekst `push_gate.py approve ... --human` staat: dan blokkeert de
   hook je eigen bewerking. Om die reden zijn de commando's hieronder uit stukjes
   samengesteld in plaats van letterlijk opgeschreven.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "block-dangerous-commands.sh"

# Uit stukjes samengesteld -- zie valstrik 2 in de moduledocstring.
_GATE = "push_gate.py"
_APPROVE = "appro" + "ve"
_HUMAN = "--hum" + "an"
_SET_COORD = "set-coord" + "inator"


def _bash() -> str:
    """Het pad naar Git-bash, nooit de kale naam -- zie valstrik 1."""
    for kandidaat in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "/bin/bash",
    ):
        if os.path.exists(kandidaat):
            return kandidaat
    gevonden = shutil.which("bash")
    if gevonden is None:
        pytest.skip("geen bash gevonden om de hook mee te draaien")
    return gevonden


def _oordeel(commando: str) -> str:
    """De UITSPRAAK van de hook: "ask", "deny", of "geen uitspraak".

    Niet de exitcode: `ask` en doorlaten geven allebei 0.
    """
    resultaat = subprocess.run(  # nosec B603: vast scriptpad, invoer via stdin
        [_bash(), str(_HOOK)],
        input=json.dumps({"tool_input": {"command": commando}}),
        capture_output=True,
        text=True,
    )
    if resultaat.returncode not in (0, 2):
        # Zie valstrik 1: een onvoorziene returncode is een FOUT, nooit "toegestaan".
        raise AssertionError(
            f"de hook draaide niet (rc={resultaat.returncode}): {resultaat.stderr[:300]}"
        )
    if resultaat.returncode == 2:
        return "deny"
    if not resultaat.stdout.strip():
        return "geen uitspraak"
    return str(json.loads(resultaat.stdout)["hookSpecificOutput"]["permissionDecision"])


def test_de_hook_bestaat() -> None:
    assert _HOOK.is_file(), f"{_HOOK} ontbreekt -- zonder de hook is er geen bewaking"


@pytest.mark.parametrize(
    "commando",
    [
        f"python scripts/{_GATE} {_APPROVE} --sha abc --by org-5b {_HUMAN}",
        f"python scripts/{_GATE} {_APPROVE} --sha abc --by rakesh {_HUMAN}=1",
        f"cd /c/tmp/ss-regie && python scripts/{_GATE} {_APPROVE} --sha abc --by x {_HUMAN}",
        f".venv/Scripts/python scripts/{_GATE} {_APPROVE} --sha abc --by x {_HUMAN}",
        f"python scripts/{_GATE} {_SET_COORD} --session org-f0",
    ],
)
def test_de_menselijke_handelingen_gaan_langs_rakesh(commando: str) -> None:
    """Een agent tekent niet namens een mens en wijst de regie niet aan.

    "ask" en niet "deny": Rakesh moet deze handeling WEL kunnen doen.
    """
    assert _oordeel(commando) == "ask", commando


@pytest.mark.parametrize(
    "commando",
    [
        f"python scripts/{_GATE} {_APPROVE} --sha abc --by org-5b",
        f"python scripts/{_GATE} request --sha abc --session org-f0",
        f"python scripts/{_GATE} status",
        f"python scripts/{_GATE} verify",
        f"python scripts/{_GATE} whois",
        "echo iets onschuldigs",
        "git commit -m gewoon",
    ],
)
def test_het_gewone_werk_blijft_doorgaan(commando: str) -> None:
    """Zonder deze helft is "vraag alles" een geldige oplossing, en dat is geen bewaking."""
    assert _oordeel(commando) == "geen uitspraak", commando


def test_de_bestaande_bewaking_draait_nog_mee() -> None:
    """De regel die er al stond mag niet zijn gesneuveld, en blijft een DENY.

    Daar is deny wel de juiste vorm: --no-verify hoort ook een mens niet te doen.
    """
    assert _oordeel("git push --no-verify origin develop") == "deny"
