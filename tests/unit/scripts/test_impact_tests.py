"""De impact-selectie kiest op IMPORT, en de hooks roepen hem ook echt aan.

**Waarom dit bestaat.** Op 2026-09-24 bleek een test 45 commits lang rood te staan zonder dat
iemand het wist: commit 8d936380 zette test en implementatie samen neer (groen), commit
87ea4a3a verving daarna een lijst door een begrensde `deque` -- een goede reparatie tegen een
geheugenlek -- en liet de assertie `== []` staan. Een lege `deque` is niet gelijk aan een lege
lijst.

Zelf nagemeten: noch `mypy --strict-equality` noch `pyright` in strikte modus meldt die
vergelijking. Beide containers vergelijken via `object`, dus formeel overlappen de types. Deze
fout is alleen te vinden door de test te DRAAIEN -- en de pre-commit hook draaide er nul.

De selectie kostte in de meting vier seconden en vond hem. Deze tests leggen vast dat hij dat
blijft doen, en dat de hooks hem ook werkelijk aanroepen.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import impact_tests  # noqa: E402

BRON = "src/domains/memory/observability.py"
MODULE = "src.domains.memory.observability"
PAKKET = "src.domains.memory"
NAAM = "observability"


def _deelt(inhoud: str) -> bool:
    return impact_tests._importeert(inhoud, MODULE, PAKKET, NAAM)


# ------------------------------------------------------- wat WEL geselecteerd wordt


def test_de_volledige_modulenaam_telt_als_import() -> None:
    assert _deelt("from src.domains.memory.observability import _NoOpHistogram\n")
    assert _deelt("import src.domains.memory.observability\n")


def test_de_pakketvorm_telt_ook() -> None:
    """`from src.domains.memory import observability` is net zo goed een import."""
    assert _deelt("from src.domains.memory import observability\n")


def test_de_pakketvorm_met_meerdere_namen_telt_ook() -> None:
    assert _deelt("from src.domains.memory import store, observability, index\n")


def test_een_import_MET_commentaar_erachter_telt_gewoon_mee() -> None:
    """Zonder het strippen van commentaar zou deze legitieme import worden GEMIST.

    De namen achter `import` worden los vergeleken, dus `observability  # uitleg` is een
    andere naam dan `observability`. Dat is onder-selectie: precies het gevaar dat deze
    selectie niet mag hebben, want een gemiste test is een test die niet draait.
    """
    assert _deelt("from src.domains.memory import observability  # de metriek-fallbacks\n")


# ------------------------------------- de tegenrichting: wat NIET geselecteerd mag worden


def test_een_los_woord_is_GEEN_import() -> None:
    """De kern van de reparatie, met het gemeten geval erbij.

    De oude impact-analyse zocht de BESTANDSNAAM als tekst. Voor dit ene bestand leverde dat
    30 treffers op, waarvan er 2 de module echt importeren; de overige 28 noemden alleen het
    woord. Dat is dezelfde faalvorm die dit project overal bestrijdt -- tekst toetsen waar
    structuur hoort -- en hier kostte het 60 seconden per commit aan tests die niets met de
    wijziging te maken hebben.
    """
    assert not _deelt('"""Deze module regelt observability voor agents."""\n')
    assert not _deelt("observability_enabled = True\n")
    assert not _deelt("from src.domains.memory import store  # observability volgt later\n")


def test_een_ANDER_pakket_met_dezelfde_naam_telt_niet_mee() -> None:
    """Zonder deze grens selecteert elke gelijknamige module in een ander pakket mee."""
    assert not _deelt("from src.core.telemetry import observability\n")


def test_weiger_alles_is_geen_geldige_oplossing() -> None:
    """De harde tegenrichting.

    Zonder deze test zou `return False` slagen op alle voorgaande weiger-tests, en dan
    selecteert de hook nooit meer iets -- een bewaker die alles doorlaat.
    """
    assert _deelt(f"from {MODULE} import iets\n") is True


# ------------------------------------------------------- de selectie als geheel


@pytest.fixture
def eigen_boom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Een eigen mini-repo, zodat de test niet afhangt van de echte testverzameling."""
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_importeert.py").write_text(
        f"from {MODULE} import _NoOpHistogram\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "unit" / "test_noemt_alleen_het_woord.py").write_text(
        f"# gaat over {NAAM} maar importeert het niet\n", encoding="utf-8"
    )
    monkeypatch.setattr(impact_tests, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        impact_tests,
        "_testbestanden",
        lambda: [
            "tests/unit/test_importeert.py",
            "tests/unit/test_noemt_alleen_het_woord.py",
        ],
    )
    return tmp_path


def test_alleen_de_importerende_test_wordt_gekozen(eigen_boom: Path) -> None:
    assert impact_tests.geraakte_tests([BRON]) == ["tests/unit/test_importeert.py"]


def test_een_gewijzigd_testbestand_draait_altijd_zelf_mee(eigen_boom: Path) -> None:
    """Wie een test in DOELMAPPEN aanpast, draait hem -- ook als geen bron is gewijzigd.

    Tegenrichting: een testbestand buiten DOELMAPPEN telt NIET mee als "zelf meegenomen".
    Dat is de bewuste gedragsverandering van 2026-09-28: de commitpoort bewaakt alleen de
    vier mappen die de pushpoort ook dekt.
    """
    gekozen = impact_tests.geraakte_tests(["tests/unit/test_noemt_alleen_het_woord.py"])
    assert gekozen == ["tests/unit/test_noemt_alleen_het_woord.py"]

    # Tegenrichting: een testbestand buiten DOELMAPPEN lokt geen run uit
    gekozen_buiten = impact_tests.geraakte_tests(["tests/e2e/test_omnichannel_flow.py"])
    assert gekozen_buiten == [], (
        "een testbestand buiten DOELMAPPEN mag de commitpoort niet blokkeren -- "
        "de pushpoort dekt tests/e2e/ niet en de commitpoort hoort dat ook niet te doen"
    )


def test_een_wijziging_buiten_de_code_selecteert_niets(eigen_boom: Path) -> None:
    """Een README of een YAML mag geen testronde uitlokken."""
    # `tests/fixtures/data.json` staat er met opzet bij: die begint WEL met `tests/`.
    # Zonder de .py-controle zou hij als "gewijzigd testbestand" worden doorgegeven aan
    # pytest, en dan draait de hook op een bestand dat geen tests bevat.
    assert (
        impact_tests.geraakte_tests(["README.md", "docker-compose.yml", "tests/fixtures/data.json"])
        == []
    )


# --------------------------- gevonden bij het EERSTE echte gebruik van dit script


def test_een_scriptmodule_bij_zijn_KALE_naam_telt_ook_als_import() -> None:
    """Vijf testbestanden zetten scripts/ op sys.path en importeren dan bij de kale naam.

    Gemeten: een wijziging in `scripts/mutation_harness.py` selecteerde NUL tests, terwijl
    `tests/architecture/test_het_mutatieharnas_wijkt_voor_de_testronde.py` hem wel gebruikt.
    Het puntpad `scripts.mutation_harness` komt in die bestanden nooit voor. Onder-selectie
    op precies het pad waarvoor dit gereedschap is gemaakt.
    """
    assert impact_tests._kale_naam_import("import mutation_harness  # noqa: E402\n", "mutation_harness")
    assert impact_tests._kale_naam_import("from mutation_harness import Mutation\n", "mutation_harness")
    assert impact_tests._kale_naam_import("import os, mutation_harness\n", "mutation_harness")


def test_een_kale_VERMELDING_is_nog_steeds_geen_import() -> None:
    """De tegenrichting. Zonder deze grens valt de hele reparatie van de woordzoekopdracht weg."""
    assert not impact_tests._kale_naam_import("# mutation_harness doet dit ook\n", "mutation_harness")
    assert not impact_tests._kale_naam_import("mutation_harness_pad = 'x'\n", "mutation_harness")
    assert not impact_tests._kale_naam_import("import mutation_harness_extra\n", "mutation_harness")
    # Zonder deze regel blijft `if True:` in plaats van de import-controle groen --
    # gemeten in het mutatiebewijs, en precies hoe een tegenrichting te zwak wordt.
    assert not impact_tests._kale_naam_import("mutation_harness\n", "mutation_harness")


def test_een_NIEUW_testbestand_telt_mee_ook_als_git_het_nog_niet_kent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`git ls-files` toont een vers aangemaakt testbestand niet.

    Dat is precies het moment waarop je hem nodig hebt: je schrijft een nieuwe test bij een
    wijziging, en die zou dan niet meedraaien. De selectie neemt nu ook de ongetrackte
    bestanden mee (zonder de genegeerde).
    """
    geroepen: list[list[str]] = []

    def _nep_git(args: list[str]) -> str:
        geroepen.append(args)
        if "--others" in args:
            return "tests/test_gloednieuw.py\n"
        return ""

    monkeypatch.setattr(impact_tests, "_git", _nep_git)

    assert impact_tests._testbestanden() == ["tests/test_gloednieuw.py"]
    assert any("--others" in a for a in geroepen), (
        "de selectie vraagt git niet meer om de ongetrackte bestanden"
    )


def test_de_SELECTIE_vindt_een_scriptmodule_via_de_kale_naam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Via `geraakte_tests`, want een test op de hulpfunctie bewaakt de bedrading niet.

    Derde keer vandaag dat deze vorm toeslaat: bij de ratchet-metrieken, bij de hook-aanroep,
    en hier. Het mutatiebewijs betrapte hem telkens, de test niet -- daarom hoort bij elke
    hulpfunctie ook een test op de plek waar hij wordt aangeroepen.
    """
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_kale_import.py").write_text(
        "import mutation_harness\n", encoding="utf-8"
    )
    monkeypatch.setattr(impact_tests, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(impact_tests, "_testbestanden", lambda: ["tests/test_kale_import.py"])

    assert impact_tests.geraakte_tests(["scripts/mutation_harness.py"]) == [
        "tests/test_kale_import.py"
    ]


# ------------------- instructiebestanden: geen import, wel gelezen door bewakers


_LEEST = 'PAD = REPO_ROOT / "CLAUDE.md"' + "\n" + "tekst = PAD.read_text()" + "\n"
_NOEMT_IN_DOCSTRING = '"""Deze test hoort bij de NOOIT-lijst uit CLAUDE.md."""' + "\n"
_DOCSTRING_IS_PRECIES_HET_PAD = '"""CLAUDE.md"""' + "\n"
_NOEMT_IN_MELDING = 'assert x, "CLAUDE.md verbiedt dit"' + "\n"
_ANDERE_README = 'PAD = "docs/compliance/soc2/README.md"' + "\n"


def test_een_test_die_het_instructiebestand_LEEST_wordt_gekozen() -> None:
    assert impact_tests._leest_dit_pad(_LEEST, "CLAUDE.md")


def test_een_vermelding_in_een_DOCSTRING_telt_niet() -> None:
    """Van de 46 tests die CLAUDE.md noemen, doen er 43 dat alleen in proza."""
    assert not impact_tests._leest_dit_pad(_NOEMT_IN_DOCSTRING, "CLAUDE.md")


def test_een_vermelding_in_een_ASSERT_MELDING_telt_ook_niet() -> None:
    """Dit was de scherpste grens, en hij kostte een correctie op mijn eigen meting.

    Een assert-melding is geen docstring, dus een eerste versie telde hem als "leest het
    bestand". Daardoor kwam ik op 9 van de 46 in plaats van 3. Tests als
    `test_no_bom_in_python_sources.py` noemen CLAUDE.md alleen in de tekst van een melding --
    dat is proza dat toevallig in code staat.
    """
    assert not impact_tests._leest_dit_pad(_NOEMT_IN_MELDING, "CLAUDE.md")


def test_een_ANDER_bestand_met_dezelfde_naam_telt_niet() -> None:
    """Gemeten met een losse `bevat`-vergelijking: een wijziging in de hoofd-README selecteerde
    een test die `docs/compliance/soc2/README.md` leest. Ander bestand, zelfde naam."""
    assert not impact_tests._leest_dit_pad(_ANDERE_README, "README.md")


def test_de_SELECTIE_kiest_een_bewaker_van_een_instructiebestand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Via `geraakte_tests`, niet via de hulpfunctie -- anders bewaakt de test de bedrading niet.

    Dit is het gat waarvoor deze hele taak bestond: een wijziging in CLAUDE.md selecteerde
    NUL tests, terwijl de hook daarna "alle pre-commit checks geslaagd" meldde.
    """
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_bewaker.py").write_text(_LEEST, encoding="utf-8")
    (tmp_path / "tests" / "test_noemt.py").write_text(_NOEMT_IN_DOCSTRING, encoding="utf-8")
    monkeypatch.setattr(impact_tests, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        impact_tests, "_testbestanden", lambda: ["tests/test_bewaker.py", "tests/test_noemt.py"]
    )

    assert impact_tests.geraakte_tests(["CLAUDE.md"]) == ["tests/test_bewaker.py"]


def test_een_docstring_die_PRECIES_het_pad_is_telt_ook_niet() -> None:
    """Het smalle geval waarin de docstring-uitsluiting nog verschil maakt.

    Onder de EXACTE padvergelijking doet die uitsluiting bijna niets meer: een docstring die
    het bestand in proza noemt ("... uit CLAUDE.md.") is als geheel nooit gelijk aan het pad.
    Ze telt nog in precies dit geval -- een docstring die letterlijk het pad IS. Dat is smal,
    en daarom staat het hier expliciet in plaats van als onbewezen bescherming in de code.
    """
    assert not impact_tests._leest_dit_pad(_DOCSTRING_IS_PRECIES_HET_PAD, "CLAUDE.md")

