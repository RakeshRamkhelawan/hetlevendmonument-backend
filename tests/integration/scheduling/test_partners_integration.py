"""Integration tests for Design Partner Program API.

Tests use real PostgreSQL database with no mocks (except auth).
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.scheduling.partners.models import DesignPartner, PartnerFeedback

pytestmark = pytest.mark.asyncio


class TestPartnerRegistration:
    """Tests for POST /scheduling/partners (partner registration)."""

    async def test_register_partner_success(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """Successfully register a new design partner."""
        response = await async_client.post(
            "/api/v1/scheduling/partners",
            json={
                "tenant_id": 999,
                "name": "Acme Corp",
                "industry": "Technology",
                "contact_email": "acme@example.com",
                "contact_name": "John Doe",
                "start_date": datetime.now(timezone.utc).isoformat(),
                "end_date": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
                "max_users": 50,
                "allowed_features": ["scheduling", "analytics"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["partner_id"] is not None
        assert data["name"] == "Acme Corp"
        assert data["status"] == "onboarding"

        # Verify in database
        partner = await db_session.get(DesignPartner, data["partner_id"])
        assert partner is not None
        assert partner.name == "Acme Corp"
        assert partner.tenant_id == 999
        assert partner.industry == "Technology"
        assert partner.contact_email == "acme@example.com"

    async def test_register_partner_validation_error(self, async_client: AsyncClient):
        """Should fail with missing required fields."""
        response = await async_client.post(
            "/api/v1/scheduling/partners",
            json={
                "name": "Incomplete Partner",
                # Missing required fields
            },
        )

        assert response.status_code == 422

    async def test_register_partner_duplicate_name(
        self, async_client: AsyncClient, partner_factory
    ):
        """Should handle duplicate partner names gracefully."""
        # Create first partner
        await partner_factory(name="Unique Partner")

        # Try to create another with same name (should work - no unique constraint)
        response = await async_client.post(
            "/api/v1/scheduling/partners",
            json={
                "tenant_id": 999,
                "name": "Unique Partner",  # Same name
                "industry": "Technology",
                "contact_email": "different@example.com",
                "start_date": datetime.now(timezone.utc).isoformat(),
                "end_date": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
            },
        )

        # Tenant already has a partner record (one-per-tenant constraint)
        assert response.status_code == 400


class TestPartnerList:
    """Tests for GET /scheduling/partners (list partners)."""

    async def test_list_partners_empty(self, async_client: AsyncClient):
        """List partners when none exist."""
        response = await async_client.get("/api/v1/scheduling/partners")

        assert response.status_code == 200
        data = response.json()
        assert data["partners"] == []
        assert data["total"] == 0

    async def test_list_partners_with_data(self, async_client: AsyncClient, partner_factory):
        """List partners returns created partners."""
        # Create test partners
        partner1 = await partner_factory(name="Partner One", industry="Tech")
        partner2 = await partner_factory(name="Partner Two", industry="Finance")

        response = await async_client.get("/api/v1/scheduling/partners")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["partners"]) == 2

        # Verify partner data
        partner_names = {p["name"] for p in data["partners"]}
        assert "Partner One" in partner_names
        assert "Partner Two" in partner_names

    async def test_list_partners_pagination(self, async_client: AsyncClient, partner_factory):
        """Test pagination of partner list."""
        # Create multiple partners
        for i in range(5):
            await partner_factory(name=f"Partner {i}")

        # Get first page
        response = await async_client.get("/api/v1/scheduling/partners?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["partners"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

        # Get second page
        response = await async_client.get("/api/v1/scheduling/partners?page=2&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["partners"]) == 2
        assert data["page"] == 2

    async def test_list_partners_filter_by_status(self, async_client: AsyncClient, partner_factory):
        """Filter partners by status."""
        await partner_factory(name="Active Partner", status="active")
        await partner_factory(name="Onboarding Partner", status="onboarding")
        await partner_factory(name="Suspended Partner", status="suspended")

        response = await async_client.get("/api/v1/scheduling/partners?status=active")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["partners"][0]["status"] == "active"

    async def test_list_partners_filter_by_industry(
        self, async_client: AsyncClient, partner_factory
    ):
        """Filter partners by industry."""
        await partner_factory(name="Tech Partner", industry="Technology")
        await partner_factory(name="Finance Partner", industry="Finance")

        response = await async_client.get("/api/v1/scheduling/partners?industry=Finance")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["partners"][0]["industry"] == "Finance"


class TestPartnerDetails:
    """Tests for GET /scheduling/partners/{partner_id}."""

    async def test_get_partner_success(self, async_client: AsyncClient, partner_factory):
        """Get partner details successfully."""
        partner = await partner_factory(
            name="Detailed Partner",
            industry="Healthcare",
            contact_email="health@example.com",
        )

        response = await async_client.get(f"/api/v1/scheduling/partners/{partner.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == partner.id
        assert data["name"] == "Detailed Partner"
        assert data["industry"] == "Healthcare"
        assert data["contact_email"] == "health@example.com"

    async def test_get_partner_not_found(self, async_client: AsyncClient):
        """Get non-existent partner returns 404."""
        response = await async_client.get("/api/v1/scheduling/partners/nonexistent-id")

        assert response.status_code == 404


class TestPartnerActivation:
    """Tests for POST /scheduling/partners/{partner_id}/activate."""

    async def test_activate_partner_success(
        self, async_client: AsyncClient, partner_factory, db_session
    ):
        """Successfully activate a partner."""
        partner = await partner_factory(status="onboarding")

        response = await async_client.post(f"/api/v1/scheduling/partners/{partner.id}/activate")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "active"

        # Verify in database
        await db_session.refresh(partner)
        assert partner.status == "active"

    async def test_activate_partner_not_found(self, async_client: AsyncClient):
        """Activate non-existent partner returns 404."""
        response = await async_client.post("/api/v1/scheduling/partners/nonexistent-id/activate")

        assert response.status_code == 404


class TestPartnerSuspension:
    """Tests for POST /scheduling/partners/{partner_id}/suspend."""

    async def test_suspend_partner_success(
        self, async_client: AsyncClient, partner_factory, db_session
    ):
        """Successfully suspend a partner."""
        partner = await partner_factory(status="active")

        response = await async_client.post(
            f"/api/v1/scheduling/partners/{partner.id}/suspend",
            json={"reason": "Contract violation"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "suspended"

        # Verify in database
        await db_session.refresh(partner)
        assert partner.status == "suspended"

    async def test_suspend_partner_not_found(self, async_client: AsyncClient):
        """Suspend non-existent partner returns 404."""
        response = await async_client.post(
            "/api/v1/scheduling/partners/nonexistent-id/suspend",
            json={"reason": "Test"},
        )

        assert response.status_code == 404


class TestFeedbackSubmission:
    """Tests for POST /scheduling/partners/{partner_id}/feedback."""

    async def test_submit_feedback_success(
        self, async_client: AsyncClient, partner_factory, db_session
    ):
        """Successfully submit feedback for a partner."""
        partner = await partner_factory()

        response = await async_client.post(
            f"/api/v1/scheduling/partners/{partner.id}/feedback",
            json={
                "feedback_type": "bug",
                "severity": "high",
                "category": "integration",
                "title": "Calendar sync fails",
                "description": "Events are not syncing properly",
                "reproduction_steps": "1. Create event 2. Wait for sync",
                "expected_behavior": "Event should appear",
                "actual_behavior": "Event is missing",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["feedback_id"] is not None
        assert data["priority"] is not None
        assert data["status"] == "open"

        # Verify in database
        feedback = await db_session.get(PartnerFeedback, data["feedback_id"])
        assert feedback is not None
        assert feedback.title == "Calendar sync fails"
        assert feedback.partner_id == partner.id
        assert feedback.severity == "high"

    async def test_submit_feedback_validation_error(
        self, async_client: AsyncClient, partner_factory
    ):
        """Submit feedback with missing required fields."""
        partner = await partner_factory()

        response = await async_client.post(
            f"/api/v1/scheduling/partners/{partner.id}/feedback",
            json={
                "title": "Incomplete feedback",
                # Missing required fields
            },
        )

        assert response.status_code == 422

    async def test_submit_feedback_invalid_partner(self, async_client: AsyncClient):
        """Submit feedback for non-existent partner."""
        response = await async_client.post(
            "/api/v1/scheduling/partners/nonexistent-id/feedback",
            json={
                "feedback_type": "bug",
                "severity": "high",
                "category": "integration",
                "title": "Test feedback",
                "description": "Test description",
            },
        )

        # Should return 400 (partner not found)
        assert response.status_code == 400


class TestFeedbackList:
    """Tests for GET /scheduling/partners/{partner_id}/feedback."""

    async def test_list_partner_feedback(
        self, async_client: AsyncClient, partner_factory, db_session
    ):
        """List feedback for a specific partner."""
        partner = await partner_factory()

        # Create feedback entries
        from src.core.scheduling.partners.models import PartnerFeedback

        for i in range(3):
            feedback = PartnerFeedback(
                partner_id=partner.id,
                feedback_type="bug",
                severity="medium",
                category="scheduling",
                title=f"Bug {i}",
                description=f"Description {i}",
                status="open",
            )
            db_session.add(feedback)
        await db_session.flush()

        response = await async_client.get(f"/api/v1/scheduling/partners/{partner.id}/feedback")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["feedback"]) == 3

    async def test_list_partner_feedback_pagination(
        self, async_client: AsyncClient, partner_factory, db_session
    ):
        """Test pagination of partner feedback."""
        partner = await partner_factory()

        # Create feedback entries
        from src.core.scheduling.partners.models import PartnerFeedback

        for i in range(5):
            feedback = PartnerFeedback(
                partner_id=partner.id,
                feedback_type="feature_request",
                severity="low",
                category="ui",
                title=f"Feature {i}",
                description=f"Description {i}",
                status="open",
            )
            db_session.add(feedback)
        await db_session.flush()

        response = await async_client.get(
            f"/api/v1/scheduling/partners/{partner.id}/feedback?page=1&page_size=2"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["feedback"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    async def test_list_partner_feedback_filter_by_status(
        self, async_client: AsyncClient, partner_factory, db_session
    ):
        """Filter partner feedback by status."""
        partner = await partner_factory()

        from src.core.scheduling.partners.models import PartnerFeedback

        # Create feedback with different statuses
        open_feedback = PartnerFeedback(
            partner_id=partner.id,
            feedback_type="bug",
            severity="high",
            category="scheduling",
            title="Open Bug",
            description="This is open",
            status="open",
        )
        resolved_feedback = PartnerFeedback(
            partner_id=partner.id,
            feedback_type="bug",
            severity="low",
            category="scheduling",
            title="Resolved Bug",
            description="This is resolved",
            status="resolved",
        )
        db_session.add(open_feedback)
        db_session.add(resolved_feedback)
        await db_session.flush()

        response = await async_client.get(
            f"/api/v1/scheduling/partners/{partner.id}/feedback?status=resolved"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["feedback"][0]["status"] == "resolved"


class TestFeedbackAll:
    """Tests for GET /scheduling/partners/feedback/all."""

    async def test_list_all_feedback(self, async_client: AsyncClient, partner_factory, db_session):
        """List all feedback across all partners."""
        partner1 = await partner_factory(name="Partner 1")
        partner2 = await partner_factory(name="Partner 2")

        from src.core.scheduling.partners.models import PartnerFeedback

        # Create feedback for both partners
        for partner in [partner1, partner2]:
            feedback = PartnerFeedback(
                partner_id=partner.id,
                feedback_type="bug",
                severity="medium",
                category="scheduling",
                title=f"Bug for {partner.name}",
                description="Test",
                status="open",
            )
            db_session.add(feedback)
        await db_session.flush()

        response = await async_client.get("/api/v1/scheduling/partners/feedback/all")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["feedback"]) == 2


class TestFeedbackAssignment:
    """Tests for POST /scheduling/partners/feedback/{feedback_id}/assign."""

    async def test_assign_feedback_success(
        self, async_client: AsyncClient, partner_factory, db_session
    ):
        """Successfully assign feedback to engineer."""
        partner = await partner_factory()

        from src.core.scheduling.partners.models import PartnerFeedback

        feedback = PartnerFeedback(
            partner_id=partner.id,
            feedback_type="bug",
            severity="high",
            category="scheduling",
            title="Critical Bug",
            description="Needs attention",
            status="open",
        )
        db_session.add(feedback)
        await db_session.flush()

        response = await async_client.post(
            f"/api/v1/scheduling/partners/feedback/{feedback.id}/assign",
            json={"engineer_id": "engineer-123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["assigned_to"] == "engineer-123"

        # Verify in database
        await db_session.refresh(feedback)
        assert feedback.assigned_to == "engineer-123"

    async def test_assign_feedback_missing_engineer_id(
        self, async_client: AsyncClient, partner_factory, db_session
    ):
        """Assign feedback without engineer_id returns 400."""
        partner = await partner_factory()

        from src.core.scheduling.partners.models import PartnerFeedback

        feedback = PartnerFeedback(
            partner_id=partner.id,
            feedback_type="bug",
            severity="medium",
            category="scheduling",
            title="Test Bug",
            description="Test",
            status="open",
        )
        db_session.add(feedback)
        await db_session.flush()

        response = await async_client.post(
            f"/api/v1/scheduling/partners/feedback/{feedback.id}/assign",
            json={},  # Missing engineer_id
        )

        assert response.status_code == 400

    async def test_assign_feedback_not_found(self, async_client: AsyncClient):
        """Assign non-existent feedback returns 404."""
        response = await async_client.post(
            "/api/v1/scheduling/partners/feedback/nonexistent-id/assign",
            json={"engineer_id": "engineer-123"},
        )

        assert response.status_code == 404


class TestFeedbackResolution:
    """Tests for POST /scheduling/partners/feedback/{feedback_id}/resolve."""

    async def test_resolve_feedback_success(
        self, async_client: AsyncClient, partner_factory, db_session
    ):
        """Successfully resolve feedback."""
        partner = await partner_factory()

        from src.core.scheduling.partners.models import PartnerFeedback

        feedback = PartnerFeedback(
            partner_id=partner.id,
            feedback_type="bug",
            severity="medium",
            category="scheduling",
            title="Bug to resolve",
            description="Will be fixed",
            status="open",
        )
        db_session.add(feedback)
        await db_session.flush()

        response = await async_client.post(
            f"/api/v1/scheduling/partners/feedback/{feedback.id}/resolve",
            json={"notes": "Fixed in version 1.2.3"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "resolved"

        # Verify in database
        await db_session.refresh(feedback)
        assert feedback.status == "resolved"

    async def test_resolve_feedback_not_found(self, async_client: AsyncClient):
        """Resolve non-existent feedback returns 404."""
        response = await async_client.post(
            "/api/v1/scheduling/partners/feedback/nonexistent-id/resolve",
            json={"notes": "Test"},
        )

        assert response.status_code == 404
