"""De ratchet op nooit-draaiende tests is GEWIRED, en twee onmeetbare vormen zijn VERBODEN.

ADR-036 OP-196 en OP-201.

**Wat hier NIET meer staat: het tellen.** Drie eerdere versies van dit bestand telden zelf, met de
AST. Dat telde een OPSOMMING VAN SYNTAXVORMEN, en pytest kent er meer: een onafhankelijke Gate
2-review heeft met echte pytest 8.4.2 TWINTIG vormen aangetoond die een test niet laten draaien
terwijl die guard groen bleef -- een alias-van-een-alias, `pytestmark` via
`AnnAssign`/`AugAssign`/tuple-doel, `pytest.param(marks=pytest.mark.skip(...))`, `collect_ignore`
in een conftest, `pytest.skip(..., allow_module_level=True)`, `from unittest import skip`, en meer.
Drie ervan waren GOEDKOPER dan de vorm die de vorige ronde juist had gesloten. De ronden liepen van
4 gemiste vormen naar 20; nog een ronde vormen bijschrijven is een verliezende race.

Het tellen zit daarom in `scripts/count_disabled_tests.py`, dat PYTEST ZELF de verzameling laat
opleveren en per verzameld item `iter_markers()` bevraagt. Aliassen, `pytestmark` op elk niveau,
`pytest.param(marks=...)`, unittest-decorators, `collect_ignore`, geneste klassen en de
`Test*`/`test_*`-filtering zijn daarmee per CONSTRUCTIE gedekt in plaats van per bedachte variant.
De valse positieven van de AST-versie verdwijnen ook: een gewone `reader.skip(4)` is voor pytest
geen skip.

**Kruisvalidatie, en dit is de reden dat de overstap te vertrouwen is.** De AST-versie kwam op 180
uitgezette tests over 21 bestanden. Het collectie-script komt onafhankelijk op exact 180 over
dezelfde 21 bestanden, met per bestand hetzelfde getal. Twee volledig verschillende mechanismen die
hetzelfde meten. Het verschil was aanvankelijk 175 tegen 180, en dat is GEMETEN en niet verklaard:
de vijf ontbrekende waren onontkoombare inline `pytest.skip()`-aanroepen in twee bestanden, die
pytest pas bij het UITVOEREN ziet. Die zijn omgezet naar `@pytest.mark.skip` -- semantisch
identiek, want de skip was onontkoombaar en de tests deden niets anders.

**Waarom het script een eigen CI-stap heeft en geen test is.** Gemeten: de collectie van de vier
poortmappen kost 16,5s warm en 59-70s koud (16.318 tests), en de blokkerende poortstap draait met
`--timeout=60`. Een test die dit als subproces doet wordt gekild. Besluit Rakesh 2026-09-02, met
expliciete GO voor de blokkerende stap zoals `quality-gates.md` die eist.

**Wat er WEL in dit bestand hoort, en waarom precies dit.** Twee vormen kan het collectie-script
principieel niet zien, en die worden daarom niet GETELD maar VERBODEN:

1. **`skipif` met een CONSTANTE voorwaarde.** Bij het verzamelen is de voorwaarde al geevalueerd:
   `pytest.mark.skipif(not PYOTP_AVAILABLE, ...)` levert `args=(True,)` of `(False,)` afhankelijk
   van de machine. Een marker-object kan dus niet vertellen of er een letterlijke `True` stond of
   een berekende waarde. Meetellen zou de telling omgevingsafhankelijk maken. Of de voorwaarde een
   constante IS, is wel een AST-vraag -- en `skipif(True)`, `skipif(1)`, `skipif("True")` en
   `skipif(condition=True)` zijn geen voorwaardelijke skips maar gewone skips met een andere naam.
   Alle vier waren gemeten ontwijkingen van de vorige guard. Nul voorkomens vandaag, dus dit is een
   hard verbod zonder uitzonderingslijst.
2. **Een ONONTKOOMBARE inline `pytest.skip()`.** Die draait pas bij het uitvoeren, dus de collectie
   ziet hem niet. Nul voorkomens vandaag (de vijf die er waren zijn omgezet naar een marker), dus
   ook dit is een hard verbod. Een `pytest.skip()` ACHTER een voorwaarde blijft toegestaan -- dat
   is de legitieme vorm en `tests/smoke` gebruikt hem.

Plus een wiring-controle: de blokkerende CI-stap moet bestaan en het script daadwerkelijk
aanroepen, en het script moet dezelfde mappen en uitsluitingen meten als de poortstap. Zonder die
controle kan het script stilletjes iets anders meten dan er draait -- dat is precies hoe OP-11
(tests/core) en OP-180 (tests/contracts) maanden onzichtbaar bleven.

**Mutatiebewijs -- beide richtingen, uitgevoerd en gemeten 2026-09-02.** De twee verbodsregels
worden bij ELKE run getoetst op synthetische bronmodules (`_REGEL_GEVALLEN` plus
`test_the_rules_classify_every_known_form`), zodat het bewijs meedraait in plaats van in proza te
staan. De wiring-controles zijn gemuteerd op de workflow en op de scriptconstanten; zie de
docstring per test welke mutatie erbij hoort.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import unicodedata
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci-feature.yml"
SCRIPT = REPO_ROOT / "scripts" / "count_disabled_tests.py"
BASELINE = REPO_ROOT / "scripts" / "disabled_tests_baseline.json"

#: Waar de blokkerende poortstap zijn uitvoer naartoe schrijft. Dit is het anker waarmee die stap
#: te onderscheiden is van de drie integratiestappen in dezelfde workflow (`pytest -c
#: pyproject.toml` staat op vier regels: :261, :358, :417, :441).
GATE_OUTPUT_FILE = "pytest-unit-output.txt"

#: Wat er in een testbody MAG staan voor een inline `pytest.skip()` zonder dat die skip
#: ontkoombaar wordt: statements die NIET kunnen springen. Een `if`, `for`, `try`, `with`,
#: `return`, `raise`, `while` of `match` ervoor betekent dat de skip voorwaardelijk bereikbaar is
#: en dus legitiem. `ast.Expr` staat erbij omdat een losse expressie (`print(...)`,
#: `logger.info(...)`) niet springt; zonder die toevoeging werd een onvoorwaardelijke skip met een
#: gewone aanroep ervoor als NUL gemeten, en dat is de gevaarlijke richting.
_HARMLESS_BEFORE_SKIP = (
    ast.Import,
    ast.ImportFrom,
    ast.Assign,
    ast.AnnAssign,
    ast.Pass,
    ast.Expr,
)


def _load_script():
    """Laad het telscript als module, om zijn constanten te kunnen kruiscontroleren."""
    spec = importlib.util.spec_from_file_location("_count_disabled_tests", SCRIPT)
    assert spec is not None and spec.loader is not None, f"{SCRIPT} is niet te laden"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_test(node: ast.stmt) -> bool:
    """Wat pytest als test verzamelt: `python_functions = "test_*"` uit `pyproject.toml`."""
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
        "test_"
    )


def _mogelijk_woord(source: str, woord: str) -> bool:
    """Kan `source` een identifier `woord` bevatten? Een bewijsbare SUPERSET van `ast`-vinden, om `ast.parse` te sparen.

    **Gemeten 2026-10-24 (waar de tijd zat):** 1785 bestanden lezen 0,2 tot 0,7 s, `ast.parse` van die bestanden 4,0 tot
    5,2 s, terwijl er maar 11 bestanden `skipif` bevatten. De guard parste dus alles voor een handvol treffers.

    Een `ast.Attribute` met `attr == woord` kan alleen uit een identifier komen, en Python normaliseert identifiers met
    NFKC: `ｓｋｉｐｉｆ` (volbreed) wordt in de boom `skipif`. Daarom wordt op de GENORMALISEERDE tekst gezocht, anders
    is het filter nauwer dan `ast` en ontstaat een ontwijking. `test_the_prefilter_is_a_superset_of_the_ast_search`
    dwingt dat af. Een bestand zonder het woord kan de vorm niet bevatten; een fout positief kost alleen een parse.
    """
    return woord in unicodedata.normalize("NFKC", source)


def find_constant_skipif(source: str) -> list[int]:
    """Regelnummers van elke `skipif` met een voorwaarde die een CONSTANTE is.

    Dekt de positionele en de `condition=`-vorm, en elke constante: `True`, `1`, `"True"`. Dat
    laatste is geen theorie -- pytest evalueert een string-voorwaarde, dus `skipif("True", ...)`
    skipt altijd, en een reviewer heeft dat als ontwijking gemeten.
    """
    if not _mogelijk_woord(source, "skipif"):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    gevonden: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        doel = node.func
        if not isinstance(doel, ast.Attribute) or doel.attr != "skipif":
            continue
        voorwaarde: ast.expr | None = node.args[0] if node.args else None
        for sleutelwoord in node.keywords:
            if sleutelwoord.arg == "condition":
                voorwaarde = sleutelwoord.value
        if isinstance(voorwaarde, ast.Constant):
            gevonden.append(node.lineno)
    return gevonden


def find_unavoidable_inline_skip(source: str) -> list[int]:
    """Regelnummers van elke `pytest.skip()` die als eerste daad van een test onontkoombaar is.

    Eist `pytest.skip` en niet elke `<iets>.skip(...)`: een gewone `reader.skip(4)` is voor pytest
    geen skip, en die als uitgezette test melden is een valse positief op een blokkerende poort.
    """
    if not _mogelijk_woord(source, "skip"):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    gevonden: list[int] = []

    def bekijk(node: ast.stmt) -> None:
        # Expliciete recursie: `ast.walk` duikt functiebodies in en dat heeft in dit project al
        # twee keer een guard hol gemaakt (zie de valkuilenlijst).
        if isinstance(node, ast.ClassDef):
            for kind in node.body:
                bekijk(kind)
            return
        if not _is_test(node):
            return
        assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for stmt in node.body:
            waarde = stmt.value if isinstance(stmt, ast.Expr) else None
            if isinstance(waarde, ast.Constant) and isinstance(waarde.value, str):
                continue  # docstring
            if isinstance(waarde, ast.Call):
                doel = waarde.func
                if (
                    isinstance(doel, ast.Attribute)
                    and doel.attr == "skip"
                    and isinstance(doel.value, ast.Name)
                    and doel.value.id == "pytest"
                ):
                    gevonden.append(stmt.lineno)
                    return
            if not isinstance(stmt, _HARMLESS_BEFORE_SKIP):
                return

    for kind in tree.body:
        bekijk(kind)
    return gevonden


def _gate_dirs_from_script() -> tuple[str, ...]:
    return tuple(_load_script().GATE_DIRS)


def _gate_step_lines() -> list[str]:
    """De regels van de BLOKKERENDE poortstap in de CI-workflow."""
    return [
        regel
        for regel in CI_WORKFLOW.read_text(encoding="utf-8").splitlines()
        if "pytest -c pyproject.toml" in regel
        and GATE_OUTPUT_FILE in regel
        and not regel.strip().startswith("#")
    ]


def _scan_gate(zoeker) -> dict[str, list[int]]:
    """Pas `zoeker` toe op elk bestand dat de poort inleest."""
    module = _load_script()
    treffers: dict[str, list[int]] = {}
    for wortel in module.GATE_DIRS:
        map_pad = REPO_ROOT / wortel
        assert map_pad.is_dir(), (
            f"Poortmap {wortel} bestaat niet. Zonder deze controle scant `rglob` hem naar nul "
            "zonder fout, en meet deze guard te LAAG terwijl hij groen meldt."
        )
        for pad in sorted(map_pad.rglob("test_*.py")):
            rel = str(pad.relative_to(REPO_ROOT)).replace("\\", "/")
            # Op PADSEGMENT, niet op prefix: `startswith("tests/unit/temp_disabled")` sloot ook
            # `tests/unit/temp_disabled_extra/` uit, en die map VERZAMELT pytest wel
            # (`norecursedirs` matcht de basisnaam exact).
            if any(
                rel == genegeerd or rel.startswith(genegeerd + "/")
                for genegeerd in ("tests/unit/temp_disabled",)
            ):
                continue
            regels = zoeker(pad.read_text(encoding="utf-8", errors="ignore"))
            if regels:
                treffers[rel] = regels
    return treffers


#: Elk geval is een VOLLEDIGE synthetische module plus de verwachte treffers. Dit toetst de echte
#: zoekers, niet een los tekstpredikaat. De nul-gevallen zijn de dragende tegenrichting: zonder hen
#: zou "verbied alles" een geldige implementatie zijn en zou deze guard de legitieme
#: voorwaardelijke vormen bestraffen die dit project juist WIL.
_REGEL_GEVALLEN: tuple[tuple[str, str, int, int], ...] = (
    # (omschrijving, bron, verwachte constante-skipifs, verwachte onontkoombare inline skips)
    (
        "skipif(True, ...) is een gewone skip",
        'import pytest\n@pytest.mark.skipif(True, reason="uit")\ndef test_a(): pass\n',
        1,
        0,
    ),
    (
        "skipif(1, ...) -- een teken verschil met de vorige",
        'import pytest\n@pytest.mark.skipif(1, reason="uit")\ndef test_a(): pass\n',
        1,
        0,
    ),
    (
        'skipif("True", ...) -- pytest evalueert de string',
        'import pytest\n@pytest.mark.skipif("True", reason="uit")\ndef test_a(): pass\n',
        1,
        0,
    ),
    (
        "skipif(condition=True, ...) -- als keyword",
        'import pytest\n@pytest.mark.skipif(condition=True, reason="uit")\ndef test_a(): pass\n',
        1,
        0,
    ),
    (
        "skipif(False, ...) is net zo goed een constante",
        'import pytest\n@pytest.mark.skipif(False, reason="uit")\ndef test_a(): pass\n',
        1,
        0,
    ),
    (
        "onontkoombare inline skip",
        'import pytest\ndef test_a():\n    """doc"""\n    pytest.skip("uit")\n',
        0,
        1,
    ),
    (
        "onontkoombare inline skip met een gewone aanroep ervoor",
        'import pytest\ndef test_a():\n    print("opzetten")\n    pytest.skip("uit")\n',
        0,
        1,
    ),
    (
        "onontkoombare inline skip in een klassemethode",
        'import pytest\nclass TestX:\n    def test_a(self):\n        pytest.skip("uit")\n',
        0,
        1,
    ),
    (
        "LEGITIEM: skipif met een ECHTE voorwaarde",
        "import os\nimport pytest\n"
        '@pytest.mark.skipif(not os.getenv("TEST_BASE_URL"), reason="zet TEST_BASE_URL")\n'
        "def test_a(): pass\n",
        0,
        0,
    ),
    (
        "LEGITIEM: skipif op een naam die pas op de machine bekend is",
        "import pytest\nfrom mod import BESCHIKBAAR\n"
        '@pytest.mark.skipif(not BESCHIKBAAR, reason="x mist")\ndef test_a(): pass\n',
        0,
        0,
    ),
    (
        "LEGITIEM: inline skip ACHTER een voorwaarde",
        "import pytest\ndef test_a():\n    if not have_faiss():\n"
        '        pytest.skip("geen FAISS")\n    assert True\n',
        0,
        0,
    ),
    (
        "LEGITIEM: inline skip NA een lus die eruit kan returnen",
        "import pytest\ndef test_a():\n    for x in items():\n        if x:\n"
        '            return\n    pytest.skip("niet gevonden")\n',
        0,
        0,
    ),
    (
        "LEGITIEM: een gewone .skip() op een ander object is geen pytest-skip",
        "def test_reader():\n    reader.skip(4)\n    assert reader.pos == 4\n",
        0,
        0,
    ),
    (
        "LEGITIEM: een functie zonder test_-prefix wordt niet verzameld",
        'import pytest\ndef helper():\n    pytest.skip("uit")\n',
        0,
        0,
    ),
    (
        "LEGITIEM: een gewone skip-marker -- die telt het SCRIPT, niet deze guard",
        'import pytest\n@pytest.mark.skip(reason="uit")\ndef test_a(): pass\n',
        0,
        0,
    ),
    (
        "LEGITIEM: de TEKST van een skipif in testdata is geen skipif",
        'import pytest\n@pytest.mark.parametrize("bron", '
        "[\"pytest.mark.skipif(True, reason='uit')\"])\ndef test_a(bron): pass\n",
        0,
        0,
    ),
)


@pytest.mark.architecture
@pytest.mark.parametrize(
    ("omschrijving", "bron", "verwacht_skipif", "verwacht_inline"), _REGEL_GEVALLEN
)
def test_the_rules_classify_every_known_form(
    omschrijving: str, bron: str, verwacht_skipif: int, verwacht_inline: int
) -> None:
    """De REGELS worden gemuteerd op synthetische modules, niet de poort.

    Een regel per vorm die deze guard beweert te dekken, en acht nul-gevallen als tegenrichting.
    De eerste vijf zijn gemeten ontwijkingen van een eerdere versie van deze guard.
    """
    gemeten = (len(find_constant_skipif(bron)), len(find_unavoidable_inline_skip(bron)))
    assert gemeten == (verwacht_skipif, verwacht_inline), (
        f"{omschrijving}: gemeten (constante-skipif, inline) = {gemeten}, verwacht "
        f"{(verwacht_skipif, verwacht_inline)}."
    )


@pytest.mark.architecture
def test_no_skipif_with_a_constant_condition() -> None:
    """Een `skipif` met een constante voorwaarde is een gewone skip met een andere naam.

    Nul voorkomens op 2026-09-02, dus dit is een hard verbod zonder uitzonderingslijst. Rood te
    maken door `@pytest.mark.skipif(True, reason="...")` aan een poortbestand toe te voegen.
    """
    treffers = _scan_gate(find_constant_skipif)
    assert not treffers, (
        "Deze `skipif`-markers hebben een CONSTANTE voorwaarde en skippen dus altijd:\n"
        + "\n".join(f"  {pad}:{regels}" for pad, regels in sorted(treffers.items()))
        + "\n\nDat is geen voorwaardelijke skip maar een gewone skip, en het ontwijkt de ratchet "
        "in `scripts/count_disabled_tests.py` -- die kan bij het verzamelen niet zien of de "
        "voorwaarde een letterlijke constante was of een berekende waarde.\n"
        "Zet er de voorwaarde in die je werkelijk bedoelt, of gebruik `@pytest.mark.skip` en laat "
        "de ratchet hem tellen. Zie ADR-036 OP-201."
    )


@pytest.mark.architecture
def test_no_unavoidable_inline_skip() -> None:
    """Een onontkoombare `pytest.skip()` in een testbody hoort een marker te zijn.

    Reden: hij draait pas bij het UITVOEREN, dus de collectie-gebaseerde ratchet ziet hem niet.
    De vijf die er waren zijn op 2026-09-02 omgezet naar `@pytest.mark.skip`; nul voorkomens nu,
    dus een hard verbod. Rood te maken door een test te schrijven die met `pytest.skip("...")`
    begint. Een `pytest.skip()` ACHTER een voorwaarde blijft toegestaan.
    """
    treffers = _scan_gate(find_unavoidable_inline_skip)
    assert not treffers, (
        "Deze tests beginnen met een onontkoombare `pytest.skip()`:\n"
        + "\n".join(f"  {pad}:{regels}" for pad, regels in sorted(treffers.items()))
        + "\n\nDie is voor pytest pas bij het uitvoeren zichtbaar, dus de ratchet in "
        "`scripts/count_disabled_tests.py` telt hem NIET mee en het aantal uitgezette tests kan "
        "er ongemerkt langs groeien.\n"
        "Gebruik `@pytest.mark.skip(reason=...)` -- semantisch identiek en wel zichtbaar. Staat de "
        "skip achter een voorwaarde, dan is hij legitiem en wordt hij hier niet gemeld. Zie "
        "ADR-036 OP-201."
    )


@pytest.mark.architecture
def test_the_ci_gate_step_is_findable() -> None:
    """Vangnet: zonder een vindbare poortstap kan de volgende test niets vergelijken.

    Rood te maken door `pytest-unit-output.txt` in de workflow te hernoemen of de stap te
    splitsen.
    """
    regels = _gate_step_lines()
    assert len(regels) == 1, (
        f"Verwacht precies EEN pytest-stap in {CI_WORKFLOW.name} die naar {GATE_OUTPUT_FILE} "
        f"schrijft, gevonden {len(regels)}. Is de stap gesplitst of het uitvoerbestand hernoemd, "
        "dan moet deze guard mee -- hij mag niet stil gaan onder-meten."
    )


@pytest.mark.architecture
def test_the_script_measures_the_same_dirs_as_the_ci_gate() -> None:
    """Het telscript moet precies de mappen meten die de poort DRAAIT.

    Zonder deze kruiscontrole meet het script vier mappen nadat iemand een vijfde aan de
    blokkerende stap heeft toegevoegd -- dan onder-meet het en meldt het toch groen. Dat is
    hetzelfde patroon als OP-11 (tests/core) en OP-180 (tests/contracts), die daardoor maanden
    onzichtbaar bleven. Rood te maken door een map uit `GATE_DIRS` in het script te halen of een
    vijfde aan de CI-stap toe te voegen.
    """
    in_ci = tuple(
        woord
        for regel in _gate_step_lines()
        for woord in regel.split()
        if woord.startswith("tests/")
    )
    assert in_ci == _gate_dirs_from_script(), (
        f"De blokkerende CI-stap draait {in_ci}, `scripts/count_disabled_tests.py` meet "
        f"{_gate_dirs_from_script()}. Werk `GATE_DIRS` in het script bij en meet de basislijn "
        "opnieuw met `--write-baseline`."
    )


@pytest.mark.architecture
def test_the_ratchet_has_a_blocking_ci_step() -> None:
    """De ratchet moet ECHT in de pijplijn hangen, en niet als waarschuwing.

    Dit is de les van OP-200: `lint-imports` stond vijftien maanden in `ci-local-fast.sh` met
    `2>/dev/null` en alleen een WAARSCHUWING, en de enige test die het pretendeerde negeerde de
    exitcode. Een gedocumenteerde poort zonder harde stap is theater. Rood te maken door de stap
    uit de workflow te halen of er `continue-on-error: true` op te zetten.
    """
    inhoud = CI_WORKFLOW.read_text(encoding="utf-8")
    aanroep = "python scripts/count_disabled_tests.py"
    assert aanroep in inhoud, (
        f"{CI_WORKFLOW.name} roept `{aanroep}` niet aan. Zonder blokkerende stap telt niemand de "
        "tests die nooit draaien, en kan dat aantal ongemerkt groeien. Zie ADR-036 OP-196."
    )
    # De stap zelf mag geen `continue-on-error` dragen. Gemeten over het blok vanaf de stapnaam
    # tot de volgende stap, zodat een vlag op een ANDERE stap deze test niet vals rood maakt.
    naam = "- name: Ratchet op tests die nooit draaien"
    assert naam in inhoud, f"{CI_WORKFLOW.name} mist de stap `{naam}`."
    blok = inhoud.split(naam, 1)[1]
    volgende = blok.find("\n      - name:")
    blok = blok[:volgende] if volgende != -1 else blok
    assert "continue-on-error" not in blok, (
        "De ratchet-stap draagt `continue-on-error`. Dan rapporteert hij wel maar blokkeert hij "
        "nooit, en dat is exact het patroon dat `quality-gates.md` verbiedt zonder gedateerde, "
        "door Rakesh goedgekeurde uitzondering."
    )


@pytest.mark.architecture
def test_the_baseline_exists_and_is_parseable() -> None:
    """Zonder basislijn faalt het script bij elke run; dat hoort hier zichtbaar te zijn.

    Rood te maken door `scripts/disabled_tests_baseline.json` te verwijderen of ongeldige JSON
    te maken.
    """
    assert BASELINE.exists(), (
        f"{BASELINE.name} ontbreekt. Leg hem vast met "
        "`python scripts/count_disabled_tests.py --write-baseline` en commit hem mee."
    )
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    per_bestand = data["per_bestand"]
    assert per_bestand and sum(per_bestand.values()) == data["totaal"], (
        f"{BASELINE.name} is inconsistent: `totaal` is {data.get('totaal')} maar de som over "
        f"{len(per_bestand)} bestanden is {sum(per_bestand.values())}."
    )


#: Bronnen waarin de `ast` een `skipif`- of `skip`-aanroep VINDT, ook op manieren die een tekstzoeker mist. Elk geval moet
#: het voorfilter doorstaan: dat is wat "superset" betekent. De volbreed-geschreven vorm is de dragende: Python
#: normaliseert identifiers met NFKC, dus zonder die normalisatie in het filter is het nauwer dan `ast`.
_SUPERSET_GEVALLEN: tuple[tuple[str, str, str], ...] = (
    ("gewone vorm", 'import pytest\n@pytest.mark.skipif(True, reason="x")\ndef test_a(): pass\n', "skipif"),
    ("alias van mark", "from pytest import mark as m\n@m.skipif(1, reason='x')\ndef test_a(): pass\n", "skipif"),
    ("volbreed geschreven attribuut", "import pytest\n@pytest.mark.\uff53kipif(True, reason='x')\ndef test_a(): pass\n", "skipif"),
    ("inline skip", "import pytest\ndef test_a():\n    pytest.skip('x')\n", "skip"),
    ("volbreed geschreven skip", "import pytest\ndef test_a():\n    pytest.\uff53kip('x')\n", "skip"),
)


@pytest.mark.parametrize(("omschrijving", "bron", "woord"), _SUPERSET_GEVALLEN)
def test_the_prefilter_is_a_superset_of_the_ast_search(omschrijving: str, bron: str, woord: str) -> None:
    """Wat `ast` vindt, laat het tekstvoorfilter door (en het filter zelf is dus nooit nauwer).

    Mutatiebewijs (2026-10-24): `unicodedata.normalize` uit `_mogelijk_woord` gehaald -> de twee volbreed-gevallen
    ROOD; het filter op `"skipif"` vervangen door `"skipifx"` -> alle skipif-gevallen rood.
    """
    boom = ast.parse(bron)
    gevonden = any(isinstance(n, ast.Attribute) and n.attr == woord for n in ast.walk(boom))

    assert gevonden, f"{omschrijving}: de ast ziet het woord {woord!r} niet; het geval klopt niet"
    assert _mogelijk_woord(bron, woord), f"{omschrijving}: het voorfilter laat een bron door ast gevonden WEG"


def test_the_prefilter_skips_a_file_without_the_word() -> None:
    """Tegenrichting: zonder deze toets is 'laat alles door' (geen versnelling) een geldig filter."""
    assert not _mogelijk_woord("import pytest\n\ndef test_a():\n    assert 1\n", "skipif")


def test_the_filtered_search_gives_the_same_answer_as_the_unfiltered_search() -> None:
    """Op de synthetische modules geeft de gefilterde zoeker hetzelfde als een parse zonder filter."""
    ongefilterd = {
        omschrijving: [
            n.lineno
            for n in ast.walk(ast.parse(bron))
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "skipif"
            and n.args
            and isinstance(n.args[0], ast.Constant)
        ]
        for omschrijving, bron, woord in _SUPERSET_GEVALLEN
        if woord == "skipif"
    }
    gefilterd = {
        omschrijving: find_constant_skipif(bron)
        for omschrijving, bron, woord in _SUPERSET_GEVALLEN
        if woord == "skipif"
    }

    assert gefilterd == ongefilterd
