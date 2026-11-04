import logging
from datetime import datetime, timezone
from typing import Any

import yaml
from pydantic import BaseModel

# --- DATA MODELS ---


class SOPStep(BaseModel):
    tool: str
    params: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    description: str | None = None
    timeout: int = 30  # seconds


class SOP(BaseModel):
    id: str
    description: str
    version: str = "1.0"
    steps: list[SOPStep]
    variables: list[str] = []  # Expected input variables


class SOPExecutionResult(BaseModel):
    sop_id: str
    status: str  # "SUCCESS", "FAILED"
    start_time: datetime
    end_time: datetime | None = None
    step_results: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
    error: str | None = None


# --- EXECUTOR ---


class SOPExecutor:
    """
    Executes Standard Operating Procedures (YAML Playbooks).
    This removes ambiguity from Agent actions.
    """

    def __init__(self, tool_broker: Any = None) -> None:
        self.tool_broker = tool_broker
        self.logger = logging.getLogger("sop_executor")
        self._sops: dict[str, SOP] = {}

    def load_sop(self, yaml_content: str) -> SOP:
        """Parse YAML string into an SOP object."""
        try:
            data = yaml.safe_load(yaml_content)
            sop = SOP(**data)
            self._sops[sop.id] = sop
            return sop
        except Exception as e:
            self.logger.error(f"Failed to load SOP: {e}")
            raise ValueError(f"Invalid SOP YAML: {e}")

    def load_sop_from_file(self, file_path: str) -> SOP:
        """Load SOP from a file."""
        with open(file_path, encoding="utf-8") as f:
            return self.load_sop(f.read())

    async def execute_sop(
        self, sop_id: str, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> SOPExecutionResult:  # TODO(TYPE): replace Any with concrete type
        """
        Executes a loaded SOP step-by-step.
        Replaces {placeholders} in params with context values.
        """
        if sop_id not in self._sops:
            raise ValueError(f"SOP {sop_id} not found. Load it first.")

        sop = self._sops[sop_id]
        result = SOPExecutionResult(
            sop_id=sop_id, status="RUNNING", start_time=datetime.now(timezone.utc)
        )

        try:
            for i, step in enumerate(sop.steps):
                # 1. Prepare Parameters (Variable Substitution)
                # We do a deep traversal to replace strings like "{username}"
                final_params = self._resolve_params(step.params, context)

                step_log = {
                    "step_index": i,
                    "tool": step.tool,
                    "params": final_params,
                    "status": "pending",
                }

                # 2. Execute Tool
                try:
                    output = await self._execute_tool(step.tool, final_params)
                    step_log["status"] = "success"
                    step_log["output"] = output

                    # Update context for future steps (e.g. store previous output)
                    # We store it as step_N_output
                    context[f"step_{i}_output"] = output

                except Exception as e:
                    step_log["status"] = "failed"
                    step_log["error"] = str(e)
                    result.step_results.append(step_log)
                    raise e  # Stop execution on failure

                result.step_results.append(step_log)

            result.status = "SUCCESS"

        except Exception as e:
            result.status = "FAILED"
            result.error = str(e)

        result.end_time = datetime.now(timezone.utc)
        return result

    async def _execute_tool(
        self, tool_name: str, params: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """
        Proxies the call to the actual ToolBroker.
        """
        if self.tool_broker:
            # Assume tool_broker has an async execute method
            # If tool_broker is not async, wrap it or adjust here.
            # This is a generic integration point.
            if hasattr(self.tool_broker, "execute_tool"):
                return await self.tool_broker.execute_tool(tool_name, params)
            else:
                return f"ToolBroker mock output for {tool_name}"
        else:
            # Fallback for testing without broker
            return f"Mock output for {tool_name} with {params}"

    def _resolve_params(
        self, params: Any, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """
        Recursively replaces {placeholders} in a dictionary or list or string.
        """
        if isinstance(params, dict):
            return {k: self._resolve_params(v, context) for k, v in params.items()}
        elif isinstance(params, list):
            return [self._resolve_params(item, context) for item in params]
        elif isinstance(params, str):
            try:
                # 1. Simple Full Substitution: "{var}" -> object
                if params.startswith("{") and params.endswith("}") and params.count("{") == 1:
                    key = params[1:-1]
                    val = self._get_value_from_context(key, context)
                    if val is not None:
                        return val

                # 2. String Interpolation: "Hello {var}" -> "Hello World"
                # We need a custom formatter or pre-process keys to handle dots
                # Quick hack: Iterate over all placeholders found
                import re

                placeholders = re.findall(r"\{([a-zA-Z0-9_.]+)\}", params)

                result = params
                for ph in placeholders:
                    val = self._get_value_from_context(ph, context)
                    if val is not None:
                        result = result.replace(f"{{{ph}}}", str(val))
                return result

            except Exception as e:
                # If variable missing, keep original string to avoid crash
                return params
        else:
            return params

    def _get_value_from_context(
        self, path: str, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Helper to get nested values like 'user.name' from context dict"""
        try:
            parts = path.split(".")
            curr = context
            for part in parts:
                if isinstance(curr, dict):
                    curr = curr[part]
                else:
                    # Try attribute access if it's an object
                    curr = getattr(curr, part)
            return curr
        except (KeyError, AttributeError, TypeError):
            return None
