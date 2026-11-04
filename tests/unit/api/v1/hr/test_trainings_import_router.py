"""Router-tests voor `POST /api/v1/hr/trainings/import` en `GET /api/v1/hr/trainings`.

Zelfde discipline als `test_skills_import_router.py` -- repository gemockt, toetst alleen
de HTTP-laag. Minder uitgebreid dan het skills-testbestand: de generieke mechanismen (admin-
gate, tenant-uit-JWT, rij-cap, bestandsvalidatie, rate limit, rij-remapping) zijn daar al
bewezen voor exact dezelfde onderliggende hulpfuncties (`_import_parsing.py`) -- hier alleen
de trainings-specifieke happy/unhappy paths.

Repository-mock via `app.dependency_overrides[get_hr_trainings_import_repository]` -- zelfde
reden als `test_skills_import_router.py`'s equivalent, niet hier herhaald."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from src.core.api.v1.hr.dependencies import (
    HRTrainingsRepository,
    get_hr_trainings_import_repository,
    require_hr_read,
    require_hr_write,
)
from src.core.api.v1.hr.trainings_import_router import router as trainings_router
from src.core.auth.auth_service import UserResponse
from src.core.database.database import get_db
from src.core.exceptions.handlers import register_exception_handlers
from src.core.repositories.hr_import_types import ImportRowError, UpsertOutcome
from src.core.shared.rate_limiter import _rate_limiter

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_rate_limiter() -> Iterator[None]:
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
    return AsyncMock(spec=HRTrainingsRepository)


@pytest.fixture
def app(mock_repo: AsyncMock) -> FastAPI:
    application = FastAPI()
    register_exception_handlers(application)
    application.include_router(trainings_router, prefix="/api/v1/hr")

    async def _mock_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    application.dependency_overrides[get_db] = _mock_db
    application.dependency_overrides[require_hr_read] = lambda: _admin_user()
    application.dependency_overrides[require_hr_write] = lambda: _admin_user()
    application.dependency_overrides[get_hr_trainings_import_repository] = lambda: mock_repo
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _csv_upload(rows: list[dict[str, str]]) -> dict[str, tuple[str, BytesIO, str]]:
    header = ",".join(rows[0].keys()) if rows else "name"
    lines = [header] + [",".join(str(v) for v in row.values()) for row in rows]
    content = "\n".join(lines).encode("utf-8")
    return {"file": ("trainings.csv", BytesIO(content), "text/csv")}


class TestAdminGate:
    def test_import_requires_admin_role(self, app: FastAPI) -> None:
        def _deny() -> UserResponse:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Admin access required")

        app.dependency_overrides[require_hr_read] = _deny
        app.dependency_overrides[require_hr_write] = _deny
        client = TestClient(app)

        response = client.post(
            "/api/v1/hr/trainings/import",
            data={"entity_type": "training"},
            files=_csv_upload([{"name": "Onboarding"}]),
        )

        assert response.status_code == 403


class TestHappyPath:
    def test_import_training_rows_calls_the_repository_and_returns_200(
        self, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        """Patcht ook `AuditService` -- zelfde reden als `test_skills_import_router.py`'s
        equivalent (code-review BE-AGT-060 dag 3, finding 5), niet hier herhaald."""
        mock_repo.upsert_trainings = AsyncMock(
            return_value=UpsertOutcome(inserted=1, updated=0, row_errors=[])
        )
        with patch("src.core.api.v1.hr.trainings_import_router.AuditService") as mock_audit:
            mock_audit.log_event = AsyncMock(return_value=True)
            response = client.post(
                "/api/v1/hr/trainings/import",
                data={"entity_type": "training"},
                files=_csv_upload([{"name": "Onboarding"}]),
            )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["data"]["inserted"] == 1
        mock_repo.upsert_trainings.assert_awaited_once()
        mock_audit.log_event.assert_awaited_once()
        audit_await_args = mock_audit.log_event.await_args
        assert audit_await_args is not None
        assert audit_await_args.kwargs["event_type"] == "hr_trainings_import"
        assert audit_await_args.kwargs["metadata"] == {
            "inserted": 1,
            "updated": 0,
            "rejected": 0,
        }

    def test_import_employee_training_rows_calls_the_matching_repository_method(
        self, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        mock_repo.upsert_employee_trainings = AsyncMock(
            return_value=UpsertOutcome(inserted=1, updated=0, row_errors=[])
        )
        response = client.post(
            "/api/v1/hr/trainings/import",
            data={"entity_type": "employee_training"},
            files=_csv_upload([{"user_email": "jan@example.test", "training_name": "Onboarding"}]),
        )

        assert response.status_code == 200
        mock_repo.upsert_employee_trainings.assert_awaited_once()

    def test_list_trainings_calls_the_repository_with_pagination(
        self, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        mock_repo.list_trainings = AsyncMock(return_value=[])
        response = client.get("/api/v1/hr/trainings?limit=10&offset=5")

        assert response.status_code == 200
        mock_repo.list_trainings.assert_awaited_once()
        await_args = mock_repo.list_trainings.await_args
        assert await_args is not None
        assert await_args.kwargs == {"limit": 10, "offset": 5}


class TestRateLimit:
    def test_the_write_endpoint_actually_enforces_its_rate_limit(
        self, app: FastAPI, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        """Zelfde bewijs als `test_skills_import_router.py::TestRateLimit` -- elke `@hr_import_
        *_limit`-toepassing op elk endpoint is een APARTE decorator-aanroep die zijn eigen
        `Request`-detectie moet slagen; de skills-tests bewijzen niets over de trainings-
        router (`GET /skills` had deze parameter al aanvankelijk niet, `GET /trainings` had
        hem toevallig al wel -- dat had zonder deze test onopgemerkt kunnen blijven)."""
        app.dependency_overrides[require_hr_read] = lambda: _admin_user(tenant_id=997)
        app.dependency_overrides[require_hr_write] = lambda: _admin_user(tenant_id=997)
        mock_repo.upsert_trainings = AsyncMock(
            return_value=UpsertOutcome(inserted=1, updated=0, row_errors=[])
        )

        statuses = []
        for _ in range(11):  # limiet is 10/minuut
            response = client.post(
                "/api/v1/hr/trainings/import",
                data={"entity_type": "training"},
                files=_csv_upload([{"name": "Onboarding"}]),
            )
            statuses.append(response.status_code)

        assert statuses[:10] == [200] * 10
        assert statuses[10] == 429

    def test_the_read_endpoint_actually_enforces_its_rate_limit(
        self, app: FastAPI, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        app.dependency_overrides[require_hr_read] = lambda: _admin_user(tenant_id=996)
        app.dependency_overrides[require_hr_write] = lambda: _admin_user(tenant_id=996)
        mock_repo.list_trainings = AsyncMock(return_value=[])

        statuses = [client.get("/api/v1/hr/trainings").status_code for _ in range(61)]

        assert statuses[:60] == [200] * 60
        assert statuses[60] == 429


class TestPartialFailureEnvelope:
    def test_an_invalid_status_value_is_reported_as_a_row_error_not_a_500(
        self, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        """`status` is een gesloten vocabulaire op de repository-laag (CHECK-constraint) --
        de router mag een ongeldige waarde niet als serverfout laten doorschieten."""
        mock_repo.upsert_employee_trainings = AsyncMock(
            return_value=UpsertOutcome(
                inserted=0,
                updated=0,
                row_errors=[
                    ImportRowError(
                        row_index=1,
                        message="status moet een van ('assigned', 'in_progress', "
                        "'completed') zijn, kreeg 'bogus'",
                    )
                ],
            )
        )
        response = client.post(
            "/api/v1/hr/trainings/import",
            data={"entity_type": "employee_training"},
            files=_csv_upload(
                [
                    {
                        "user_email": "jan@example.test",
                        "training_name": "Onboarding",
                        "status": "bogus",
                    }
                ]
            ),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["inserted"] == 0
        assert len(body["data"]["errors"]) == 1


class TestConcurrentImportConflict:
    def test_a_unique_constraint_violation_becomes_a_409_not_an_uncaught_500(
        self, client: TestClient, mock_repo: AsyncMock
    ) -> None:
        """Zelfde race als `test_skills_import_router.py`'s equivalent -- zie die module's
        docstring voor de onderbouwing, niet hier herhaald."""
        mock_repo.upsert_trainings = AsyncMock(
            side_effect=IntegrityError(
                "INSERT INTO trainings ...", {}, Exception("UNIQUE constraint failed")
            )
        )
        response = client.post(
            "/api/v1/hr/trainings/import",
            data={"entity_type": "training"},
            files=_csv_upload([{"name": "Onboarding"}]),
        )

        assert response.status_code == 409
        assert response.json()["error"]["error_code"] == "CONFLICT"
