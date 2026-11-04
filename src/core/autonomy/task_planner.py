"""
Legacy TaskPlanner Implementation - BACKWARD COMPATIBILITY WRAPPER
Maintains compatibility with existing code while delegating to enhanced implementation
ASCII-only compliance enforced
"""

# Import all components from enhanced implementation

from .enhanced_task_planner import (
    EnhancedTaskPlanner,
    ExecutionPlan,
    ExecutionStep,
    Goal,
    TaskPlanner,
    create_enhanced_task_planner,
    create_task_planner,
)

# Re-export all symbols for backward compatibility
__all__ = [
    "Goal",
    "ExecutionStep",
    "ExecutionPlan",
    "TaskPlanner",
    "EnhancedTaskPlanner",
    "create_task_planner",
    "create_enhanced_task_planner",
]
