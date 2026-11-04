"""Een geparkeerde push-aanvraag is zichtbaar, en alleen als hij echt nog moet landen.

WAAROM DIT BESTAAT
------------------
Sinds 2026-09-28 wacht een sessie na `push_gate.py request` drie minuten en gaat dan door.
Dat mag alleen als de aanvraag zichtbaar blijft. Gemeten op 2026-10-01 (taak 0 van
`docs/agent-briefs/generated/2026-10-01-sprint-dag-een-geparkeerde-push-ziet-niemand.md`,
commit 5a1aef5b) drie gaten:

1. `_toon_geparkeerd` toetst alleen BEREIKBAARHEID. Een merge waarvan beide ouders op develop
   staan maar die zelf nooit is gepusht (echt geval: cc3bfa3a) blijft eeuwig "wachtend".
2. Een aanvraag waarvan de sha niet te vinden is (status None) wordt STIL weggelaten.
3. `.claude/hooks/session-start.sh` toont de wachtrij niet, en had geen enkele test.

Besluit van de regie dat deze tests vastleggen:
- "geland" = bereikbaar vanuit de basis, OF een merge waarvan alle ouders bereikbaar zijn en
  waarvan `git diff <basis>...<sha>` leeg is;
- een onvindbare sha verschijnt LUID als niet-vast-te-stellen;
- de sessiestart-hook toont de geparkeerde aanvragen uit dezelfde bron als `status`.

HOE DIT MEET
------------
Geen enkele monkeypatch op wat hier gemeten wordt. Elke test bouwt een WEGWERP-git-repo in
`tmp_path`, schrijft daar het gatebestand, en draait het ECHTE script als subproces met
`cwd=<wegwerp-repo>`. `push_gate.py` bepaalt zijn gatebestand uit
`git rev-parse --git-common-dir` in de cwd, dus het gatebestand is vanzelf het bestand in de
wegwerp-repo: het echte gatebestand wordt nooit aangeraakt. Alle git-aanroepen krijgen een
omgeving ZONDER `GIT_*`-sleutels (anders wint `GIT_DIR` van de cwd, zie
`tests/architecture/test_a_test_never_runs_git_against_another_repo.py`).

De hook en `scripts/push_gate.py` worden als KOPIE in de wegwerp-repo gezet op hetzelfde
relatieve pad, zodat de hook zijn script vindt of hij nu via `$0` of via `--show-toplevel`
zoekt. De uitvoer van het gedraaide script wordt getoetst, niet de tekst ervan.

Wat deze tests NIET toetsen: het exacte uitvoerformaat van de hook (alleen sha-prefix en
sessienaam), de leeftijdsweergave, en de tijd die `gh pr view` in de hook kost.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_WORTEL = Path(__file__).resolve().parents[3]
_SCRIPT = _WORTEL / "scripts" / "push_gate.py"
_HOOK = _WORTEL / ".claude" / "hooks" / "session-start.sh"

AANVRAGER = "sessie-zichtbaarheidstest"
ONVINDBAAR = "d" * 40

# Het volledige pad, want `subprocess` kiest op Windows anders de WSL-bash uit System32
# (gemeten: "execvpe(/bin/bash) failed") in plaats van de bash die `shutil.which` vindt.
_BASH = shutil.which("bash") or "bash"


def _schone_omgeving() -> dict[str, str]:
    """De omgeving zonder `GIT_*`, zodat git de repo uit `cwd` kiest en niet uit `GIT_DIR`."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


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
        env=_schone_omgeving(),
    )
    return uit.stdout.strip()


def _commit(repo: Path, bestand: str, inhoud: str, bericht: str) -> str:
    (repo / bestand).write_text(inhoud, encoding="utf-8")
    _git(repo, "add", bestand)
    _git(repo, "commit", "-q", "-m", bericht)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    """Een wegwerp-repo met `refs/remotes/origin/develop` en vier soorten aanvraag-commits.

    Geschiedenis:  A - D1 - T   (T = origin/develop)
      GEWONE      = N, kind van T met een nieuw bestand            (1 ouder, niet bereikbaar)
      LEGE_MERGE  = merge --no-ff van T in D1                      (ouders D1 en T, tree == T)
      EIGEN_MERGE = dezelfde merge, met een extra bestand erbij    (conflictoplossing)
    """
    pad = tmp_path_factory.mktemp("geparkeerd-repo")
    hooks_leeg = tmp_path_factory.mktemp("geen-hooks")
    _git(pad, "init", "-q", "-b", "develop")
    _git(pad, "config", "core.hooksPath", str(hooks_leeg))
    _commit(pad, "a.txt", "a\n", "A")
    d1 = _commit(pad, "d1.txt", "d1\n", "D1")
    t = _commit(pad, "t.txt", "t\n", "T")
    _git(pad, "update-ref", "refs/remotes/origin/develop", t)

    _git(pad, "checkout", "-q", "--detach", d1)
    _git(pad, "merge", "-q", "--no-ff", "-m", "lege merge", t)
    lege_merge = _git(pad, "rev-parse", "HEAD")

    (pad / "oplossing.txt").write_text("conflictoplossing\n", encoding="utf-8")
    _git(pad, "add", "oplossing.txt")
    _git(pad, "commit", "-q", "--amend", "-m", "merge met eigen wijziging")
    eigen_merge = _git(pad, "rev-parse", "HEAD")

    _git(pad, "checkout", "-q", "--detach", t)
    gewone = _commit(pad, "n.txt", "nieuw\n", "N")
    _git(pad, "checkout", "-q", "develop")

    (pad / "scripts").mkdir()
    shutil.copy(_SCRIPT, pad / "scripts" / "push_gate.py")
    (pad / ".claude" / "hooks").mkdir(parents=True)
    shutil.copy(_HOOK, pad / ".claude" / "hooks" / "session-start.sh")
    return {
        "pad": pad,
        "lege_merge": lege_merge,
        "eigen_merge": eigen_merge,
        "gewone": gewone,
    }


def _zet_aanvraag(repo: Path, sha: str) -> None:
    """Schrijf een open aanvraag (zonder goedkeuring) in het gatebestand van de wegwerp-repo."""
    gate = repo / ".git" / "sanskritisetu-push-gate.json"
    wanneer = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    data = {
        "coordinator": None,
        "approved": {},
        "requested": {sha: {"session": AANVRAGER, "worktree": str(repo), "requested_at": wanneer}},
    }
    gate.write_text(json.dumps(data), encoding="utf-8")


def _status(repo: Path) -> str:
    uit = subprocess.run(
        [sys.executable, str(repo / "scripts" / "push_gate.py"), "status"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        env=_schone_omgeving(),
    )
    return uit.stdout


def _sessiestart(repo: Path) -> str:
    uit = subprocess.run(
        [_BASH, str(repo / ".claude" / "hooks" / "session-start.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        env=_schone_omgeving(),
    )
    return uit.stdout


def _pad(repo: dict[str, object]) -> Path:
    pad = repo["pad"]
    assert isinstance(pad, Path)
    return pad


def _sha(repo: dict[str, object], sleutel: str) -> str:
    sha = repo[sleutel]
    assert isinstance(sha, str)
    return sha


class TestDeSessiestartToontDeWachtrij:
    """(a) ROOD tegen 5a1aef5b: de hook kent het gatebestand niet."""

    def test_de_hook_toont_de_sha_van_een_geparkeerde_aanvraag(
        self, repo: dict[str, object]
    ) -> None:
        sha = _sha(repo, "gewone")
        _zet_aanvraag(_pad(repo), sha)

        assert sha[:12] in _sessiestart(_pad(repo))

    def test_de_hook_toont_wie_de_aanvraag_deed(self, repo: dict[str, object]) -> None:
        _zet_aanvraag(_pad(repo), _sha(repo, "gewone"))

        assert AANVRAGER in _sessiestart(_pad(repo))

    def test_de_hook_zwijgt_over_een_gelande_aanvraag(self, repo: dict[str, object]) -> None:
        """Vangnet: zonder deze is 'toon altijd iets' een geldige oplossing."""
        geland = _git(_pad(repo), "rev-parse", "refs/remotes/origin/develop")
        _zet_aanvraag(_pad(repo), geland)

        assert geland[:12] not in _sessiestart(_pad(repo))


class TestEenMergeZonderEigenInhoudIsGeland:
    def test_een_merge_met_gelande_ouders_en_lege_diff_staat_niet_in_status(
        self, repo: dict[str, object]
    ) -> None:
        """(b) ROOD tegen 5a1aef5b: bereikbaarheid alleen houdt deze merge eeuwig wachtend."""
        sha = _sha(repo, "lege_merge")
        _zet_aanvraag(_pad(repo), sha)

        assert sha[:12] not in _status(_pad(repo))

    def test_een_merge_met_een_eigen_wijziging_staat_wel_in_status(
        self, repo: dict[str, object]
    ) -> None:
        """(e) GROEN-vangnet: zonder deze is 'elke merge is geland' een geldige oplossing."""
        sha = _sha(repo, "eigen_merge")
        _zet_aanvraag(_pad(repo), sha)

        assert sha[:12] in _status(_pad(repo))


class TestEenEchteNietGelandeCommitBlijftZichtbaar:
    def test_een_gewone_commit_met_inhoud_staat_in_status(self, repo: dict[str, object]) -> None:
        """(d) GROEN-vangnet: zonder deze is 'toon niets' een geldige oplossing."""
        sha = _sha(repo, "gewone")
        _zet_aanvraag(_pad(repo), sha)

        assert sha[:12] in _status(_pad(repo))


class TestEenOnvindbareShaVerdwijntNietStil:
    def test_een_niet_bestaande_sha_staat_in_status(self, repo: dict[str, object]) -> None:
        """(c) ROOD tegen 5a1aef5b: status None wordt in `_toon_geparkeerd` weggelaten."""
        _zet_aanvraag(_pad(repo), ONVINDBAAR)

        assert ONVINDBAAR[:12] in _status(_pad(repo))

    def test_een_niet_bestaande_sha_heet_niet_vast_te_stellen(
        self, repo: dict[str, object]
    ) -> None:
        """Niet als vastgestelde achterstand presenteren: dat is een bewering zonder meting."""
        _zet_aanvraag(_pad(repo), ONVINDBAAR)

        assert "NIET VAST TE STELLEN" in _status(_pad(repo)).upper()
