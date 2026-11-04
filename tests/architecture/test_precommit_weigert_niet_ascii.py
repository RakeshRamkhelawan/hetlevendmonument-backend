"""De NOOIT-lijst (geen niet-ASCII in broncode) wordt LOKAAL afgedwongen, met dezelfde controle als de CI (2026-10-23).

Gemeten (CI-run 39852524654 op develop, 2026-10-22): de stap "NOOIT-lijst: non-ASCII in Python gate" faalde op twee tekens
(`src/core/llm/mistral_provider.py` en `src/core/copilot/service.py`); de lokale controles hadden ze laten passeren, want alleen de CI
had een eigen `grep`. Proza voorkomt niets, gereedschap wel: `scripts/check_non_ascii.py` is nu DE definitie (mappen, uitzondering,
melding), en de pre-commit en de CI roepen dezelfde code aan.

Wat deze tests vastleggen:

1. het script doet wat het belooft: een bestand met een niet-ASCII-teken (accent, emoji) faalt met bestand en regel, schone ASCII slaagt;
2. de pre-commit roept het script aan op de GESTAGEDE `.py`-bestanden van `src/`, `scripts/` en `mcp-server/` (de mappen van de CI) en
   stopt de commit bij een fout;
3. de CI-stap roept hetzelfde script aan in plaats van een eigen `grep`, zodat lokaal en CI niet kunnen uiteenlopen;
4. de broncode is nu ASCII (de toestand die de CI eist).

De tests lezen STRUCTUUR (de aanroep op een niet-commentaarregel, het `exit 1` in hetzelfde blok), niet de tekst van een commentaar.

Naast `test_no_non_ascii_in_core_zone.py`: die dekt alleen vier kernmappen (bewust, toen er 301 bestanden vervuild waren) en kent
geen pre-commit of CI. Deze tests dekken de mappen van de CI en de koppeling met de hook.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_non_ascii.py"
HOOK = REPO / "scripts" / "hooks" / "pre-commit"
WORKFLOW = REPO / ".github" / "workflows" / "ci-feature.yml"
WORTELS = ("src", "scripts", "mcp-server")
ARCHIEF = "src/alembic/versions/archive/"


def _draai(*bestanden: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, bestanden)],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )


def _zonder_commentaar(tekst: str) -> list[str]:
    """De regels van een shell- of yaml-bestand zonder de regels die met `#` beginnen."""
    return [regel for regel in tekst.splitlines() if not regel.lstrip().startswith("#")]


def _blok_na(regels: list[str], begin: int) -> list[str]:
    """De regels vanaf `begin` tot en met de eerstvolgende `fi` (het `if ... then ... fi`-blok van de hook)."""
    blok: list[str] = []
    for regel in regels[begin:]:
        blok.append(regel)
        if regel.strip() == "fi":
            break
    return blok


class TestHetScript:
    def test_het_script_bestaat(self) -> None:
        assert SCRIPT.is_file(), "scripts/check_non_ascii.py ontbreekt"

    def test_schone_ascii_slaagt(self, tmp_path: Path) -> None:
        bestand = tmp_path / "schoon.py"
        bestand.write_text("x = 1  # gewoon ASCII\n", encoding="utf-8")

        assert _draai(bestand).returncode == 0

    def test_een_accent_faalt(self, tmp_path: Path) -> None:
        bestand = tmp_path / "accent.py"
        bestand.write_text('x = 1\ny = "Een é hier"\n', encoding="utf-8")

        assert _draai(bestand).returncode == 1

    def test_een_emoji_faalt(self, tmp_path: Path) -> None:
        bestand = tmp_path / "emoji.py"
        bestand.write_text('x = "\U0001f600"\n', encoding="utf-8")

        assert _draai(bestand).returncode == 1

    def test_de_melding_noemt_bestand_en_regel(self, tmp_path: Path) -> None:
        bestand = tmp_path / "accent.py"
        bestand.write_text('x = 1\ny = "Een é hier"\n', encoding="utf-8")

        uitvoer = _draai(bestand)

        assert f"{bestand}:2" in uitvoer.stdout + uitvoer.stderr

    def test_alle_bestanden_worden_gelezen_niet_alleen_het_eerste(self, tmp_path: Path) -> None:
        schoon = tmp_path / "schoon.py"
        schoon.write_text("x = 1\n", encoding="utf-8")
        accent = tmp_path / "accent.py"
        accent.write_text('y = "é"\n', encoding="utf-8")

        assert _draai(schoon, accent).returncode == 1

    def test_geen_bestanden_is_geen_fout(self) -> None:
        assert _draai().returncode == 0

    @pytest.mark.parametrize("teken", ["\u0085", " ", " "])
    def test_een_teken_dat_splitlines_als_regeleinde_ziet_faalt_ook(
        self, tmp_path: Path, teken: str
    ) -> None:
        # Security-review Gate 2 (2026-10-23): `str.splitlines()` splitst op deze tekens en gooit ze weg, zodat een bestand waarin zo'n
        # teken het ENIGE niet-ASCII-teken is erdoor kwam. De oude `grep -P '[^\x00-\x7F]'` ving het wel.
        bestand = tmp_path / "regeleinde.py"
        bestand.write_text(f"x = 1  # a{teken}b\n", encoding="utf-8")

        assert _draai(bestand).returncode == 1

    def test_een_bestandsnaam_met_een_accent_wordt_ook_gescand(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `git ls-files` citeert zo'n naam als "src/caf\303\251.py" (core.quotepath, de standaard); een filter op `.py` zag hem dan niet.
        for sleutel in [k for k in os.environ if k.startswith("GIT_")]:
            monkeypatch.delenv(sleutel)
        schone_omgeving = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, env=schone_omgeving)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "café.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, env=schone_omgeving)
        spec = importlib.util.spec_from_file_location("_check_non_ascii", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        gevonden = [pad.name for pad in module.alle_bestanden(tmp_path)]

        assert gevonden == ["café.py"]


class TestDePrecommitHook:
    def _regels(self) -> list[str]:
        return _zonder_commentaar(HOOK.read_text(encoding="utf-8"))

    def _aanroep(self) -> int:
        regels = self._regels()
        posities = [
            i
            for i, regel in enumerate(regels)
            if "check_non_ascii.py" in regel and "xargs" in regel
        ]
        assert posities, (
            "de pre-commit roept scripts/check_non_ascii.py niet aan op de gestagede bestanden"
        )
        return posities[0]

    def test_de_hook_roept_het_script_aan(self) -> None:
        self._aanroep()

    def test_een_oudere_tak_zonder_het_script_loopt_niet_vast_op_de_gedeelde_hook(self) -> None:
        # `.git/hooks` is gedeeld door alle werkmappen; een tak zonder scripts/check_non_ascii.py slaat de stap over in plaats van
        # elke commit te laten falen. `test_het_script_bestaat` bewaakt dat het script in elke tak met deze hook bestaat.
        assert any("! -f scripts/check_non_ascii.py" in regel for regel in self._regels())

    def test_de_hook_kiest_de_gestagede_bestanden_van_alle_drie_de_mappen(self) -> None:
        regels = self._regels()
        selecties = [
            regel
            for regel in regels
            if "STAGED" in regel
            and "grep -E" in regel
            and all(wortel in regel for wortel in WORTELS)
        ]

        assert selecties, f"geen selectie van gestagede .py-bestanden over {WORTELS}"

    def test_de_hook_leest_gestagede_namen_ongeciteerd(self) -> None:
        # Zonder core.quotepath=off citeert git "src/caf\303\251.py" en zien de `grep -E '^(src|...)/.*\.py$'`-selecties zo'n bestand niet.
        regels = [r for r in self._regels() if r.startswith("STAGED=")]

        assert len(regels) == 1 and "-c core.quotepath=off diff --cached" in regels[0]

    def test_de_hook_laat_het_archief_buiten_beschouwing_zoals_de_ci(self) -> None:
        assert any(ARCHIEF in regel for regel in self._regels()), (
            f"{ARCHIEF} wordt niet uitgezonderd"
        )

    def test_de_hook_stopt_de_commit_bij_een_fout(self) -> None:
        blok = _blok_na(self._regels(), self._aanroep() - 1)

        assert any(re.search(r"\bexit 1\b", regel) for regel in blok), (
            "geen `exit 1` bij een niet-ASCII-teken"
        )

    def test_de_hook_gebruikt_de_projectpython_en_geen_kale_python(self) -> None:
        regel = self._regels()[self._aanroep()]

        assert '"$PYTHON"' in regel, "het script draait niet met de python van het project"


class TestDeCi:
    def _stap(self) -> list[str]:
        regels = WORKFLOW.read_text(encoding="utf-8").splitlines()
        begin = next(
            i for i, regel in enumerate(regels) if "NOOIT-lijst: non-ASCII in Python gate" in regel
        )
        stap = [regels[begin]]
        for regel in regels[begin + 1 :]:
            if regel.lstrip().startswith("- name:"):
                break
            stap.append(regel)
        return _zonder_commentaar("\n".join(stap))

    def test_de_ci_roept_hetzelfde_script_aan(self) -> None:
        assert any("scripts/check_non_ascii.py" in regel for regel in self._stap())

    def test_de_ci_heeft_geen_eigen_grep_meer_voor_niet_ascii(self) -> None:
        assert not any("x7F" in regel for regel in self._stap()), (
            "de CI heeft nog een eigen niet-ASCII-patroon"
        )


class TestDeBroncodeIsAscii:
    def test_er_staat_geen_niet_ascii_in_de_python_broncode(self) -> None:
        bestanden = subprocess.run(
            ["git", "ls-files", "--", *WORTELS],
            capture_output=True,
            text=True,
            cwd=REPO,
            check=True,
        ).stdout.splitlines()
        schendingen = [
            f"{naam}:{nummer}"
            for naam in bestanden
            if naam.endswith(".py") and not naam.startswith(ARCHIEF)
            for nummer, regel in enumerate(
                (REPO / naam).read_text(encoding="utf-8").splitlines(), start=1
            )
            if not regel.isascii()
        ]

        assert not schendingen, f"niet-ASCII in de broncode: {schendingen}"
