"""
Unit tests voor Digital Twin API endpoints.

Test-aanpak: mock alle dependencies (service, consent manager, auth).
Controleert:
- POST /track-user-behavior → 202 Accepted bij succes
- POST /track-user-behavior → 202 maar accepted=False bij reject
- POST /analyze-struggle → correct response
- GET /twin/consent → correct status
- PUT /twin/consent → update met geldige/ongeldige status
- DELETE /twin/data → 204 No Content
- GET /twin/export → JSON export
"""

import importlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.learning.consent.consent_manager import ConsentCategories, TwinConsentManager, TwinConsentStatus

# Patch rate limiter so endpoints work in TestClient without slowapi middleware.
from unittest.mock import patch

from src.core.middleware.rate_limiter import get_limiter

_original_get_limiter = get_limiter
_patched_limiters: list = []


def _mock_get_limiter(service_name: str = "main"):
    limiter = _original_get_limiter(service_name)
    _patched_limiters.append((limiter, limiter.__dict__.get("limit")))
    limiter.limit = lambda limit_str: lambda func: func  # type: ignore[method-assign]
    return limiter


# Force re-evaluation of the endpoint module so it picks up the patched limiter.
# De patch en de mutatie van de gecachte Limiter worden na de reload teruggezet,
# zodat andere testmodules (bv. scheduling routes) een echte limiter krijgen.
from src.api.v1.endpoints import digital_twin as _dt_module

try:
    with patch("src.core.middleware.rate_limiter.get_limiter", _mock_get_limiter):
        importlib.reload(_dt_module)
finally:
    for _limiter, _orig_limit in reversed(_patched_limiters):
        if _orig_limit is None:
            _limiter.__dict__.pop("limit", None)
        else:
            _limiter.limit = _orig_limit  # type: ignore[method-assign]
    _patched_limiters.clear()


def _make_test_app():
    """Maak een minimale FastAPI app voor de digital_twin router."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(_dt_module.router, prefix="/api/v1")
    return app


def _mock_user(user_id: int = 42, tenant_id: int = 1):
    """Maak een mock User object."""
    user = MagicMock()
    user.id = user_id
    user.tenant_id = tenant_id
    return user


class TestTrackUserBehaviorEndpoint:
    """Tests voor POST /api/v1/learning/track-user-behavior."""

    def test_track_accepted(self):
        mock_user = _mock_user()
        mock_service = AsyncMock()
        mock_service.track_behavior = AsyncMock(return_value="trace_abc123")

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_twin_service
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_twin_service] = lambda: mock_service

        client = TestClient(app)
        response = client.post(
            "/api/v1/learning/track-user-behavior",
            json={
                "session_id": "sess_001",
                "behavior_type": "file_edit",
                "context": {"edit_count": 3},
            },
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] is True
        assert data["trace_id"] == "trace_abc123"

    def test_track_rejected_by_consent(self):
        mock_user = _mock_user()
        mock_service = AsyncMock()
        mock_service.track_behavior = AsyncMock(return_value=None)  # rejected

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_twin_service
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_twin_service] = lambda: mock_service

        client = TestClient(app)
        response = client.post(
            "/api/v1/learning/track-user-behavior",
            json={
                "session_id": "sess_001",
                "behavior_type": "file_edit",
            },
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] is False
        assert data["trace_id"] is None

    def test_track_service_error_returns_202_not_500(self):
        """Service error → 202 maar accepted=False, geen 500."""
        mock_user = _mock_user()
        mock_service = AsyncMock()
        mock_service.track_behavior = AsyncMock(side_effect=RuntimeError("chaos"))

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_twin_service
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_twin_service] = lambda: mock_service

        client = TestClient(app)
        response = client.post(
            "/api/v1/learning/track-user-behavior",
            json={"session_id": "s", "behavior_type": "edit"},
        )

        assert response.status_code == 202
        assert response.json()["accepted"] is False

    def test_track_validates_behavior_type_max_length(self):
        mock_user = _mock_user()
        mock_service = AsyncMock()

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_twin_service
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_twin_service] = lambda: mock_service

        client = TestClient(app)
        response = client.post(
            "/api/v1/learning/track-user-behavior",
            json={
                "session_id": "s",
                "behavior_type": "x" * 101,  # > max_length=100
            },
        )

        assert response.status_code == 422


class TestAnalyzeStruggleEndpoint:
    """Tests voor POST /api/v1/learning/analyze-struggle."""

    def test_analyze_struggle_returns_result(self):
        mock_user = _mock_user()
        mock_service = AsyncMock()
        mock_service.analyze_struggle = AsyncMock(
            return_value={
                "score": 0.85,
                "needs_intervention": True,
                "suggestion": "Probeer dit eens...",
            }
        )

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_twin_service
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_twin_service] = lambda: mock_service

        client = TestClient(app)
        response = client.post(
            "/api/v1/learning/analyze-struggle",
            json={
                "context": {
                    "recent_edits_same_line": 10,
                    "recent_file_switches": 8,
                },
                "user_profile": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["score"] == 0.85
        assert data["needs_intervention"] is True
        assert data["suggestion"] == "Probeer dit eens..."


class TestConsentEndpoints:
    """Tests voor consent endpoints."""

    def test_get_consent_returns_categories(self):
        mock_user = _mock_user()
        mock_consent_mgr = AsyncMock(spec=TwinConsentManager)
        mock_consent_mgr.get_consent_status = AsyncMock(
            return_value=TwinConsentStatus.ENABLED
        )
        mock_consent_mgr.get_consent_categories = AsyncMock(
            return_value=ConsentCategories(
                behavior_tracking=True,
                profile_aggregation=True,
                ai_interventions=True,
                cross_session_memory=True,
            )
        )

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_consent_manager
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_consent_manager] = lambda: mock_consent_mgr

        client = TestClient(app)
        response = client.get("/api/v1/learning/twin/consent")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "enabled"
        cats = data["categories"]
        assert cats["behavior_tracking"] is True
        assert cats["profile_aggregation"] is True
        assert cats["ai_interventions"] is True
        assert cats["cross_session_memory"] is True

    def test_put_consent_valid_status(self):
        mock_user = _mock_user()
        mock_consent_mgr = AsyncMock(spec=TwinConsentManager)
        mock_consent_mgr.set_consent_status = AsyncMock()
        mock_consent_mgr.get_consent_status = AsyncMock(
            return_value=TwinConsentStatus.DISABLED
        )
        mock_consent_mgr.get_consent_categories = AsyncMock(
            return_value=ConsentCategories(
                behavior_tracking=False,
                profile_aggregation=False,
                ai_interventions=False,
                cross_session_memory=False,
            )
        )

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_consent_manager
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_consent_manager] = lambda: mock_consent_mgr

        client = TestClient(app)
        response = client.put(
            "/api/v1/learning/twin/consent",
            json={"status": "disabled"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disabled"
        cats = data["categories"]
        assert cats["behavior_tracking"] is False
        assert cats["profile_aggregation"] is False
        assert cats["ai_interventions"] is False
        assert cats["cross_session_memory"] is False
        mock_consent_mgr.set_consent_status.assert_called_once()

    def test_patch_consent_categories_partial(self):
        mock_user = _mock_user()
        mock_consent_mgr = AsyncMock(spec=TwinConsentManager)
        mock_consent_mgr.get_consent_status = AsyncMock(
            return_value=TwinConsentStatus.PAUSED
        )
        mock_consent_mgr.get_consent_categories = AsyncMock(
            return_value=ConsentCategories(
                behavior_tracking=True,
                profile_aggregation=True,
                ai_interventions=True,
                cross_session_memory=True,
            )
        )
        mock_consent_mgr.set_consent_categories = AsyncMock()

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_consent_manager
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_consent_manager] = lambda: mock_consent_mgr

        client = TestClient(app)
        response = client.patch(
            "/api/v1/learning/twin/consent",
            json={"ai_interventions": False},
        )

        assert response.status_code == 200
        data = response.json()
        cats = data["categories"]
        assert cats["behavior_tracking"] is True
        assert cats["profile_aggregation"] is True
        assert cats["ai_interventions"] is False
        assert cats["cross_session_memory"] is True
        mock_consent_mgr.set_consent_categories.assert_called_once()

    def test_patch_consent_all_categories(self):
        mock_user = _mock_user()
        mock_consent_mgr = AsyncMock(spec=TwinConsentManager)
        mock_consent_mgr.get_consent_status = AsyncMock(
            return_value=TwinConsentStatus.DISABLED
        )
        mock_consent_mgr.get_consent_categories = AsyncMock(
            return_value=ConsentCategories(
                behavior_tracking=True,
                profile_aggregation=True,
                ai_interventions=True,
                cross_session_memory=True,
            )
        )
        mock_consent_mgr.set_consent_categories = AsyncMock()

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_consent_manager
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_consent_manager] = lambda: mock_consent_mgr

        client = TestClient(app)
        response = client.patch(
            "/api/v1/learning/twin/consent",
            json={
                "behavior_tracking": False,
                "profile_aggregation": False,
                "ai_interventions": False,
                "cross_session_memory": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        cats = data["categories"]
        assert cats["behavior_tracking"] is False
        assert cats["profile_aggregation"] is False
        assert cats["ai_interventions"] is False
        assert cats["cross_session_memory"] is False

    def test_put_consent_invalid_status(self):
        mock_user = _mock_user()
        mock_consent_mgr = AsyncMock(spec=TwinConsentManager)

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_consent_manager
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_consent_manager] = lambda: mock_consent_mgr

        client = TestClient(app)
        response = client.put(
            "/api/v1/learning/twin/consent",
            json={"status": "invalid_status"},
        )

        assert response.status_code == 422

    def test_delete_twin_data_returns_202_with_job_id(self):
        mock_user = _mock_user()
        mock_message = MagicMock()
        mock_message.message_id = "msg_abc_123"

        app = _make_test_app()

        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user

        # Mock the dramatiq actor
        import src.core.learning.worker as worker_module
        original_actor = worker_module.twin_hard_delete_async
        worker_module.twin_hard_delete_async = MagicMock()
        worker_module.twin_hard_delete_async.send = MagicMock(return_value=mock_message)

        try:
            client = TestClient(app)
            response = client.delete("/api/v1/learning/twin/data")

            assert response.status_code == 202
            data = response.json()
            assert data["job_id"] == "msg_abc_123"
            assert data["status"] == "queued"
            worker_module.twin_hard_delete_async.send.assert_called_once_with("42", 1)
        finally:
            worker_module.twin_hard_delete_async = original_actor

    def test_export_twin_data_returns_json(self):
        mock_user = _mock_user()
        mock_consent_mgr = AsyncMock(spec=TwinConsentManager)
        mock_consent_mgr.export_user_data = AsyncMock(
            return_value={
                "user_id": "42",
                "observations": [],
                "cognitive_profile": {"confidence_level": 0.0},
            }
        )

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_consent_manager
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_consent_manager] = lambda: mock_consent_mgr

        client = TestClient(app)
        response = client.get("/api/v1/learning/twin/export")

        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "observations" in data

    def test_delete_uses_tenant_id_from_jwt_not_body(self):
        """Tenant ID must come from JWT, never from request body."""
        mock_user = _mock_user(user_id=42, tenant_id=7)
        mock_message = MagicMock()
        mock_message.message_id = "msg_xyz_789"

        app = _make_test_app()

        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user

        # Mock the dramatiq actor
        import src.core.learning.worker as worker_module
        original_actor = worker_module.twin_hard_delete_async
        worker_module.twin_hard_delete_async = MagicMock()
        worker_module.twin_hard_delete_async.send = MagicMock(return_value=mock_message)

        try:
            client = TestClient(app)
            response = client.delete("/api/v1/learning/twin/data")

            assert response.status_code == 202
            worker_module.twin_hard_delete_async.send.assert_called_once_with("42", 7)
        finally:
            worker_module.twin_hard_delete_async = original_actor

    def test_export_uses_tenant_id_from_jwt(self):
        """Export must filter on tenant_id from JWT."""
        mock_user = _mock_user(user_id=42, tenant_id=7)
        mock_consent_mgr = AsyncMock(spec=TwinConsentManager)
        mock_consent_mgr.export_user_data = AsyncMock(return_value={"user_id": "42"})

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_consent_manager
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_consent_manager] = lambda: mock_consent_mgr

        client = TestClient(app)
        client.get("/api/v1/learning/twin/export")

        mock_consent_mgr.export_user_data.assert_awaited_once_with(
            user_id="42", tenant_id=7
        )


class TestArt22Endpoints:
    """Tests voor AVG Artikel 22 endpoints."""

    def test_get_art22_info_returns_correct_structure(self):
        mock_user = _mock_user()
        mock_consent_mgr = AsyncMock(spec=TwinConsentManager)
        mock_consent_mgr.get_consent_categories = AsyncMock(
            return_value=ConsentCategories(
                behavior_tracking=True,
                profile_aggregation=True,
                ai_interventions=True,
                cross_session_memory=True,
            )
        )

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_consent_manager
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_consent_manager] = lambda: mock_consent_mgr

        client = TestClient(app)
        response = client.get("/api/v1/learning/twin/consent/art22-info")

        assert response.status_code == 200
        data = response.json()
        assert data["applies_to_user"] is True
        assert "description" in data
        assert "opt_out_path" in data
        assert "legal_basis" in data
        assert "human_oversight" in data

    def test_get_art22_info_reflects_opt_out(self):
        mock_user = _mock_user()
        mock_consent_mgr = AsyncMock(spec=TwinConsentManager)
        mock_consent_mgr.get_consent_categories = AsyncMock(
            return_value=ConsentCategories(
                behavior_tracking=True,
                profile_aggregation=True,
                ai_interventions=False,
                cross_session_memory=True,
            )
        )

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_consent_manager
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_consent_manager] = lambda: mock_consent_mgr

        client = TestClient(app)
        response = client.get("/api/v1/learning/twin/consent/art22-info")

        assert response.status_code == 200
        data = response.json()
        assert data["applies_to_user"] is False

    def test_post_consent_feedback_returns_204(self):
        mock_user = _mock_user()

        app = _make_test_app()

        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user

        client = TestClient(app)
        response = client.post(
            "/api/v1/learning/twin/consent/feedback",
            json={
                "category": "ai_interventions",
                "enabled": False,
                "reason": "I prefer human help",
                "source": "settings_page",
            },
        )

        assert response.status_code == 204

    def test_post_consent_feedback_without_reason_returns_204(self):
        mock_user = _mock_user()

        app = _make_test_app()

        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user

        client = TestClient(app)
        response = client.post(
            "/api/v1/learning/twin/consent/feedback",
            json={
                "category": "ai_interventions",
                "enabled": False,
            },
        )

        assert response.status_code == 204

    def test_post_suggestion_feedback_returns_204(self):
        mock_user = _mock_user()
        mock_db = AsyncMock()
        mock_tracker = AsyncMock()

        app = _make_test_app()

        from src.core.auth.dependencies import get_current_user
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        # Mock CostTracker to avoid real DB calls
        import src.core.learning.cost.cost_tracker
        original_cost_tracker = src.core.learning.cost.cost_tracker.CostTracker
        src.core.learning.cost.cost_tracker.CostTracker = lambda db: mock_tracker

        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/learning/twin/suggestion/42/feedback",
                json={"was_useful": True, "comment": "Great suggestion"},
            )

            assert response.status_code == 204
            mock_tracker.record_feedback.assert_awaited_once_with(log_id=42, was_useful=True)
        finally:
            src.core.learning.cost.cost_tracker.CostTracker = original_cost_tracker

    def test_post_suggestion_feedback_without_comment_returns_204(self):
        mock_user = _mock_user()
        mock_db = AsyncMock()
        mock_tracker = AsyncMock()

        app = _make_test_app()

        from src.core.auth.dependencies import get_current_user
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        # Mock CostTracker to avoid real DB calls
        import src.core.learning.cost.cost_tracker
        original_cost_tracker = src.core.learning.cost.cost_tracker.CostTracker
        src.core.learning.cost.cost_tracker.CostTracker = lambda db: mock_tracker

        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/learning/twin/suggestion/42/feedback",
                json={"was_useful": False},
            )

            assert response.status_code == 204
            mock_tracker.record_feedback.assert_awaited_once_with(log_id=42, was_useful=False)
        finally:
            src.core.learning.cost.cost_tracker.CostTracker = original_cost_tracker


class TestTenantIsolation:
    """Verify tenant_id is never accepted from client and always from JWT."""

    def test_track_passes_tenant_id_from_user(self):
        mock_user = _mock_user(user_id=99, tenant_id=3)
        mock_service = AsyncMock()
        mock_service.track_behavior = AsyncMock(return_value="trace_xyz")

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_twin_service
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_twin_service] = lambda: mock_service

        client = TestClient(app)
        client.post(
            "/api/v1/learning/track-user-behavior",
            json={"session_id": "s", "behavior_type": "edit"},
        )

        mock_service.track_behavior.assert_awaited_once()
        call_kwargs = mock_service.track_behavior.call_args.kwargs
        assert call_kwargs["tenant_id"] == 3

    def test_track_passes_confidence_score(self):
        mock_user = _mock_user()
        mock_service = AsyncMock()
        mock_service.track_behavior = AsyncMock(return_value="trace_xyz")

        app = _make_test_app()

        from src.api.v1.endpoints.digital_twin import _get_twin_service
        from src.core.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[_get_twin_service] = lambda: mock_service

        client = TestClient(app)
        client.post(
            "/api/v1/learning/track-user-behavior",
            json={
                "session_id": "s",
                "behavior_type": "edit",
                "confidence_score": 0.75,
            },
        )

        call_kwargs = mock_service.track_behavior.call_args.kwargs
        assert call_kwargs["confidence_score"] == 0.75
