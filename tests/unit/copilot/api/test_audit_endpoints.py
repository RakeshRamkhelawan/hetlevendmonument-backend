"""Unit tests for Co-Pilot audit endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status

from src.core.copilot.api import audit_endpoints
from src.core.copilot.api.schemas import ContestRequest
from tests.helpers.limiet_request import echte_request


class _MockDecision:
    def __init__(self, decision_id: UUID, tenant_id: int, user_id: int):
        self.decision_id = decision_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.timestamp = datetime.now(timezone.utc)
        self.verdict = "APPROVED"
        self.action_type = "send_notification"
        self.explanation_for_user = "Test explanation"
        self.reasoning = "Test reasoning"
        self.model_id = "model-1"
        self.model_version = "1.0"
        self.data_classification = "INTERNAL"
        self.previous_decision_hash = "abc"
        self.decision_hash = "def"
        self.deliberation_ms = 100


class _MockVerdict:
    def __init__(self, decision_id: UUID, officer_name: str):
        self.decision_id = decision_id
        self.officer_name = officer_name
        self.officer_version = "1.0"
        self.verdict = "APPROVE"
        self.confidence = 0.95
        self.reason_code = "OK"
        self.reason_text = "All good"


def _make_mock_user(user_id: int = 1, roles: list[str] | None = None, is_superuser: bool = False):
    user = MagicMock()
    user.id = user_id
    user.email = f"user{user_id}@example.com"
    user.roles = roles or []
    user.is_superuser = is_superuser
    return user


def _make_db_mock(results: list | None = None, scalar_value: int | None = 0):
    """Create an AsyncSession mock that returns results in order.

    Args:
        results: list of mock result objects returned by session.execute()
        scalar_value: value returned by session.scalar() (for COUNT queries)
    """
    session = AsyncMock()
    _results = list(results) if results else []
    _idx = [0]

    async def _mock_execute(*args, **kwargs):
        if _idx[0] < len(_results):
            result = _results[_idx[0]]
            _idx[0] += 1
            return result
        return MagicMock(
            scalar_one_or_none=lambda: None,
            scalars=lambda: MagicMock(all=lambda: []),
        )

    async def _mock_scalar(*args, **kwargs):
        return scalar_value

    session.execute = _mock_execute
    session.scalar = _mock_scalar
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


def _dummy_result():
    return MagicMock()


def _result_scalar_one_or_none(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _result_scalars_all(values):
    r = MagicMock()
    r.scalars.return_value.all.return_value = values
    return r


@pytest.mark.unit
@pytest.mark.als
class TestGetDecisionExplanation:
    async def test_get_decision_returns_full_explanation_for_owner(self):
        user = _make_mock_user(user_id=1)
        did = uuid4()
        decision = _MockDecision(did, 1, user.id)
        verdict = _MockVerdict(did, "ComplianceOfficer")

        db = _make_db_mock(
            [
                _dummy_result(),
                _result_scalar_one_or_none(decision),
                _result_scalars_all([verdict]),
            ]
        )

        result = await audit_endpoints.get_decision_explanation(
            request=echte_request(),
            decision_id=did,
            current_user=user,
            db=db,
            tenant_id=1,
        )
        assert result.decision_id == did
        assert result.can_contest is True
        assert result.officer_verdicts[0].officer_name == "ComplianceOfficer"

    async def test_get_decision_returns_404_when_not_found(self):
        user = _make_mock_user()
        did = uuid4()
        db = _make_db_mock([_dummy_result(), _result_scalar_one_or_none(None)])

        with pytest.raises(HTTPException) as exc_info:
            await audit_endpoints.get_decision_explanation(
                request=echte_request(),
                decision_id=did,
                current_user=user,
                db=db,
                tenant_id=1,
            )
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_decision_returns_404_with_same_message_for_other_tenant(self):
        """RLS blocks cross-tenant; same opaque message as not-found."""
        user = _make_mock_user()
        did = uuid4()
        db = _make_db_mock([_result_scalar_one_or_none(None)])

        with pytest.raises(HTTPException) as exc_info:
            await audit_endpoints.get_decision_explanation(
                request=echte_request(),
                decision_id=did,
                current_user=user,
                db=db,
                tenant_id=1,
            )
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "Decision not found"

    async def test_get_decision_returns_403_when_other_user_non_admin(self):
        user = _make_mock_user(user_id=1)
        did = uuid4()
        decision = _MockDecision(did, 1, 999)  # other user
        db = _make_db_mock([_dummy_result(), _result_scalar_one_or_none(decision)])

        with pytest.raises(HTTPException) as exc_info:
            await audit_endpoints.get_decision_explanation(
                request=echte_request(),
                decision_id=did,
                current_user=user,
                db=db,
                tenant_id=1,
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_get_decision_returns_200_when_admin_sees_other_user_in_same_tenant(self):
        admin = _make_mock_user(user_id=2, roles=["admin"])
        did = uuid4()
        decision = _MockDecision(did, 1, 999)  # other user
        verdict = _MockVerdict(did, "ComplianceOfficer")

        db = _make_db_mock(
            [
                _dummy_result(),
                _result_scalar_one_or_none(decision),
                _result_scalars_all([verdict]),
            ]
        )

        result = await audit_endpoints.get_decision_explanation(
            request=echte_request(),
            decision_id=did,
            current_user=admin,
            db=db,
            tenant_id=1,
        )
        assert result.decision_id == did


@pytest.mark.unit
@pytest.mark.als
class TestContestDecision:
    @patch("src.core.copilot.api.audit_endpoints.submit_contest")
    async def test_contest_creates_record_and_returns_201(self, mock_submit):
        user = _make_mock_user(user_id=1)
        did = uuid4()
        decision = _MockDecision(did, 1, user.id)

        class _Proxy:
            contest_id = uuid4()
            status = "pending"
            submitted_at = datetime.now(timezone.utc)
            admin_notification = "verzonden"

        mock_submit.return_value = _Proxy()

        db = _make_db_mock([_dummy_result(), _result_scalar_one_or_none(decision)])

        result = await audit_endpoints.contest_decision(
            request=echte_request(),
            decision_id=did,
            body=ContestRequest(
                reason_category="factual_error",
                reason_text="This is a detailed reason for contesting",
            ),
            current_user=user,
            db=db,
            tenant_id=1,
        )
        assert result.status == "pending"
        assert result.expected_review_within_hours == 72
        mock_submit.assert_called_once()

    def test_contest_rejects_too_short_reason_text(self):
        with pytest.raises(Exception):
            ContestRequest(reason_category="other", reason_text="short")

    def test_contest_rejects_invalid_category(self):
        with pytest.raises(Exception):
            ContestRequest(reason_category="invalid_category", reason_text="a" * 50)


@pytest.mark.unit
@pytest.mark.als
class TestVerifyChain:
    async def test_verify_returns_chain_valid_true_for_intact_chain(self):
        admin = _make_mock_user(user_id=1, roles=["admin"])
        d1 = _MockDecision(uuid4(), 1, 1)
        d2 = _MockDecision(uuid4(), 1, 1)
        d1.decision_hash = "hash1"
        d2.previous_decision_hash = "hash1"
        d2.decision_hash = "hash2"

        db = _make_db_mock([_dummy_result(), _result_scalars_all([d1, d2])])

        result = await audit_endpoints.verify_chain(
            request=echte_request(),
            current_user=admin,
            db=db,
            tenant_id=1,
        )
        assert result.chain_valid is True
        assert result.decisions_checked == 2

    async def test_verify_returns_chain_valid_false_with_broken_links(self):
        admin = _make_mock_user(user_id=1, roles=["admin"])
        d1 = _MockDecision(uuid4(), 1, 1)
        d2 = _MockDecision(uuid4(), 1, 1)
        d1.decision_hash = "hash1"
        d2.previous_decision_hash = "broken"
        d2.decision_hash = "hash2"

        db = _make_db_mock([_dummy_result(), _result_scalars_all([d1, d2])])

        result = await audit_endpoints.verify_chain(
            request=echte_request(),
            current_user=admin,
            db=db,
            tenant_id=1,
        )
        assert result.chain_valid is False
        assert len(result.broken_links) == 1

    async def test_verify_requires_admin_role(self):
        user = _make_mock_user(user_id=1, roles=[])
        db = _make_db_mock()

        with pytest.raises(HTTPException) as exc_info:
            await audit_endpoints.verify_chain(
                request=echte_request(),
                current_user=user,
                db=db,
                tenant_id=1,
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.unit
@pytest.mark.als
class TestAuditReport:
    @patch("src.core.copilot.api.audit_endpoints.AuditReportGenerator")
    async def test_report_pdf_returns_pdf_content_type(self, mock_gen_cls):
        admin = _make_mock_user(user_id=1, roles=["admin"])
        mock_gen = AsyncMock()
        mock_gen.generate_pdf = AsyncMock(return_value=b"%PDF-1.4 fake pdf")
        mock_gen_cls.return_value = mock_gen

        db = _make_db_mock([_dummy_result(), _result_scalars_all([])], scalar_value=0)

        from fastapi import Request

        request = echte_request()
        result = await audit_endpoints.get_audit_report(
            request=request,
            from_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            to_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
            format="pdf",
            current_user=admin,
            db=db,
            tenant_id=1,
        )
        assert result.media_type == "application/pdf"

    @patch("src.core.copilot.api.audit_endpoints.AuditReportGenerator")
    async def test_report_json_returns_structured_summary(self, mock_gen_cls):
        admin = _make_mock_user(user_id=1, roles=["admin"])
        mock_gen = AsyncMock()
        mock_gen.generate_json = AsyncMock(return_value='{"total": 0}')
        mock_gen_cls.return_value = mock_gen

        db = _make_db_mock([_dummy_result(), _result_scalars_all([])], scalar_value=0)

        from fastapi import Request

        request = echte_request()
        result = await audit_endpoints.get_audit_report(
            request=request,
            from_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            to_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
            format="json",
            current_user=admin,
            db=db,
            tenant_id=1,
        )
        assert result.media_type == "application/json"

    async def test_report_rejects_range_over_400_days(self):
        admin = _make_mock_user(user_id=1, roles=["admin"])
        db = _make_db_mock()

        from fastapi import Request

        request = echte_request()
        with pytest.raises(HTTPException) as exc_info:
            await audit_endpoints.get_audit_report(
                request=request,
                from_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                to_date=datetime(2027, 6, 1, tzinfo=timezone.utc),
                format="json",
                current_user=admin,
                db=db,
                tenant_id=1,
            )
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    async def test_report_rejects_non_admin(self):
        user = _make_mock_user(user_id=1, roles=[])
        db = _make_db_mock()

        from fastapi import Request

        request = echte_request()
        with pytest.raises(HTTPException) as exc_info:
            await audit_endpoints.get_audit_report(
                request=request,
                from_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                to_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
                format="json",
                current_user=user,
                db=db,
                tenant_id=1,
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.unit
@pytest.mark.als
class TestIsTenantAdmin:
    def test_superuser_is_admin(self):
        user = _make_mock_user(is_superuser=True)
        assert audit_endpoints._is_tenant_admin(user) is True

    def test_admin_role_is_admin(self):
        user = _make_mock_user(roles=["admin"])
        assert audit_endpoints._is_tenant_admin(user) is True

    def test_tenantadmin_role_is_admin(self):
        user = _make_mock_user(roles=["tenantadmin"])
        assert audit_endpoints._is_tenant_admin(user) is True

    def test_normal_user_is_not_admin(self):
        user = _make_mock_user(roles=["user"])
        assert audit_endpoints._is_tenant_admin(user) is False
