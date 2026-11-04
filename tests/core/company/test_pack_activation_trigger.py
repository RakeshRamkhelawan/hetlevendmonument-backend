"""Tests: department create/update triggers PackActivationScorer (Golden Rule R2)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest


@pytest.fixture
def mock_db_manager():
    """Create a properly mocked DatabaseManager."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_manager = MagicMock()
    mock_manager.get_session = MagicMock(return_value=mock_session)
    return mock_manager


@pytest.fixture
def mock_tenant_ctx():
    ctx = MagicMock()
    ctx.tenant_id = 1
    return ctx


@pytest.fixture
def department_service(mock_db_manager, mock_tenant_ctx):
    from src.core.company.department_service import DepartmentService

    return DepartmentService(db_manager=mock_db_manager, tenant_context=mock_tenant_ctx)


def _create_mock_department(dept_id=None, name="Test Dept", company_id=None):
    """Create a mock department with proper attributes for validation."""
    mock_dept = MagicMock()
    mock_dept.id = dept_id or uuid4()
    mock_dept.name = name
    mock_dept.company_id = company_id or uuid4()
    mock_dept.parent_department_id = None
    mock_dept.head_user_id = None
    mock_dept.board_role = "CTO"
    mock_dept.budget_monthly_tokens = None
    mock_dept.version = 1
    mock_dept.created_at = None
    mock_dept.updated_at = None
    mock_dept.tenant_id = 1
    mock_dept.domain_pack_ids = []
    return mock_dept


@pytest.mark.asyncio
async def test_create_department_calls_pack_scorer(department_service, mock_db_manager):
    """Creating a department triggers PackActivationScorer.score_all_packs()."""
    company_id = uuid4()

    # Setup mock session with proper async context manager
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    # Mock company query result
    mock_company = MagicMock()
    mock_company.id = company_id
    mock_company.company_type = "enterprise"
    mock_company.sector = "technology"

    # Setup session.execute to return company
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_company
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.add = MagicMock()

    mock_db_manager.get_session = MagicMock(return_value=mock_session)

    with patch("src.core.company.department_service.PackActivationScorer") as MockScorer:
        scorer_instance = MockScorer.return_value
        scorer_instance.score_all_packs.return_value = []

        with (
            patch.object(
                department_service, "_create_department_record", new_callable=AsyncMock
            ) as mock_create,
            patch("src.core.company.department_service.DepartmentResponse") as MockResponse,
        ):
            mock_dept = _create_mock_department(
                dept_id=uuid4(), name="Engineering", company_id=company_id
            )
            mock_create.return_value = mock_dept
            MockResponse.model_validate.return_value = MagicMock()

            await department_service.create_department(
                company_id=company_id,
                data={"name": "Engineering", "board_role": "CTO"},
            )

        scorer_instance.score_all_packs.assert_called_once()


@pytest.mark.asyncio
async def test_high_confidence_pack_is_auto_activated(department_service, mock_db_manager):
    """Packs with confidence >= 0.70 are marked activated_automatically=True."""
    import uuid

    from src.core.company.pack_activation import PackScore

    # Setup mock session
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_company = MagicMock()
    mock_company.id = uuid4()
    mock_company.company_type = "enterprise"
    mock_company.sector = "finance"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_company
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.add = MagicMock()

    mock_db_manager.get_session = MagicMock(return_value=mock_session)

    # Use PackScore instead of PackActivationResult since that's what the scorer returns
    high_conf_pack = PackScore(
        pack_id=str(uuid.uuid4()),
        pack_name="Finance Pack",
        score=0.85,
        confidence="HIGH",
        reasons=["sector=finance, board_role=CFO"],
        input_signals=["sector:finance", "board_role:CFO"],
        activated_automatically=True,
    )

    with patch("src.core.company.department_service.PackActivationScorer") as MockScorer:
        scorer_instance = MockScorer.return_value
        scorer_instance.score_all_packs.return_value = [high_conf_pack]

        with (
            patch.object(
                department_service, "_create_department_record", new_callable=AsyncMock
            ) as mock_create,
            patch.object(
                department_service,
                "_save_pack_activation_audit",
                new_callable=AsyncMock,
            ) as mock_audit,
            patch("src.core.company.department_service.DepartmentResponse") as MockResponse,
        ):
            mock_dept = _create_mock_department(dept_id=uuid4(), name="Finance", company_id=uuid4())
            mock_create.return_value = mock_dept
            MockResponse.model_validate.return_value = MagicMock()

            await department_service.create_department(
                company_id=uuid4(),
                data={"name": "Finance", "board_role": "CFO"},
            )

        mock_audit.assert_called_once()
        # Verify the result passed to audit has activated_automatically=True
        call_args = mock_audit.call_args[0][0]
        assert call_args.activated_automatically is True
