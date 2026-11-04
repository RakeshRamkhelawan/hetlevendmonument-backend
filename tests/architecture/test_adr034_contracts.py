"""Architecture tests voor de import-linter-contracten van ADR-033 en ADR-034.

**Waarom dit bestand is herschreven (ADR-036 OP-200, 2026-09-02).** De vorige versie had een
test `test_lint_imports_no_parse_error` die sinds 2026-06-09 groen stond en NIETS toetste. Twee
gemeten oorzaken, en beide moeten hier staan omdat ze elk apart de test vacuum maken:

1. Hij riep `python -m importlinter` aan. Dat werkt niet: `No module named importlinter.__main__;
   'importlinter' is a package and cannot be directly executed`, exitcode 1. De contracten werden
   dus nooit geevalueerd. (Ook gemeten: `python -m importlinter.cli lint-imports` geeft NUL regels
   uitvoer en exitcode 0 -- hij draait de contracten evenmin. De enige werkende ingang is het
   console-script `lint-imports`.)
2. Zelfs als de aanroep had gewerkt, negeerde hij de EXITCODE en toetste hij alleen of drie
   woorden niet in stderr stonden. Dat is de vorm "negeerde de returncode van een subproces" uit
   `.claude/rules/quality-gates.md`.

Dat is ernstiger dan een losse holle test, want CLAUDE.md noemt import-linter als HET
handhavingsmechanisme voor de router-grens (ADR-033 Contract 1) en de agent_runtime-grens
(ADR-034 Contract 2+3). Nagemeten: `lint-imports` komt in GEEN enkele GitHub-workflow voor, en
`scripts/ci-local-fast.sh:155` draait het met `2>/dev/null` en alleen als WAARSCHUWING
("verwacht voor legacy bestanden"). Er was dus nergens een blokkerende poort op die contracten.

**Waarom dit veilig kan.** Gemeten 2026-09-02 in een schone worktree op `develop`:
`lint-imports` geeft `Contracts: 9 kept, 0 broken` met exitcode 0, in 5 seconden. En de
tegenproef: met een toegevoegde `from src.core.database.database import get_db` in
`src/core/api/auth/router.py` geeft hij exitcode 1 en `Contracts: 8 kept, 1 broken`. Deze poort
is dus vandaag groen en betrapt werkelijk. `requirements-test.txt` pint `import-linter==2.13` en
`.github/workflows/ci-feature.yml:130` installeert dat bestand, dus het console-script is in de
poort-job aanwezig.
"""

import functools
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPORTLINTER_CFG = REPO_ROOT / ".importlinter"

#: Zoveel contracten staan er op 2026-09-02 in `.importlinter`. Dit getal is er zodat een
#: contract niet STIL kan verdwijnen: `lint-imports` meldt dan gewoon een lager aantal en blijft
#: groen. Een contract toevoegen of weghalen is een bewuste wijziging en past dit getal aan.
EXPECTED_CONTRACTS = 9


@functools.lru_cache(maxsize=1)
def _lint_imports() -> subprocess.CompletedProcess[str]:
    """Draai het console-script een keer per proces (gemeten 5s) en geef het hele resultaat."""
    uitvoerbaar = shutil.which("lint-imports")
    if uitvoerbaar is None:
        pytest.fail(
            "Het console-script `lint-imports` staat niet op PATH. Installeer de "
            "test-dependencies (`pip install -r requirements-test.txt`, dat pint "
            "import-linter==2.13). Deze test wordt NIET overgeslagen als de tool ontbreekt: "
            "dan zou hij weer vacuum groen zijn, en dat is precies wat OP-200 was."
        )
    # `text=True` ZONDER `encoding` decodeert met de locale-codering. Op deze machine is
    # dat cp1252, en `lint-imports` tekent zijn rapport met kaderlijnen in UTF-8. Gemeten
    # 2026-09-10: byte 0x90 op positie 7 is in cp1252 niet gedefinieerd, `stdout` wordt
    # None en de guard valt om met "NoneType has no attribute splitlines" -- terwijl het
    # echte antwoord "Contracts: 9 kept, 0 broken" was. De uitkomst hing dus af van
    # PYTHONIOENCODING in de omgeving van de aanroeper. Vast op UTF-8, met `replace` zodat
    # een onverwachte byte de guard nooit meer kan laten crashen in plaats van meten.
    return subprocess.run(
        [uitvoerbaar],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )


def _summary_line() -> str:
    """De `Contracts: N kept, M broken`-regel; leeg als hij er niet is."""
    resultaat = _lint_imports()
    for regel in resultaat.stdout.splitlines():
        if regel.startswith("Contracts:"):
            return regel.strip()
    return ""


@pytest.mark.unit
def test_contract_2_defined_in_importlinter() -> None:
    content = IMPORTLINTER_CFG.read_text(encoding="utf-8")
    assert "agent_runtime_boundary" in content, (
        "Contract 2 (agent_runtime_boundary) ontbreekt in .importlinter"
    )


@pytest.mark.unit
def test_contract_3_defined_in_importlinter() -> None:
    content = IMPORTLINTER_CFG.read_text(encoding="utf-8")
    assert "agent_runtime_no_db" in content, (
        "Contract 3 (agent_runtime_no_db) ontbreekt in .importlinter"
    )


@pytest.mark.unit
def test_the_import_linter_actually_evaluated_the_contracts() -> None:
    """Vangnet tegen een vacuum groene poort -- dit is wat de vorige versie miste.

    Zonder deze assertie kan de aanroep stilletjes niets doen (exitcode 0, geen uitvoer) en
    lijken de volgende tests te slagen. Rood te maken door het console-script te vervangen door
    `python -m importlinter.cli lint-imports`, dat gemeten NUL regels oplevert.
    """
    assert _summary_line(), (
        "`lint-imports` gaf geen `Contracts: ...`-samenvattingsregel, dus de contracten zijn "
        "NIET geevalueerd. Exitcode "
        f"{_lint_imports().returncode}.\nstdout:\n{_lint_imports().stdout[-2000:]}\n"
        f"stderr:\n{_lint_imports().stderr[-2000:]}"
    )


@pytest.mark.unit
def test_every_declared_contract_is_evaluated() -> None:
    """Een contract mag niet STIL uit `.importlinter` verdwijnen.

    `lint-imports` meldt dan simpelweg een lager aantal en blijft groen. Rood te maken door een
    contractblok uit `.importlinter` te verwijderen.
    """
    samenvatting = _summary_line()
    assert f"Contracts: {EXPECTED_CONTRACTS} " in samenvatting, (
        f"Verwacht {EXPECTED_CONTRACTS} contracten, `lint-imports` meldt: {samenvatting!r}. "
        "Is er een contract toegevoegd of weggehaald, pas dan `EXPECTED_CONTRACTS` aan in "
        "DEZELFDE commit -- anders kan een grens stil verdwijnen."
    )


@pytest.mark.unit
def test_the_import_linter_contracts_are_kept() -> None:
    """DE poort: geen enkel import-contract mag gebroken zijn.

    Dit toetst de EXITCODE, want dat is wat de vorige versie niet deed. Rood te maken door een
    verboden import aan een router toe te voegen; gemeten met
    `from src.core.database.database import get_db` in `src/core/api/auth/router.py` ->
    exitcode 1, `Contracts: 8 kept, 1 broken`.
    """
    resultaat = _lint_imports()
    assert resultaat.returncode == 0, (
        f"import-linter meldt gebroken contracten ({_summary_line()}).\n\n"
        "Een router mag domeinlogica niet DIRECT importeren (ADR-033 Contract 1); dat hoort via "
        "het bijbehorende `*.dependencies`-bestand. De agent_runtime-grenzen zijn ADR-034 "
        "Contract 2+3. Draai `lint-imports` voor de volledige lijst.\n\n"
        f"stdout:\n{resultaat.stdout[-4000:]}"
    )
