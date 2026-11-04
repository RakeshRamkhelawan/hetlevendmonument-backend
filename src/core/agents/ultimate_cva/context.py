from datetime import datetime, timezone
from typing import Any

from .models import IntentType, ParsedCommand, UltimateExecutionResult


def enhance_context(
    context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    parsed_command: ParsedCommand,
    execution_history: list[UltimateExecutionResult],
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Enhance context with historical data and intelligent defaults"""
    enhanced = context.copy()
    enhanced["timestamp"] = datetime.now(timezone.utc).isoformat()
    enhanced["parsed_confidence"] = parsed_command.confidence
    enhanced["llm_enhanced"] = True

    # Add historical context from recent executions
    if execution_history:
        recent_commands = [ex for ex in execution_history[-5:] if ex.success]
        if recent_commands:
            enhanced["recent_success_rate"] = len(recent_commands) / min(5, len(execution_history))
            enhanced["average_response_time"] = sum(
                ex.execution_time for ex in recent_commands
            ) / len(recent_commands)

    return enhanced


def update_context_memory(
    context_memory: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    parsed_command: ParsedCommand,
    result: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Update context memory for learning (returns updated list)"""
    memory_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": parsed_command.original_text,
        "intent": parsed_command.intent.value,
        "confidence": parsed_command.confidence,
        "success": result.get("success", False),
        "context": context,
        "llm_provider": result.get("llm_provider", "unknown"),
    }

    # Create new list to avoid side effects if possible, but list is mutable
    context_memory.append(memory_entry)

    if len(context_memory) > 50:
        return context_memory[-25:]
    return context_memory


def generate_intelligent_suggestions(
    parsed_command: ParsedCommand,
    result: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    execution_history: list[UltimateExecutionResult],
) -> list[str]:
    """Generate intelligent suggestions based on command and result"""
    suggestions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    if result.get("success"):
        if parsed_command.intent == IntentType.SYSTEM_STATUS:
            suggestions.append(
                "[IDEA] You can also ask about specific agent performance or task status"
            )
        elif parsed_command.intent == IntentType.AGENT_MANAGEMENT:
            suggestions.append(
                "[IDEA] Try assigning a task to a specific agent or checking agent performance"
            )
        elif parsed_command.intent == IntentType.TASK_MANAGEMENT:
            suggestions.append("[IDEA] You can check task status or list all tasks to track progress")
    else:
        suggestions.append("[TOOL] Try checking system status first to identify any issues")

    # Performance-based suggestions
    if execution_history:
        avg_time = sum(ex.execution_time for ex in execution_history[-5:]) / min(
            5, len(execution_history)
        )
        if avg_time > 2.0:
            suggestions.append("[FAST] System response is slower than usual - consider optimization")

    return suggestions or ["[OK] Ultimate CVA operating optimally - all commands available"]
