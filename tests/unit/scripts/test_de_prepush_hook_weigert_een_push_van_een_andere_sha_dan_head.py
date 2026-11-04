"""De pre-push hook weigert een develop-push waarvan de sha niet de HEAD van de werkmap is.

WAAROM DIT BESTAAT
------------------
Gemeten 2026-10-01 bij de push van 20c48b3c (zie
`docs/agent-briefs/generated/2026-10-01-sprint-dag-de-testronde-bij-push-test-de-verkeerde-code.md`,
basis 574026c8): de hook toetst de goedkeuring op de gepushte sha, maar de testronde draait in
de werkmap, op wat daar ook uitgecheckt staat. Een sha pushen die niet is uitgecheckt liet dus
"groen" zien over andere code dan er landde.

Besluit van de regie dat deze tests vastleggen: bij een push naar `refs/heads/develop` met een
`local_sha` die niet gelijk is aan `git rev-parse HEAD` weigert de hook, VOOR de snelle CI, de
testronde en het docs-pad, en de melding noemt beide shas.

HOE DIT MEET
------------
De ECHTE hook (`scripts/hooks/pre-push`, niet gekopieerd) draait als subproces met
`cwd=<wegwerp-repo>`; de hook bepaalt zijn repo met `git rev-parse --show-toplevel`. De
omgeving heeft geen `GIT_*`-sleutels (anders wint `GIT_DIR` van `cwd`, zie
`tests/architecture/test_a_test_never_runs_git_against_another_repo.py`). Het echte
gatebestand wordt niet aangeraakt: `push_gate.py` bestaat in de wegwerp-repo niet, dus de hook
slaat de goedkeuringscontrole over (`[ -f "$PUSH_GATE" ]`, regel 138).

De hook heeft GEEN mechanisme om de testronde over te slaan. Daarom bevat de wegwerp-repo
precies wat hij vooraf nodig heeft:
- `scripts/ci-local-fast.sh`, een stub die een markeerbestand schrijft. Dat bestand is het
  bewijs dat de hook voorbij de nieuwe controle is gekomen. Zo toetst (b) en (c) niet op de
  TEKST van een melding die nog niet bestaat, maar op GEDRAG;
- `.venv/bin/python`, een wrapper naar de interpreter van deze test, zodat de hook niet een
  willekeurige `python` op het PATH kiest;
- vier mappen `tests/unit`, `tests/architecture`, `tests/core`, `tests/contracts` met elk een
  slagende test. Zonder die mappen faalt de testronde van de hook altijd, en dan is "weigert"
  niet te onderscheiden van "doet niets" (exitcode 1 in beide gevallen). De testronde die dit
  uitvoert is dus een mini-ronde van vier lege tests in de wegwerp-repo, niet de echte.

(d) gebruikt een push van alleen een .md-bestand; het docs-pad roept `scripts/validate_feature_docs.py` aan, een stub met eigen markeerbestand.

(d) pusht een commit met alleen een .md-bestand; het docs-pad roept `scripts/validate_feature_docs.py`
aan, hier een stub met een eigen markeerbestand.

Wat deze tests NIET toetsen: de exacte tekst van de melding (alleen dat beide shas erin staan,
als voorvoegsel van 7 tekens), de volgorde ten opzichte van de goedkeuringscontrole (die is hier
uitgeschakeld), en het gedrag bij ongecommitte wijzigingen in getrackte bestanden.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_WORTEL = Path(__file__).resolve().parents[3]
_HOOK = _WORTEL / "scripts" / "hooks" / "pre-push"

NUL_SHA = "0" * 40
MARKER = "ci-gedraaid.marker"
DOCS_MARKER = "docs-pad-gedraaid.marker"
# Zeven tekens is genoeg om een sha te herkennen in zowel de lange als de korte schrijfwijze.
VOORVOEGSEL = 7


def _bash() -> str:
    """Het pad naar Git-bash, nooit de kale naam: `bash` kan naar de WSL-relay wijzen.

    Gemeten op deze machine: `bash` op het PATH is C:\\Windows\\System32\\bash.exe en geeft
    `execvpe(/bin/bash) failed`. Een hook die dan niet draait, laat elke "weigert"-assertie
    groen zijn zonder iets te meten.
    """
    for kandidaat in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "/bin/bash",
    ):
        if os.path.exists(kandidaat):
            return kandidaat
    gevonden = shutil.which("bash")
    if gevonden is None or "system32" in gevonden.lower():
        pytest.skip("geen Git-bash gevonden om de hook mee te draaien")
    return gevonden


def _schone_omgeving(tmp: Path) -> dict[str, str]:
    """De omgeving zonder `GIT_*`; `TMPDIR` naar de wegwerpmap zodat het ronde-log daar landt."""
    omgeving = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    omgeving["TMPDIR"] = str(tmp)
    return omgeving


def _git(repo: Path, *args: str) -> str:
    uit = subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t.t",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        env=_schone_omgeving(repo),
    )
    return uit.stdout.strip()


def _schrijf(pad: Path, inhoud: str) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    with open(pad, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(inhoud)


@dataclass(frozen=True)
class Uitslag:
    returncode: int
    uitvoer: str
    ci_draaide: bool
    docs_pad_draaide: bool
    basis_sha: str
    punt_sha: str


def _draai_hook(
    tmp_path: Path, *, head_op: str, push_ref: str, punt_bestand: str = "nieuw.py"
) -> Uitslag:
    """Bouw een wegwerp-repo, zet HEAD op `head_op`, push `punt` naar `push_ref`.

    Geschiedenis: BASIS (branch develop) - PUNT (branch kandidaat, voegt een .py toe).
    `head_op` is "basis" of "punt"; de gepushte `local_sha` is altijd PUNT.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    hooks_leeg = tmp_path / "geen-hooks"
    hooks_leeg.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "core.hooksPath", str(hooks_leeg))

    _schrijf(
        repo / "scripts" / "ci-local-fast.sh",
        f'#!/usr/bin/env bash\ntouch "$(dirname "$0")/../{MARKER}"\n',
    )
    # Het docs-pad roept dit script als laatste stap aan; de stub bewijst dat dat pad draaide.
    _schrijf(
        repo / "scripts" / "validate_feature_docs.py",
        "from pathlib import Path\n\n"
        f'Path(__file__).resolve().parent.parent.joinpath("{DOCS_MARKER}").write_text("x")\n',
    )
    for map_naam in ("unit", "architecture", "core", "contracts"):
        # Unieke bestandsnaam per map: pytest weigert anders twee `test_stub` zonder __init__.
        _schrijf(
            repo / "tests" / map_naam / f"test_stub_{map_naam}.py", "def test_stub():\n    pass\n"
        )
    _schrijf(repo / "README.txt", "basis\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "basis")
    basis = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "-b", "kandidaat")
    _schrijf(repo / punt_bestand, "inhoud\n")
    _git(repo, "add", punt_bestand)
    _git(repo, "commit", "-q", "-m", "punt")
    punt = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "--detach", basis if head_op == "basis" else punt)

    wrapper = repo / ".venv" / "bin" / "python"
    _schrijf(wrapper, f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "$@"\n')

    regel = f"{push_ref} {punt} {push_ref} {NUL_SHA}\n"
    uit = subprocess.run(  # nosec B603: vast hookpad, invoer via stdin
        [_bash(), str(_HOOK)],
        cwd=repo,
        # Bytes, geen tekst: tekstmodus maakt op Windows van "\n" een "\r\n", en dan eindigt de
        # remote-sha met een CR die de hook als niet-nul leest (echte git stuurt alleen LF).
        input=regel.encode("ascii"),
        capture_output=True,
        check=False,
        env=_schone_omgeving(tmp_path),
        timeout=120,
    )
    return Uitslag(
        returncode=uit.returncode,
        uitvoer=(uit.stdout + uit.stderr).decode("utf-8", errors="replace"),
        ci_draaide=(repo / MARKER).exists(),
        docs_pad_draaide=(repo / DOCS_MARKER).exists(),
        basis_sha=basis,
        punt_sha=punt,
    )


@pytest.fixture(scope="module")
def sha_niet_gelijk_aan_head(tmp_path_factory: pytest.TempPathFactory) -> Uitslag:
    """(a) develop-push van PUNT terwijl HEAD op BASIS staat. Een run, drie tests."""
    return _draai_hook(
        tmp_path_factory.mktemp("niet-gelijk"), head_op="basis", push_ref="refs/heads/develop"
    )


@pytest.fixture(scope="module")
def md_sha_niet_gelijk_aan_head(tmp_path_factory: pytest.TempPathFactory) -> Uitslag:
    """(d) develop-push van een commit met ALLEEN een .md-wijziging, HEAD op BASIS."""
    return _draai_hook(
        tmp_path_factory.mktemp("md-niet-gelijk"),
        head_op="basis",
        push_ref="refs/heads/develop",
        punt_bestand="nieuw.md",
    )


@pytest.fixture(scope="module")
def sha_gelijk_aan_head(tmp_path_factory: pytest.TempPathFactory) -> Uitslag:
    """(b) develop-push van PUNT terwijl HEAD op PUNT staat."""
    return _draai_hook(
        tmp_path_factory.mktemp("gelijk"), head_op="punt", push_ref="refs/heads/develop"
    )


@pytest.fixture(scope="module")
def zijtak_push_met_afwijkende_head(tmp_path_factory: pytest.TempPathFactory) -> Uitslag:
    """(c) push van PUNT naar een zijtak terwijl HEAD op BASIS staat."""
    return _draai_hook(
        tmp_path_factory.mktemp("zijtak"), head_op="basis", push_ref="refs/heads/iter/x"
    )


class TestEenDevelopPushVanEenAndereShaDanHeadWordtGeweigerd:
    """(a) ROOD tegen 574026c8: de hook vergelijkt nergens met HEAD."""

    def test_de_hook_geeft_een_foutcode(self, sha_niet_gelijk_aan_head: Uitslag) -> None:
        assert sha_niet_gelijk_aan_head.returncode != 0

    def test_de_snelle_ci_start_niet(self, sha_niet_gelijk_aan_head: Uitslag) -> None:
        assert sha_niet_gelijk_aan_head.ci_draaide is False

    def test_de_melding_noemt_de_gepushte_sha(self, sha_niet_gelijk_aan_head: Uitslag) -> None:
        uitslag = sha_niet_gelijk_aan_head

        assert uitslag.punt_sha[:VOORVOEGSEL] in uitslag.uitvoer

    def test_de_melding_noemt_de_sha_van_head(self, sha_niet_gelijk_aan_head: Uitslag) -> None:
        uitslag = sha_niet_gelijk_aan_head

        assert uitslag.basis_sha[:VOORVOEGSEL] in uitslag.uitvoer


class TestEenPushWaarvanHeadGelijkIsGaatDoor:
    """(b) GROEN-vangnet: zonder deze is 'weiger elke develop-push' een geldige oplossing."""

    def test_de_hook_komt_voorbij_de_nieuwe_controle(self, sha_gelijk_aan_head: Uitslag) -> None:
        assert sha_gelijk_aan_head.ci_draaide is True


class TestEenZijtakPushWordtNietGeraakt:
    """(c) GROEN-vangnet: de nieuwe controle geldt alleen voor refs/heads/develop."""

    def test_de_hook_komt_voorbij_de_nieuwe_controle(
        self, zijtak_push_met_afwijkende_head: Uitslag
    ) -> None:
        assert zijtak_push_met_afwijkende_head.ci_draaide is True


class TestOokHetSnelleDocumentpadKrijgtDeControle:
    """(d) ROOD tegen 574026c8: de docs-detectie staat voor elke vergelijking met HEAD."""

    def test_de_hook_geeft_een_foutcode(self, md_sha_niet_gelijk_aan_head: Uitslag) -> None:
        assert md_sha_niet_gelijk_aan_head.returncode != 0

    def test_het_docs_pad_start_niet(self, md_sha_niet_gelijk_aan_head: Uitslag) -> None:
        assert md_sha_niet_gelijk_aan_head.docs_pad_draaide is False

    def test_de_melding_noemt_de_gepushte_sha(self, md_sha_niet_gelijk_aan_head: Uitslag) -> None:
        uitslag = md_sha_niet_gelijk_aan_head

        assert uitslag.punt_sha[:VOORVOEGSEL] in uitslag.uitvoer

    def test_de_melding_noemt_de_sha_van_head(self, md_sha_niet_gelijk_aan_head: Uitslag) -> None:
        uitslag = md_sha_niet_gelijk_aan_head

        assert uitslag.basis_sha[:VOORVOEGSEL] in uitslag.uitvoer
