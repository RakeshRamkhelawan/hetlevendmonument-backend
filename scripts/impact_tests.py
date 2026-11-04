"""Welke tests raakt deze wijziging? Selecteert op IMPORT, niet op een los woord.

**Waarom dit bestaat (gemeten 2026-09-24/25).** Op de tak `iter/genuine-implementations`
stond een test 45 commits lang rood zonder dat iemand het wist. Het verloop, exact te dateren:
commit 8d936380 voegde de test en de implementatie samen toe, en toen was hij groen. Commit
87ea4a3a verving daarna een open lijst door een begrensde `deque` -- een goede reparatie, want
die stopt een geheugenlek -- en liet de assertie `== []` staan. Een lege `deque` is niet gelijk
aan een lege lijst, dus vanaf dat moment was de test rood, en dat bleef zo tot de merge.

**Geen typechecker vangt dit.** Zelf nagemeten op precies deze vergelijking:

    python -m mypy --strict-equality <bestand>   ->  Success: no issues found
    python -m pyright <bestand> (strict + reportUnnecessaryComparison)  ->  0 errors

Beide containers vergelijken via `object`, dus formeel overlappen de types. Deze fout is
alleen te vinden door de test te DRAAIEN.

**En het gereedschap ontbrak niet -- de stap werd overgeslagen.** De impact-analyse uit
`.claude/skills/sprint-workflow` selecteerde die test gewoon. Gemeten op het gewijzigde
bestand: 30 testbestanden, 403 tests, 64 seconden, en de failure kwam eruit. Vier seconden
als je alleen de echte importeurs draait. Vier seconden aan de commit tegenover twintig
minuten bij de merge -- of 45 commits lang niemand die het weet. De pre-commit hook draaide
tot vandaag NUL tests, en de volledige testpoort draait alleen bij een push naar `develop`;
een `iter/`-tak kreeg dus geen enkel testsignaal tot het moment van samenvoegen.

**Waarom op import en niet op het woord.** De oude vorm zocht de BESTANDSNAAM als tekst. Voor
`src/domains/memory/observability.py` leverde dat 30 treffers op, waarvan er 2 de module echt
importeren; de andere 28 bevatten toevallig het woord "observability". Dat is niet alleen
verspilde tijd: het is dezelfde faalvorm die dit project overal bestrijdt -- tekst toetsen waar
structuur hoort.

**De eerlijke grens van deze selectie.** Statisch zoeken naar importregels vindt een test die
de module NOEMT. Het vindt NIET de test die de code indirect raakt via een derde module die
hem doorexporteert. Dat is een echte blinde vlek en geen detail: daarvoor bestaat
dekkingsgebaseerde selectie (`pytest-testmon`), die meet wat een test tijdens het draaien
werkelijk aanraakt. Dit script is de goedkope eerste laag, niet het eindstation. De volledige
testpoort bij een push naar `develop` blijft het vangnet.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Alleen wijzigingen hieronder kunnen productietests raken.
BRONMAPPEN = ("src/", "scripts/")

#: Alleen tests hieronder worden door de commitpoort bewaakt.
#: Moet EXACT overeenkomen met de vier mappen in de pre-push testpoort:
#:   pytest tests/unit tests/architecture tests/core tests/contracts
#: Bewaakt door tests/architecture/test_commitpoort_en_pushpoort_dekken_hetzelfde.py
DOELMAPPEN = ("tests/unit/", "tests/architecture/", "tests/core/", "tests/contracts/")


def _git(args: list[str]) -> str:
    """Draai git en geef stdout terug; een fout wordt een lege uitvoer.

    Zonder pijpen, om dezelfde reden als in `mcp-server/tools/coordination.py::_git`: op
    Windows kan `subprocess.run` na een timeout oneindig blijven wachten in zijn eigen
    herstelpad. Hier is de kans klein, maar een hook die hangt is erger dan een hook die faalt.
    """
    try:
        uit = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    return uit.stdout.decode("utf-8", errors="replace")


def modulenaam(pad: str) -> str:
    """`src/domains/memory/observability.py` -> `src.domains.memory.observability`."""
    return pad.removesuffix(".py").replace("/", ".").replace("\\", ".")


def _deel(pad: str) -> tuple[str, str, str]:
    """De module, zijn pakket en zijn eigen naam."""
    module = modulenaam(pad)
    ouder, _, naam = module.rpartition(".")
    return module, ouder, naam


def _kale_naam_import(inhoud: str, naam: str) -> bool:
    """Wordt deze module bij zijn KALE naam geimporteerd?

    **Waarom dit nodig is, gevonden bij het eerste echte gebruik van dit script.** Een
    wijziging in `scripts/mutation_harness.py` selecteerde NUL tests, terwijl
    `tests/architecture/test_het_mutatieharnas_wijkt_voor_de_testronde.py` hem wel degelijk
    gebruikt. De reden: vijf testbestanden zetten `scripts/` op `sys.path` en schrijven dan
    `import mutation_harness`. Het puntpad `scripts.mutation_harness` komt in die bestanden
    nooit voor, dus de selectie zag niets.

    Dat is geen theoretische blinde vlek maar een gemeten onder-selectie op het pad waarvoor
    dit gereedschap gemaakt is. Het blijft een IMPORTREGEL die we toetsen, niet een los woord:
    `import <naam>` of `from <naam> import`.
    """
    for regel in inhoud.splitlines():
        gestript = regel.split("#", 1)[0].strip()
        if gestript.startswith(f"from {naam} import"):
            return True
        if gestript.startswith("import "):
            for stuk in gestript.removeprefix("import ").split(","):
                if stuk.strip().split(" as ")[0].strip() == naam:
                    return True
    return False


def _importeert(inhoud: str, module: str, ouder: str, naam: str) -> bool:
    """Haalt deze testtekst die module binnen?

    Twee vormen, en meer niet -- ingewikkelde selectielogica is precies waar fouten zich
    verstoppen:

      1. de VOLLEDIGE modulenaam komt voor. Dat dekt `import src.a.b` en
         `from src.a.b import X` in een keer.
      2. een regel begint met `from <pakket> import` EN noemt de naam van de module. Dat
         dekt `from src.a import b` en `from src.a import x, b`.

    Wat het bewust NIET dekt: het losse WOORD. Precies daar ging de oude vorm mis -- 28 van
    de 30 treffers noemden alleen het woord "observability" in proza of een variabelenaam.
    """
    if module in inhoud:
        return True
    if not ouder:
        return False
    aanhef = f"from {ouder} import"
    for regel in inhoud.splitlines():
        gestript = regel.strip()
        if not gestript.startswith(aanhef):
            continue
        # Het commentaar eraf, en dan de INGEVOERDE NAMEN los vergelijken. Zonder dit
        # telde `from src.a import store  # observability volgt later` mee -- gevonden door
        # de eigen tegenrichting-test, voordat dit gereedschap ooit een commit zag.
        rest = gestript[len(aanhef) :].split("#", 1)[0]
        namen = {stuk.strip().removeprefix("(").strip().split(" as ")[0].strip(" )")
                 for stuk in rest.split(",")}
        if naam in namen:
            return True
    return False


def _tekst_constanten_buiten_docstrings(bron: str) -> list[str]:
    """Elke stringliteral die als WAARDE in code staat -- docstrings niet meegerekend.

    Hier zit het hele verschil tussen bewaken en ruis produceren. Gemeten over de 46
    testbestanden die `CLAUDE.md` noemen: 37 noemen hem alleen in een docstring of een
    toelichting ("CLAUDE.md's kernbeslissingen-tabel claimde ..."), en slechts 9 LEZEN hem
    echt. Platte tekstmatching zou dus 80% ruis geven -- en de brief die deze taak opdroeg
    schreef zelf voor dat bij meer dan de helft ruis een andere oplossing beter is.

    Een stringliteral die geen docstring is, IS een structureel signaal: daar doet de test
    iets met dat pad. Daarmee blijft deze selectie hetzelfde principe volgen als bij Python
    -- structuur toetsen, geen los woord zoeken -- ook al bestaat er voor een markdownbestand
    geen import.
    """
    try:
        boom = ast.parse(bron)
    except (SyntaxError, ValueError):
        return []
    docstrings: set[int] = set()
    for knoop in ast.walk(boom):
        if isinstance(knoop, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            eerste = knoop.body[0] if knoop.body else None
            if (
                isinstance(eerste, ast.Expr)
                and isinstance(eerste.value, ast.Constant)
                and isinstance(eerste.value.value, str)
            ):
                docstrings.add(id(eerste.value))
    return [
        knoop.value
        for knoop in ast.walk(boom)
        if isinstance(knoop, ast.Constant)
        and isinstance(knoop.value, str)
        and id(knoop) not in docstrings
    ]


def _leest_dit_pad(bron: str, pad: str) -> bool:
    """Doet deze test iets met dit bestand?

    Twee schrijfwijzen tellen: het volledige pad (`".claude/rules/quality-gates.md"`) en de
    kale bestandsnaam (`REPO_ROOT / "CLAUDE.md"`). De tweede is ruimer en dat is met opzet:
    een gemiste test is een test die niet draait, en over-selectie kost alleen tijd.
    """
    basisnaam = pad.rsplit("/", 1)[-1]
    if pad not in bron and basisnaam not in bron:
        return False  # goedkope voorfiltering -- AST over 1960 bestanden is te traag
    for waarde in _tekst_constanten_buiten_docstrings(bron):
        # EXACT, niet "bevat". Gemeten met de losse vorm: een wijziging in de
        # hoofd-`README.md` selecteerde ook `test_compliance_claims_match_the_code.py`, die
        # `docs/compliance/soc2/README.md` leest -- een ANDER bestand met dezelfde naam.
        # Over-selectie kost alleen tijd, maar een selectie die het verkeerde bestand
        # aanwijst ondermijnt het vertrouwen in de hele stap.
        # De achtervoegselregel geldt ALLEEN voor een pad met een map erin. Bij een bestand
        # in de hoofdmap is `pad` gelijk aan de basisnaam, en dan zou `endswith("/" + pad)`
        # elk gelijknamig bestand in elke submap meenemen -- precies de valse treffer die de
        # tegenrichting-test betrapte (`docs/compliance/soc2/README.md` bij een wijziging in
        # de hoofd-README).
        if waarde in (pad, basisnaam) or ("/" in pad and waarde.endswith("/" + pad)):
            return True
    return False


def _pytest_uitgesloten() -> tuple[frozenset[str], frozenset[str]]:
    """Paden en basename-patronen die pytest zelf overslaat.

    Leest pyproject.toml als enige bron van waarheid, zodat een nieuwe --ignore= of
    norecursedirs-entry automatisch geldt voor de commitpoort.

    Geeft (ignore_paden, norecurse_basenames):
    - ignore_paden: prefixen uit --ignore= in addopts
    - norecurse_basenames: basenames uit norecursedirs (geen schuine streep erin)
    """
    try:
        with (REPO_ROOT / "pyproject.toml").open("rb") as _f:
            cfg = tomllib.load(_f).get("tool", {}).get("pytest", {}).get("ini_options", {})
    except Exception:
        return frozenset(), frozenset()

    addopts = cfg.get("addopts", [])
    if isinstance(addopts, str):
        addopts = addopts.split()
    ignore_paden: set[str] = set()
    for opt in addopts:
        if isinstance(opt, str) and opt.startswith("--ignore="):
            ignore_paden.add(opt.removeprefix("--ignore=").replace("\\", "/"))

    norecurse = frozenset(d for d in cfg.get("norecursedirs", []) if "/" not in d)
    return frozenset(ignore_paden), norecurse


def _testbestanden() -> list[str]:
    """Alle testbestanden in de mappen die de blokkerende pushpoort dekt.

    Beperkt tot DOELMAPPEN zodat de commitpoort en de pushpoort hetzelfde oppervlak
    bewaken. Gemeten 2026-09-28: zonder deze beperking trok een wijziging in
    validators.py ook tests/e2e/ mee, die de pushpoort nooit eist -- een pre-existing
    e2e-failure blokkeerde dan een volledig groene commit.

    OOK de nog niet getrackte: `git ls-files` alleen toont een vers aangemaakt
    testbestand niet, en dat is het moment waarop je hem het hardst nodig hebt.

    Paden die pytest zou overslaan (--ignore=, norecursedirs) worden hier ook
    uitgesloten -- anders overrulet een expliciete bestandsnaam die uitsluiting.
    Gemeten 2026-09-30: tests/unit/temp_disabled/ liep door en kostte 6 minuten.
    """
    ignore_paden, norecurse = _pytest_uitgesloten()

    regels: list[str] = []
    for doelmap in DOELMAPPEN:
        regels += _git(["ls-files", doelmap]).splitlines()
        regels += _git(["ls-files", "--others", "--exclude-standard", doelmap]).splitlines()

    resultaat: list[str] = []
    for regel in regels:
        pad = regel.strip().replace("\\", "/")
        if not pad.endswith(".py"):
            continue
        # Filter --ignore= paden (prefix-check)
        if any(pad.startswith(igp + "/") or pad == igp for igp in ignore_paden):
            continue
        # Filter norecursedirs-basenames op mapcomponenten (niet het bestandsdeel zelf)
        mappen = pad.split("/")[:-1]
        if any(deel in norecurse for deel in mappen):
            continue
        resultaat.append(pad)

    return sorted(set(resultaat))


def geraakte_tests(gewijzigd: list[str]) -> list[str]:
    """De testbestanden die een van deze gewijzigde bronbestanden importeren.

    Een gewijzigd TESTbestand zit er altijd zelf bij: wie een test aanpast, draait hem.
    """
    gekozen: set[str] = set()
    bronnen: list[tuple[str, str, str]] = []
    #: Elk gewijzigd bestand, ongeacht extensie. Een instructiebestand als `CLAUDE.md` kent
    #: geen import, maar wordt wel door bewakers GELEZEN -- gemeten: 9 van de 46 tests die
    #: hem noemen doen dat in code. Zonder deze lijst selecteerde een wijziging daarin NUL
    #: tests terwijl de hook wel "alle checks geslaagd" meldde: een valse geruststelling.
    paden: list[str] = []

    for pad in gewijzigd:
        genormaliseerd = pad.replace("\\", "/").strip()
        if not genormaliseerd:
            continue
        paden.append(genormaliseerd)
        if not genormaliseerd.endswith(".py"):
            continue
        if any(genormaliseerd.startswith(m) for m in DOELMAPPEN):
            gekozen.add(genormaliseerd)
        elif genormaliseerd.startswith(BRONMAPPEN):
            bronnen.append(_deel(genormaliseerd))

    if bronnen or paden:
        for test in _testbestanden():
            try:
                inhoud = (REPO_ROOT / test).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(
                _importeert(inhoud, *bron)
                # Een module direct onder `scripts/` wordt in tests bij zijn kale naam
                # geimporteerd, na een sys.path-insert. Zie `_kale_naam_import`.
                or (bron[1] == "scripts" and _kale_naam_import(inhoud, bron[2]))
                for bron in bronnen
            ) or any(_leest_dit_pad(inhoud, pad) for pad in paden):
                gekozen.add(test)

    return sorted(gekozen)


def _merge_bezig() -> bool:
    """Is er een merge onderweg (bestaat MERGE_HEAD)?"""
    try:
        uit = subprocess.run(
            ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"],
            cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return uit.returncode == 0


def _gewijzigd_uit_git(modus: str, bereik: str | None) -> list[str]:
    if modus == "staged":
        # Bij een merge toetst de selectie de DOORSNEDE: bestanden die afwijken van HEAD EN van
        # MERGE_HEAD. Dat is wat de merge zelf toevoegt (conflictoplossingen, bestanden die aan
        # beide kanten zijn gewijzigd); wat maar van een kant komt, heeft op zijn eigen tak al zijn
        # toetsing gehad. Het verschil met alleen MERGE_HEAD was niet genoeg: een kleine tak in
        # een grote stand verschilt van MERGE_HEAD in alles wat de stand al had (gemeten
        # 2026-10-22: 567 testbestanden). Zonder merge blijft het verschil met HEAD.
        if _merge_bezig():
            basis = ["--cached", "--name-only", "--diff-filter=ACMRT"]
            met_head = set(_git(["diff", *basis, "HEAD"]).splitlines())
            met_merge_head = set(_git(["diff", *basis, "MERGE_HEAD"]).splitlines())
            return sorted(p.strip() for p in met_head & met_merge_head if p.strip())
        uit = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMRT"])
    else:
        if not bereik:
            return []
        uit = _git(["diff", "--name-only", "--diff-filter=ACMRT", bereik])
    return [r.strip() for r in uit.splitlines() if r.strip()]


def main() -> int:
    ontleder = argparse.ArgumentParser(description=__doc__)
    groep = ontleder.add_mutually_exclusive_group(required=True)
    groep.add_argument("--staged", action="store_true", help="de gestagede wijzigingen")
    groep.add_argument("--range", dest="bereik", help="een git-bereik, bv. abc123..HEAD")
    groep.add_argument("--files", nargs="+", help="expliciete bestandslijst")
    argumenten = ontleder.parse_args()

    if argumenten.files:
        gewijzigd = list(argumenten.files)
    else:
        gewijzigd = _gewijzigd_uit_git(
            "staged" if argumenten.staged else "range", argumenten.bereik
        )

    # Regeleinde altijd LF, ook op Windows. Zonder dit krijgt elk pad een wagenretour
    # mee, en dan meldt pytest "file or directory not found" op een bestand dat gewoon
    # bestaat -- gemeten bij de eerste praktijkproef van deze hook. De hook blokkeerde
    # toen terecht, maar om de VERKEERDE reden, en zo verliest een controle zijn
    # geloofwaardigheid: wie hem twee keer onterecht ziet blokkeren, zet hem uit.
    sys.stdout.reconfigure(newline=chr(10))  # type: ignore[union-attr]
    for test in geraakte_tests(gewijzigd):
        print(test)
    return 0


if __name__ == "__main__":
    sys.exit(main())
