"""
Comprehensive Test Suite for CVA State Machine
Tests CVAMode transitions, validation, callbacks, and edge cases
Target Coverage: 80%+
"""

import asyncio
from datetime import datetime, timezone

import pytest

from src.core.agents.cva_state_machine import (
    CVAMode,
    CVAStateMachine,
    StateTransitionCallback,
    StateTransitionError,
)


class TestCVAMode:
    """Tests for CVAMode enum"""

    def test_cva_mode_values(self):
        """Test CVAMode enum values are correct"""
        assert CVAMode.REACTIVE.value == "reactive"
        assert CVAMode.PROACTIVE.value == "proactive"
        assert CVAMode.AUTONOMOUS.value == "autonomous"
        assert CVAMode.CEO_MODE.value == "ceo_mode"

    def test_cva_mode_comparison(self):
        """Test CVAMode enum comparison"""
        assert CVAMode.REACTIVE == CVAMode.REACTIVE
        assert CVAMode.REACTIVE != CVAMode.PROACTIVE
        assert CVAMode.CEO_MODE != CVAMode.AUTONOMOUS

    def test_cva_mode_iteration(self):
        """Test iterating over CVAMode enum"""
        modes = list(CVAMode)
        assert len(modes) == 4
        assert CVAMode.REACTIVE in modes
        assert CVAMode.PROACTIVE in modes
        assert CVAMode.AUTONOMOUS in modes
        assert CVAMode.CEO_MODE in modes


class TestStateTransitionCallback:
    """Tests for StateTransitionCallback"""

    def test_callback_initialization(self):
        """Test callback registry initialization"""
        callback = StateTransitionCallback()
        assert isinstance(callback._on_enter, dict)
        assert isinstance(callback._on_exit, dict)
        assert isinstance(callback._on_transition, list)
        assert len(callback._on_enter) == 4
        assert len(callback._on_exit) == 4

    def test_register_on_enter_callback(self):
        """Test registering on_enter callback"""
        callback_registry = StateTransitionCallback()

        def mock_callback(context):
            pass

        callback_registry.register_on_enter(CVAMode.REACTIVE, mock_callback)
        assert len(callback_registry._on_enter[CVAMode.REACTIVE]) == 1
        assert callback_registry._on_enter[CVAMode.REACTIVE][0] == mock_callback

    def test_register_on_exit_callback(self):
        """Test registering on_exit callback"""
        callback_registry = StateTransitionCallback()

        def mock_callback(context):
            pass

        callback_registry.register_on_exit(CVAMode.PROACTIVE, mock_callback)
        assert len(callback_registry._on_exit[CVAMode.PROACTIVE]) == 1
        assert callback_registry._on_exit[CVAMode.PROACTIVE][0] == mock_callback

    def test_register_on_transition_callback(self):
        """Test registering on_transition callback"""
        callback_registry = StateTransitionCallback()

        def mock_callback(context):
            pass

        callback_registry.register_on_transition(mock_callback)
        assert len(callback_registry._on_transition) == 1
        assert callback_registry._on_transition[0] == mock_callback

    def test_non_callable_callback_raises_error(self):
        """Test that registering non-callable raises TypeError"""
        callback_registry = StateTransitionCallback()

        with pytest.raises(TypeError):
            callback_registry.register_on_enter(CVAMode.REACTIVE, "not_callable")

        with pytest.raises(TypeError):
            callback_registry.register_on_exit(CVAMode.PROACTIVE, 42)

        with pytest.raises(TypeError):
            callback_registry.register_on_transition([1, 2, 3])

    @pytest.mark.asyncio
    async def test_execute_on_enter_callbacks(self):
        """Test executing on_enter callbacks"""
        callback_registry = StateTransitionCallback()
        executed = []

        def callback1(context):
            executed.append(1)

        async def callback2(context):
            executed.append(2)

        callback_registry.register_on_enter(CVAMode.REACTIVE, callback1)
        callback_registry.register_on_enter(CVAMode.REACTIVE, callback2)

        await callback_registry.execute_on_enter(CVAMode.REACTIVE, {})

        assert 1 in executed
        assert 2 in executed
        assert len(executed) == 2

    @pytest.mark.asyncio
    async def test_execute_on_exit_callbacks(self):
        """Test executing on_exit callbacks"""
        callback_registry = StateTransitionCallback()
        executed = []

        def callback1(context):
            executed.append("exit1")

        async def callback2(context):
            executed.append("exit2")

        callback_registry.register_on_exit(CVAMode.PROACTIVE, callback1)
        callback_registry.register_on_exit(CVAMode.PROACTIVE, callback2)

        await callback_registry.execute_on_exit(CVAMode.PROACTIVE, {})

        assert "exit1" in executed
        assert "exit2" in executed

    @pytest.mark.asyncio
    async def test_execute_on_transition_callbacks(self):
        """Test executing on_transition callbacks"""
        callback_registry = StateTransitionCallback()
        executed_transitions = []

        def transition_callback(context):
            executed_transitions.append(
                {"from": context.get("from_mode"), "to": context.get("to_mode")}
            )

        callback_registry.register_on_transition(transition_callback)

        await callback_registry.execute_on_transition(CVAMode.REACTIVE, CVAMode.PROACTIVE, {})

        assert len(executed_transitions) == 1
        assert executed_transitions[0]["from"] == CVAMode.REACTIVE
        assert executed_transitions[0]["to"] == CVAMode.PROACTIVE


class TestCVAStateMachineInitialization:
    """Tests for CVAStateMachine initialization"""

    def test_initialization_with_default_mode(self):
        """Test state machine initializes with REACTIVE as default"""
        state_machine = CVAStateMachine()
        assert state_machine.current_mode == CVAMode.REACTIVE
        assert state_machine.previous_mode is None
        assert state_machine.transition_count == 0

    def test_initialization_with_custom_mode(self):
        """Test state machine initializes with custom mode"""
        state_machine = CVAStateMachine(initial_mode=CVAMode.CEO_MODE)
        assert state_machine.current_mode == CVAMode.CEO_MODE
        assert state_machine.transition_count == 0

    def test_initialization_invalid_mode_raises_error(self):
        """Test that invalid initial mode raises TypeError"""
        with pytest.raises(TypeError):
            CVAStateMachine(initial_mode="invalid")

        with pytest.raises(TypeError):
            CVAStateMachine(initial_mode=42)

    def test_valid_transitions_configuration(self):
        """Test that valid transitions are properly configured"""
        assert CVAMode.REACTIVE in CVAStateMachine.VALID_TRANSITIONS
        assert CVAMode.PROACTIVE in CVAStateMachine.VALID_TRANSITIONS
        assert CVAMode.AUTONOMOUS in CVAStateMachine.VALID_TRANSITIONS
        assert CVAMode.CEO_MODE in CVAStateMachine.VALID_TRANSITIONS

    def test_mode_hierarchy_levels(self):
        """Test mode hierarchy is correctly configured"""
        assert CVAStateMachine.MODE_HIERARCHY[CVAMode.REACTIVE] == 1
        assert CVAStateMachine.MODE_HIERARCHY[CVAMode.PROACTIVE] == 2
        assert CVAStateMachine.MODE_HIERARCHY[CVAMode.AUTONOMOUS] == 3
        assert CVAStateMachine.MODE_HIERARCHY[CVAMode.CEO_MODE] == 4


class TestCVAStateMachineTransitions:
    """Tests for CVAStateMachine transitions"""

    def test_reactive_to_proactive_valid_transition(self):
        """Test REACTIVE → PROACTIVE is valid"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        assert sm.is_valid_transition(CVAMode.PROACTIVE)

    def test_reactive_to_ceo_mode_valid_transition(self):
        """Test REACTIVE → CEO_MODE is valid"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        assert sm.is_valid_transition(CVAMode.CEO_MODE)

    def test_proactive_to_reactive_valid_transition(self):
        """Test PROACTIVE → REACTIVE is valid"""
        sm = CVAStateMachine(initial_mode=CVAMode.PROACTIVE)
        assert sm.is_valid_transition(CVAMode.REACTIVE)

    def test_proactive_to_autonomous_valid_transition(self):
        """Test PROACTIVE → AUTONOMOUS is valid"""
        sm = CVAStateMachine(initial_mode=CVAMode.PROACTIVE)
        assert sm.is_valid_transition(CVAMode.AUTONOMOUS)

    def test_autonomous_to_proactive_valid_transition(self):
        """Test AUTONOMOUS → PROACTIVE is valid"""
        sm = CVAStateMachine(initial_mode=CVAMode.AUTONOMOUS)
        assert sm.is_valid_transition(CVAMode.PROACTIVE)

    def test_ceo_mode_to_reactive_valid_transition(self):
        """Test CEO_MODE → REACTIVE is valid"""
        sm = CVAStateMachine(initial_mode=CVAMode.CEO_MODE)
        assert sm.is_valid_transition(CVAMode.REACTIVE)

    def test_reactive_to_autonomous_invalid_transition(self):
        """Test REACTIVE → AUTONOMOUS is invalid"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        assert not sm.is_valid_transition(CVAMode.AUTONOMOUS)

    def test_self_transition_invalid(self):
        """Test that self-transitions are invalid"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        assert not sm.is_valid_transition(CVAMode.REACTIVE)

    def test_validate_transition_raises_error_for_invalid(self):
        """Test validate_transition raises StateTransitionError for invalid"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)

        with pytest.raises(StateTransitionError):
            sm.validate_transition(CVAMode.AUTONOMOUS)

    def test_validate_transition_returns_true_for_valid(self):
        """Test validate_transition returns True for valid"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        assert sm.validate_transition(CVAMode.PROACTIVE) is True

    def test_validate_self_transition_raises_error(self):
        """Test that validating self-transition raises error"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)

        with pytest.raises(StateTransitionError):
            sm.validate_transition(CVAMode.REACTIVE)


class TestCVAStateMachineAsyncTransitions:
    """Tests for async transition_to method"""

    @pytest.mark.asyncio
    async def test_transition_to_updates_current_mode(self):
        """Test that transition_to updates current_mode"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        await sm.transition_to(CVAMode.PROACTIVE)
        assert sm.current_mode == CVAMode.PROACTIVE

    @pytest.mark.asyncio
    async def test_transition_to_sets_previous_mode(self):
        """Test that transition_to sets previous_mode"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        await sm.transition_to(CVAMode.PROACTIVE)
        assert sm.previous_mode == CVAMode.REACTIVE

    @pytest.mark.asyncio
    async def test_transition_to_increments_counter(self):
        """Test that transition_to increments transition_count"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        assert sm.transition_count == 0

        await sm.transition_to(CVAMode.PROACTIVE)
        assert sm.transition_count == 1

        await sm.transition_to(CVAMode.REACTIVE)
        assert sm.transition_count == 2

    @pytest.mark.asyncio
    async def test_transition_to_records_history(self):
        """Test that transition_to records transition history"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        await sm.transition_to(CVAMode.PROACTIVE, context={"reason": "test"})

        history = sm.get_transition_history()
        assert len(history) == 1
        assert history[0]["from"] == "reactive"
        assert history[0]["to"] == "proactive"
        assert history[0]["context"]["reason"] == "test"

    @pytest.mark.asyncio
    async def test_transition_to_sets_timestamp(self):
        """Test that transition_to sets last_transition_time"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        before = datetime.now(timezone.utc)

        await sm.transition_to(CVAMode.PROACTIVE)

        after = datetime.now(timezone.utc)
        assert sm.last_transition_time is not None
        assert before <= sm.last_transition_time <= after

    @pytest.mark.asyncio
    async def test_transition_to_invalid_raises_error(self):
        """Test that transition_to raises StateTransitionError for invalid"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)

        with pytest.raises(StateTransitionError):
            await sm.transition_to(CVAMode.AUTONOMOUS)

    @pytest.mark.asyncio
    async def test_multiple_sequential_transitions(self):
        """Test multiple sequential transitions"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)

        # REACTIVE → PROACTIVE
        await sm.transition_to(CVAMode.PROACTIVE)
        assert sm.current_mode == CVAMode.PROACTIVE

        # PROACTIVE → AUTONOMOUS
        await sm.transition_to(CVAMode.AUTONOMOUS)
        assert sm.current_mode == CVAMode.AUTONOMOUS

        # AUTONOMOUS → CEO_MODE
        await sm.transition_to(CVAMode.CEO_MODE)
        assert sm.current_mode == CVAMode.CEO_MODE

        assert sm.transition_count == 3


class TestCVAStateMachineCallbacks:
    """Tests for callback execution during transitions"""

    @pytest.mark.asyncio
    async def test_on_exit_callback_called(self):
        """Test that on_exit callbacks are called"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        called = []

        def exit_callback(context):
            called.append("exit")

        sm.callbacks.register_on_exit(CVAMode.REACTIVE, exit_callback)
        await sm.transition_to(CVAMode.PROACTIVE)

        assert "exit" in called

    @pytest.mark.asyncio
    async def test_on_enter_callback_called(self):
        """Test that on_enter callbacks are called"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        called = []

        def enter_callback(context):
            called.append("enter")

        sm.callbacks.register_on_enter(CVAMode.PROACTIVE, enter_callback)
        await sm.transition_to(CVAMode.PROACTIVE)

        assert "enter" in called

    @pytest.mark.asyncio
    async def test_on_transition_callback_called(self):
        """Test that on_transition callbacks are called"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        transitions = []

        def transition_callback(context):
            transitions.append((context["from_mode"], context["to_mode"]))

        sm.callbacks.register_on_transition(transition_callback)
        await sm.transition_to(CVAMode.PROACTIVE)

        assert (CVAMode.REACTIVE, CVAMode.PROACTIVE) in transitions

    @pytest.mark.asyncio
    async def test_callback_execution_order(self):
        """Test that callbacks are executed in correct order"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        order = []

        def exit_cb(ctx):
            order.append("exit")

        def transition_cb(ctx):
            order.append("transition")

        def enter_cb(ctx):
            order.append("enter")

        sm.callbacks.register_on_exit(CVAMode.REACTIVE, exit_cb)
        sm.callbacks.register_on_transition(transition_cb)
        sm.callbacks.register_on_enter(CVAMode.PROACTIVE, enter_cb)

        await sm.transition_to(CVAMode.PROACTIVE)

        # Order should be: exit, transition, enter
        assert order.index("exit") < order.index("transition")
        assert order.index("transition") < order.index("enter")

    @pytest.mark.asyncio
    async def test_async_callbacks_executed(self):
        """Test that async callbacks are properly awaited"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        called = []

        async def async_callback(context):
            await asyncio.sleep(0.01)
            called.append("async")

        sm.callbacks.register_on_enter(CVAMode.PROACTIVE, async_callback)
        await sm.transition_to(CVAMode.PROACTIVE)

        assert "async" in called


class TestCVAStateMachineQueries:
    """Tests for state machine query methods"""

    def test_get_current_mode(self):
        """Test get_current_mode returns current mode"""
        sm = CVAStateMachine(initial_mode=CVAMode.AUTONOMOUS)
        assert sm.get_current_mode() == CVAMode.AUTONOMOUS

    def test_get_previous_mode_none_initially(self):
        """Test get_previous_mode returns None initially"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        assert sm.get_previous_mode() is None

    @pytest.mark.asyncio
    async def test_get_previous_mode_after_transition(self):
        """Test get_previous_mode returns previous mode after transition"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        await sm.transition_to(CVAMode.PROACTIVE)
        assert sm.get_previous_mode() == CVAMode.REACTIVE

    def test_get_available_transitions_from_reactive(self):
        """Test get_available_transitions from REACTIVE"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        available = sm.get_available_transitions()

        assert CVAMode.PROACTIVE in available
        assert CVAMode.CEO_MODE in available
        assert CVAMode.REACTIVE not in available
        assert CVAMode.AUTONOMOUS not in available

    def test_get_available_transitions_from_proactive(self):
        """Test get_available_transitions from PROACTIVE"""
        sm = CVAStateMachine(initial_mode=CVAMode.PROACTIVE)
        available = sm.get_available_transitions()

        assert CVAMode.REACTIVE in available
        assert CVAMode.AUTONOMOUS in available
        assert CVAMode.CEO_MODE in available
        assert CVAMode.PROACTIVE not in available

    def test_get_transition_count(self):
        """Test get_transition_count returns correct count"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        assert sm.get_transition_count() == 0

    @pytest.mark.asyncio
    async def test_get_transition_history(self):
        """Test get_transition_history returns complete history"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)

        await sm.transition_to(CVAMode.PROACTIVE)
        await sm.transition_to(CVAMode.AUTONOMOUS)

        history = sm.get_transition_history()
        assert len(history) == 2
        assert history[0]["from"] == "reactive"
        assert history[1]["to"] == "autonomous"

    def test_get_mode_hierarchy_level_reactive(self):
        """Test hierarchy level for REACTIVE"""
        sm = CVAStateMachine()
        assert sm.get_mode_hierarchy_level(CVAMode.REACTIVE) == 1

    def test_get_mode_hierarchy_level_proactive(self):
        """Test hierarchy level for PROACTIVE"""
        sm = CVAStateMachine()
        assert sm.get_mode_hierarchy_level(CVAMode.PROACTIVE) == 2

    def test_get_mode_hierarchy_level_autonomous(self):
        """Test hierarchy level for AUTONOMOUS"""
        sm = CVAStateMachine()
        assert sm.get_mode_hierarchy_level(CVAMode.AUTONOMOUS) == 3

    def test_get_mode_hierarchy_level_ceo_mode(self):
        """Test hierarchy level for CEO_MODE"""
        sm = CVAStateMachine()
        assert sm.get_mode_hierarchy_level(CVAMode.CEO_MODE) == 4

    def test_is_mode_available(self):
        """Test is_mode_available"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        assert sm.is_mode_available(CVAMode.PROACTIVE)
        assert sm.is_mode_available(CVAMode.CEO_MODE)
        assert not sm.is_mode_available(CVAMode.AUTONOMOUS)

    def test_can_escalate_from_reactive(self):
        """Test can_escalate from REACTIVE"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        assert sm.can_escalate(CVAMode.PROACTIVE)
        assert sm.can_escalate(CVAMode.AUTONOMOUS)
        assert sm.can_escalate(CVAMode.CEO_MODE)

    def test_can_escalate_from_proactive(self):
        """Test can_escalate from PROACTIVE"""
        sm = CVAStateMachine(initial_mode=CVAMode.PROACTIVE)
        assert not sm.can_escalate(CVAMode.REACTIVE)
        assert sm.can_escalate(CVAMode.AUTONOMOUS)
        assert sm.can_escalate(CVAMode.CEO_MODE)

    def test_can_deescalate_from_autonomous(self):
        """Test can_deescalate from AUTONOMOUS"""
        sm = CVAStateMachine(initial_mode=CVAMode.AUTONOMOUS)
        assert sm.can_deescalate(CVAMode.REACTIVE)
        assert sm.can_deescalate(CVAMode.PROACTIVE)
        assert not sm.can_deescalate(CVAMode.CEO_MODE)

    def test_can_deescalate_from_ceo_mode(self):
        """Test can_deescalate from CEO_MODE"""
        sm = CVAStateMachine(initial_mode=CVAMode.CEO_MODE)
        assert sm.can_deescalate(CVAMode.REACTIVE)
        assert sm.can_deescalate(CVAMode.PROACTIVE)
        assert sm.can_deescalate(CVAMode.AUTONOMOUS)


class TestCVAStateMachineStateManagement:
    """Tests for state management and reset"""

    def test_reset_to_mode(self):
        """Test reset_to clears transition history"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        sm.transition_count = 5
        sm.previous_mode = CVAMode.PROACTIVE

        sm.reset_to(CVAMode.AUTONOMOUS)

        assert sm.current_mode == CVAMode.AUTONOMOUS
        assert sm.previous_mode is None
        assert sm.transition_count == 0
        assert len(sm.transition_history) == 0

    def test_get_state_summary(self):
        """Test get_state_summary returns complete state"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        summary = sm.get_state_summary()

        assert "current_mode" in summary
        assert "previous_mode" in summary
        assert "transition_count" in summary
        assert "available_transitions" in summary
        assert "hierarchy_level" in summary
        assert summary["current_mode"] == "reactive"
        assert summary["transition_count"] == 0

    @pytest.mark.asyncio
    async def test_get_state_summary_after_transitions(self):
        """Test get_state_summary after multiple transitions"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        await sm.transition_to(CVAMode.PROACTIVE)

        summary = sm.get_state_summary()

        assert summary["current_mode"] == "proactive"
        assert summary["previous_mode"] == "reactive"
        assert summary["transition_count"] == 1
        assert summary["hierarchy_level"] == 2


class TestCVAStateMachineEdgeCases:
    """Tests for edge cases and error handling"""

    def test_invalid_mode_type_is_valid_transition(self):
        """Test is_valid_transition with invalid mode type"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        assert not sm.is_valid_transition("invalid")
        assert not sm.is_valid_transition(42)
        assert not sm.is_valid_transition(None)

    def test_invalid_mode_type_validate_transition(self):
        """Test validate_transition with invalid mode type"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)

        with pytest.raises(StateTransitionError):
            sm.validate_transition("invalid")

    @pytest.mark.asyncio
    async def test_transition_with_context(self):
        """Test that context is preserved during transition"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        context = {"user_id": 123, "reason": "test"}

        await sm.transition_to(CVAMode.PROACTIVE, context=context)

        history = sm.get_transition_history()
        assert history[0]["context"]["user_id"] == 123
        assert history[0]["context"]["reason"] == "test"

    @pytest.mark.asyncio
    async def test_transition_without_context(self):
        """Test that None context is handled properly"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        await sm.transition_to(CVAMode.PROACTIVE, context=None)

        assert sm.current_mode == CVAMode.PROACTIVE

    def test_get_mode_hierarchy_default_to_current(self):
        """Test get_mode_hierarchy_level defaults to current mode"""
        sm = CVAStateMachine(initial_mode=CVAMode.AUTONOMOUS)

        # Without passing mode parameter
        level = sm.get_mode_hierarchy_level()
        assert level == 3  # AUTONOMOUS level

    def test_transition_history_immutability(self):
        """Test that returned history is a copy"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)

        history1 = sm.get_transition_history()
        history2 = sm.get_transition_history()

        # Should be equal but not the same object
        assert history1 == history2
        assert history1 is not history2


class TestCVAStateMachineTransitionGraphComplexity:
    """Tests for complex transition scenarios"""

    @pytest.mark.asyncio
    async def test_circular_transitions(self):
        """Test performing circular transitions"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)

        # REACTIVE → PROACTIVE → AUTONOMOUS → CEO_MODE → PROACTIVE → REACTIVE
        await sm.transition_to(CVAMode.PROACTIVE)
        await sm.transition_to(CVAMode.AUTONOMOUS)
        await sm.transition_to(CVAMode.CEO_MODE)
        await sm.transition_to(CVAMode.PROACTIVE)
        await sm.transition_to(CVAMode.REACTIVE)

        assert sm.current_mode == CVAMode.REACTIVE
        assert sm.transition_count == 5
        assert len(sm.get_transition_history()) == 5

    @pytest.mark.asyncio
    async def test_escalation_path(self):
        """Test full escalation path: REACTIVE → CEO_MODE"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)

        await sm.transition_to(CVAMode.PROACTIVE)
        await sm.transition_to(CVAMode.AUTONOMOUS)
        await sm.transition_to(CVAMode.CEO_MODE)

        assert sm.current_mode == CVAMode.CEO_MODE
        assert sm.get_mode_hierarchy_level() == 4

    @pytest.mark.asyncio
    async def test_deescalation_path(self):
        """Test full deescalation path: CEO_MODE → REACTIVE"""
        sm = CVAStateMachine(initial_mode=CVAMode.CEO_MODE)

        await sm.transition_to(CVAMode.AUTONOMOUS)
        await sm.transition_to(CVAMode.PROACTIVE)
        await sm.transition_to(CVAMode.REACTIVE)

        assert sm.current_mode == CVAMode.REACTIVE
        assert sm.get_mode_hierarchy_level() == 1


class TestCVAStateMachineStressTest:
    """Stress tests for state machine"""

    @pytest.mark.asyncio
    async def test_many_transitions(self):
        """Test handling many transitions"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)

        # Perform 50 transitions
        for i in range(50):
            if sm.current_mode == CVAMode.REACTIVE:
                await sm.transition_to(CVAMode.PROACTIVE)
            elif sm.current_mode == CVAMode.PROACTIVE:
                await sm.transition_to(CVAMode.REACTIVE)

        assert sm.transition_count == 50
        assert len(sm.get_transition_history()) == 50

    @pytest.mark.asyncio
    async def test_many_callbacks(self):
        """Test handling many registered callbacks"""
        sm = CVAStateMachine(initial_mode=CVAMode.REACTIVE)
        called = []

        # Register 10 callbacks for each event
        for i in range(10):
            sm.callbacks.register_on_exit(
                CVAMode.REACTIVE, lambda ctx, i=i: called.append(f"exit{i}")
            )
            sm.callbacks.register_on_transition(lambda ctx, i=i: called.append(f"trans{i}"))
            sm.callbacks.register_on_enter(
                CVAMode.PROACTIVE, lambda ctx, i=i: called.append(f"enter{i}")
            )

        await sm.transition_to(CVAMode.PROACTIVE)

        # Should have called all callbacks
        assert len(called) >= 20  # At least exit and transition callbacks
