"""
Execution Feedback Agent - Learning from Workflow Executions
=============================================================

Monitors workflow executions and learns from failures/slowdowns.

Capabilities:
- Analyze execution metrics (success rate, timing, errors)
- Detect failure patterns
- Generate improvement suggestions based on real data
- Track performance trends
- Recommend fixes for common failures

Uses LLM to understand failure context and suggest targeted improvements.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, cast

from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.llm_client import LLMMessage

logger = logging.getLogger(__name__)


class ExecutionFeedbackAgent:
    """
    Analyzes workflow executions and generates improvement suggestions.

    Learns from failures to make workflows more resilient.
    """

    def __init__(self, tenant_id: int) -> None:
        """
        Initialize execution feedback agent.

        Het taalmodel is de keuze van de TENANT (ADR-041 B14); er is geen `llm_provider` meer. Hier stond
        `deepseek` als standaard en bij een fout stil een namaakmodel. Een uitvoeringscontext bevat
        klantgegevens (workflow, foutmeldingen), dus het gaat via de deur (`TenantTaalmodel`).

        Args:
            tenant_id: Tenant ID for multi-tenant isolation
        """
        self.tenant_id = tenant_id
        self.llm_client = TenantTaalmodel(tenant_id)
        logger.info("[SEARCH] ExecutionFeedbackAgent initialized", extra={"tenant_id": tenant_id})

    async def analyze_execution(
        self,
        execution_id: str,
        workflow_id: str,
        status: str,
        duration: float,
        error_message: str | None = None,
        node_results: list[dict[str, Any]] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Analyze a workflow execution and generate improvement suggestions.

        Args:
            execution_id: Unique execution ID
            workflow_id: Workflow being executed
            status: SUCCEEDED, FAILED, TIMEOUT, etc.
            duration: Execution time in seconds
            error_message: Error message if failed
            node_results: Results from each node execution

        Returns: Dict[str, Any] with analysis and suggestions  # TODO(TYPE): replace Any with concrete type
        """

        logger.info(
            f"[CHART] Analyzing execution: {execution_id} ({status})",
            extra={
                "tenant_id": self.tenant_id,
                "duration": duration,
                "error": error_message[:50] if error_message else None,
            },
        )

        try:
            # Build context from execution data
            context = self._build_execution_context(status, duration, error_message, node_results)

            # Analyze with LLM
            suggestions = await self._analyze_with_llm(context, status, error_message)

            # Validate suggestions
            validated = self._validate_suggestions(suggestions)

            # Generate summary
            summary = self._generate_summary(status, duration, validated)

            logger.info(
                f"[OK] Analysis complete: {len(validated)} suggestions",
                extra={"tenant_id": self.tenant_id},
            )

            return {
                "execution_id": execution_id,
                "analysis": summary,
                "suggestions": validated,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"[FAIL] Analysis failed: {str(e)}", exc_info=True)
            raise

    async def _analyze_with_llm(
        self,
        context: str,
        status: str,
        error_message: str | None,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Use LLM to generate improvement suggestions from execution data.
        """

        system_prompt = """You are a workflow optimization expert. Analyze the execution context and suggest specific improvements.

For each suggestion, provide:
1. type: one of [add_node, update_node, optimize, timeout, retry, cache]
2. title: short summary
3. description: detailed fix
4. reasoning: why this prevents the failure
5. impact: low/medium/high
6. action_data: implementation details

Return ONLY valid JSON array."""

        user_prompt = f"""
Execution Context:
{context}

Status: {status}
{"Error: " + error_message if error_message else ""}

Based on this execution failure, what 2-3 specific improvements would prevent this?
Return valid JSON array only, no other text."""

        try:
            response = await self.llm_client.async_prompt(
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                temperature=0.5,
                max_tokens=1500,
            )

            content = response.content.strip()

            # Extract JSON
            json_match = None
            if content.startswith("["):
                json_match = content
            else:
                start_idx = content.find("[")
                end_idx = content.rfind("]") + 1
                if start_idx >= 0 and end_idx > start_idx:
                    json_match = content[start_idx:end_idx]

            if json_match:
                suggestions = cast(list[dict[str, Any]], json.loads(json_match))  # TODO(TYPE): replace Any with concrete type
                logger.info(f"[OK] LLM generated {len(suggestions)} suggestions")
                return suggestions
            else:
                logger.warning("No JSON in response, using fallback")
                return self._fallback_suggestions(status, error_message)

        except Exception as e:
            logger.error(f"LLM analysis failed: {str(e)}")
            return self._fallback_suggestions(status, error_message)

    def _fallback_suggestions(
        self,
        status: str,
        error_message: str | None,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate rule-based suggestions if LLM fails.
        """

        suggestions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if status == "FAILED":
            if error_message:
                if "timeout" in (error_message or "").lower():
                    suggestions.append(
                        {
                            "type": "timeout",
                            "title": "Add timeout protection",
                            "description": "This node is timing out. Add retry logic and longer timeout.",
                            "reasoning": "Timeouts cause cascading failures",
                            "impact": "high",
                            "action_data": {"timeout_seconds": 60, "retry_count": 3},
                        }
                    )
                elif "connection" in (error_message or "").lower():
                    suggestions.append(
                        {
                            "type": "retry",
                            "title": "Add connection retry logic",
                            "description": "Network errors detected. Add retry with exponential backoff.",
                            "reasoning": "Transient failures need retry logic",
                            "impact": "medium",
                            "action_data": {"retry_count": 3, "backoff_factor": 2},
                        }
                    )
                else:
                    suggestions.append(
                        {
                            "type": "add_node",
                            "title": "Add error handler",
                            "description": "Execution failed. Add dedicated error handling node.",
                            "reasoning": "Graceful error handling prevents workflow death",
                            "impact": "high",
                            "action_data": {"node_name": "Error Handler"},
                        }
                    )

        elif status == "TIMEOUT":
            suggestions.append(
                {
                    "type": "optimize",
                    "title": "Optimize slow operations",
                    "description": "Workflow is too slow. Add caching or parallelize steps.",
                    "reasoning": "Performance issues lead to timeouts",
                    "impact": "high",
                    "action_data": {"optimize_type": "cache"},
                }
            )

        if not suggestions:
            suggestions.append(
                {
                    "type": "add_node",
                    "title": "Add validation",
                    "description": "Add input validation to catch issues early.",
                    "reasoning": "Early validation prevents downstream failures",
                    "impact": "medium",
                    "action_data": {"node_name": "Input Validator"},
                }
            )

        return suggestions

    def _build_execution_context(
        self,
        status: str,
        duration: float,
        error_message: str | None,
        node_results: list[dict[str, Any]] | None,  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Build human-readable context from execution data."""

        context = f"""
Execution Results:
- Status: {status}
- Duration: {duration:.2f}s
- Completed: {datetime.now(timezone.utc).isoformat()}
"""

        if error_message:
            context += f"- Error: {error_message}\n"

        if node_results:
            context += "\nNode Performance:\n"
            for node in node_results:
                status_str = node.get("status", "UNKNOWN")
                duration_str = (
                    f"{node.get('duration', 0):.2f}s" if node.get("duration") else "unknown"
                )
                context += f"  - {node.get('node_id', '?')}: {status_str} ({duration_str})\n"

                if node.get("error"):
                    context += f"    Error: {node.get('error')}\n"

        return context

    def _validate_suggestions(
        self,
        suggestions: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Validate and filter suggestions."""

        validated: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        valid_types = [
            "add_node",
            "update_node",
            "optimize",
            "timeout",
            "retry",
            "cache",
        ]

        for s in suggestions:
            if not isinstance(s, dict):
                continue

            if s.get("type") not in valid_types:
                continue

            if not s.get("title") or not s.get("description"):
                continue

            # Ensure defaults
            if not s.get("action_data"):
                s["action_data"] = {}
            if not s.get("reasoning"):
                s["reasoning"] = ""
            if not s.get("impact"):
                s["impact"] = "medium"

            validated.append(s)

        return validated

    def _generate_summary(
        self,
        status: str,
        duration: float,
        suggestions: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Generate analysis summary."""

        status_emoji = {
            "SUCCEEDED": "[OK]",
            "FAILED": "[FAIL]",
            "TIMEOUT": "[TIMER]",
        }.get(status, "[WARN]")

        summary = f"""
## Execution Analysis

{status_emoji} **Status:** {status}
[TIMER] **Duration:** {duration:.2f}s
[IDEA] **Suggestions:** {len(suggestions)} improvements recommended

**Recommended Actions:**
"""

        for i, s in enumerate(suggestions, 1):
            summary += f"\n{i}. **{s.get('title', 'Improvement')}**\n   {s.get('description', '')}"

        return summary
