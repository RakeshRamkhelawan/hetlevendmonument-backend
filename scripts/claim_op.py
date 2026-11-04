"""Gedeelde, git-onafhankelijke claim-state voor ADR-036 OP-nummers (2026-09-10).

**Waarom dit bestand bestaat.** Meerdere Claude Code-sessies werken tegelijk in
aparte `git worktree`s aan losse OP-nummers. Elke worktree heeft zijn EIGEN kopie
van elk getrackt bestand -- inclusief het ADR-036-register zelf -- dus een
claim-aantekening IN het register wordt pas voor een andere sessie zichtbaar na
een commit, en een commit op hetzelfde bestand vanuit twee sessies is precies het
commit-race-scenario dat CLAUDE.md's worktree-regel probeert te voorkomen.
Gemeten vandaag: een sessie zag haar EIGEN commit op haar eigen tak als "een agent
die ik niet ken" opduiken, puur omdat de claim-aantekening in het gedeelde
register stond en de andere sessie het register op een ander moment had gelezen.

**Waarom dit WEL werkt zonder commits.** De state leeft in de GEDEELDE `.git`-map
(`git rev-parse --git-common-dir`) -- letterlijk hetzelfde fysieke bestand ongeacht
vanuit welke worktree je dit script aanroept. Dat is exact het mechanisme waarmee
git hooks al gedeeld worden tussen alle worktrees van deze repo (geverifieerd
2026-09-10: `git rev-parse --git-path hooks` vanuit een worktree wijst naar de
hoofdmap se `.git/hooks`, niet naar een eigen kopie). Een schrijf vanuit worktree A
is binnen milliseconden zichtbaar voor worktree B -- geen commit, geen merge, geen
push. Het bestand zit in `.git/`, dus het kan per definitie nooit getrackt of
gepusht worden.

**Wat dit NIET is.** Geen vervanging van de ADR-036-registerrij zelf (die blijft de
inhoudelijke bron van waarheid over een bevinding). Dit is uitsluitend het
"wie is hier nu mee bezig"-signaal, zodat twee sessies niet onafhankelijk aan
hetzelfde nummer beginnen. Ook geen harde afdwinging op OS-niveau: een sessie die
dit script nooit aanroept, wordt niet tegengehouden. De verplichting staat in
CLAUDE.md (geladen door elke sessie); dit script maakt het naleven ervan een
kwestie van 1 commando in plaats van het handmatig doorzoeken van een 700-regels
register.

Gebruik:
    python scripts/claim_op.py check OP-202
    python scripts/claim_op.py claim OP-202 OP-216 --session <naam> --branch <tak> [--note "..."]
    python scripts/claim_op.py release OP-202 --session <naam>
    python scripts/claim_op.py list

<naam> is de sessienaam die `ListAgents` toont ("This session is ..."). `claim`
weigert (exit 1) een nummer dat een ANDERE sessie al vasthoudt; dezelfde sessie mag
haar eigen claim opnieuw zetten (bijv. om branch/note bij te werken). Stale claims
(sessie afgesloten zonder `release`) worden niet automatisch opgeruimd -- `list`
toont de `claimed_at`-datum, en een mens (of een andere sessie, na het navragen bij
Rakesh) kan een duidelijk verouderde claim met `release` weghalen.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def _git_common_dir() -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    )
    path = Path(completed.stdout.strip())
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


CLAIMS_PATH = _git_common_dir() / "sanskritisetu-active-work.json"
LOCK_PATH = CLAIMS_PATH.with_suffix(".lock")

#: Hoe oud een claim mag worden voor `list` en `check` erover beginnen. Bewust GEEN
#: automatische opruiming: stil verwijderen vervangt het ene onbetrouwbare signaal door
#: het andere. Zie CLAUDE.md, sectie "Werken met meerdere sessies tegelijk".
VEROUDERD_NA_DAGEN = 2


def _worktree_root() -> str:
    """De werkmap van deze worktree -- de DUURZAME identiteit van een claim.

    Waarom niet de sessienaam (ADR-036 OP-241, gemeten 2026-09-14): die verandert bij een
    resume. Een sessie heette `sanskritisetu-org-93` en kwam terug als `org-03`, waarna een
    andere sessie haar LEVENDE claim voor verweesd aanzag en bijna vrijgaf. Een worktreepad
    overleeft een resume, een hernoeming en een herstart van de machine.
    """
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return str(Path(completed.stdout.strip()).resolve())
    except (subprocess.CalledProcessError, OSError):
        return ""


def _is_van_mij(info: dict, session: str, worktree: str) -> bool:
    """Een claim is van jou als de SESSIENAAM of de WERKMAP overeenkomt.

    Twee ingangen met opzet: de naam vangt het geval dat je vanuit een andere map werkt,
    de werkmap vangt het geval dat je naam is veranderd. Oude claims zonder `worktree`
    (geschreven voor 2026-09-15) hebben een lege waarde en vallen terug op de naam.
    """
    if info.get("session") == session:
        return True
    opgeslagen = info.get("worktree", "")
    return bool(opgeslagen) and bool(worktree) and opgeslagen == worktree


def _ouderdom(info: dict) -> str:
    """Leesbare ouderdom, met een waarschuwing zodra een claim lang blijft staan."""
    try:
        sinds = datetime.fromisoformat(info["claimed_at"])
    except (KeyError, ValueError):
        return ""
    dagen = (datetime.now(timezone.utc) - sinds).days
    if dagen >= VEROUDERD_NA_DAGEN:
        return f" [{dagen} dagen oud -- NAVRAGEN of dit nog loopt]"
    return ""


@contextmanager
def _locked(timeout: float = 5.0):
    """Simpele exclusieve lock via atomair `O_CREAT|O_EXCL`.

    Voldoende voor een handvol AI-sessies die elk hooguit eens per paar minuten
    schrijven -- geen zwaardere lock-library nodig. Ruimt zichzelf altijd op, ook
    bij een exception in de `with`-body.
    """
    deadline = time.monotonic() + timeout
    fd = None
    while fd is None:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Kon de lock niet krijgen binnen {timeout}s -- {LOCK_PATH} "
                    "bestaat al. Verwijder hem handmatig als een eerdere aanroep "
                    "is gecrasht (dat laat een wees-lock achter)."
                ) from None
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        LOCK_PATH.unlink(missing_ok=True)


def _read() -> dict:
    if not CLAIMS_PATH.exists():
        return {"claims": {}}
    return json.loads(CLAIMS_PATH.read_text(encoding="utf-8"))


def _write(data: dict) -> None:
    CLAIMS_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cmd_claim(args: argparse.Namespace) -> int:
    with _locked():
        data = _read()
        worktree = _worktree_root()
        conflicts = [
            (op, data["claims"][op])
            for op in args.op
            if op in data["claims"]
            and not _is_van_mij(data["claims"][op], args.session, worktree)
        ]
        if conflicts:
            print("GEWEIGERD -- al geclaimd door een andere sessie:")
            for op, existing in conflicts:
                print(
                    f"  {op}: sessie={existing['session']} "
                    f"branch={existing.get('branch', '?')} "
                    f"sinds={existing['claimed_at']}"
                )
            return 1
        now = datetime.now(timezone.utc).isoformat()
        for op in args.op:
            data["claims"][op] = {
                "session": args.session,
                "worktree": worktree,
                "branch": args.branch or "",
                "note": args.note or "",
                "claimed_at": now,
            }
        _write(data)
    print(f"Geclaimd: {', '.join(args.op)} door {args.session}")
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    with _locked():
        data = _read()
        worktree = _worktree_root()
        not_mine = [
            op
            for op in args.op
            if op in data["claims"]
            and not _is_van_mij(data["claims"][op], args.session, worktree)
        ]
        if not_mine:
            print(f"GEWEIGERD -- niet jouw claim: {', '.join(not_mine)}")
            return 1
        for op in args.op:
            data["claims"].pop(op, None)
        _write(data)
    print(f"Vrijgegeven: {', '.join(args.op)}")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    data = _read()
    if not data["claims"]:
        print("Geen actieve claims.")
        return 0
    for op, info in sorted(data["claims"].items()):
        print(
            f"{op}: sessie={info['session']} branch={info.get('branch', '?')} "
            f"werkmap={info.get('worktree', '-')} "
            f"sinds={info['claimed_at']}{_ouderdom(info)} note={info.get('note', '')}"
        )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    data = _read()
    existing = data["claims"].get(args.op[0])
    if existing:
        print(
            f"GECLAIMD door {existing['session']} sinds {existing['claimed_at']}"
            f"{_ouderdom(existing)} (branch={existing.get('branch', '?')}, "
            f"werkmap={existing.get('worktree', '-')})"
        )
        return 1
    print("VRIJ")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_claim = sub.add_parser("claim", help="Claim een of meer OP-nummers")
    p_claim.add_argument("op", nargs="+")
    p_claim.add_argument("--session", required=True)
    p_claim.add_argument("--branch")
    p_claim.add_argument("--note")
    p_claim.set_defaults(func=cmd_claim)

    p_release = sub.add_parser("release", help="Geef een of meer OP-nummers vrij")
    p_release.add_argument("op", nargs="+")
    p_release.add_argument("--session", required=True)
    p_release.set_defaults(func=cmd_release)

    p_list = sub.add_parser("list", help="Toon alle actieve claims")
    p_list.set_defaults(func=cmd_list)

    p_check = sub.add_parser("check", help="Is dit ene OP-nummer vrij?")
    p_check.add_argument("op", nargs=1)
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
