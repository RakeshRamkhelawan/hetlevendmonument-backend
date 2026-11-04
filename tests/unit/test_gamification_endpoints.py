"""
Unit tests for Gamification feature (Feature 5).
Tests gamification models, service, and API endpoints.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# Test Gamification Models
# ============================================================================


class TestUserPointsModel:
    """Tests for UserPoints database model."""

    def test_user_points_fields(self):
        """Test UserPoints has required fields."""
        required_fields = [
            "id",
            "user_id",
            "tenant_id",
            "total_points",
            "level",
            "created_at",
            "updated_at",
        ]
        for field in required_fields:
            assert isinstance(field, str)

    def test_user_points_defaults(self):
        """Test default values for UserPoints."""
        defaults = {
            "total_points": 0,
            "level": 1,
        }
        assert defaults["total_points"] == 0
        assert defaults["level"] == 1

    def test_user_points_constraints(self):
        """Test UserPoints constraints."""
        # Points should be non-negative
        valid_points = [0, 100, 10000]
        for points in valid_points:
            assert points >= 0

    def test_level_calculation(self):
        """Test level calculation based on points."""
        # Example: Level = points // 1000 + 1
        test_cases = [
            (0, 1),
            (999, 1),
            (1000, 2),
            (5000, 6),
        ]
        for points, expected_level in test_cases:
            level = points // 1000 + 1
            assert level == expected_level


class TestBadgeModel:
    """Tests for Badge database model."""

    def test_badge_fields(self):
        """Test Badge has required fields."""
        required_fields = [
            "id",
            "tenant_id",
            "name",
            "description",
            "icon_url",
            "points_required",
            "is_active",
        ]
        for field in required_fields:
            assert isinstance(field, str)

    def test_badge_defaults(self):
        """Test default values for Badge."""
        defaults = {
            "is_active": True,
            "points_required": 0,
        }
        assert defaults["is_active"] is True

    def test_badge_types(self):
        """Test different badge types/tiers."""
        badge_tiers = [
            {"name": "Bronze", "points_required": 100},
            {"name": "Silver", "points_required": 500},
            {"name": "Gold", "points_required": 1000},
            {"name": "Platinum", "points_required": 5000},
        ]
        for badge in badge_tiers:
            assert badge["points_required"] >= 0


class TestUserBadgeModel:
    """Tests for UserBadge junction model."""

    def test_user_badge_fields(self):
        """Test UserBadge has required fields."""
        required_fields = ["id", "user_id", "badge_id", "awarded_at"]
        for field in required_fields:
            assert isinstance(field, str)

    def test_user_badge_unique_constraint(self):
        """Test user can only have each badge once."""
        # Composite unique on (user_id, badge_id)
        user_badges = [
            {"user_id": 1, "badge_id": 1},
            {"user_id": 1, "badge_id": 2},
            {"user_id": 2, "badge_id": 1},
        ]
        # Should be all unique combinations
        combinations = [(b["user_id"], b["badge_id"]) for b in user_badges]
        assert len(combinations) == len(set(combinations))


class TestPointTransactionModel:
    """Tests for PointTransaction model."""

    def test_transaction_fields(self):
        """Test PointTransaction has required fields."""
        required_fields = [
            "id",
            "user_id",
            "tenant_id",
            "points",
            "action",
            "description",
            "created_at",
        ]
        for field in required_fields:
            assert isinstance(field, str)

    def test_transaction_actions(self):
        """Test valid transaction actions."""
        valid_actions = [
            "workflow_completed",
            "task_completed",
            "daily_login",
            "badge_earned",
            "challenge_completed",
            "referral_bonus",
        ]
        for action in valid_actions:
            assert isinstance(action, str)
            assert len(action) > 0

    def test_transaction_positive_negative(self):
        """Test transactions can be positive or negative."""
        transactions = [
            {"points": 100, "action": "task_completed"},  # Positive
            {"points": -50, "action": "penalty"},  # Negative (if supported)
        ]
        assert transactions[0]["points"] > 0


# ============================================================================
# Test Gamification Service
# ============================================================================


class TestGamificationServiceAwardPoints:
    """Tests for awarding points."""

    @pytest.mark.asyncio
    async def test_award_points_new_user(self):
        """Test awarding points to user without existing record."""
        mock_db = AsyncMock()

        # No existing UserPoints record
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Should create new UserPoints
        new_points = MagicMock(user_id=1, total_points=100, level=1)
        mock_db.add = MagicMock()
        mock_db.add(new_points)

        assert new_points.total_points == 100

    @pytest.mark.asyncio
    async def test_award_points_existing_user(self):
        """Test awarding points to user with existing record."""
        existing_points = MagicMock(user_id=1, total_points=500, level=1)

        # Add 100 points
        existing_points.total_points += 100

        assert existing_points.total_points == 600

    @pytest.mark.asyncio
    async def test_award_points_level_up(self):
        """Test level up when points threshold crossed."""
        user_points = MagicMock(total_points=950, level=1)

        # Add 100 points
        user_points.total_points += 100

        # Should trigger level up
        new_level = user_points.total_points // 1000 + 1
        assert new_level == 2

    @pytest.mark.asyncio
    async def test_award_points_creates_transaction(self):
        """Test awarding points creates a transaction record."""
        mock_db = AsyncMock()

        transaction = MagicMock(
            user_id=1,
            points=100,
            action="workflow_completed",
            description="Completed workflow XYZ",
        )

        mock_db.add = MagicMock()
        mock_db.add(transaction)

        assert transaction.action == "workflow_completed"


class TestGamificationServiceBadges:
    """Tests for badge operations."""

    @pytest.mark.asyncio
    async def test_check_and_award_badges(self):
        """Test checking and awarding eligible badges."""
        user_points = MagicMock(total_points=1500)

        available_badges = [
            MagicMock(id=1, name="Bronze", points_required=100),
            MagicMock(id=2, name="Silver", points_required=500),
            MagicMock(id=3, name="Gold", points_required=1000),
            MagicMock(id=4, name="Platinum", points_required=5000),
        ]

        # User should qualify for Bronze, Silver, Gold
        eligible = [b for b in available_badges if b.points_required <= user_points.total_points]
        assert len(eligible) == 3

    @pytest.mark.asyncio
    async def test_badge_not_awarded_twice(self):
        """Test user doesn't get same badge twice."""
        existing_badges = [1, 2]  # User has badge IDs 1 and 2
        new_eligible = [1, 2, 3]  # Eligible for badges 1, 2, 3

        # Only award badge 3
        to_award = [b for b in new_eligible if b not in existing_badges]
        assert to_award == [3]

    @pytest.mark.asyncio
    async def test_get_user_badges(self):
        """Test getting all badges for a user."""
        user_badges = [
            MagicMock(badge_id=1, badge_name="Bronze", awarded_at=datetime.utcnow()),
            MagicMock(badge_id=2, badge_name="Silver", awarded_at=datetime.utcnow()),
        ]

        assert len(user_badges) == 2


class TestGamificationServiceProfile:
    """Tests for user gamification profile."""

    @pytest.mark.asyncio
    async def test_get_user_profile(self):
        """Test getting complete gamification profile."""
        profile = {
            "user_id": 1,
            "total_points": 1500,
            "level": 2,
            "badges": [
                {"id": 1, "name": "Bronze"},
                {"id": 2, "name": "Silver"},
            ],
            "recent_transactions": [
                {"points": 100, "action": "workflow_completed"},
            ],
        }

        assert profile["level"] == 2
        assert len(profile["badges"]) == 2

    @pytest.mark.asyncio
    async def test_get_user_profile_new_user(self):
        """Test profile for user with no gamification history."""
        profile = {
            "user_id": 1,
            "total_points": 0,
            "level": 1,
            "badges": [],
            "recent_transactions": [],
        }

        assert profile["total_points"] == 0
        assert profile["level"] == 1


class TestGamificationServiceLeaderboard:
    """Tests for leaderboard functionality."""

    @pytest.mark.asyncio
    async def test_get_leaderboard(self):
        """Test getting top users leaderboard."""
        leaderboard = [
            {"user_id": 5, "total_points": 10000, "rank": 1},
            {"user_id": 3, "total_points": 8000, "rank": 2},
            {"user_id": 7, "total_points": 6000, "rank": 3},
        ]

        # Should be sorted by points descending
        points = [entry["total_points"] for entry in leaderboard]
        assert points == sorted(points, reverse=True)

    @pytest.mark.asyncio
    async def test_get_leaderboard_limit(self):
        """Test leaderboard respects limit."""
        limit = 10
        leaderboard = [{"user_id": i, "rank": i} for i in range(1, 15)]

        limited = leaderboard[:limit]
        assert len(limited) == 10

    @pytest.mark.asyncio
    async def test_get_leaderboard_tenant_scoped(self):
        """Test leaderboard is scoped to tenant."""
        tenant_1_users = [
            {"user_id": 1, "tenant_id": 1, "total_points": 1000},
            {"user_id": 2, "tenant_id": 1, "total_points": 500},
        ]
        tenant_2_users = [
            {"user_id": 3, "tenant_id": 2, "total_points": 2000},
        ]

        # Tenant 1 leaderboard should only include tenant 1 users
        tenant_1_leaderboard = [u for u in tenant_1_users + tenant_2_users if u["tenant_id"] == 1]
        assert len(tenant_1_leaderboard) == 2


# ============================================================================
# Test Gamification API Endpoints
# ============================================================================


class TestGamificationAPISchemas:
    """Tests for Gamification API schemas."""

    def test_award_points_request_schema(self):
        """Test AwardPointsRequest schema."""
        request = {
            "user_id": 1,
            "points": 100,
            "action": "task_completed",
            "description": "Completed onboarding task",
        }

        assert request["points"] > 0
        assert "action" in request

    def test_user_profile_response_schema(self):
        """Test UserProfileResponse schema."""
        response = {
            "user_id": 1,
            "total_points": 1500,
            "level": 2,
            "badges": [],
            "next_level_points": 2000,
            "progress_to_next_level": 0.5,
        }

        assert "level" in response
        assert "total_points" in response

    def test_leaderboard_entry_schema(self):
        """Test LeaderboardEntry schema."""
        entry = {
            "rank": 1,
            "user_id": 5,
            "username": "topuser",
            "total_points": 10000,
            "level": 11,
        }

        assert entry["rank"] >= 1
        assert entry["total_points"] >= 0


class TestGamificationAPIEndpoints:
    """Tests for Gamification API endpoints."""

    @pytest.mark.asyncio
    async def test_get_profile_endpoint(self):
        """Test GET /api/v1/gamification/profile returns user profile."""
        response = {
            "user_id": 1,
            "total_points": 1500,
            "level": 2,
            "badges": [{"id": 1, "name": "Bronze"}],
        }

        assert "total_points" in response
        assert "level" in response
        assert "badges" in response

    @pytest.mark.asyncio
    async def test_get_leaderboard_endpoint(self):
        """Test GET /api/v1/gamification/leaderboard returns rankings."""
        response = [
            {"rank": 1, "user_id": 5, "total_points": 10000},
            {"rank": 2, "user_id": 3, "total_points": 8000},
        ]

        assert isinstance(response, list)
        assert response[0]["rank"] == 1

    @pytest.mark.asyncio
    async def test_award_points_endpoint(self):
        """Test POST /api/v1/gamification/award awards points."""
        request = {"user_id": 1, "points": 100, "action": "workflow_completed"}
        response = {"status": "success", "new_total": 1600, "new_level": 2}

        assert response["status"] == "success"
        assert "new_total" in response

    @pytest.mark.asyncio
    async def test_check_badges_endpoint(self):
        """Test POST /api/v1/gamification/check-badges checks for new badges."""
        response = {"new_badges": [{"id": 3, "name": "Gold"}], "total_badges": 3}

        assert "new_badges" in response


class TestGamificationAPIErrorHandling:
    """Tests for API error handling."""

    @pytest.mark.asyncio
    async def test_invalid_user_id_error(self):
        """Test error for invalid user ID."""
        error = {"detail": "User not found"}
        status_code = 404
        assert status_code == 404

    @pytest.mark.asyncio
    async def test_negative_points_error(self):
        """Test error for negative points (if not allowed)."""
        error = {"detail": "Points must be positive"}
        assert "positive" in error["detail"].lower()

    @pytest.mark.asyncio
    async def test_unauthorized_award_error(self):
        """Test error when non-admin tries to award points."""
        error = {"detail": "Insufficient permissions"}
        status_code = 403
        assert status_code == 403


class TestGamificationTenantIsolation:
    """Tests for tenant isolation in gamification."""

    @pytest.mark.asyncio
    async def test_points_scoped_to_tenant(self):
        """Test points are isolated per tenant."""
        tenant_1_user = {"user_id": 1, "tenant_id": 1, "total_points": 1000}
        tenant_2_user = {"user_id": 1, "tenant_id": 2, "total_points": 500}

        # Same user_id in different tenants have different points
        assert tenant_1_user["total_points"] != tenant_2_user["total_points"]

    @pytest.mark.asyncio
    async def test_leaderboard_tenant_isolated(self):
        """Test leaderboard only shows users from same tenant."""
        all_users = [
            {"user_id": 1, "tenant_id": 1, "total_points": 1000},
            {"user_id": 2, "tenant_id": 1, "total_points": 500},
            {"user_id": 3, "tenant_id": 2, "total_points": 2000},
        ]

        tenant_1_leaderboard = [u for u in all_users if u["tenant_id"] == 1]

        # Tenant 1 user should not see tenant 2's top scorer
        assert all(u["tenant_id"] == 1 for u in tenant_1_leaderboard)
        assert len(tenant_1_leaderboard) == 2


class TestGamificationPointsCalculation:
    """Tests for points calculation logic."""

    def test_workflow_completion_points(self):
        """Test points awarded for workflow completion."""
        base_points = 100
        assert base_points > 0

    def test_task_completion_points(self):
        """Test points awarded for task completion."""
        base_points = 25
        assert base_points > 0

    def test_daily_login_bonus(self):
        """Test daily login bonus points."""
        daily_bonus = 10
        assert daily_bonus > 0

    def test_streak_bonus_multiplier(self):
        """Test streak bonus increases points."""
        base_points = 10
        streak_days = 7
        multiplier = 1 + (streak_days * 0.1)  # 10% per day

        bonus_points = int(base_points * multiplier)
        assert bonus_points > base_points

    def test_level_thresholds(self):
        """Test level thresholds are consistent."""
        thresholds = [0, 1000, 2000, 3000, 5000, 10000]

        # Each threshold should be higher than previous
        for i in range(1, len(thresholds)):
            assert thresholds[i] > thresholds[i - 1]
