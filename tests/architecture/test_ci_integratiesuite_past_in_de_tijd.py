"""De CI-integratiesuite is verdeeld in shards die elk binnen hun tijd passen, en samen de hele suite draaien.

Brief 2026-10-26 (integratiesuite groen en binnen de tijd). Gemeten door 8c op 2026-10-26, lokaal, zonder xdist: er
zijn 3731 integratietests (de workflow noemde nog 1731) en de hele suite kost ~105 minuten (3563 tests in 6000 s, dus
~1,7 s per test, vooral setup). De ene CI-stap had 55 minuten: hij haalde het einde niet, ook als alles groen was.

De oplossing is een matrix van jobs (`integration`), elk met een EIGEN PostgreSQL-dienst (een service-container hoort
bij een job, dus elke shard heeft zijn eigen database) en elk een deel van de testbestanden uit
`scripts/ci_integratie_shard.py`. Geen xdist binnen een job: `tests/integration/conftest.py` waarschuwt dat parallelle
workers op een gedeelde database de transactie-isolatie breken.

Wat deze guard toetst, per STRUCTUUR (YAML en AST, geen tekstzoeken):
  1. elk testbestand onder `tests/integration` dat pytest verzamelt zit in PRECIES een shard (de uitsluitingen komen
     uit `norecursedirs` in `pyproject.toml`, niet uit een lijst in het script zelf);
  2. de langste shard past, met een veiligheidsfactor, in de `timeout-minutes` van de job;
  3. de matrix in de workflow noemt precies de shards 1..N en elke stap geeft zijn nummer aan het script;
  4. de job heeft een eigen database met een testnaam (test-achtervoegsel, niet de dev-poort 5435) en de stap geeft
     die op via `SANSKRITISETU_TEST_DATABASE_URL`;
  5. geen xdist in de integratiestap.

MUTATIEBEWIJS (2026-10-26, elk een mutatie van het script of de workflow, kopie als terugweg; basis 11 groen):
    script: 1 shard i.p.v. 5                              -> ROOD (matrix en tijd)
    script: 4 shards, matrix blijft 5                     -> ROOD
    script: eerste bestand valt uit de verdeling          -> ROOD (dekking)
    script: een bestand in twee shards                    -> ROOD
    script: 4x zoveel seconden per test                   -> ROOD (tijd)
    workflow: matrix zonder shard 5                       -> ROOD
    workflow: POSTGRES_DB zonder _test                    -> ROOD
    workflow: dev-poort 5435 erbij                        -> ROOD
    workflow: -n 4 in de integratiestap                   -> ROOD
    workflow: controle op een lege bestandslijst weg      -> ROOD
    workflow: stapgrens gelijk aan jobgrens               -> ROOD
    workflow: jobgrens 20 minuten                         -> ROOD
    workflow: stap geeft het matrixnummer niet door       -> ROOD
    workflow: `timeout` om pytest 43m -> 90m              -> ROOD (Gate 2: de echte grens, niet de jobgrens)
    workflow: pytest draait `tests/integration` (hele map)-> ROOD
    workflow: de lege-lijst-controle alleen als comment   -> ROOD (structuur, geen tekst)
    workflow: de `shard N: X tests verzameld`-echo weg    -> ROOD (verzamelde aantal per shard)
    alles terug                                           -> GROEN (14 tests, 17 mutaties)
Gemeten verdeling op echte aantallen (3731 verzameld): shard 1-5 = 759, 717, 723, 722, 810 tests, 20 tot 23
minuten per shard bij 1,7 s per test (lokaal). NIET gemeten op een GitHub-runner.
"""

from __future__ import annotations

import functools
import importlib.util
import re
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import yaml

from tests.architecture._ci_workflow import logische_regels, tokeniseer

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/ci_integratie_shard.py"
WORKFLOW = REPO_ROOT / ".github/workflows/ci-feature.yml"
INTEGRATIE = REPO_ROOT / "tests/integration"
JOB = "integration"


@functools.cache
def _script() -> ModuleType:
    # Een keer geladen: het script telt alle testbestanden met een AST en dat kostte per test opnieuw tientallen
    # seconden onder belasting, tegen een testgrens van 60 s.
    spec = importlib.util.spec_from_file_location("ci_integratie_shard", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _job() -> dict[str, Any]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = data.get("jobs") or {}
    assert JOB in jobs, f"{WORKFLOW.name} heeft geen job `{JOB}`."
    return jobs[JOB]


def _stap_met_tests(job: dict[str, Any]) -> dict[str, Any]:
    stappen = [
        s for s in job.get("steps") or [] if "ci_integratie_shard.py" in str(s.get("run", ""))
    ]
    assert len(stappen) == 1, (
        "De integratiejob heeft niet precies een stap die het shardscript gebruikt."
    )
    return stappen[0]


def _pytest_tokens(stap: dict[str, Any]) -> list[str]:
    """De tokens van de logische commandoregel (comments eruit) waarop pytest echt wordt gestart."""
    regels = [
        tokeniseer(regel)
        for regel in logische_regels(str(stap["run"]))
        if "pytest" in tokeniseer(regel)
    ]
    assert len(regels) == 1, "De integratiestap start pytest niet op precies een commandoregel."
    return regels[0]


def _grens_in_de_run_seconden(stap: dict[str, Any]) -> int:
    """De WERKELIJKE grens: de `timeout ... 43m` om pytest heen, niet de 50 minuten van de job."""
    minuten = [
        int(token[:-1]) for token in _pytest_tokens(stap) if re.fullmatch(r"\d+m", token) is not None
    ]
    assert len(minuten) == 1, "De pytest-regel heeft niet precies een `timeout <n>m`."
    return minuten[0] * 60


def _door_pytest_verzameld() -> set[str]:
    """Wat pytest onder `tests/integration` verzamelt, volgens `norecursedirs` in pyproject.toml."""
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    uitgesloten = set(config["tool"]["pytest"]["ini_options"]["norecursedirs"])
    gevonden: set[str] = set()
    for pad in INTEGRATIE.rglob("test_*.py"):
        delen = set(pad.relative_to(REPO_ROOT).parts[:-1])
        if delen & uitgesloten:
            continue
        gevonden.add(pad.relative_to(REPO_ROOT).as_posix())
    return gevonden


def _shards(module: ModuleType) -> list[list[str]]:
    return [module.shard(n) for n in range(1, module.AANTAL_SHARDS + 1)]


def test_elk_testbestand_zit_in_precies_een_shard() -> None:
    module = _script()
    alle = [bestand for shard in _shards(module) for bestand in shard]

    assert (len(alle) == len(set(alle)), set(alle) == _door_pytest_verzameld()) == (True, True)


def test_er_zijn_testbestanden_zodat_de_dekking_iets_meet() -> None:
    assert len(_door_pytest_verzameld()) > 100


def test_de_langste_shard_past_met_veiligheidsfactor_in_de_tijd_van_de_job() -> None:
    module = _script()
    grens = _grens_in_de_run_seconden(_stap_met_tests(_job()))

    langste = max(module.schatting_seconden(shard) for shard in _shards(module))

    assert langste <= grens, (
        f"De langste shard schat {langste:.0f} s (met factor {module.VEILIGHEIDSFACTOR}) maar de `timeout` om "
        f"pytest heeft {grens} s. Meer shards in scripts/ci_integratie_shard.py en in de matrix."
    )


def test_een_enkele_shard_zou_de_hele_suite_niet_laten_passen() -> None:
    """De andere kant: zonder verdeling past de suite NIET; anders is `1 shard` ook een geldige uitkomst."""
    module = _script()
    alles = module.verdeel(module.gewichten(), 1)[0]

    assert module.schatting_seconden(alles) > _grens_in_de_run_seconden(_stap_met_tests(_job()))


def test_de_verdeling_is_deterministisch() -> None:
    module = _script()

    assert _shards(module) == _shards(module)


def test_de_matrix_noemt_precies_de_shards_van_het_script() -> None:
    module = _script()
    matrix = _job()["strategy"]["matrix"]["shard"]

    assert matrix == list(range(1, module.AANTAL_SHARDS + 1))


def test_de_stap_geeft_zijn_matrixnummer_aan_het_script() -> None:
    stap = _stap_met_tests(_job())

    assert (
        re.search(r"ci_integratie_shard\.py\s+\$\{\{\s*matrix\.shard\s*\}\}", stap["run"])
        is not None
    )


def test_een_lege_bestandslijst_laat_de_stap_falen_in_plaats_van_de_hele_map_te_draaien() -> None:
    """Een lege lijst zou `pytest` zonder pad laten lopen. Structuur: een `if [ -z "$SHARD_BESTANDEN" ]`-regel
    (comments eruit) en daarna een `exit 1`."""
    regels = [tokeniseer(r) for r in logische_regels(str(_stap_met_tests(_job())["run"]))]
    controle = [
        i
        for i, tokens in enumerate(regels)
        if tokens[:2] == ["if", "["] and "-z" in tokens and "$SHARD_BESTANDEN" in tokens
    ]
    uitgang = [i for i, tokens in enumerate(regels) if tokens[:2] == ["exit", "1"]]

    assert controle and uitgang and min(uitgang) > min(controle)


def test_pytest_krijgt_de_bestanden_van_het_script_en_geen_hele_map() -> None:
    """De shard draait ALLEEN zijn bestanden: een pytest-regel met `tests/integration` of zonder de lijst zou per
    shard de hele suite draaien."""
    tokens = _pytest_tokens(_stap_met_tests(_job()))

    assert "$SHARD_BESTANDEN" in tokens and not [t for t in tokens if t.startswith("tests/integration")]


def test_elke_shard_zet_zijn_verzamelde_aantal_in_het_joblog() -> None:
    """De regie telt de verzamelde aantallen van de shards op tegen 3731: de onafhankelijke meting naast de
    AST-schatting van het script. Structuur: een `VERZAMELD=`-toewijzing waarin pytest met `--collect-only` draait
    (comments eruit) en een `echo` die `tests verzameld` meldt."""
    regels = [tokeniseer(r) for r in logische_regels(str(_stap_met_tests(_job())["run"]))]
    toewijzing = [
        i
        for i, tokens in enumerate(regels)
        if any(tok.startswith("VERZAMELD=") and "--collect-only" in tok for tok in tokens)
    ]
    melding = [
        i
        for i, tokens in enumerate(regels)
        if tokens[:1] == ["echo"] and any("tests verzameld" in tok and "VERZAMELD" in tok for tok in tokens)
    ]

    assert toewijzing and melding and min(melding) > min(toewijzing)


def test_de_timeout_om_pytest_is_kleiner_dan_de_stapgrens_en_die_kleiner_dan_de_jobgrens() -> None:
    job = _job()
    stap = _stap_met_tests(job)

    assert (
        _grens_in_de_run_seconden(stap) < int(stap["timeout-minutes"]) * 60
        and int(stap["timeout-minutes"]) < int(job["timeout-minutes"])
    )


def test_de_job_heeft_een_eigen_database_met_een_testnaam() -> None:
    job = _job()
    postgres = job["services"]["postgres"]
    naam = postgres["env"]["POSTGRES_DB"]
    url = urlsplit(_stap_met_tests(job)["env"]["SANSKRITISETU_TEST_DATABASE_URL"])
    poorten = [str(p) for p in postgres.get("ports", [])]

    assert (
        naam.endswith("_test"),
        url.path.lstrip("/") == naam,
        url.port != 5435,
        any(p.startswith("5435:") for p in poorten),
    ) == (True, True, True, False)


def test_geen_xdist_in_de_integratiestap() -> None:
    run = str(_stap_met_tests(_job())["run"])

    assert re.search(r"(^|\s)(-n\s*\S+|--numprocesses|-p\s+xdist|--dist)(\s|$)", run) is None


def test_de_stap_heeft_een_eigen_grens_onder_die_van_de_job() -> None:
    job = _job()
    stap = _stap_met_tests(job)

    assert int(stap["timeout-minutes"]) < int(job["timeout-minutes"])
