"""Router-tests voor `POST /api/v1/hr/skills/import` en `GET /api/v1/hr/skills`.

Repository gemockt -- dit bestand toetst de HTTP-laag (admin-gate, tenant-uit-JWT,
rij-cap-afwijzing, kapot-bestand-afwijzing, deel-fout-envelope), niet de repository-logica
zelf (die heeft zijn eigen, echte-DB-gebaseerde tests in tests/unit/repositories/).

Repository-mock via `app.dependency_overrides[get_hr_skills_import_repository]`, NIET via
`patch(".HRSkillsImportRepository")` -- de router construeert de repository niet meer zelf
(code-review BE-AGT-060 dag 3, finding 4: directe instantiatie in de handler was een ADR-033
Laag 1-patroon; nu een `Depends()`-provider in `dependencies.py`, zelfde patroon als
`get_db`/`require_hr_write`)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Iterator
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from src.core.api.v1.hr.dependencies import (
    HRSkillsImportRepository,
    get_hr_skills_import_repository,
    require_hr_read,
    require_hr_write,
)
from src.core.api.v1.hr.skills_import_router import router as skills_router
from src.core.auth.auth_service import UserResponse
from src.core.database.database import get_db
from src.core.exceptions.handlers import register_exception_handlers
from src.core.repositories.hr_import_types import ImportRowError, UpsertOutcome
from src.core.shared.rate_limiter import _rate_limiter

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_rate_limiter() -> Iterator[None]:
    """Voorkomt dat een limit-test uit een eerdere testfunctie deze test laat meeliften."""
    _rate_limiter._requests.clear()
    yield
    _rate_limiter._requests.clear()


def _admin_user(tenant_id: int = 1, user_id: int = 42) -> UserResponse:
    return UserResponse(
        id=user_id, email="admin@example.test", tenant_id=tenant_id, roles=["admin"]
    )


@pytest.fixture
def mock_repo() -> AsyncMock:
    # spec= laat een typo'de methodenaam op de router-kant echt falen (AttributeError) i.p.v.
    # stil een verse AsyncMock terug te geven (Gate 2 code-review, BE-AGT-060 dag 3).
    return AsyncMock(spec=HRSkillsImportRepository)


@pytest.fixture
def app(mock_repo: AsyncMock) -> FastAPI:
    application = FastAPI()
    # Zonder dit registreert de app geen handler voor ValidationError/SanskritiError, en
    # propageert client.post(...) de exception rauw i.p.v. als 400-response (production's
    # create_app() roept dit al aan -- deze minimale testapp moet het zelf ook doen).
    register_exception_handlers(application)
    application.include_router(skills_router, prefix="/api/v1/hr")

    async def _mock_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    application.dependency_overrides[get_db] = _mock_db
    application.dependency_overrides[require_hr_read] = lambda: _admin_user()
    application.dependency_overrides[require_hr_write] = lambda: _admin_user()
    application.dependency_overrides[get_hr_skills_import_repository] = lambda: mock_repo
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _csv_upload(rows: list[dict[str, str]]) -> dict[str, tuple[str, BytesIO, str]]:
    header = ",".join(rows[0].keys()) if rows else "name"
    lines = [header] + [",".join(str(v) for v in row.values()) for row in rows]
    content = "\n".join(lines).encode("utf-8")
    return {"file": ("skills.csv", BytesIO(content), "text/csv")}


class TestAdminGate:
    def test_import_requires_admin_role(self, app: FastAPI) -> None:
        def _deny() -> UserResponse:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Admin access required")

        app.dependency_overrides[require_hr_read] = _deny
        app.dependency_overrides[require_hr_write] = _deny
        client = TestClient(app)

        response = client.post(
            "/api/v1/hr/skills/import",
            data={"entity_type": "skill"},
            files=_csv_upload([{"name": "Excel"}]),
        )

        assert response.status_code == 403

    def test_list_requires_admin_role(self, app: FastAPI) -> None:
        def _deny() -> UserResponse:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Admin access required")

        app.dependency_overrides[require_hr_read] = _deny
        app.dependency_overrides[require_hr_write] = _deny
        client = TestClient(app)

        response = client.get("/api/v1/hr/skills")

        assert response.status_code == 403


class TestTenantFromJWT:
    def test_import_uses_the_authenticated_users_tenant_id_not_the_request_body(
        self, app: FastAPI, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        """De rijschema's hebben geen tenant_id-veld -- dit bewijst dat de repository-aanroep
        de tenant van de GEAUTHENTICEERDE gebruiker gebruikt, niet iets uit het bestand."""
        app.dependency_overrides[require_hr_read] = lambda: _admin_user(tenant_id=77)
        app.dependency_overrides[require_hr_write] = lambda: _admin_user(tenant_id=77)
        mock_repo.upsert_skills = AsyncMock(
            return_value=UpsertOutcome(inserted=1, updated=0, row_errors=[])
        )

        response = client.post(
            "/api/v1/hr/skills/import",
            data={"entity_type": "skill"},
            files=_csv_upload([{"name": "Excel"}]),
        )

        assert response.status_code == 200
        mock_repo.upsert_skills.assert_awaited_once()
        await_args = mock_repo.upsert_skills.await_args
        assert await_args is not None
        assert await_args.args[0] == 77


class TestBatchCapAndFileValidation:
    def test_rejects_a_batch_over_the_row_cap(self, client: TestClient) -> None:
        rows = [{"name": f"Skill{i}"} for i in range(501)]

        response = client.post(
            "/api/v1/hr/skills/import",
            data={"entity_type": "skill"},
            files=_csv_upload(rows),
        )

        assert response.status_code == 400

    def test_rejects_an_empty_file(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/hr/skills/import",
            data={"entity_type": "skill"},
            files={"file": ("empty.csv", BytesIO(b""), "text/csv")},
        )

        assert response.status_code == 400

    def test_rejects_an_unknown_content_type(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/hr/skills/import",
            data={"entity_type": "skill"},
            files={"file": ("skills.bin", BytesIO(b"not a real file"), "application/x-msdownload")},
        )

        assert response.status_code == 400

    def test_rejects_a_file_over_the_size_limit(self, client: TestClient) -> None:
        oversized = b"name\n" + b"A" * (6 * 1024 * 1024)

        response = client.post(
            "/api/v1/hr/skills/import",
            data={"entity_type": "skill"},
            files={"file": ("skills.csv", BytesIO(oversized), "text/csv")},
        )

        assert response.status_code == 400


class TestPartialFailureEnvelope:
    def test_returns_both_successes_and_row_errors_in_one_response(
        self, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        mock_repo.upsert_skills = AsyncMock(
            return_value=UpsertOutcome(
                inserted=1,
                updated=0,
                row_errors=[ImportRowError(row_index=2, message="name is verplicht")],
            )
        )
        # JSON, niet CSV: een lege-string-waarde serialiseert in CSV naar een lege regel,
        # die csv.DictReader stilzwijgend overslaat -- dat zou hier de tweede rij laten
        # verdwijnen voor de test hem kan aanbieden (gevonden tijdens het schrijven van
        # deze test: de aanname "2 rijen" bleek er zo 1 te worden).
        payload = json.dumps([{"name": "Excel"}, {"name": ""}]).encode("utf-8")
        response = client.post(
            "/api/v1/hr/skills/import",
            data={"entity_type": "skill"},
            files={"file": ("skills.json", BytesIO(payload), "application/json")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["inserted"] == 1
        assert body["data"]["errors"] == [{"row_index": 2, "message": "name is verplicht"}]

    def test_a_pydantic_validation_failure_and_a_repository_failure_both_appear_with_correct_row_numbers(
        self, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        """CSV-bestandsrijnummers zijn 1-based INCLUSIEF de headerregel (zoals een gebruiker het
        in Excel ziet, sprint-plan Ontwerpbeslissing 3) -- de header is Excel-rij 1, dus de
        eerste datarij is Excel-rij 2. Die eerste datarij heeft een ongeldig getal (Pydantic-
        fout, nooit de repository bereikt); de DERDE datarij (Excel-rij 4) wordt door de
        repository afgewezen. Beide moeten met het JUISTE Excel-rijnummer in de eindrespons
        staan, niet het positienummer binnen de gefilterde deelverzameling."""
        # De repository ziet alleen de tweede en derde datarij (Excel-rij 3 en 4) -- de
        # eerste datarij viel al af op Pydantic-niveau. Zijn eigen row_errors tellen vanaf
        # 1 over DIE gefilterde lijst -- rij-index 2 daar is dus de OORSPRONKELIJKE Excel-
        # rij 4.
        mock_repo.upsert_role_requirements = AsyncMock(
            return_value=UpsertOutcome(
                inserted=1,
                updated=0,
                row_errors=[ImportRowError(row_index=2, message="onbekende rol: Ghost")],
            )
        )
        response = client.post(
            "/api/v1/hr/skills/import",
            data={"entity_type": "role_requirement"},
            files=_csv_upload(
                [
                    {
                        "role_name": "Accountant",
                        "skill_name": "IFRS",
                        "required_level": "not-a-number",
                    },
                    {"role_name": "Accountant", "skill_name": "IFRS", "required_level": "3"},
                    {"role_name": "Ghost", "skill_name": "IFRS", "required_level": "3"},
                ]
            ),
        )

        assert response.status_code == 200
        errors = response.json()["data"]["errors"]
        assert [e["row_index"] for e in errors] == [2, 4]


class TestHappyPath:
    def test_import_skill_rows_calls_the_repository_and_returns_200(
        self, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        """Patcht ook `AuditService` -- een `AsyncMock()`-`db` laat `log_event()`'s eigen
        `async with db.begin_nested():` op een `TypeError` stuklopen, die door `log_event`'s
        eigen `except Exception` EN de router's `best_effort()` wordt opgevangen. Zonder deze
        assertie zou een kwarg-typo in de audit-aanroep dus onopgemerkt groen blijven (code-
        review BE-AGT-060 dag 3, finding 5)."""
        mock_repo.upsert_skills = AsyncMock(
            return_value=UpsertOutcome(inserted=2, updated=0, row_errors=[])
        )
        with patch("src.core.api.v1.hr.skills_import_router.AuditService") as mock_audit:
            mock_audit.log_event = AsyncMock(return_value=True)
            response = client.post(
                "/api/v1/hr/skills/import",
                data={"entity_type": "skill"},
                files=_csv_upload([{"name": "Excel"}, {"name": "IFRS"}]),
            )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["data"]["inserted"] == 2
        mock_audit.log_event.assert_awaited_once()
        audit_await_args = mock_audit.log_event.await_args
        assert audit_await_args is not None
        assert audit_await_args.kwargs["event_type"] == "hr_skills_import"
        assert audit_await_args.kwargs["metadata"] == {
            "inserted": 2,
            "updated": 0,
            "rejected": 0,
        }

    def test_import_accepts_json_content_type(
        self, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        payload = json.dumps([{"name": "Excel"}]).encode("utf-8")
        mock_repo.upsert_skills = AsyncMock(
            return_value=UpsertOutcome(inserted=1, updated=0, row_errors=[])
        )
        response = client.post(
            "/api/v1/hr/skills/import",
            data={"entity_type": "skill"},
            files={"file": ("skills.json", BytesIO(payload), "application/json")},
        )

        assert response.status_code == 200

    def test_list_skills_calls_the_repository_with_pagination(
        self, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        mock_repo.list_skills = AsyncMock(return_value=[])
        response = client.get("/api/v1/hr/skills?limit=10&offset=5")

        assert response.status_code == 200
        mock_repo.list_skills.assert_awaited_once()
        await_args = mock_repo.list_skills.await_args
        assert await_args is not None
        assert await_args.kwargs == {"limit": 10, "offset": 5}


class TestRateLimit:
    def test_the_write_endpoint_actually_enforces_its_rate_limit(
        self, app: FastAPI, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        """Bewijst dat `@hr_import_write_limit` echt werkt, niet stilzwijgend niets doet.

        De decorator (`src/core/shared/rate_limiter.py::privacy_rate_limit`) vindt zijn
        sleutel via een `Request`-object in de functie-signatuur -- ONTBREEKT die parameter,
        dan slaat de wrapper de limiet stilzwijgend over (`if not request: return await
        func(...)`). Dit is precies zo'n geval geweest tijdens de implementatie (de GET-
        endpoints hadden deze parameter aanvankelijk niet) -- deze test zou dat hebben
        gevangen als hij toen al had bestaan.
        """
        app.dependency_overrides[require_hr_read] = lambda: _admin_user(tenant_id=999)
        app.dependency_overrides[require_hr_write] = lambda: _admin_user(tenant_id=999)
        mock_repo.upsert_skills = AsyncMock(
            return_value=UpsertOutcome(inserted=1, updated=0, row_errors=[])
        )

        statuses = []
        for _ in range(11):  # limiet is 10/minuut
            response = client.post(
                "/api/v1/hr/skills/import",
                data={"entity_type": "skill"},
                files=_csv_upload([{"name": "Excel"}]),
            )
            statuses.append(response.status_code)

        assert statuses[:10] == [200] * 10
        assert statuses[10] == 429

    def test_the_read_endpoint_actually_enforces_its_rate_limit(
        self, app: FastAPI, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        """Zelfde bewijs als de write-test hierboven, nu voor `@hr_import_read_limit` (60/min)
        op `GET /skills` -- de twee decorators zijn los toegepast en delen geen wrapper-state,
        dus een van de twee correct hebben bewijst niets over de ander."""
        app.dependency_overrides[require_hr_read] = lambda: _admin_user(tenant_id=998)
        app.dependency_overrides[require_hr_write] = lambda: _admin_user(tenant_id=998)
        mock_repo.list_skills = AsyncMock(return_value=[])

        statuses = [client.get("/api/v1/hr/skills").status_code for _ in range(61)]

        assert statuses[:60] == [200] * 60
        assert statuses[60] == 429


class TestConcurrentImportConflict:
    def test_a_unique_constraint_violation_becomes_a_409_not_an_uncaught_500(
        self, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        """Twee gelijktijdige imports met een overlappende nieuwe skill-naam raceren op de
        check-then-insert-lookup (uq_skills_tenant_name) -- de repository's `flush()` gooit
        dan een `IntegrityError` die de router moet vertalen, niet ongevangen laten
        doorschieten (Dag 2 final-approver-brief liet dit expliciet aan Dag 3 over)."""
        mock_repo.upsert_skills = AsyncMock(
            side_effect=IntegrityError(
                "INSERT INTO skills ...", {}, Exception("UNIQUE constraint failed")
            )
        )
        response = client.post(
            "/api/v1/hr/skills/import",
            data={"entity_type": "skill"},
            files=_csv_upload([{"name": "Excel"}]),
        )

        assert response.status_code == 409
        assert response.json()["error"]["error_code"] == "CONFLICT"
