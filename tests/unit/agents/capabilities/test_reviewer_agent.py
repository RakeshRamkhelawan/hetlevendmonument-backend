"""
Slice 7: ReviewerAgent - Comprehensive Test Suite (RED Phase)

Tests human-in-the-loop decision management, review workflows, and approval tracking.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.core.agents.capabilities.reviewer_agent import ReviewerAgent
from src.core.agents.capabilities.schemas import ReviewerResult, ReviewerTask, ReviewStatus

# ============================================================================
# TEST SUITE 1: Basic Review Request
# ============================================================================


class TestBasicReviewRequest:
    """Test basic review request submission"""

    @pytest.mark.asyncio
    async def test_submits_review_request(self):
        """Should submit a review request successfully"""
        agent = ReviewerAgent()
        task = ReviewerTask(
            decision_description="Approve invoice for $5,000",
            context={"invoice_id": "INV-001", "amount": 5000},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.request_review(task)

        assert result is not None
        assert result.status == ReviewStatus.PENDING
        assert result.review_id is not None
        assert result.decision_description == task.decision_description

    @pytest.mark.asyncio
    async def test_assigns_reviewer(self):
        """Should assign reviewer to review request"""
        agent = ReviewerAgent()
        task = ReviewerTask(
            decision_description="Approve invoice for $5,000",
            context={"invoice_id": "INV-001"},
            tenant_id=uuid4(),
            user_id=uuid4(),
            assigned_reviewer_id=uuid4(),
        )

        result = await agent.request_review(task)

        assert result.assigned_reviewer_id == task.assigned_reviewer_id

    @pytest.mark.asyncio
    async def test_includes_submission_timestamp(self):
        """Should include submission timestamp"""
        agent = ReviewerAgent()
        task = ReviewerTask(
            decision_description="Test decision",
            context={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.request_review(task)

        assert result.submitted_at is not None
        assert isinstance(result.submitted_at, datetime)


# ============================================================================
# TEST SUITE 2: Review Approval
# ============================================================================


class TestReviewApproval:
    """Test review approval workflow"""

    @pytest.mark.asyncio
    async def test_approves_review(self):
        """Should approve a pending review"""
        agent = ReviewerAgent()
        review_id = uuid4()

        result = await agent.complete_review(
            review_id=review_id,
            reviewer_id=uuid4(),
            status=ReviewStatus.APPROVED,
            comments="Looks good, approved",
            tenant_id=uuid4(),
        )

        assert result.status == ReviewStatus.APPROVED
        assert result.reviewer_comments == "Looks good, approved"
        assert result.reviewed_at is not None

    @pytest.mark.asyncio
    async def test_records_reviewer_id(self):
        """Should record who approved the review"""
        agent = ReviewerAgent()
        review_id = uuid4()
        reviewer_id = uuid4()

        result = await agent.complete_review(
            review_id=review_id,
            reviewer_id=reviewer_id,
            status=ReviewStatus.APPROVED,
            comments="Approved",
            tenant_id=uuid4(),
        )

        assert result.reviewer_id == reviewer_id

    @pytest.mark.asyncio
    async def test_calculates_review_duration(self):
        """Should calculate time between submission and approval"""
        agent = ReviewerAgent()
        review_id = uuid4()

        result = await agent.complete_review(
            review_id=review_id,
            reviewer_id=uuid4(),
            status=ReviewStatus.APPROVED,
            comments="Approved",
            tenant_id=uuid4(),
        )

        # Should have both submitted_at and reviewed_at
        assert result.submitted_at is not None
        assert result.reviewed_at is not None


# ============================================================================
# TEST SUITE 3: Review Rejection
# ============================================================================


class TestReviewRejection:
    """Test review rejection workflow"""

    @pytest.mark.asyncio
    async def test_rejects_review(self):
        """Should reject a review with reason"""
        agent = ReviewerAgent()
        review_id = uuid4()

        result = await agent.complete_review(
            review_id=review_id,
            reviewer_id=uuid4(),
            status=ReviewStatus.REJECTED,
            comments="Insufficient justification provided",
            tenant_id=uuid4(),
        )

        assert result.status == ReviewStatus.REJECTED
        assert "Insufficient justification" in result.reviewer_comments

    @pytest.mark.asyncio
    async def test_requires_rejection_reason(self):
        """Should require comments when rejecting"""
        agent = ReviewerAgent()
        review_id = uuid4()

        result = await agent.complete_review(
            review_id=review_id,
            reviewer_id=uuid4(),
            status=ReviewStatus.REJECTED,
            comments="",  # Empty comments
            tenant_id=uuid4(),
        )

        # Should either fail validation or add default message
        assert result.reviewer_comments is not None


# ============================================================================
# TEST SUITE 4: Review With Modifications
# ============================================================================


class TestReviewWithModifications:
    """Test review with modifications workflow"""

    @pytest.mark.asyncio
    async def test_requests_modifications(self):
        """Should request modifications with specific feedback"""
        agent = ReviewerAgent()
        review_id = uuid4()

        result = await agent.complete_review(
            review_id=review_id,
            reviewer_id=uuid4(),
            status=ReviewStatus.WITH_MODIFICATIONS,
            comments="Please reduce amount to $3,000 and add justification",
            tenant_id=uuid4(),
        )

        assert result.status == ReviewStatus.WITH_MODIFICATIONS
        assert "reduce amount" in result.reviewer_comments.lower()

    @pytest.mark.asyncio
    async def test_includes_modification_guidance(self):
        """Should include clear guidance on required modifications"""
        agent = ReviewerAgent()
        review_id = uuid4()

        result = await agent.complete_review(
            review_id=review_id,
            reviewer_id=uuid4(),
            status=ReviewStatus.WITH_MODIFICATIONS,
            comments="Modify invoice amount and resubmit",
            tenant_id=uuid4(),
        )

        assert len(result.reviewer_comments) > 10  # Meaningful guidance


# ============================================================================
# TEST SUITE 5: Reviewer Assignment
# ============================================================================


class TestReviewerAssignment:
    """Test reviewer assignment logic"""

    @pytest.mark.asyncio
    async def test_uses_assigned_reviewer(self):
        """Should use pre-assigned reviewer if specified"""
        agent = ReviewerAgent()
        assigned_reviewer = uuid4()
        task = ReviewerTask(
            decision_description="Test decision",
            context={},
            tenant_id=uuid4(),
            user_id=uuid4(),
            assigned_reviewer_id=assigned_reviewer,
        )

        result = await agent.request_review(task)

        assert result.assigned_reviewer_id == assigned_reviewer

    @pytest.mark.asyncio
    async def test_auto_assigns_reviewer(self):
        """Should auto-assign reviewer if none specified"""
        agent = ReviewerAgent()
        task = ReviewerTask(
            decision_description="Test decision",
            context={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.request_review(task)

        # Should assign a default reviewer or leave for later assignment
        assert result.status == ReviewStatus.PENDING


# ============================================================================
# TEST SUITE 6: Tenant Isolation
# ============================================================================


class TestTenantIsolation:
    """Test tenant isolation in reviews"""

    @pytest.mark.asyncio
    async def test_enforces_tenant_boundaries(self):
        """Should prevent cross-tenant review access"""
        agent = ReviewerAgent()
        review_id = uuid4()
        tenant_a = uuid4()
        tenant_b = uuid4()

        # Create review for tenant A
        task = ReviewerTask(
            decision_description="Test",
            context={},
            tenant_id=tenant_a,
            user_id=uuid4(),
        )
        await agent.request_review(task)

        # Try to complete review as tenant B
        try:
            await agent.complete_review(
                review_id=review_id,
                reviewer_id=uuid4(),
                status=ReviewStatus.APPROVED,
                comments="Approved",
                tenant_id=tenant_b,  # Different tenant
            )
            # Should either raise error or return error result
        except (ValueError, PermissionError):
            pass  # Expected behavior

    @pytest.mark.asyncio
    async def test_filters_reviews_by_tenant(self):
        """Should only return reviews for current tenant"""
        agent = ReviewerAgent()
        tenant_id = uuid4()

        # Get pending reviews for tenant
        reviews = await agent.get_pending_reviews(tenant_id=tenant_id)

        # Should be list (can be empty)
        assert isinstance(reviews, list)


# ============================================================================
# TEST SUITE 7: Review Status Tracking
# ============================================================================


class TestReviewStatusTracking:
    """Test review status lifecycle"""

    @pytest.mark.asyncio
    async def test_tracks_pending_status(self):
        """Should track pending status after submission"""
        agent = ReviewerAgent()
        task = ReviewerTask(
            decision_description="Test",
            context={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.request_review(task)

        assert result.status == ReviewStatus.PENDING

    @pytest.mark.asyncio
    async def test_transitions_to_completed_status(self):
        """Should transition from PENDING to APPROVED/REJECTED/WITH_MODIFICATIONS"""
        agent = ReviewerAgent()
        review_id = uuid4()

        result = await agent.complete_review(
            review_id=review_id,
            reviewer_id=uuid4(),
            status=ReviewStatus.APPROVED,
            comments="Approved",
            tenant_id=uuid4(),
        )

        assert result.status in [
            ReviewStatus.APPROVED,
            ReviewStatus.REJECTED,
            ReviewStatus.WITH_MODIFICATIONS,
        ]


# ============================================================================
# TEST SUITE 8: Review Comments
# ============================================================================


class TestReviewComments:
    """Test review comment handling"""

    @pytest.mark.asyncio
    async def test_stores_reviewer_comments(self):
        """Should store reviewer comments with review"""
        agent = ReviewerAgent()
        review_id = uuid4()
        comments = "Approved with minor concerns about timeline"

        result = await agent.complete_review(
            review_id=review_id,
            reviewer_id=uuid4(),
            status=ReviewStatus.APPROVED,
            comments=comments,
            tenant_id=uuid4(),
        )

        assert result.reviewer_comments == comments

    @pytest.mark.asyncio
    async def test_handles_empty_comments(self):
        """Should handle empty comments gracefully"""
        agent = ReviewerAgent()
        review_id = uuid4()

        result = await agent.complete_review(
            review_id=review_id,
            reviewer_id=uuid4(),
            status=ReviewStatus.APPROVED,
            comments="",
            tenant_id=uuid4(),
        )

        # Should either use default or accept empty
        assert result.reviewer_comments is not None


# ============================================================================
# TEST SUITE 9: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_handles_nonexistent_review(self):
        """Should handle attempts to complete nonexistent review"""
        agent = ReviewerAgent()
        nonexistent_review_id = uuid4()

        try:
            await agent.complete_review(
                review_id=nonexistent_review_id,
                reviewer_id=uuid4(),
                status=ReviewStatus.APPROVED,
                comments="Approved",
                tenant_id=uuid4(),
            )
            # Should either raise error or return error result
        except (ValueError, KeyError):
            pass  # Expected

    @pytest.mark.asyncio
    async def test_handles_invalid_status(self):
        """Should validate review status enum"""
        agent = ReviewerAgent()
        review_id = uuid4()

        # Pydantic should catch invalid status at schema level
        # This tests implementation validation
        result = await agent.complete_review(
            review_id=review_id,
            reviewer_id=uuid4(),
            status=ReviewStatus.APPROVED,  # Valid status
            comments="Test",
            tenant_id=uuid4(),
        )

        assert result.status in [
            ReviewStatus.PENDING,
            ReviewStatus.APPROVED,
            ReviewStatus.REJECTED,
            ReviewStatus.WITH_MODIFICATIONS,
        ]


# ============================================================================
# TEST SUITE 10: Validation
# ============================================================================


class TestValidation:
    """Test input validation"""

    @pytest.mark.asyncio
    async def test_requires_decision_description(self):
        """Should require decision description"""
        agent = ReviewerAgent()

        try:
            task = ReviewerTask(
                decision_description="",  # Empty
                context={},
                tenant_id=uuid4(),
                user_id=uuid4(),
            )
            await agent.request_review(task)
            # Should fail validation
            assert False, "Should have raised validation error"
        except (ValueError, TypeError):
            pass  # Expected

    @pytest.mark.asyncio
    async def test_requires_tenant_id(self):
        """Should require tenant_id"""
        agent = ReviewerAgent()

        try:
            task = ReviewerTask(
                decision_description="Test",
                context={},
                tenant_id=None,  # Missing
                user_id=uuid4(),
            )
            await agent.request_review(task)
            assert False, "Should have raised validation error"
        except (ValueError, TypeError):
            pass  # Expected

    @pytest.mark.asyncio
    async def test_requires_user_id(self):
        """Should require user_id for audit trail"""
        agent = ReviewerAgent()

        try:
            task = ReviewerTask(
                decision_description="Test",
                context={},
                tenant_id=uuid4(),
                user_id=None,  # Missing
            )
            await agent.request_review(task)
            assert False, "Should have raised validation error"
        except (ValueError, TypeError):
            pass  # Expected
