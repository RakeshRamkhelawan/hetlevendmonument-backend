"""
F2 self-healing -- Real repair execution tests (TDD RED phase).

Covers:
1. Per-strategy dispatch: MANUAL -> success=False, others -> success=True
2. Max repair attempts (3) enforced; attempt #4 escalates to MANUAL
3. Cooldown (60 s) between consecutive attempts on the same failure_id
4. Repair history recording
5. repairs_in_progress drops to 0 after completion
"""

import asyncio
from datetime import datetime, timedelta, timezone

from src.core.autonomy.self_healing_system import (
    FailureType,
    RepairPlan,
    RepairResult,
    RepairStrategy,
    SelfHealingSystem,
    SystemFailure,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_failure(
    failure_type: FailureType = FailureType.AGENT_CRASH,
    failure_id: str = "f2-test",
) -> SystemFailure:
    return SystemFailure(
        failure_id=failure_id,
        failure_type=failure_type,
        component="test_component",
        severity=5,
        timestamp=datetime.now(timezone.utc),
        description="test failure",
    )


def _make_plan(
    failure_id: str = "f2-test",
    strategy: RepairStrategy = RepairStrategy.RESTART,
) -> RepairPlan:
    return RepairPlan(
        plan_id=f"plan_{failure_id}",
        failure_id=failure_id,
        actions=["restart_component", "verify_health"],
        estimated_duration=timedelta(seconds=5),
        success_probability=0.85,
        strategy=strategy,
    )


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. Per-strategy dispatch
# ---------------------------------------------------------------------------


class TestRepairStrategyDispatch:
    """Different strategies must produce the correct success outcome."""

    def test_restart_strategy_returns_success(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan(strategy=RepairStrategy.RESTART)
        result = _run(system.execute_repair_plan(plan))
        assert result.success is True
        assert result.final_status == "healthy"

    def test_patch_strategy_returns_success(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan(strategy=RepairStrategy.PATCH)
        result = _run(system.execute_repair_plan(plan))
        assert result.success is True

    def test_rollback_strategy_returns_success(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan(strategy=RepairStrategy.ROLLBACK)
        result = _run(system.execute_repair_plan(plan))
        assert result.success is True

    def test_replace_strategy_returns_success(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan(strategy=RepairStrategy.REPLACE)
        result = _run(system.execute_repair_plan(plan))
        assert result.success is True

    def test_manual_strategy_returns_failure(self) -> None:
        """MANUAL means a human is required -- auto-repair cannot succeed."""
        system = SelfHealingSystem()
        plan = _make_plan(strategy=RepairStrategy.MANUAL)
        result = _run(system.execute_repair_plan(plan))
        assert result.success is False
        assert "manual" in result.final_status.lower()

    def test_restart_actions_are_not_empty(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan(strategy=RepairStrategy.RESTART)
        result = _run(system.execute_repair_plan(plan))
        assert len(result.actions_taken) > 0


# ---------------------------------------------------------------------------
# 2. Attempt tracking and max-attempt limit
# ---------------------------------------------------------------------------


class TestRepairAttemptLimits:
    """Max 3 repair attempts per failure_id; #4 must be rejected."""

    def test_first_attempt_increments_counter(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan()
        _run(system.execute_repair_plan(plan))
        assert system.get_attempt_count("f2-test") == 1

    def test_after_cooldown_second_attempt_increments_counter(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan()
        _run(system.execute_repair_plan(plan))
        # Manually expire cooldown so 2nd attempt is not blocked
        system._repair_cooldowns["f2-test"] = datetime.now(timezone.utc) - timedelta(seconds=61)
        _run(system.execute_repair_plan(plan))
        assert system.get_attempt_count("f2-test") == 2

    def test_third_attempt_still_succeeds(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan()
        for _ in range(3):
            _run(system.execute_repair_plan(plan))
            # Expire cooldown between each attempt
            system._repair_cooldowns["f2-test"] = datetime.now(timezone.utc) - timedelta(seconds=61)
        assert system.get_attempt_count("f2-test") == 3

    def test_fourth_attempt_escalates_to_manual(self) -> None:
        """After 3 repairs the 4th must be rejected (max attempts exceeded)."""
        system = SelfHealingSystem()
        plan = _make_plan()
        for _ in range(3):
            _run(system.execute_repair_plan(plan))
            system._repair_cooldowns["f2-test"] = datetime.now(timezone.utc) - timedelta(seconds=61)
        # 4th attempt -- should be rejected
        result = _run(system.execute_repair_plan(plan))
        assert result.success is False
        status_lower = result.final_status.lower()
        assert "max" in status_lower or "escalat" in status_lower

    def test_cooldown_blocked_attempt_does_not_count(self) -> None:
        """A cooldown-blocked attempt must NOT count against the 3-attempt limit."""
        system = SelfHealingSystem()
        plan = _make_plan()
        _run(system.execute_repair_plan(plan))  # attempt 1
        # Attempt 2 immediately -- blocked by cooldown
        _run(system.execute_repair_plan(plan))
        # Counter must still be 1
        assert system.get_attempt_count("f2-test") == 1


# ---------------------------------------------------------------------------
# 3. Cooldown enforcement
# ---------------------------------------------------------------------------


class TestRepairCooldown:
    """60-second cooldown must be enforced between consecutive repairs."""

    def test_immediate_second_attempt_blocked(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan()
        _run(system.execute_repair_plan(plan))
        # 2nd attempt without waiting -- must be blocked
        result = _run(system.execute_repair_plan(plan))
        assert result.success is False
        assert "cooldown" in result.final_status.lower()

    def test_attempt_after_cooldown_expired_is_allowed(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan()
        _run(system.execute_repair_plan(plan))
        # Expire the cooldown manually
        system._repair_cooldowns["f2-test"] = datetime.now(timezone.utc) - timedelta(seconds=61)
        result = _run(system.execute_repair_plan(plan))
        assert result.success is True

    def test_fresh_system_has_no_cooldown(self) -> None:
        """Brand-new SelfHealingSystem has no cooldown for any failure."""
        system = SelfHealingSystem()
        plan = _make_plan()
        result = _run(system.execute_repair_plan(plan))
        assert result.success is True


# ---------------------------------------------------------------------------
# 4. History recording and system status
# ---------------------------------------------------------------------------


class TestRepairHistoryAndStatus:
    """Repair results must appear in history + reflected in status."""

    def test_repair_added_to_history(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan()
        _run(system.execute_repair_plan(plan))
        assert len(system.repair_history) == 1

    def test_two_different_failures_both_in_history(self) -> None:
        system = SelfHealingSystem()
        plan_a = _make_plan(failure_id="fa")
        plan_b = _make_plan(failure_id="fb")
        _run(system.execute_repair_plan(plan_a))
        _run(system.execute_repair_plan(plan_b))
        assert len(system.repair_history) == 2

    def test_status_repairs_in_progress_zero_after_completion(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan()
        _run(system.execute_repair_plan(plan))
        status = _run(system.get_system_status())
        assert status["repairs_in_progress"] == 0

    def test_repair_result_has_nonnegative_execution_time(self) -> None:
        system = SelfHealingSystem()
        plan = _make_plan()
        result = _run(system.execute_repair_plan(plan))
        assert result.execution_time >= 0.0

    def test_successful_repair_removes_failure_from_active(self) -> None:
        system = SelfHealingSystem()
        failure = _make_failure()
        plan = _run(system.detect_and_diagnose_failure(failure))
        assert "f2-test" in system.failures
        _run(system.execute_repair_plan(plan))
        assert "f2-test" not in system.failures
