"""Elke workflowstap die `tests/integration` draait, geeft zijn testdatabase zelf op.

Brief 2026-10-26 (CI-integratiestappen krijgen hun testdatabase). Gemeten in CI-run 40282606456 op develop
4b5ef97c: de volledige unitsuite was groen (28021 passed) en daarna faalde de Python-job op de stap
`pytest ... tests/integration/api/v1/tenants`. `tests/integration/conftest.py` vraagt de database aan
`tests/fixtures/testdatabase.py`, en die gooit `TestdatabaseNietOpgegeven` zolang `SANSKRITISETU_TEST_DATABASE_URL`
niet gezet is. Dat is met opzet zo (ADR-036 OP-243: niet raden). De workflow had wel een PostgreSQL-dienst maar zette
de variabele in geen enkele integratiestap, dus de integratiesuite draaide op GitHub niet meer.

STRUCTUUR, GEEN TEKST: de workflows worden als YAML ingelezen. Een stap telt als integratiestap als een LOGISCHE
commandoregel van zijn `run` (comments eruit, via `_ci_workflow.logische_regels`) een argument heeft dat met
`tests/integration` begint. De variabele moet in de `env` van die stap, van zijn job of van de workflow staan, of
inline op de commandoregel (`VARIABELE=waarde pytest ...`), en een niet-lege waarde hebben.

MUTATIEBEWIJS (2026-10-26, op het echte `ci-feature.yml`, per stap; kopie als terugweg):
    variabele weg uit "Tenant integration tests"          -> `..._echte_workflows_geeft_...` ROOD
    variabele weg uit "Integration tests (full suite)"    -> ROOD
    variabele alleen als `#`-comment laten staan          -> ROOD
    variabele met lege waarde                             -> ROOD
    alles terug                                           -> GROEN
De andere kant (een legitiem geval mag niet blijven hangen) staat in de synthetische tests hieronder: env van de
stap, env van de job, inline op de commandoregel, `tests/integration` alleen in een comment, en een unitstap.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from tests.architecture._ci_workflow import (
    WORKFLOW_DIR,
    WorkflowOntleedFout,
    logische_regels,
    tokeniseer,
)

VARIABELE = "SANSKRITISETU_TEST_DATABASE_URL"
INTEGRATIEPAD = "tests/integration"
#: Sinds de matrix (brief 2026-10-26) staan de paden niet meer in de stap zelf: het shardscript geeft ze.
SHARDSCRIPT = "ci_integratie_shard.py"
DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/sanskritisetu"


def _heeft_waarde(env: object) -> bool:
    return isinstance(env, dict) and bool(str(env.get(VARIABELE, "")).strip())


def _draait_integratietests(script: str) -> list[list[str]]:
    """De getokeniseerde commandoregels die een pad onder `tests/integration` als argument hebben."""
    gevonden: list[list[str]] = []
    for regel in logische_regels(script):
        tokens = tokeniseer(regel)
        if any(token.startswith(INTEGRATIEPAD) or SHARDSCRIPT in token for token in tokens):
            gevonden.append(tokens)
    return gevonden


def integratiestappen_zonder_testdatabase(workflows: dict[str, dict[str, Any]]) -> list[str]:
    """`workflow::job::stap` van elke integratiestap die de variabele niet opgeeft."""
    zonder: list[str] = []
    for bestand, workflow in sorted(workflows.items()):
        workflow_env = workflow.get("env")
        for job_naam, job in sorted((workflow.get("jobs") or {}).items()):
            for index, stap in enumerate(job.get("steps") or []):
                script = stap.get("run")
                if not isinstance(script, str):
                    continue
                regels = _draait_integratietests(script)
                if not regels:
                    continue
                in_env = (
                    _heeft_waarde(stap.get("env"))
                    or _heeft_waarde(job.get("env"))
                    or _heeft_waarde(workflow_env)
                )
                inline = all(
                    any(
                        token.startswith(f"{VARIABELE}=") and token != f"{VARIABELE}="
                        for token in tokens
                    )
                    for tokens in regels
                )
                if not (in_env or inline):
                    naam = stap.get("name") or f"stap {index}"
                    zonder.append(f"{bestand}::{job_naam}::{naam}")
    return zonder


def _echte_workflows() -> dict[str, dict[str, Any]]:
    bestanden = sorted(WORKFLOW_DIR.glob("*.y*ml"))
    return {b.name: yaml.safe_load(b.read_text(encoding="utf-8")) for b in bestanden}


def _workflow(
    stap_env: dict[str, str] | None, run: str, job_env: dict[str, str] | None = None
) -> dict[str, Any]:
    stap: dict[str, Any] = {"name": "Integration tests", "run": run}
    if stap_env is not None:
        stap["env"] = stap_env
    job: dict[str, Any] = {"steps": [stap]}
    if job_env is not None:
        job["env"] = job_env
    return {"jobs": {"python": job}}


def test_elke_integratiestap_in_de_echte_workflows_geeft_zijn_testdatabase_op() -> None:
    assert integratiestappen_zonder_testdatabase(_echte_workflows()) == []


def test_de_echte_workflows_bevatten_integratiestappen_zodat_de_toets_iets_meet() -> None:
    echte = _echte_workflows()
    aantal = sum(
        1
        for workflow in echte.values()
        for job in (workflow.get("jobs") or {}).values()
        for stap in job.get("steps") or []
        if isinstance(stap.get("run"), str) and _draait_integratietests(stap["run"])
    )

    assert aantal >= 1


def test_alle_workflows_parseren_als_yaml() -> None:
    bestanden = sorted(WORKFLOW_DIR.glob("*.y*ml"))

    assert len(_echte_workflows()) == len(bestanden) > 0


def test_een_integratiestap_zonder_de_variabele_wordt_gevonden() -> None:
    workflows = {"x.yml": _workflow({"ENVIRONMENT": "test"}, "pytest tests/integration -q")}

    assert integratiestappen_zonder_testdatabase(workflows) == ["x.yml::python::Integration tests"]


def test_een_integratiestap_met_de_variabele_in_zijn_env_is_in_orde() -> None:
    workflows = {"x.yml": _workflow({VARIABELE: DB_URL}, "pytest tests/integration -q")}

    assert integratiestappen_zonder_testdatabase(workflows) == []


def test_een_lege_waarde_telt_niet() -> None:
    workflows = {"x.yml": _workflow({VARIABELE: ""}, "pytest tests/integration -q")}

    assert len(integratiestappen_zonder_testdatabase(workflows)) == 1


def test_de_variabele_in_de_job_env_telt() -> None:
    workflows = {
        "x.yml": _workflow(None, "pytest tests/integration -q", job_env={VARIABELE: DB_URL})
    }

    assert integratiestappen_zonder_testdatabase(workflows) == []


def test_de_variabele_inline_op_de_commandoregel_telt() -> None:
    workflows = {"x.yml": _workflow(None, f"{VARIABELE}={DB_URL} pytest tests/integration -q")}

    assert integratiestappen_zonder_testdatabase(workflows) == []


def test_de_variabele_alleen_in_een_comment_telt_niet() -> None:
    run = f"# {VARIABELE}={DB_URL}\npytest tests/integration -q"
    workflows = {"x.yml": _workflow(None, run)}

    assert len(integratiestappen_zonder_testdatabase(workflows)) == 1


def test_tests_integration_alleen_in_een_comment_maakt_een_stap_geen_integratiestap() -> None:
    run = "# draait later tests/integration\npytest tests/unit -q"
    workflows = {"x.yml": _workflow(None, run)}

    assert integratiestappen_zonder_testdatabase(workflows) == []


def test_een_stap_die_zijn_paden_van_het_shardscript_krijgt_is_een_integratiestap() -> None:
    run = 'BESTANDEN="$(python scripts/ci_integratie_shard.py 3)"\npytest $BESTANDEN -q'
    workflows = {"x.yml": _workflow({"ENVIRONMENT": "test"}, run)}

    assert integratiestappen_zonder_testdatabase(workflows) == ["x.yml::python::Integration tests"]


def test_een_shardstap_met_de_variabele_is_in_orde() -> None:
    run = 'BESTANDEN="$(python scripts/ci_integratie_shard.py 3)"\npytest $BESTANDEN -q'
    workflows = {"x.yml": _workflow({VARIABELE: DB_URL}, run)}

    assert integratiestappen_zonder_testdatabase(workflows) == []


def test_een_unitstap_zonder_variabele_blijft_in_orde() -> None:
    workflows = {"x.yml": _workflow(None, "pytest tests/unit -q")}

    assert integratiestappen_zonder_testdatabase(workflows) == []


def test_een_stap_met_twee_commandos_waarvan_een_zonder_inline_variabele_wordt_gevonden() -> None:
    run = f"{VARIABELE}={DB_URL} pytest tests/integration/a -q\npytest tests/integration/b -q"
    workflows = {"x.yml": _workflow(None, run)}

    assert len(integratiestappen_zonder_testdatabase(workflows)) == 1


def test_een_onontleedbaar_script_faalt_hard_en_valt_niet_stil_terug() -> None:
    workflows = {"x.yml": _workflow(None, "echo 'onafgesloten\npytest tests/integration")}

    with pytest.raises(WorkflowOntleedFout):
        integratiestappen_zonder_testdatabase(workflows)
