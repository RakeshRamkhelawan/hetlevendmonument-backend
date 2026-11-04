"""Gereedschap voor mutatiebewijs. Gebruik dit; schrijf het niet opnieuw.

**Waarom dit bestaat, en waarom het GEREEDSCHAP is en geen regel.** Elke val hieronder stond al
als les in `.claude/skills/valkuilen/SKILL.md`, en is daarna alsnog opgetreden -- de heredoc-val
drie keer opgeschreven en in een nacht vier keer opnieuw gemaakt, het mutatiebewijs twee keer
ongeldig. Een les in proza voorkomt niets. Een functie die de val onmogelijk maakt wel.

Bewijs dat dit onderscheid echt is: `scripts/count_disabled_tests.py` is gereedschap en werkt;
"gebruik geen heredoc met escapes" is een regel en faalde vier keer op een avond.

**De vier vallen die dit dichtzet, elk met de meting die hem opleverde:**

1. **Een commando dat sowieso faalt meldt ROOD en leest als bewijs.** Gemeten 2026-09-03:
   npm via Python's subprocess laat `vitest-canvas-mock` omvallen ("Vitest failed to find the
   current suite"), dus elk van de drie mutaties leek betrapt terwijl geen enkele assertie had
   gedraaid. De tegenrichting werd ook rood en verried het. `verify_red` en `verify_green` eisen
   daarom BEWIJS dat er tests zijn uitgevoerd, niet alleen een exitcode.

2. **Een anker met LF vindt niets in een bestand met CRLF.** Gemeten dezelfde nacht: vier ankers
   meldden "niet gevonden", en later meldde een guard GROEN omdat de mutatie het bestand niet
   raakte. Een mutatie die niets muteert is niet te onderscheiden van een guard die werkt.
   `replace_anchor` past het regeleinde aan het doelbestand aan en eist dat het anker UNIEK is.

3. **Een script dat sterft laat de repo GEMUTEERD achter.** Gemeten: een tijdslimiet halverwege
   liet een testbestand met een verwijderde decorator staan, en bij een tweede poging faalde op
   Windows het TERUGZETTEN zelf (`WinError 1224`, OneDrive houdt een sectie open). `restored`
   schrijft atomair, probeert het drie keer, en verifieert de SHA-256 -- en stopt het proces als
   die afwijkt in plaats van door te gaan op een vervuilde boom.

4. **Twee muterende processen in dezelfde worktree.** Gemeten: twee reviewagenten in een worktree
   zagen elkaars mutaties; een van hen moest een besmet resultaat weggooien. `assert_sole_writer`
   legt een lockbestand neer zodat de tweede het meteen weet.

Gebruik:

    from scripts.mutation_harness import Mutation, replace_anchor, verify_red, verify_green

    with Mutation("src/pad/naar/module.py") as m:            # kopie + gegarandeerd herstel
        m.write(replace_anchor(m.text, OUD, NIEUW))          # regeleinde-agnostisch, uniek
        verify_red(["python", "-m", "pytest", TEST, "-q"])    # faalt als er NIETS is gedraaid
    verify_green(["python", "-m", "pytest", TEST, "-q"])     # tegenrichting, na herstel
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from types import TracebackType


class MutationError(RuntimeError):
    """Het bewijs is ongeldig. Nooit onderdrukken: dan bewijst de rest ook niets."""


def _atomic_write(path: Path, data: bytes) -> None:
    """Schrijf via een tijdelijk bestand in dezelfde map; drie pogingen tegen de OneDrive-lock."""
    tmp = path.with_suffix(path.suffix + ".mutation-tmp")
    laatste: OSError | None = None
    for poging in range(3):
        try:
            tmp.write_bytes(data)
            os.replace(tmp, path)
            return
        except OSError as exc:  # OneDrive/virusscanner houdt een mapped section open
            laatste = exc
            time.sleep(0.5 * (poging + 1))
    raise MutationError(f"schrijven naar {path} mislukt na 3 pogingen: {laatste}")


def replace_anchor(text: str, old: str, new: str, *, count: int = 1) -> str:
    """Vervang `old` door `new`, met het regeleinde van `text` en een UNIEK anker.

    Twee eisen, en beide komen uit een gemeten fout:
    - het regeleinde van `old`/`new` wordt aan `text` aangepast, want een LF-anker vindt niets in
      een CRLF-bestand;
    - het anker moet exact `count` keer voorkomen. Nul betekent dat de mutatie niets doet en de
      test daarna ten onrechte groen meldt; meer dan een betekent dat je niet weet wat je muteert.
    """
    nl = "\r\n" if "\r\n" in text else "\n"
    if nl != "\n":
        old, new = old.replace("\n", nl), new.replace("\n", nl)
    gevonden = text.count(old)
    if gevonden != count:
        raise MutationError(
            f"anker komt {gevonden}x voor, verwacht {count}x. "
            f"Bij 0 muteert dit niets en meldt de test daarna GROEN zonder betekenis. "
            f"Anker begint met: {old[:70]!r}"
        )
    return text.replace(old, new, count)


def _run(cmd: list[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    # encoding expliciet: op Windows gebruikt subprocess anders cp1252 en klapt het om op
    # UTF-8-uitvoer van vitest/pytest (gemeten: UnicodeDecodeError op byte 0x9d).
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", check=False
    )


#: Bewijs dat een testrunner werkelijk tests heeft UITGEVOERD. Zonder deze controle is een
#: exitcode van een kapotte opstelling niet te onderscheiden van een betrapte mutatie.
_RAN_TESTS = re.compile(
    r"\b\d+ (passed|failed)\b"  # pytest
    r"|Tests\s+\d+ (passed|failed)"  # vitest
    r"|\b\d+ (passed|failed)\b.*\bin \d",
    re.I,
)
_DID_NOT_RUN = re.compile(
    r"no tests ran|Tests\s+no tests|collected 0 items|failed to find the current suite", re.I
)


def _assert_actually_ran(res: subprocess.CompletedProcess[str], cmd: list[str]) -> str:
    uit = (res.stdout or "") + "\n" + (res.stderr or "")
    if _DID_NOT_RUN.search(uit) or not _RAN_TESTS.search(uit):
        raise MutationError(
            "de testrunner heeft GEEN tests uitgevoerd, dus de exitcode zegt niets over de "
            f"mutatie.\ncommando: {' '.join(cmd)}\nlaatste regels:\n"
            + "\n".join(uit.strip().splitlines()[-8:])
        )
    return uit


def verify_red(cmd: list[str], *, cwd: Path | None = None) -> str:
    """Eis dat het commando FAALT en dat er echt tests hebben gedraaid."""
    res = _run(cmd, cwd)
    uit = _assert_actually_ran(res, cmd)
    if res.returncode == 0:
        raise MutationError(
            "verwacht ROOD maar het commando slaagde -- de guard betrapt deze mutatie niet.\n"
            + "\n".join(uit.strip().splitlines()[-6:])
        )
    return uit


def verify_green(cmd: list[str], *, cwd: Path | None = None) -> str:
    """Eis dat het commando SLAAGT en dat er echt tests hebben gedraaid.

    Deze helft is dragend: zonder haar is "weiger alles" een geldige implementatie.
    """
    res = _run(cmd, cwd)
    uit = _assert_actually_ran(res, cmd)
    if res.returncode != 0:
        raise MutationError(
            "verwacht GROEN maar het commando faalde -- de tegenrichting is stuk.\n"
            + "\n".join(uit.strip().splitlines()[-6:])
        )
    return uit


def eis_vrije_testronde() -> None:
    """Weiger te muteren zolang de volledige testronde draait.

    **Waarom dit hier staat en niet alleen in een regel.** CLAUDE.md verbiedt sinds
    2026-09-20 een reviewagent of een mutatietest naast de testronde, met de meting erbij
    (exit 124). Op 2026-09-25 liep een sessie er toch in -- dezelfde sessie die die regel die
    dag nog aan iemand anders had uitgelegd. Resultaat: twee workercrashes (`node down`) en
    28m17 in plaats van 17m12, dus een NIET-meting die opnieuw moest.

    Dat is geen kennisprobleem. Het slot bestond, was machinebreed en leesbaar vanuit elke
    worktree -- alleen raadpleegde niemand buiten de testronde het ooit. Zelfde vorm als de
    impact-analyse die bestond maar nergens werd aangeroepen: het gereedschap lag er, de
    bedrading ontbrak.

    **De grens van wat dit dekt, eerlijk.** Dit vangt mutaties. Het vangt NIET elk zwaar
    proces: de niet-meting van 2026-09-25 kwam mede door losse `python -c`-aanroepen die de
    applicatie laadden, en die komen hier nooit langs. De bredere regel -- een meting is pas
    een meting als je kunt zeggen wat er naast draaide -- blijft dus mensenwerk. Dit dekt het
    geval dat aantoonbaar tweemaal is misgegaan.
    """
    slot = Path(__file__).resolve().parent
    if str(slot) not in sys.path:
        sys.path.insert(0, str(slot))
    try:
        import testpoort_slot
    except ImportError:  # pragma: no cover -- het slot hoort er te zijn
        return
    gegevens = testpoort_slot.houder()
    if gegevens is None:
        return
    raise MutationError(
        "De volledige testronde DRAAIT: "
        f"{testpoort_slot.beschrijf_houder(gegevens)}. "
        "Muteren naast een lopende ronde maakt er een NIET-meting van -- gemeten "
        "2026-09-20 (exit 124) en opnieuw 2026-09-25 (twee workercrashes, 28m17 tegen "
        "17m12 schoon). Wacht tot hij klaar is, of neem zelf het slot als de ronde vastligt."
    )


def assert_sole_writer(worktree: Path, wie: str) -> None:
    """Weiger te muteren als een ander proces dat in deze worktree al doet.

    Gemeten 2026-09-03: twee reviewagenten in een worktree zagen elkaars mutaties, en een van
    beiden moest een resultaat weggooien omdat het bestand drie keer van hash veranderde.
    """
    lock = worktree / ".mutation-lock"
    if lock.exists():
        raise MutationError(
            f"{lock} bestaat al ({lock.read_text(encoding='utf-8', errors='replace').strip()}). "
            "Een ander proces muteert deze worktree; maak een eigen `git worktree` in C:/tmp."
        )
    lock.write_text(f"{wie} pid={os.getpid()} {time.strftime('%Y-%m-%d %H:%M:%S')}\n", "utf-8")


class Mutation:
    """Contextmanager die een bestand muteert en het GEGARANDEERD terugzet.

    Bij het verlaten wordt de SHA-256 vergeleken. Wijkt die af, dan stopt het proces met code 2
    in plaats van door te gaan -- een volgende meting op een vervuilde boom is waardeloos en
    misleidend.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.original: bytes = b""
        self.digest: str = ""

    @property
    def text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def write(self, nieuw: str) -> None:
        _atomic_write(self.path, nieuw.encode("utf-8"))

    def __enter__(self) -> Mutation:
        eis_vrije_testronde()
        self.original = self.path.read_bytes()
        self.digest = hashlib.sha256(self.original).hexdigest()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _atomic_write(self.path, self.original)
        na = hashlib.sha256(self.path.read_bytes()).hexdigest()
        if na != self.digest:
            print(
                f"TERUGZETTEN MISLUKT voor {self.path}: {na[:16]} != {self.digest[:16]}. "
                "Gestopt om te voorkomen dat de volgende meting op een vervuilde boom draait.",
                file=sys.stderr,
            )
            sys.exit(2)
