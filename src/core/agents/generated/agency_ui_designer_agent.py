"""Legacy compatibility Agency UI Designer agent."""

from __future__ import annotations

import time
from typing import Any, Dict

from src.core.agents.llm_types import ExecutionResult


class AgencyUiDesignerAgent:
    """Compatibility agent used by legacy e2e tests."""

    def __init__(self, agent_id: str = "agency_ui_designer", tenant_id: int = 1) -> None:
        self.agent_id = agent_id
        self.tenant_id = tenant_id

    async def initialize(self) -> None:
        pass

    def _create_design_system(self, payload: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        colors = payload.get("brand_colors", {}) if isinstance(payload, dict) else {}
        primary = colors.get("primary", "#3b82f6")
        secondary = colors.get("secondary", "#6366f1")
        spacing = payload.get("spacing_base", 8) if isinstance(payload, dict) else 8
        return {
            "css_variables": f":root{{--color-primary:{primary};--color-secondary:{secondary};--spacing-base:{spacing}px;}}",
            "component_tokens": {
                "button": {"radius": "8px", "padding": f"{spacing}px {spacing * 2}px"},
                "card": {"radius": "12px", "shadow": "sm"},
            },
        }

    async def process_task(self, task_data: Any) -> ExecutionResult:  # TODO(TYPE): replace Any with concrete type
        start = time.time()
        payload = getattr(task_data, "payload", None)
        if not isinstance(payload, dict):
            payload = (getattr(task_data, "metadata", {}) or {}).get("payload", {})
        result = self._create_design_system(payload if isinstance(payload, dict) else {})
        return ExecutionResult(
            task_id=getattr(task_data, "id", "agency_ui_designer_task"),
            success=True,
            result_data=result,
            execution_time=time.time() - start,
        )


agency_ui_designer = AgencyUiDesignerAgent()
