"""De commitcontrole bij een merge toetst wat de tak toevoegt, draait grote selecties met `-n 4`
en gebruikt de Python van het project.

Brief 2026-10-22 (commitcontrole bij een merge). Gemeten: een merge van develop in de noodstop-tak
liet de pre-commit-controle 398 testbestanden kiezen, serieel (`xargs python -m pytest -x`), onder
de systeem-Python 3.13 in plaats van `.venv`. Drie dingen, drie groepen tests:

1. Bij een merge (MERGE_HEAD bestaat) kiest `impact_tests --staged` de DOORSNEDE van het verschil met
   HEAD en met MERGE_HEAD: wat de merge zelf toevoegt (conflictoplossingen, aan beide kanten gewijzigd).
2. Meer dan 50 geselecteerde bestanden draaien met `-n 4`, nooit meer; kleiner draait serieel.
3. De hook gebruikt `.venv` (deze werkkopie, dan de hoofdrepo, dan VIRTUAL_ENV), nooit de eerste
   python uit PATH, en stopt luid als er geen 3.11 is.

MUTATIEBEWIJS (zie de regels onder de tests; beide richtingen):
    doorsnede -> alleen verschil met MERGE_HEAD                      -> 2 tests ROOD
    doorsnede -> alleen verschil met HEAD                            -> 2 tests ROOD
    drempel `-gt 50` -> `-gt 0` (ook kleine selectie parallel)        -> `bij_50_serieel` ROOD
    `-n 4` -> `-n 8`                                                  -> `bij_meer_dan_50` ROOD
    `kies_python` neemt kale `python` uit PATH                        -> groep 3 ROOD
    een legitiem geval: zonder merge blijft het verschil met HEAD     -> `zonder_merge` GROEN
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404: vaste git- en bash-argumenten
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / "scripts" / "hooks" / "pre-commit"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import impact_tests  # noqa: E402


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
        pytest.skip("geen bash gevonden om de hook mee te draaien")
    return gevonden


def _schone_omgeving() -> dict[str, str]:
    """Zonder GIT_* (een hook-omgeving wint van cwd) en zonder actieve VIRTUAL_ENV."""
    omgeving = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    omgeving["VIRTUAL_ENV"] = ""
    return omgeving


def _git(map_: Path, *args: str) -> str:
    uit = subprocess.run(  # nosec B603 B607: vaste argumenten
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.org", *args],
        cwd=map_,
        env=_schone_omgeving(),
        capture_output=True,
        text=True,
        check=False,
    )
    return uit.stdout


def _schrijf(map_: Path, naam: str, inhoud: str) -> None:
    (map_ / naam).write_text(inhoud, encoding="utf-8", newline="\n")


def _merge_repo(
    tmp_path: Path, met_conflict: bool = False, kleine_tak_in_de_stand: bool = False
) -> Path:
    """Een repo waarin `tak` en `develop` elk iets toevoegen en worden samengevoegd (zonder commit).

    Standaard voegt `tak` develop samen; met `kleine_tak_in_de_stand` voegt `develop` (de grote
    stand) de kleine tak samen. `beide.txt` is aan twee kanten gewijzigd zonder conflict.
    """
    _git(tmp_path, "init", "-q", "-b", "develop")
    _schrijf(tmp_path, "gedeeld.txt", "basis\n")
    _schrijf(tmp_path, "beide.txt", "a\nb\nc\nd\ne\nf\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "basis")
    _git(tmp_path, "checkout", "-q", "-b", "tak")
    _schrijf(tmp_path, "alleen_tak.py", "x = 1\n")
    _schrijf(tmp_path, "beide.txt", "A\nb\nc\nd\ne\nf\n")
    if met_conflict:
        _schrijf(tmp_path, "gedeeld.txt", "van tak\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "tak")
    _git(tmp_path, "checkout", "-q", "develop")
    _schrijf(tmp_path, "alleen_develop.py", "y = 2\n")
    _schrijf(tmp_path, "beide.txt", "a\nb\nc\nd\ne\nF\n")
    if met_conflict:
        _schrijf(tmp_path, "gedeeld.txt", "van develop\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "develop")
    if kleine_tak_in_de_stand:
        _git(tmp_path, "merge", "--no-commit", "--no-ff", "tak")
    else:
        _git(tmp_path, "checkout", "-q", "tak")
        _git(tmp_path, "merge", "--no-commit", "--no-ff", "develop")
    if met_conflict:
        _schrijf(tmp_path, "gedeeld.txt", "opgelost\n")
        _git(tmp_path, "add", "gedeeld.txt")
    return tmp_path


def _selectie(repo: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    for naam in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(naam)
    monkeypatch.setattr(impact_tests, "REPO_ROOT", repo)
    return impact_tests._gewijzigd_uit_git("staged", None)


def test_een_tak_die_develop_samenvoegt_selecteert_niets_dat_alleen_van_develop_komt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selectie = _selectie(_merge_repo(tmp_path), monkeypatch)

    assert "alleen_develop.py" not in selectie


def test_een_tak_die_develop_samenvoegt_selecteert_niets_dat_alleen_van_de_tak_komt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selectie = _selectie(_merge_repo(tmp_path), monkeypatch)

    assert "alleen_tak.py" not in selectie


def test_een_kleine_tak_in_een_grote_stand_selecteert_niets_van_de_stand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selectie = _selectie(_merge_repo(tmp_path, kleine_tak_in_de_stand=True), monkeypatch)

    assert "alleen_develop.py" not in selectie


def test_een_kleine_tak_in_een_grote_stand_selecteert_ook_niet_wat_alleen_de_tak_toevoegt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selectie = _selectie(_merge_repo(tmp_path, kleine_tak_in_de_stand=True), monkeypatch)

    assert "alleen_tak.py" not in selectie


def test_een_bestand_dat_aan_beide_kanten_is_gewijzigd_wordt_wel_geselecteerd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selectie = _selectie(_merge_repo(tmp_path), monkeypatch)

    assert selectie == ["beide.txt"]


def test_bij_een_merge_bevat_de_selectie_de_conflictoplossing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selectie = _selectie(_merge_repo(tmp_path, met_conflict=True), monkeypatch)

    assert "gedeeld.txt" in selectie


def test_zonder_merge_blijft_het_verschil_met_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(tmp_path, "init", "-q", "-b", "develop")
    _schrijf(tmp_path, "a.py", "a = 1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "basis")
    _schrijf(tmp_path, "nieuw.py", "b = 2\n")
    _git(tmp_path, "add", "-A")

    selectie = _selectie(tmp_path, monkeypatch)

    assert selectie == ["nieuw.py"]


def _bash_functie(naam: str) -> str:
    inhoud = HOOK.read_text(encoding="utf-8")
    m = re.search(rf"# {naam} begin\n(.*?)# {naam} eind\n", inhoud, re.S)
    assert m, f"de hook mist het blok {naam}"
    return m.group(1)


def _pytest_opties(aantal: int) -> str:
    uit = subprocess.run(  # nosec B603 B607: vaste argumenten
        [_bash(), "-c", _bash_functie("pytest_opties") + f"\npytest_opties {aantal}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return uit.stdout.strip()


def test_bij_50_bestanden_draait_de_selectie_serieel() -> None:
    assert _pytest_opties(50) == ""


def test_bij_een_kleine_selectie_draait_de_selectie_serieel() -> None:
    assert _pytest_opties(3) == ""


def test_bij_meer_dan_50_bestanden_staat_er_n_4_in_de_aanroep() -> None:
    assert _pytest_opties(51) == "-n 4"


def test_bij_een_zeer_grote_selectie_is_het_nog_steeds_n_4() -> None:
    assert _pytest_opties(398) == "-n 4"


def _uitvoerbaar(inhoud: str) -> str:
    return "\n".join(
        r
        for r in inhoud.splitlines()
        if not r.strip().startswith(("#", "echo ", "info ", "fail ", "ok "))
    )


def test_de_hook_geeft_de_opties_echt_aan_pytest_door() -> None:
    uitvoerbaar = _uitvoerbaar(HOOK.read_text(encoding="utf-8"))

    assert re.search(r'xargs "\$PYTHON" -m pytest \$\(pytest_opties "\$AANTAL"\)', uitvoerbaar)


def test_de_pytest_stap_heeft_geen_ontsnapping() -> None:
    uitvoerbaar = _uitvoerbaar(HOOK.read_text(encoding="utf-8"))
    regel = next(r for r in uitvoerbaar.splitlines() if "-m pytest" in r)

    assert "|| true" not in regel and "SKIP" not in uitvoerbaar


def _venv_python(map_: Path, exit_code: int) -> Path:
    exe = map_ / ".venv" / "bin" / "python"
    exe.parent.mkdir(parents=True)
    exe.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8", newline="\n")
    exe.chmod(0o755)
    return exe


def _kies_python(map_: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 B607: vaste argumenten
        [_bash(), "-c", _bash_functie("kies_python") + "\nkies_python"],
        cwd=map_,
        env=_schone_omgeving(),
        capture_output=True,
        text=True,
        check=False,
    )


def test_de_hook_kiest_de_venv_van_de_werkkopie_en_niet_de_python_uit_path(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q")
    exe = _venv_python(tmp_path, 0)

    uit = _kies_python(tmp_path)

    assert uit.returncode == 0 and Path(uit.stdout.strip()).as_posix().endswith(
        exe.relative_to(tmp_path).as_posix()
    )


def test_een_gelinkte_worktree_gebruikt_de_venv_van_de_hoofdrepo(tmp_path: Path) -> None:
    hoofd = tmp_path / "hoofd"
    hoofd.mkdir()
    _git(hoofd, "init", "-q", "-b", "develop")
    _schrijf(hoofd, "a.txt", "a\n")
    _git(hoofd, "add", "-A")
    _git(hoofd, "commit", "-q", "-m", "basis")
    exe = _venv_python(hoofd, 0)
    werk = tmp_path / "werk"
    _git(hoofd, "worktree", "add", "-q", "-b", "iter/x", str(werk))

    uit = _kies_python(werk)

    assert uit.returncode == 0 and uit.stdout.strip().endswith(exe.relative_to(hoofd).as_posix())


def test_een_eigen_venv_in_de_worktree_gaat_voor_die_van_de_hoofdrepo(tmp_path: Path) -> None:
    hoofd = tmp_path / "hoofd"
    hoofd.mkdir()
    _git(hoofd, "init", "-q", "-b", "develop")
    _schrijf(hoofd, "a.txt", "a\n")
    _git(hoofd, "add", "-A")
    _git(hoofd, "commit", "-q", "-m", "basis")
    _venv_python(hoofd, 0)
    werk = tmp_path / "werk"
    _git(hoofd, "worktree", "add", "-q", "-b", "iter/x", str(werk))
    eigen = _venv_python(werk, 0)

    uit = _kies_python(werk)

    assert uit.returncode == 0 and uit.stdout.strip().endswith(eigen.relative_to(werk).as_posix())
    assert "/werk/" in Path(uit.stdout.strip()).as_posix()


def test_zonder_projectomgeving_geeft_de_keuze_niets_en_faalt(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")

    uit = _kies_python(tmp_path)

    assert uit.returncode != 0 and uit.stdout.strip() == ""


def _draai_hook(map_: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 B607: vaste argumenten
        [_bash(), str(HOOK)],
        cwd=map_,
        env=_schone_omgeving(),
        capture_output=True,
        text=True,
        check=False,
    )


def test_de_hook_stopt_luid_zonder_projectomgeving(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")

    uit = _draai_hook(tmp_path)

    assert uit.returncode == 1 and "GEEN projectomgeving" in (uit.stdout + uit.stderr)


def test_de_hook_stopt_luid_bij_een_andere_python_dan_3_11(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _venv_python(tmp_path, 1)

    uit = _draai_hook(tmp_path)

    assert uit.returncode == 1 and "geen Python 3.11" in (uit.stdout + uit.stderr)


def _hook_met_nep_pytest(map_: Path, pytest_exit: int) -> subprocess.CompletedProcess[str]:
    """De hele hook met een nep-python: 3.11, kiest een testbestand, en pytest geeft `pytest_exit`."""
    exe = map_ / ".venv" / "bin" / "python"
    exe.parent.mkdir(parents=True)
    exe.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        '  *"-m pytest"*) exit ' + str(pytest_exit) + ";;\n"
        "  *impact_tests*) echo test_x.py; exit 0;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
        newline="\n",
    )
    exe.chmod(0o755)
    _git(map_, "init", "-q")
    _schrijf(map_, "iets.txt", "x\n")
    _git(map_, "add", "-A")
    return _draai_hook(map_)


def test_een_falende_pytest_laat_de_hook_met_exit_1_eindigen(tmp_path: Path) -> None:
    uit = _hook_met_nep_pytest(tmp_path, pytest_exit=1)

    assert uit.returncode == 1 and "een test die deze wijziging raakt, faalt" in (
        uit.stdout + uit.stderr
    )


def test_een_slagende_pytest_laat_de_hook_met_exit_0_eindigen(tmp_path: Path) -> None:
    uit = _hook_met_nep_pytest(tmp_path, pytest_exit=0)

    assert uit.returncode == 0, uit.stdout + uit.stderr


def test_de_hook_gaat_door_met_een_3_11_projectomgeving(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _venv_python(tmp_path, 0)

    uit = _draai_hook(tmp_path)

    assert uit.returncode == 0, uit.stdout + uit.stderr
