"""De Stop-hook telt alleen het ongecommit werk van de LOPENDE sessie.

Achtergrond (TAAK 4, 2026-09-30): met meerdere sessies in een gedeelde werkkopie
telde sectie 1 van klaar-is-echt-klaar.sh alle ongecommitte tracked bestanden,
ongeacht welke sessie ze aanraakte. Dat leverde een lus op: sessie A kon haar beurt
niet afronden zolang sessie B ongecommit werk had -- en sessie B kon niet committen
omdat een falende test haar commitpoort blokkeerde.

De oplossing: track-edits.sh (PostToolUse op Edit|Write) schrijft aangeraakte
bestandspaden naar .git/touched-by-<sessie>.txt. Sectie 1 van de Stop-hook
snijdt dat bestand met git status en blokkeert alleen als er OVERLAPPING is.

Mutatiebewijs (2026-09-30, beide richtingen):
- Lege touch file + gewijzigde bestanden van andere sessie -> EXIT 0 (GROEN)
- Touch file met gewijzigd bestand van eigen sessie -> EXIT 2 (ROOD)
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / ".claude" / "hooks" / "klaar-is-echt-klaar.sh"
TRACK = REPO_ROOT / ".claude" / "hooks" / "track-edits.sh"
SETTINGS = REPO_ROOT / ".claude" / "settings.json"


def test_klaar_hook_bevat_per_sessie_logica() -> None:
    """De Stop-hook gebruikt CLAUDE_SESSION_NAME voor per-sessie filtering."""
    inhoud = HOOK.read_text(encoding="utf-8")
    assert "CLAUDE_SESSION_NAME" in inhoud, (
        "%s bevat geen CLAUDE_SESSION_NAME -- de per-sessie logica ontbreekt" % HOOK
    )
    assert "touched-by-" in inhoud, (
        "%s bevat geen touch-bestand-logica -- sectie 1 is niet bijgewerkt" % HOOK
    )


def test_track_edits_hook_bestaat() -> None:
    """track-edits.sh moet bestaan; zonder dit wordt het touch-bestand nooit gevuld."""
    assert TRACK.exists(), (
        "%s bestaat niet -- PostToolUse-hook voor sessie-tracking ontbreekt" % TRACK
    )


def test_track_edits_staat_in_settings() -> None:
    """settings.json moet track-edits.sh als PostToolUse-hook registreren."""
    inhoud = SETTINGS.read_text(encoding="utf-8")
    assert "track-edits.sh" in inhoud, (
        "track-edits.sh staat niet in %s -- de hook draait nooit" % SETTINGS
    )


import json
import os
import shutil


def _run_hook(
    sessie: str | None,
    touch_inhoud: str | None,
    stdin_json: str | None = None,
) -> tuple[int, str]:
    """Hulpfunctie: draai de Stop-hook met optionele sessienaam, touch-bestand en stdin-JSON.

    sessie=None simuleert het geval dat CLAUDE_SESSION_NAME niet gezet is.
    stdin_json kan session_id bevatten zoals de echte Claude Code Stop-hook dat doet.
    """
    git_dir = REPO_ROOT / ".git"
    touch_pad: "Path | None" = None
    if sessie is not None:
        touch_pad = git_dir / f"touched-by-{sessie}.txt"
    try:
        if touch_pad is not None:
            if touch_inhoud is not None:
                touch_pad.write_text(touch_inhoud, encoding="utf-8")
            elif touch_pad.exists():
                touch_pad.unlink()

        bash = shutil.which("bash") or "bash"
        omgeving = os.environ.copy()
        if sessie is not None:
            omgeving["CLAUDE_SESSION_NAME"] = sessie
        else:
            omgeving.pop("CLAUDE_SESSION_NAME", None)
        omgeving["CLAUDE_PROJECT_DIR"] = str(REPO_ROOT).replace("\\", "/")

        uitvoer = subprocess.run(
            [bash, str(HOOK).replace("\\", "/")],
            capture_output=True,
            text=True,
            env=omgeving,
            cwd=str(REPO_ROOT),
            timeout=15,
            input=stdin_json or "",
        )
        return uitvoer.returncode, (uitvoer.stdout + uitvoer.stderr)
    finally:
        if touch_pad is not None and touch_pad.exists():
            touch_pad.unlink()


def _eerste_gewijzigd_bestand() -> str | None:
    """Geeft het eerste bestand uit git status --porcelain, of None als er niets is."""
    try:
        # GIT_*-sleutels strippen: de guard test_a_test_never_runs_git_against_another_repo
        # vereist dat git-aanroepen buiten de hook de geerfd GIT_DIR niet meenemen.
        schoon = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        uit = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=10,
            env=schoon,
        )
        for regel in uit.stdout.splitlines():
            if regel.strip():
                return regel.split()[-1]
    except Exception:
        pass
    return None


def test_lege_touch_file_blokkeert_niet() -> None:
    """Een sessie zonder eigen ongecommit werk wordt niet geblokkeerd door andermans bestanden.

    Dit is richting 2 van het mutatiebewijs (2026-09-30):
    - git status toont gewijzigde bestanden van andere sessies
    - touch-bestand van DEZE sessie bestaat niet (of is leeg)
    - hook moet EXIT 0 geven
    """
    exitcode, _ = _run_hook("test-sessie-richting2", touch_inhoud=None)
    assert exitcode == 0, (
        "hook blokkeert terwijl touch-bestand leeg is -- per-sessie filtering werkt niet. "
        "Exit %d" % exitcode
    )


def test_eigen_ongecommit_werk_blokkeert() -> None:
    """Een sessie met eigen ongecommit werk wordt geblokkeerd.

    Dit is richting 1 van het mutatiebewijs (2026-09-30, bijgewerkt na fix):
    - touch-bestand bevat een van de bestanden die git status WERKELIJK toont
    - hook moet EXIT 2 geven

    De test leest git status dynamisch, zodat hij niet afhankelijk is van een
    specifiek bestand dat toevallig gewijzigd is.
    """
    gewijzigd = _eerste_gewijzigd_bestand()
    if gewijzigd is None:
        import pytest

        pytest.skip("Geen gewijzigde tracked bestanden in git status om te testen")

    exitcode, uitvoer = _run_hook(
        "test-sessie-richting1",
        touch_inhoud=f"{gewijzigd}\n",
    )
    assert exitcode == 2, (
        "hook blokkeert NIET terwijl touch-bestand '%s' bevat (staat als M in git status) -- "
        "per-sessie filtering blokkeert niet waar het hoort. "
        "Exit %d, uitvoer: %s" % (gewijzigd, exitcode, uitvoer[:200])
    )


def test_session_id_uit_stdin_werkt() -> None:
    """De hook gebruikt session_id uit de stdin-JSON als CLAUDE_SESSION_NAME niet gezet is.

    Gemeten 2026-09-30: CLAUDE_SESSION_NAME is NIET gezet in de Stop-hook context.
    De fix: session_id staat in de stdin-JSON die Claude Code aan de Stop-hook geeft.
    Dit is de primaire weg; CLAUDE_SESSION_NAME blijft als terugval.

    Mutatiebewijs (richting 2): session_id in stdin, geen CLAUDE_SESSION_NAME,
    geen touch-bestand -> EXIT 0 (niet geblokkeerd).
    """
    sessie_id = "test-stdin-sessie-abc123"
    stdin_data = json.dumps({"session_id": sessie_id, "cwd": str(REPO_ROOT)})
    # Geen touch-bestand voor deze sessie-id -> sessie heeft niets aangeraakt -> EXIT 0
    exitcode, _ = _run_hook(
        sessie=None,
        touch_inhoud=None,
        stdin_json=stdin_data,
    )
    assert exitcode == 0, (
        "hook blokkeert terwijl session_id via stdin komt en geen touch-bestand bestaat -- "
        "per-sessie identificatie via stdin werkt niet. Exit %d" % exitcode
    )
