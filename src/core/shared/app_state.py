# Global application state shared between lifecycle, endpoints, and background tasks.
# Written by api/setup/lifecycle.py; read by copilot and other non-api layers.
from typing import Any

app_state: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
    "cva_agent": None,
    "sandbox_manager": None,
    "sandbox_orchestrator": None,
    "websocket_manager": None,
    "rate_limiter": None,
    "task_queue": [],
    "active_tasks": {},
    "system_metrics": {},
    "tool_broker_service": None,
    "tool_broker_enabled": False,
    "database_initialized": False,
    "phase3_collaboration_enabled": False,
    "phase4_autonomous_enabled": False,
    "mock_usage_detector_enabled": False,
    "training_service": None,
    "monitoring_task": None,
    "log_entries": [],
    "log_broadcast_queue": [],
}
