"""De ROI-tabellen kennen geen medewerker, afdeling of persoon (SP-KLANT-04).

Een rendementscijfer per medewerker is gegevens over prestaties van personeel: OR-instemming
(WOR art. 27 lid 1 sub l) en een AVG-grondslag (art. 88) zijn dan nodig, een last die de klant niet
verwacht. De meting blijft daarom per tenant en per pack. Wie een run startte staat in de auditketen.

Deze guard bewaakt een benoemde verzameling: de kolommen van `agent_run_metrics` en
`roi_assumptions`, en de vorm van de API-antwoorden (`ROISummary`, `PackRoi`).

Mutatiebewijs (kopie als terugweg, 2026-10-10), een regel per element van de verzameling:
  ROOD: kolom `user_id` aan AgentRunMetric                      -> failed (modelkolommen)
  ROOD: kolom `department` aan RoiAssumption                    -> failed (modelkolommen)
  ROOD: veld `by_department` aan PackRoi                        -> failed (antwoordvorm)
  ROOD: `user_id` in de CREATE TABLE van de migratie            -> failed (migratietekst)
  ROOD: `byDepartment` in een frontendbestand (nieuw, `git add -N`) -> failed
  GROEN: een nieuwe kolom `notes` op AgentRunMetric             -> passed
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from src.core.analytics.roi_service import MeasuredTotals, PackRoi, ROISummary
from src.core.models.roi_models import AgentRunMetric, RoiAssumption

REPO = Path(__file__).resolve().parents[2]
MIGRATIE = REPO / "src" / "alembic" / "versions" / "20261010_roi_tabellen.py"

#: Namen die een medewerker, afdeling of persoon aanwijzen. Een benoemde verzameling, geen
#: substring op "user": `user_id` en `department` zijn de vormen die de oude frontend gebruikte.
VERBODEN_VELDEN = frozenset(
    {
        "user_id",
        "initiated_by_user_id",
        "created_by",
        "set_by",
        "set_by_user_id",
        "employee_id",
        "email",
        "name",
        "full_name",
        "department",
        "department_id",
        "by_department",
        "byDepartment",
        "person",
    }
)


def _kolommen(model: type) -> set[str]:
    return {c.name for c in model.__table__.columns}  # type: ignore[attr-defined]


def test_agent_run_metrics_has_no_employee_column() -> None:
    assert not _kolommen(AgentRunMetric) & VERBODEN_VELDEN


def test_roi_assumptions_has_no_employee_column() -> None:
    assert not _kolommen(RoiAssumption) & VERBODEN_VELDEN


def test_the_api_answer_has_no_breakdown_per_person_or_department() -> None:
    velden = (
        set(ROISummary.model_fields) | set(PackRoi.model_fields) | set(MeasuredTotals.model_fields)
    )

    assert not velden & VERBODEN_VELDEN


def test_the_migration_creates_no_employee_column() -> None:
    bron = MIGRATIE.read_text(encoding="utf-8")
    gevonden = sorted(v for v in VERBODEN_VELDEN if f'"{v}"' in bron)

    assert not gevonden, f"de migratie maakt een kolom die een medewerker aanwijst: {gevonden}"


def test_both_tables_have_a_tenant_column_that_is_not_nullable() -> None:
    for model in (AgentRunMetric, RoiAssumption):
        kolom = model.__table__.columns["tenant_id"]  # type: ignore[attr-defined]
        assert kolom.nullable is False, model.__tablename__  # type: ignore[attr-defined]


_FRONTEND_UITGESLOTEN = re.compile(r"(\.(test|spec|stories)\.(ts|tsx)$|/__tests__/|\.d\.ts$)")
_FRONTEND_VERBODEN = re.compile(r"byDepartment|by_department|DepartmentMetrics")


def test_the_frontend_has_no_roi_breakdown_per_department() -> None:
    """Het scherm toont rendement per tenant en per pack, nooit per afdeling of persoon."""
    bestanden = subprocess.run(
        ["git", "ls-files", "frontend/src"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    treffers = [
        f
        for f in bestanden
        if f.endswith((".ts", ".tsx"))
        and not _FRONTEND_UITGESLOTEN.search(f)
        and (REPO / f).is_file()
        and _FRONTEND_VERBODEN.search((REPO / f).read_text(encoding="utf-8", errors="replace"))
    ]

    assert not treffers, f"ROI per afdeling in de frontend (WOR art. 27, AVG art. 88): {treffers}"
