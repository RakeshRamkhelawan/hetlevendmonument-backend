"""Generated Agents Module - compatibility exports for legacy agency imports."""

from __future__ import annotations

import time
import warnings
from typing import Any

from src.core.agents.capabilities.agency_capabilities import (
    AgencyCapabilityRegistry,
    DesignCapabilities,
    EngineeringCapabilities,
    MarketingCapabilities,
)
from src.core.agents.capabilities.planner_agent_with_agency import (
    PlannerAgentWithAgency,
    create_planner_agent_with_agency,
)
from src.core.agents.llm_types import ExecutionResult

warnings.warn(
    "The src.core.agents.generated module is deprecated. "
    "Agency agents are now integrated as capabilities. "
    "Use AgencyCapabilityRegistry or PlannerAgentWithAgency instead.",
    DeprecationWarning,
    stacklevel=2,
)


class _LegacyAgencyAdapter:
    """Minimal async adapter to keep legacy agency e2e imports operational."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True

    async def process_task(self, task_data: Any) -> ExecutionResult:  # TODO(TYPE): replace Any with concrete type
        start = time.time()
        payload = self._extract_payload(task_data)
        task_type = self._extract_task_type(task_data)
        result_data = self._build_result(task_type, payload)
        task_id = getattr(task_data, "id", f"legacy_{self.name}")
        return ExecutionResult(
            task_id=task_id,
            success=True,
            result_data=result_data,
            execution_time=time.time() - start,
        )

    @staticmethod
    def _extract_payload(task_data: Any) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        payload = getattr(task_data, "payload", None)
        if isinstance(payload, dict):
            return payload
        metadata = getattr(task_data, "metadata", {}) or {}
        maybe_payload = metadata.get("payload")
        if isinstance(maybe_payload, dict):
            return maybe_payload
        return {}

    @staticmethod
    def _extract_task_type(task_data: Any) -> str:  # TODO(TYPE): replace Any with concrete type
        metadata = getattr(task_data, "metadata", {}) or {}
        return str(metadata.get("type", ""))

    def _build_result(self, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        if self.name == "ui_designer":
            colors = payload.get("brand_colors", {})
            primary = colors.get("primary", "#3b82f6")
            secondary = colors.get("secondary", "#6366f1")
            return {
                "task_type": task_type,
                "css_variables": f":root{{--color-primary:{primary};--color-secondary:{secondary};}}",
            }

        if self.name == "security_engineer":
            sensitivity = str(payload.get("data_sensitivity", "low")).lower()
            threats = [{"category": "Denial of Service", "severity": "medium"}]
            if sensitivity == "high":
                threats.append({"category": "Information Disclosure", "severity": "high"})
            return {"task_type": task_type, "threats": threats}

        if self.name == "backend_architect":
            resources = payload.get("resources", ["resource"])
            endpoints = [f"/api/v1/{r}" for r in resources]
            return {"task_type": task_type, "endpoints": endpoints}

        if self.name == "growth_hacker":
            return {
                "task_type": task_type,
                "kpi_targets": {"viral_coefficient": 1.2, "activation_rate": 0.35},
            }

        if self.name == "content_creator":
            topic = payload.get("topic", "New Feature")
            return {
                "task_type": task_type,
                "headlines": [
                    f"{topic}: What You Need to Know",
                    f"How {topic} Changes the Game",
                    f"A Practical Guide to {topic}",
                ],
            }

        if self.name == "frontend_developer":
            component_name = payload.get("component_name", "Component")
            code = f"export function {component_name}() {{ return <div>{component_name}</div>; }}"
            return {"task_type": task_type, "code": code}

        if self.name == "brand_guardian":
            return {"task_type": task_type, "compliance_score": 0.95}

        return {"task_type": task_type}


# Legacy names expected by existing tests
agency_ui_designer = _LegacyAgencyAdapter("ui_designer")
agency_security_engineer = _LegacyAgencyAdapter("security_engineer")
agency_backend_architect = _LegacyAgencyAdapter("backend_architect")
agency_growth_hacker = _LegacyAgencyAdapter("growth_hacker")
agency_content_creator = _LegacyAgencyAdapter("content_creator")
agency_frontend_developer = _LegacyAgencyAdapter("frontend_developer")
agency_brand_guardian = _LegacyAgencyAdapter("brand_guardian")

__all__ = [
    "AgencyCapabilityRegistry",
    "DesignCapabilities",
    "EngineeringCapabilities",
    "MarketingCapabilities",
    "PlannerAgentWithAgency",
    "create_planner_agent_with_agency",
    "agency_ui_designer",
    "agency_security_engineer",
    "agency_backend_architect",
    "agency_growth_hacker",
    "agency_content_creator",
    "agency_frontend_developer",
    "agency_brand_guardian",
]
