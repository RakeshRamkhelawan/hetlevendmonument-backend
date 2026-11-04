"""
Slice 7: ReviewerAgent Direct Tests (Standalone Execution)

Run directly: python test_slice7_direct.py

Tests ReviewerAgent review workflow without pytest fixtures.
"""

import asyncio
import sys
from pathlib import Path
from uuid import UUID, uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.agents.capabilities.reviewer_agent import ReviewerAgent
from src.core.agents.capabilities.schemas import ReviewerResult, ReviewerTask, ReviewStatus


async def test_submits_review_request():
    """Test 1: Successfully submit review request."""
    agent = ReviewerAgent()

    task = ReviewerTask(
        decision_description="Approve invoice for $5,000",
        context={"invoice_id": "INV-001", "amount": 5000},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await agent.request_review(task)

    assert result is not None, "Result should not be None"
    assert result.status == ReviewStatus.PENDING, f"Expected PENDING, got {result.status}"
    assert result.review_id is not None, "Review ID should be generated"
    assert result.decision_description == task.decision_description
    print("✓ Test 1 passed: Submits review request")


async def test_assigns_reviewer():
    """Test 2: Assigns reviewer to review request."""
    agent = ReviewerAgent()
    assigned_reviewer = uuid4()

    task = ReviewerTask(
        decision_description="Approve invoice",
        context={},
        tenant_id=uuid4(),
        user_id=uuid4(),
        assigned_reviewer_id=assigned_reviewer,
    )

    result = await agent.request_review(task)

    assert result.assigned_reviewer_id == assigned_reviewer
    print("✓ Test 2 passed: Assigns reviewer")


async def test_includes_submission_timestamp():
    """Test 3: Includes submission timestamp."""
    agent = ReviewerAgent()

    task = ReviewerTask(
        decision_description="Test decision",
        context={},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await agent.request_review(task)

    assert result.submitted_at is not None, "Submitted timestamp should be set"
    print("✓ Test 3 passed: Includes submission timestamp")


async def test_approves_review():
    """Test 4: Approves a pending review."""
    agent = ReviewerAgent()

    # First, submit review
    task = ReviewerTask(
        decision_description="Test approval",
        context={},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )
    submitted = await agent.request_review(task)

    # Then approve it
    result = await agent.complete_review(
        review_id=submitted.review_id,
        reviewer_id=uuid4(),
        status=ReviewStatus.APPROVED,
        comments="Looks good, approved",
        tenant_id=submitted.tenant_id,
    )

    assert result.status == ReviewStatus.APPROVED
    assert result.reviewer_comments == "Looks good, approved"
    assert result.reviewed_at is not None
    print("✓ Test 4 passed: Approves review")


async def test_rejects_review():
    """Test 5: Rejects review with reason."""
    agent = ReviewerAgent()

    # Submit review
    task = ReviewerTask(
        decision_description="Test rejection",
        context={},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )
    submitted = await agent.request_review(task)

    # Reject it
    result = await agent.complete_review(
        review_id=submitted.review_id,
        reviewer_id=uuid4(),
        status=ReviewStatus.REJECTED,
        comments="Insufficient justification",
        tenant_id=submitted.tenant_id,
    )

    assert result.status == ReviewStatus.REJECTED
    assert "Insufficient justification" in result.reviewer_comments
    print("✓ Test 5 passed: Rejects review")


async def test_requests_modifications():
    """Test 6: Requests modifications with feedback."""
    agent = ReviewerAgent()

    # Submit review
    task = ReviewerTask(
        decision_description="Test modifications",
        context={},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )
    submitted = await agent.request_review(task)

    # Request modifications
    result = await agent.complete_review(
        review_id=submitted.review_id,
        reviewer_id=uuid4(),
        status=ReviewStatus.WITH_MODIFICATIONS,
        comments="Please reduce amount to $3,000",
        tenant_id=submitted.tenant_id,
    )

    assert result.status == ReviewStatus.WITH_MODIFICATIONS
    assert "reduce amount" in result.reviewer_comments.lower()
    print("✓ Test 6 passed: Requests modifications")


async def test_records_reviewer_id():
    """Test 7: Records reviewer ID."""
    agent = ReviewerAgent()
    reviewer_id = uuid4()

    # Submit and complete
    task = ReviewerTask(
        decision_description="Test",
        context={},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )
    submitted = await agent.request_review(task)

    result = await agent.complete_review(
        review_id=submitted.review_id,
        reviewer_id=reviewer_id,
        status=ReviewStatus.APPROVED,
        comments="Approved",
        tenant_id=submitted.tenant_id,
    )

    assert result.reviewer_id == reviewer_id
    print("✓ Test 7 passed: Records reviewer ID")


async def test_enforces_tenant_boundaries():
    """Test 8: Prevents cross-tenant access."""
    agent = ReviewerAgent()
    tenant_a = uuid4()
    tenant_b = uuid4()

    # Submit for tenant A
    task = ReviewerTask(
        decision_description="Test",
        context={},
        tenant_id=tenant_a,
        user_id=uuid4(),
    )
    submitted = await agent.request_review(task)

    # Try to complete as tenant B
    try:
        await agent.complete_review(
            review_id=submitted.review_id,
            reviewer_id=uuid4(),
            status=ReviewStatus.APPROVED,
            comments="Approved",
            tenant_id=tenant_b,  # Different tenant
        )
        assert False, "Should have raised PermissionError"
    except PermissionError:
        print("✓ Test 8 passed: Enforces tenant boundaries")


async def test_handles_empty_comments():
    """Test 9: Handles empty comments gracefully."""
    agent = ReviewerAgent()

    task = ReviewerTask(
        decision_description="Test",
        context={},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )
    submitted = await agent.request_review(task)

    result = await agent.complete_review(
        review_id=submitted.review_id,
        reviewer_id=uuid4(),
        status=ReviewStatus.APPROVED,
        comments="",  # Empty
        tenant_id=submitted.tenant_id,
    )

    assert result.reviewer_comments is not None
    assert len(result.reviewer_comments) > 0
    print("✓ Test 9 passed: Handles empty comments")


async def test_get_pending_reviews():
    """Test 10: Gets pending reviews for tenant."""
    agent = ReviewerAgent()
    tenant_id = uuid4()

    # Submit 2 reviews
    for i in range(2):
        task = ReviewerTask(
            decision_description=f"Test {i}",
            context={},
            tenant_id=tenant_id,
            user_id=uuid4(),
        )
        await agent.request_review(task)

    # Get pending
    pending = await agent.get_pending_reviews(tenant_id)

    assert isinstance(pending, list)
    assert len(pending) == 2
    print("✓ Test 10 passed: Gets pending reviews")


async def test_requires_decision_description():
    """Test 11: Requires decision description."""
    agent = ReviewerAgent()

    try:
        task = ReviewerTask(
            decision_description="",  # Empty
            context={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )
        await agent.request_review(task)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "decision_description" in str(e).lower()
        print("✓ Test 11 passed: Requires decision description")


async def test_requires_tenant_id():
    """Test 12: Requires tenant_id."""
    agent = ReviewerAgent()

    try:
        task = ReviewerTask(
            decision_description="Test",
            context={},
            tenant_id=None,
            user_id=uuid4(),
        )
        await agent.request_review(task)
        assert False, "Should raise validation error"
    except (ValueError, TypeError):
        print("✓ Test 12 passed: Requires tenant_id")


async def test_requires_user_id():
    """Test 13: Requires user_id."""
    agent = ReviewerAgent()

    try:
        task = ReviewerTask(
            decision_description="Test",
            context={},
            tenant_id=uuid4(),
            user_id=None,
        )
        await agent.request_review(task)
        assert False, "Should raise validation error"
    except (ValueError, TypeError):
        print("✓ Test 13 passed: Requires user_id")


async def main():
    """Run all direct tests."""
    print("\n" + "=" * 60)
    print("SLICE 7: ReviewerAgent Direct Tests")
    print("=" * 60 + "\n")

    tests = [
        test_submits_review_request,
        test_assigns_reviewer,
        test_includes_submission_timestamp,
        test_approves_review,
        test_rejects_review,
        test_requests_modifications,
        test_records_reviewer_id,
        test_enforces_tenant_boundaries,
        test_handles_empty_comments,
        test_get_pending_reviews,
        test_requires_decision_description,
        test_requires_tenant_id,
        test_requires_user_id,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            await test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_func.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} ERROR: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
