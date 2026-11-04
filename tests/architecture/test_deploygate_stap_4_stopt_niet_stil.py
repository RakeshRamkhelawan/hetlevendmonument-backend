"""Stap 4 van `scripts/pre-deploy-check.sh` meldt een falende `gh` luid (brief 2026-10-24, bevinding a).

Gemeten 2026-10-24 op 98e5047b: `EXISTING=$(gh secret list 2>/dev/null | awk '{print $1}')` staat onder
`set -euo pipefail`. Faalt `gh` (niet ingelogd, geen recht), dan is de status van de pijp niet nul, `set -e`
breekt de toewijzing af en het script stopt ZONDER een woord: exit 1 en niets in het log waaruit blijkt
waarom. In een CD-job is dat een rode stap waar niemand iets mee kan.

Besluit: een falende `gh` is een FAIL, geen WARN. Een gate die zijn controle niet kan uitvoeren meldt niet
groen (zelfde regel als stap 3c: geen interpreter -> fail). Op de staging-runner wordt stap 4 bewust
overgeslagen via `PRE_DEPLOY_SLA_OVER`, dus daar speelt dit niet.

**Wat deze test doet:** knipt stap 4 (met de kop van het script) uit het script, zet een NEP-`gh` vooraan het
pad en draait het met Git-bash. Drie kanten: `gh` faalt -> een FAIL-regel die `gh secret list` noemt en exit
1; `gh` toont alle vereiste namen -> exit 0; stap 4 overgeslagen -> `gh` wordt niet eens aangeroepen.

MUTATIEBEWIJS (2026-10-24):
    de oorspronkelijke regel terugzetten (zonder `if !`)       -> `..._faalt_luid` ROOD
    een falende `gh` laten eindigen in WARN en exit 0           -> `..._faalt_luid` ROOD (exitcode)
    de FAIL-tak ook bij een werkende `gh` nemen                 -> `..._werkende_gh_is_groen` ROOD
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/pre-deploy-check.sh"


def _bash() -> str:
    """Git-bash met pad, nooit de kale naam: `bash` kan op deze machine naar de WSL-relay wijzen."""
    for kandidaat in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "/bin/bash",
    ):
        if os.path.exists(kandidaat):
            return kandidaat
    gevonden = shutil.which("bash")
    if gevonden is None:
        pytest.skip("geen bash gevonden")
    return gevonden


def _stap_4_script(tmp_path: Path) -> Path:
    tekst = SCRIPT.read_text(encoding="utf-8")
    kop_einde = tekst.index('echo "=== PRE-DEPLOY')
    # Alleen stap 4 (tot de scheidingslijn van stap 5), met de hulpfuncties van de kop.
    begin = tekst.index('echo "4. GitHub Secrets')
    einde = tekst.rindex("\n# ---", 0, tekst.index("# 5. Azure service principal"))
    delen = tekst[:kop_einde] + tekst[begin:einde] + '\nexit "$ERRORS"\n'
    pad = tmp_path / "stap4.sh"
    pad.write_text(delen, encoding="utf-8", newline="\n")
    return pad


def _vereiste_namen() -> list[str]:
    tekst = SCRIPT.read_text(encoding="utf-8")
    blok = re.search(r"REQUIRED_SECRETS=\((.*?)\n\)", tekst, flags=re.S)
    assert blok is not None
    return re.findall(r'^\s*"([A-Z0-9_]+)"', blok.group(1), flags=re.M)


def _nep_gh(map_: Path, inhoud: str) -> None:
    gh = map_ / "gh"
    gh.write_text("#!/bin/sh\n" + inhoud, encoding="utf-8", newline="\n")
    gh.chmod(0o755)


def _draai(tmp_path: Path, gh_inhoud: str, sla_over: str = "") -> subprocess.CompletedProcess[str]:
    bin_map = tmp_path / "bin"
    bin_map.mkdir()
    _nep_gh(bin_map, gh_inhoud)
    omgeving = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    omgeving["PATH"] = str(bin_map) + os.pathsep + omgeving.get("PATH", "")
    omgeving["PRE_DEPLOY_SLA_OVER"] = sla_over
    return subprocess.run(
        [_bash(), str(_stap_4_script(tmp_path))],
        cwd=REPO_ROOT,
        env=omgeving,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_een_falende_gh_faalt_luid_en_niet_stil(tmp_path: Path) -> None:
    uitslag = _draai(tmp_path, "exit 1\n")

    assert (uitslag.returncode, "gh secret list" in uitslag.stdout) == (1, True), uitslag.stdout[
        -500:
    ]


def test_een_werkende_gh_met_alle_namen_is_groen(tmp_path: Path) -> None:
    namen = "\\n".join(_vereiste_namen())
    uitslag = _draai(tmp_path, f"printf '{namen}\\n'\n")

    assert uitslag.returncode == 0, uitslag.stdout[-500:]


def test_een_overgeslagen_stap_roept_gh_niet_aan(tmp_path: Path) -> None:
    uitslag = _draai(tmp_path, "exit 1\n", sla_over="4")

    assert (uitslag.returncode, "overgeslagen" in uitslag.stdout) == (0, True), uitslag.stdout[
        -500:
    ]
