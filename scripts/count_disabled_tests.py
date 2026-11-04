"""Ratchet op tests die in de blokkerende poort NOOIT draaien (ADR-036 OP-196, OP-201).

**Waarom dit een script is en geen architecture-test.** De vorige drie versies waren een
AST-guard in `tests/architecture/test_disabled_tests_do_not_grow.py`. Die telde een OPSOMMING VAN
SYNTAXVORMEN, en pytest kent er meer: een onafhankelijke review heeft met echte pytest 8.4.2
TWINTIG vormen aangetoond die een test niet laten draaien terwijl die guard groen bleef -- onder
meer een alias-van-een-alias, `pytestmark` via `AnnAssign`/`AugAssign`/tuple-doel,
`pytest.param(marks=pytest.mark.skip(...))`, `collect_ignore` in een conftest,
`pytest.skip(..., allow_module_level=True)` en `from unittest import skip`. De ronden liepen van 4
gemiste vormen naar 20; nog een ronde vormen bijschrijven is een verliezende race.

Dit script laat daarom PYTEST ZELF de verzameling opleveren. Het verzamelt de poort (`-collect-only`
in-proces) en vraagt per verzameld item `item.iter_markers()`. Daarmee zijn aliassen, `pytestmark`
op module- en klasseniveau, `pytest.param(marks=...)`, unittest-decorators, `collect_ignore`,
geneste klassen en de `Test*`/`test_*`-filtering per CONSTRUCTIE gedekt in plaats van per bedachte
variant. En de valse positieven van de AST-versie verdwijnen: een gewone `reader.skip(4)` als
eerste statement is voor pytest geen skip, dus ook niet voor dit script.

**Waarom niet in een test:** gemeten 2026-09-02 kost de collectie van de vier poortmappen 16,5s
warm en 59-70s koud (16.300 tests; het verschil is de bytecode-cache, en CI draait altijd koud),
terwijl de blokkerende poortstap met `--timeout=60` draait. Een test die dit als subproces doet
wordt dus gekild. Vandaar een eigen, blokkerende CI-stap. Besluit Rakesh 2026-09-02, met de
expliciete GO die `quality-gates.md` voor een nieuwe poort eist.

**Wat telt als "draait nooit":**

- een `skip`-marker die op het item van toepassing is, langs welke weg ook (`iter_markers` loopt
  de hele keten af: functie, klasse, module, en de marks van een `pytest.param`);
- een `xfail`-marker met `run=False` -- de test wordt dan niet uitgevoerd, dus zijn asserties
  draaien nooit, ook al rapporteert pytest `xfailed`.

**Wat NIET meetelt: een `skipif`.** Bewust, en om een reden die het noemen waard is. Op het moment
van verzamelen is de voorwaarde AL geevalueerd -- `pytest.mark.skipif(not PYOTP_AVAILABLE, ...)`
levert `args=(True,)` of `(False,)` afhankelijk van wat er op de machine staat. Een marker-object
kan dus niet vertellen of de voorwaarde een letterlijke `True` was of een berekende. Meetellen zou
deze telling omgevingsafhankelijk maken, en dat is precies waarom de AST-versie statisch telde.
De ontwijking `skipif(<constante>, ...)` wordt daarom niet GETELD maar VERBODEN, door
`tests/architecture/test_disabled_tests_do_not_grow.py`; dat is een AST-vraag en hoort daar.

Gebruik:

    python scripts/count_disabled_tests.py                  # poort: faalt bij een afwijking
    python scripts/count_disabled_tests.py --write-baseline  # basislijn opnieuw vastleggen
    python scripts/count_disabled_tests.py --list            # welke tests het zijn
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = Path(__file__).resolve().parent / "disabled_tests_baseline.json"

#: De mappen van de blokkerende CI-stap. `test_the_gate_dirs_match_the_ci_step` in
#: `tests/architecture/test_disabled_tests_do_not_grow.py` kruiscontroleert dit tegen de workflow.
#: Die controle is een TUPLE-vergelijking, dus de volgorde hier moet gelijk zijn aan de
#: volgorde op de commandoregel van die stap.
#:
#: `tests/safety` en `tests/ml` toegevoegd 2026-09-07 (ADR-036 OP-194): gemeten skip-vrij
#: en samen 89 tests. `tests/fixtures` en `tests/regression` zijn er BEWUST buiten
#: gelaten -- zie de OP-194-rij voor de meting per map.
GATE_DIRS = (
    "tests/unit",
    "tests/architecture",
    "tests/core",
    "tests/contracts",
    "tests/safety",
    "tests/ml",
)

#: Exact de uitsluitingen van die stap. Zonder deze meet het script iets anders dan de poort.
#: `tests/core/agents/test_focus_builder_chat_agent.py` stond hier tot 2026-09-17. Die
#: uitsluiting is weggehaald nadat gemeten was dat zijn vier tests slagen en gemockt zijn
#: (gerepareerd 2026-08-30, commit 1d3ac699); de reden die erbij stond ("9 verouderde
#: tests, OP-11") klopte op geen van beide punten meer.
GATE_IGNORES = ("tests/unit/generated_p1_e2e_1.py",)

#: De markerexpressie van die stap.
GATE_MARKER_EXPRESSION = "not requires_ollama"


class _Verzamelaar:
    """Pytest-plugin die per verzameld item vaststelt of hij nooit draait."""

    def __init__(self) -> None:
        self.per_bestand: dict[str, int] = {}
        self.node_ids: dict[str, list[str]] = {}
        self.verzameld = 0
        self.collectiefouten: list[str] = []

    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        for item in items:
            self.verzameld += 1
            if not _draait_nooit(item):
                continue
            try:
                rel = str(item.path.relative_to(REPO_ROOT))
            except ValueError:
                rel = str(item.path)
            rel = rel.replace("\\", "/")
            self.per_bestand[rel] = self.per_bestand.get(rel, 0) + 1
            self.node_ids.setdefault(rel, []).append(item.nodeid)

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.failed:
            self.collectiefouten.append(str(report.fspath))


def _draait_nooit(item: pytest.Item) -> bool:
    """True als dit verzamelde item onder geen enkele voorwaarde wordt uitgevoerd."""
    for _ in item.iter_markers(name="skip"):
        return True
    for marker in item.iter_markers(name="xfail"):
        if marker.kwargs.get("run") is False:
            return True
    return False


def meet() -> _Verzamelaar:
    """Verzamel de poort en geef de telling. Faalt LUID bij een collectiefout."""
    verzamelaar = _Verzamelaar()
    argumenten = [
        "-c",
        str(REPO_ROOT / "pyproject.toml"),
        *[str(REPO_ROOT / wortel) for wortel in GATE_DIRS],
        "--collect-only",
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
        "-m",
        GATE_MARKER_EXPRESSION,
        # `addopts` in `pyproject.toml` stuurt het json-rapport naar `logs/test_report.json`.
        # Zonder deze override overschrijft DEZE collectie het rapport van de echte testrun --
        # gemeten: daarna stond er `summary: {"total": 0, "collected": 16300}` in. In CI draait
        # deze stap direct na de poortstap, dus dat rapport zou meteen weg zijn. Niets LEEST het
        # programmatisch, maar het is wel de gedocumenteerde plek waar de uitslag van de laatste
        # run staat (`docs/backend/features/BE-SEC-007-gdpr-compliance-real-tests.md:227`), en
        # een diagnose die daarop leunt zou stilletjes het verkeerde bestand lezen.
        "--json-report-file=%s" % (Path(tempfile.gettempdir()) / "collect_only_report.json"),
        *["--ignore=%s" % (REPO_ROOT / pad) for pad in GATE_IGNORES],
    ]
    code = pytest.main(argumenten, plugins=[verzamelaar])
    # `--continue-on-collection-errors` staat in `addopts`, dus een kapotte module maakt de
    # collectie niet ongeldig maar wel ONVOLLEDIG -- en dan meet dit script te LAAG en zou het
    # groen melden. Daarom hier expliciet stoppen.
    if verzamelaar.collectiefouten:
        raise SystemExit(
            "COLLECTIEFOUT in %d module(s), dus de telling is onvolledig:\n  %s\n"
            "Repareer die eerst; een onvolledige collectie meet te laag en zou deze poort "
            "stilletjes groen laten."
            % (len(verzamelaar.collectiefouten), "\n  ".join(verzamelaar.collectiefouten))
        )
    if verzamelaar.verzameld == 0:
        raise SystemExit(
            "NUL tests verzameld over %s (pytest gaf %s). Zonder verzamelde tests bewaakt deze "
            "poort niets." % (list(GATE_DIRS), code)
        )
    return verzamelaar


def lees_basislijn() -> dict[str, int]:
    if not BASELINE.exists():
        raise SystemExit(
            "Basislijn %s ontbreekt. Leg hem vast met --write-baseline en commit hem mee."
            % BASELINE.name
        )
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in data["per_bestand"].items()}


def schrijf_basislijn(verzamelaar: _Verzamelaar) -> None:
    inhoud = {
        # Als lijst en niet als een lange string, zodat geen regel boven de 100 tekens uitkomt.
        "_toelichting": [
            "Aantal tests per bestand dat in de blokkerende poort NOOIT draait.",
            "Gemeten met scripts/count_disabled_tests.py via pytest-collectie.",
            "Elk getal mag alleen OMLAAG; wie er een repareert past dit bestand aan",
            "in DEZELFDE commit (--write-baseline). Zie ADR-036 OP-196 en OP-201.",
        ],
        "totaal": sum(verzamelaar.per_bestand.values()),
        "per_bestand": dict(sorted(verzamelaar.per_bestand.items())),
    }
    BASELINE.write_text(json.dumps(inhoud, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(
        "Basislijn geschreven: %d over %d bestanden -> %s"
        % (inhoud["totaal"], len(verzamelaar.per_bestand), BASELINE.name)
    )


def vergelijk(gemeten: dict[str, int], basislijn: dict[str, int]) -> int:
    toegenomen = {
        pad: (aantal, basislijn.get(pad, 0))
        for pad, aantal in sorted(gemeten.items())
        if aantal > basislijn.get(pad, 0)
    }
    afgenomen = {
        pad: (gemeten.get(pad, 0), verwacht)
        for pad, verwacht in sorted(basislijn.items())
        if gemeten.get(pad, 0) < verwacht
    }

    if toegenomen:
        print("\nFOUT -- deze bestanden hebben MEER tests die nooit draaien (nu vs vastgelegd):")
        for pad, (nu, was) in toegenomen.items():
            print("  %-64s %d vs %d" % (pad, nu, was))
        print(
            "\nEen test uitzetten om de suite groen te houden staat op de NOOIT-lijst van "
            "CLAUDE.md. Valt jouw test om in de volledige suite maar niet los, dan is er "
            "testvervuiling -- zoek de gedeelde toestand op in plaats van de test uit te zetten.\n"
            "Moet de test echt overgeslagen worden omdat iets ONTBREEKT op de machine, gebruik "
            "dan `@pytest.mark.skipif(<echte voorwaarde>, reason=...)`; die telt niet mee, want "
            "die draait zodra de voorwaarde het toelaat.\n"
            "Let op: `xfail(run=False)` telt WEL mee -- de test wordt dan niet uitgevoerd. Wil je "
            "een bekende bug documenteren zonder dekking te verliezen, gebruik `xfail` ZONDER "
            "`run=False`."
        )
    if afgenomen:
        print("\nFOUT -- deze bestanden hebben MINDER tests die nooit draaien (nu vs vastgelegd):")
        for pad, (nu, was) in afgenomen.items():
            print("  %-64s %d vs %d" % (pad, nu, was))
        print(
            "\nMooi werk. Werk de basislijn bij in DEZELFDE commit:\n"
            "  python scripts/count_disabled_tests.py --write-baseline\n"
            "Zonder dat blijft er ongebruikte ruimte staan en meet deze poort daar niets meer."
        )
    if toegenomen or afgenomen:
        return 1
    print(
        "OK -- %d tests die nooit draaien, over %d bestanden, gelijk aan de basislijn."
        % (sum(gemeten.values()), len(gemeten))
    )
    return 0


def main() -> int:
    ontleder = argparse.ArgumentParser(description=__doc__)
    ontleder.add_argument(
        "--write-baseline", action="store_true", help="leg de huidige telling vast"
    )
    ontleder.add_argument("--list", action="store_true", help="som de node-ids op")
    argumenten = ontleder.parse_args()

    verzamelaar = meet()
    print(
        "Verzameld: %d tests; nooit draaiend: %d over %d bestanden."
        % (
            verzamelaar.verzameld,
            sum(verzamelaar.per_bestand.values()),
            len(verzamelaar.per_bestand),
        )
    )
    if argumenten.list:
        for pad in sorted(verzamelaar.node_ids):
            print("\n%s (%d):" % (pad, verzamelaar.per_bestand[pad]))
            for node_id in verzamelaar.node_ids[pad]:
                print("  %s" % node_id)
    if argumenten.write_baseline:
        schrijf_basislijn(verzamelaar)
        return 0
    return vergelijk(verzamelaar.per_bestand, lees_basislijn())


if __name__ == "__main__":
    sys.exit(main())
