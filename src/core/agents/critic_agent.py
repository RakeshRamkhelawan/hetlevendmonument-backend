"""CriticAgent implementation for evaluating agent task executions.

The CriticAgent provides three modes of operation:
- ADVISORY: Async critique storage, no blocking
- BLOCKING: Validates output, retries if score < threshold
- SILENT: Logging only for telemetry

This agent follows the M-MDP pattern with heuristic-first evaluation
and optional LLM escalation for complex critiques.
"""

import asyncio
import json
import logging
import statistics
import time
import uuid
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.core.agents.critique_store import Critique, get_critique_store
from src.core.agents.mixins.learning_mixin import LearningMixin
from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.observability.metrics import (
    critique_latency_seconds,
    critique_panel_invocations_total,
    critique_score_histogram,
)
from src.core.shared.interfaces import ExecutionResult

logger = logging.getLogger(__name__)

_CRITIC_YAML_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "config" / "agents" / "critic_agent.yaml"
)
_TYPE_MAP: dict[str, type] = {"str": str, "dict": dict, "list": list, "int": int, "float": float}


def _load_critic_agent_yaml() -> dict[str, object]:
    """Load critic_agent.yaml; returns empty dict on any I/O or parse error."""
    try:
        with open(_CRITIC_YAML_PATH, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        logger.warning("critic_agent.yaml not found at %s", _CRITIC_YAML_PATH, exc_info=True)
        return {}
    except Exception as e:
        logger.error("Failed to load critic_agent.yaml: %s: %s", type(e).__name__, e, exc_info=True)
        return {}


_JUDGE_PANEL_LOWER = 0.35
_JUDGE_PANEL_UPPER = 0.75
_OUTLIER_THRESHOLD = 0.30


@dataclass
class SingleJudgeVerdict:
    judge_index: int
    score: float
    issues: list[str] = dc_field(default_factory=list)
    suggestions: list[str] = dc_field(default_factory=list)


@dataclass
class JudgePanelVerdict:
    consensus: float
    verdicts: list[SingleJudgeVerdict]
    outliers_removed: int = 0
    failed_judges: int = 0
    raw_scores: list[float] = dc_field(default_factory=list)


@dataclass
class SchemaValidationResult:
    passed: bool
    score: float
    issues: list[str]
    suggestions: list[str] = dc_field(default_factory=list)


class OutputSchemaValidator:
    """
    Tier-1 deterministic schema/format validation.

    Runs before HeuristicScorer. A hard failure (empty, wrong type, missing field,
    oversized) short-circuits LLM escalation and returns score 0.0.
    Config-driven: required_type, required_fields, max_chars.
    """

    def __init__(
        self,
        required_type: type | None = None,
        required_fields: list[str] | None = None,
        max_chars: int | None = None,
    ) -> None:
        self._required_type = required_type
        self._required_fields = required_fields or []
        self._max_chars = max_chars

    def validate(self, output: object) -> SchemaValidationResult:
        issues: list[str] = []
        suggestions: list[str] = []

        # Empty / None check
        if output is None or output == "" or output == {} or output == []:
            return SchemaValidationResult(
                passed=False,
                score=0.0,
                issues=["output is empty or None"],
                suggestions=["ensure agent produces non-empty output"],
            )

        # Type check
        if self._required_type is not None and not isinstance(output, self._required_type):
            return SchemaValidationResult(
                passed=False,
                score=0.0,
                issues=[
                    f"expected type {self._required_type.__name__}, got {type(output).__name__}"
                ],
                suggestions=[f"output must be {self._required_type.__name__}"],
            )

        # Required fields (dict outputs only)
        if self._required_fields and isinstance(output, dict):
            for f in self._required_fields:
                if f not in output:
                    issues.append(f"required field '{f}' missing from output")
                    suggestions.append(f"include '{f}' in agent output")

        # Max chars
        if self._max_chars is not None:
            s = str(output)
            if len(s) > self._max_chars:
                issues.append(f"output exceeds max_chars limit ({len(s)} > {self._max_chars})")
                suggestions.append(f"truncate output to {self._max_chars} characters")

        if issues:
            return SchemaValidationResult(
                passed=False, score=0.0, issues=issues, suggestions=suggestions
            )

        return SchemaValidationResult(passed=True, score=1.0, issues=[], suggestions=[])

    @classmethod
    def create_for_capability(cls, capability: str) -> "OutputSchemaValidator":
        """Build a validator from critic_agent.yaml capability_schemas[capability].

        Reads YAML on each call (no module-level cache).
        Returns an empty (no-constraint) validator for unknown capabilities.
        """
        data = _load_critic_agent_yaml()
        schemas: object = data.get("capability_schemas", {})
        if not isinstance(schemas, dict):
            return cls()
        cap_schema: object = schemas.get(capability)
        if not isinstance(cap_schema, dict):
            return cls()
        raw_type: object = cap_schema.get("required_type")
        required_type: type | None = _TYPE_MAP.get(str(raw_type)) if raw_type is not None else None
        raw_fields: object = cap_schema.get("required_fields")
        required_fields: list[str] = raw_fields if isinstance(raw_fields, list) else []
        raw_max: object = cap_schema.get("max_chars")
        max_chars: int | None = raw_max if isinstance(raw_max, int) else None
        return cls(
            required_type=required_type,
            required_fields=required_fields,
            max_chars=max_chars,
        )


class HeuristicScorer:
    """Heuristic-based scoring for common issues."""

    # Score penalties for different issue types
    PENALTIES = {
        "empty_output": 0.5,
        "error_in_output": 0.7,
        "missing_required_field": 0.3,
        "format_violation": 0.2,
        "incomplete_response": 0.25,
        "excessive_length": 0.1,
        "suspicious_content": 0.4,
    }

    @classmethod
    def score(cls, result: ExecutionResult) -> tuple[float, list[str], list[str]]:
        """
        Score an execution result using heuristics.

        Returns: tuple[float, list[str], list[str]] of (score, issues, suggestions)
        """
        score = 1.0
        issues: list[str] = []
        suggestions: list[str] = []
        output = getattr(result, "output", None)
        error = getattr(result, "error", None)

        # Check for errors
        if error:
            score -= cls.PENALTIES["error_in_output"]
            issues.append(f"Execution error: {error}")
            suggestions.append("Review error handling and input validation")

        # Check for empty output
        if not output:
            score -= cls.PENALTIES["empty_output"]
            issues.append("Empty output")
            suggestions.append("Ensure agent produces meaningful output")
        elif isinstance(output, str):
            # Check output length
            if len(output) == 0:
                score -= cls.PENALTIES["empty_output"]
                issues.append("Empty string output")
            elif len(output) < 10:
                score -= cls.PENALTIES["incomplete_response"]
                issues.append("Very short output (< 10 chars)")
                suggestions.append("Consider expanding response with more detail")
            elif len(output) > 10000:
                score -= cls.PENALTIES["excessive_length"]
                issues.append("Excessively long output (> 10k chars)")
                suggestions.append("Consider summarizing or structuring output")

        # Check for suspicious patterns
        if isinstance(output, str):
            suspicious = ["error", "exception", "failed", "timeout"]
            for pattern in suspicious:
                if pattern.lower() in output.lower():
                    # Only penalize if not already penalized for error
                    if not error:
                        score -= 0.05
                        issues.append(f"Suspicious pattern in output: '{pattern}'")
                    break

        # Ensure score is in valid range
        score = max(0.0, min(1.0, score))

        return score, issues, suggestions


class CriticAgent(LearningMixin):
    """
    Agent that critiques other agents' task executions.

    This is a singleton per tenant to ensure consistent critique behavior
    and resource usage.
    """

    _instances: dict[int, "CriticAgent"] = {}
    _initialized: bool = False
    _tenant_id: int

    def __new__(cls, tenant_id: int) -> "CriticAgent":
        if tenant_id not in cls._instances:
            cls._instances[tenant_id] = super().__new__(cls)
            cls._instances[tenant_id]._initialized = False
            cls._instances[tenant_id]._tenant_id = tenant_id
        return cls._instances[tenant_id]

    def __init__(self, tenant_id: int) -> None:
        if self._initialized:
            return

        self._initialized = True
        self._tenant_id = tenant_id
        self.__init_learning__(tenant_id=tenant_id)
        self._store = get_critique_store()
        self._heuristic_scorer = HeuristicScorer()
        self._default_schema_validator = OutputSchemaValidator()
        self._llm_client: TenantTaalmodel | None = None  # Lazy loaded
        self._judge_panel_size: int = self._load_judge_panel_size()

        logger.info("Initialized CriticAgent for tenant %s", tenant_id)

    @property
    def tenant_id(self) -> int:
        return self._tenant_id

    def _load_judge_panel_size(self) -> int:
        data = _load_critic_agent_yaml()
        size = data.get("judge_panel_size", 3)
        if not isinstance(size, int):
            logger.warning("judge_panel_size in critic_agent.yaml is not an int, using default 3")
            return 3
        return max(1, min(5, size))

    def _get_judge_panel_size(self) -> int:
        return self._judge_panel_size

    def _get_llm_client(self) -> TenantTaalmodel:
        """Lazy load LLM client for complex critiques."""
        if self._llm_client is None:
            # Het model van de TENANT van deze criticus, niet het platformmodel (brief 2026-10-20).
            self._llm_client = TenantTaalmodel(self._tenant_id)
        return self._llm_client

    async def critique_task(
        self,
        agent_name: str,
        task_id: str,
        result: ExecutionResult,
        mode: str = "advisory",
        use_llm: bool = False,
    ) -> Critique:
        """
        Critique a task execution result.

        Args:
            agent_name: Name of the agent being critiqued
            task_id: Unique task identifier
            result: The execution result to critique
            mode: CriticMode value (advisory, blocking, silent)
            use_llm: Whether to use LLM for complex critiques

        Returns:
            Critique object with score and feedback
        """
        critique_id = str(uuid.uuid4())
        _t0 = time.monotonic()
        panel_activated = False

        try:
            # Tier-1: schema validation -- short-circuits LLM escalation on hard failures
            schema_result = self._default_schema_validator.validate(getattr(result, "output", None))
            if not schema_result.passed:
                critique = Critique(
                    critique_id=critique_id,
                    agent_name=agent_name,
                    task_id=task_id,
                    tenant_id=self._tenant_id,
                    score=0.0,
                    issues=schema_result.issues,
                    suggestions=schema_result.suggestions,
                    mode=mode,
                    metadata={"schema_validation_failed": True, "tier": "schema"},
                )
                await self._store.store(critique)
                return critique

            # Phase 1: Heuristic scoring (always run)
            score, issues, suggestions = self._heuristic_scorer.score(result)
            heuristic_score = score  # capture before LLM blending

            # Phase 2: LLM escalation (optional)
            if use_llm and score < 0.8:
                llm_score, llm_issues, llm_suggestions = await self._llm_critique(
                    agent_name, result
                )
                # Weighted combination
                score = (score * 0.3) + (llm_score * 0.7)
                issues.extend(llm_issues)
                suggestions.extend(llm_suggestions)

            # Phase 3: Judge panel (ambiguous zone only)
            judge_panel_meta: (
                dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
            ) = None
            if use_llm and _JUDGE_PANEL_LOWER <= score <= _JUDGE_PANEL_UPPER:
                panel_activated = True
                panel_verdict = await self._judge_panel_critique(agent_name, result)
                if panel_verdict is not None:
                    score = panel_verdict.consensus
                    judge_panel_meta = {
                        "consensus": panel_verdict.consensus,
                        "outliers_removed": panel_verdict.outliers_removed,
                        "failed_judges": panel_verdict.failed_judges,
                        "raw_scores": panel_verdict.raw_scores,
                    }

            # Create critique
            metadata: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "heuristic_score": heuristic_score,
                "used_llm": use_llm,
            }
            if judge_panel_meta is not None:
                metadata["judge_panel"] = judge_panel_meta

            critique = Critique(
                critique_id=critique_id,
                agent_name=agent_name,
                task_id=task_id,
                tenant_id=self._tenant_id,
                score=score,
                issues=issues,
                suggestions=suggestions,
                mode=mode,
                metadata=metadata,
            )

            # Store critique
            await self._store.store(critique)

            _elapsed = time.monotonic() - _t0
            critique_score_histogram.labels(tenant_id=str(self._tenant_id), mode=mode).observe(
                score
            )
            critique_latency_seconds.labels(mode=mode).observe(_elapsed)
            if panel_activated:
                critique_panel_invocations_total.labels(tenant_id=str(self._tenant_id)).inc()
            # NOTE: exception and schema-failure paths intentionally omit observation (no valid score).
            await self._record_method_observation(
                method_name="critique_task",
                args_snapshot={"agent_name": agent_name, "task_id": task_id, "use_llm": use_llm},
                result_snapshot={"score": score, "schema_valid": schema_result.passed},
                duration_seconds=_elapsed,
            )

            logger.debug(
                "Critique %s for %s task %s: score=%.2f",
                critique_id,
                agent_name,
                task_id,
                score,
                extra={
                    "agent_name": agent_name,
                    "task_id": task_id,
                    "score": score,
                    "mode": mode,
                },
            )

            return critique

        except Exception as e:
            logger.error("critique_task failed: %s: %s", type(e).__name__, e, exc_info=True)
            # Return fallback critique
            fallback = Critique(
                critique_id=critique_id,
                agent_name=agent_name,
                task_id=task_id,
                tenant_id=self._tenant_id,
                score=0.5,
                issues=[f"Critique system error: {e}"],
                suggestions=["Please review manually"],
                mode=mode,
            )

            try:
                await self._store.store(fallback)
            except Exception as store_error:
                logger.error(
                    "store fallback critique failed: %s: %s",
                    type(store_error).__name__,
                    store_error,
                    exc_info=True,
                )

            return fallback

    async def _llm_critique(
        self,
        agent_name: str,
        result: ExecutionResult,
    ) -> tuple[float, list[str], list[str]]:
        """Use LLM for advanced critique when heuristics are insufficient."""
        try:
            llm = self._get_llm_client()

            output = getattr(result, "output", "")
            error = getattr(result, "error", None)

            # NOTE: agent_name and output are embedded verbatim in the prompt. output is capped at
            # 2000 chars to limit token overflow. Prompt injection via malicious output content is a
            # known trade-off: the json.loads() parser + score clamping + isinstance guards constrain
            # the damage to misleading issues/suggestions strings only. PromptGuard (ADR-015) is the
            # primary mitigation layer for this class of attack.
            prompt = (
                "You are a code review expert. Evaluate this agent output "
                "and respond with valid JSON only.\n\n"
                f"Agent: {agent_name}\n"
                f"Output: {output[:2000]}\n"
                f"Error: {error or 'None'}\n\n"
                "Respond with exactly this JSON object and nothing else:\n"
                '{"score": 0.0, "issues": ["issue1"], "suggestions": ["suggestion1"]}\n\n'
                "Replace the placeholder values with your actual assessment. "
                "Score must be 0.0 to 1.0. "
                "Criteria: Correctness 40%, Completeness 30%, Clarity 20%, Efficiency 10%."
            )

            response = await llm.generate_response(prompt)
            if not response.get("success"):
                raise RuntimeError(str(response.get("error", "LLM critique generation failed")))

            response_text = str(response.get("content", ""))

            try:
                parsed = json.loads(response_text)
                score = max(0.0, min(1.0, float(parsed.get("score", 0.5))))
                raw_issues = parsed.get("issues", [])
                raw_suggestions = parsed.get("suggestions", [])
                issues: list[str] = (
                    [str(i) for i in raw_issues] if isinstance(raw_issues, list) else []
                )
                suggestions: list[str] = (
                    [str(s) for s in raw_suggestions] if isinstance(raw_suggestions, list) else []
                )
            except (json.JSONDecodeError, ValueError, TypeError) as parse_err:
                logger.warning(
                    "_llm_critique JSON parse failed: %s: %s",
                    type(parse_err).__name__,
                    parse_err,
                    exc_info=True,
                )
                return (
                    0.5,
                    ["LLM critique parse error -- please review manually"],
                    ["Please review manually"],
                )

            return score, issues, suggestions

        except Exception as e:
            logger.error("LLM critique failed: %s: %s", type(e).__name__, e, exc_info=True)
            return 0.5, ["LLM critique error -- please review manually"], ["Please review manually"]

    async def _judge_panel_critique(
        self,
        agent_name: str,
        result: ExecutionResult,
        timeout_per_judge: float = 15.0,
    ) -> JudgePanelVerdict | None:
        """
        Multi-model judge panel for ambiguous scores.

        N is read from critic_agent.yaml via _get_judge_panel_size() (clamp 1-5).
        Outlier-filtering: leave-one-out with _OUTLIER_THRESHOLD=0.30 when N >= 3.
        Returns None when all judges fail (caller keeps existing score).
        """
        n_judges = self._get_judge_panel_size()
        output = getattr(result, "output", "")
        # NOTE: output capped at 2000 chars to limit token overflow.
        prompt = (
            "You are an expert quality evaluator. Evaluate this agent output "
            "and respond with valid JSON only.\n\n"
            f"Agent: {agent_name}\n"
            f"Output: {str(output)[:2000]}\n\n"
            "Respond with exactly this JSON object and nothing else:\n"
            '{"score": 0.0, "issues": ["issue1"], "suggestions": ["suggestion1"]}\n\n'
            "Score must be 0.0 to 1.0. "
            "Criteria: Correctness 40%, Completeness 30%, Clarity 20%, Efficiency 10%."
        )
        raw = await self._run_judge_panel(prompt, n_judges, timeout_per_judge)
        failed_count = sum(1 for _, s in raw if s is None)
        return self._build_judge_panel_verdict(raw, failed_count)

    async def _run_judge_panel(
        self,
        prompt: str,
        n_judges: int,
        timeout_per_judge: float,
    ) -> list[tuple[int, float | None]]:
        """Run N LLM judges concurrently on the tenant's model; returns (index, score_or_None)."""
        # Alle rechters gebruiken het model van de TENANT. Er stond een lijst `judge_provider_types` (deepseek,
        # gemini, openai) voor leverancierdiversiteit; die stuurde de uitvoer van een klant naar leveranciers die
        # de klant niet koos (ADR-041 B14, brief 2026-10-20).
        llm = self._get_llm_client()

        async def run_one(index: int) -> tuple[int, float | None]:
            try:
                response = await asyncio.wait_for(
                    llm.generate_response(prompt),
                    timeout=timeout_per_judge,
                )
                if not response.get("success"):
                    return index, None
                parsed = json.loads(str(response.get("content", "")))
                score = max(0.0, min(1.0, float(parsed.get("score", 0.5))))
                return index, score
            except asyncio.TimeoutError:
                logger.warning("_run_judge_panel judge %d timed out", index)
                return index, None
            except Exception as e:
                logger.error(
                    "_run_judge_panel judge %d failed: %s: %s",
                    index,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                return index, None

        tasks = [run_one(i) for i in range(n_judges)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out: list[tuple[int, float | None]] = []
        for r in results:
            if isinstance(r, BaseException):
                out.append((-1, None))
            else:
                out.append(r)
        return out

    def _build_judge_panel_verdict(
        self,
        raw: list[tuple[int, float | None]],
        failed_count: int,
    ) -> JudgePanelVerdict | None:
        """
        Build consensus from raw judge results.

        Outlier-filtering via leave-one-out (N >= 3): remove the score that deviates
        most from the mean of the remaining judges when deviation > _OUTLIER_THRESHOLD.
        2-sigma is unsuitable for N=3 (max z-score ~1.15 < 2 by construction).
        Returns None when no successful judges.
        """
        successful = [(idx, s) for idx, s in raw if s is not None]
        if not successful:
            return None

        scores = [s for _, s in successful]
        outliers_removed = 0

        if len(scores) >= 3:
            max_dev = 0.0
            outlier_pos = -1
            for i, s in enumerate(scores):
                others = [x for j, x in enumerate(scores) if j != i]
                dev = abs(s - statistics.mean(others))
                if dev > max_dev:
                    max_dev = dev
                    outlier_pos = i
            if max_dev > _OUTLIER_THRESHOLD and outlier_pos >= 0:
                scores = [s for i, s in enumerate(scores) if i != outlier_pos]
                outliers_removed = 1

        consensus = statistics.mean(scores)

        verdicts = [SingleJudgeVerdict(judge_index=idx, score=s) for idx, s in successful]

        return JudgePanelVerdict(
            consensus=round(consensus, 4),
            verdicts=verdicts,
            outliers_removed=outliers_removed,
            failed_judges=failed_count,
            raw_scores=[s for _, s in successful],
        )

    async def get_agent_report(
        self,
        agent_name: str,
        window_hours: int = 24,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate a critique report for an agent.

        Args:
            agent_name: Name of the agent
            window_hours: Time window for report

        Returns:
            Report dictionary with statistics
        """
        avg_score = await self._store.get_average_score(self._tenant_id, agent_name, window_hours)

        distribution = await self._store.get_score_distribution(self._tenant_id, agent_name)

        common_issues_raw = await self._store.get_common_issues(
            self._tenant_id, agent_name, limit=5
        )
        common_issues = [{"issue": issue, "count": count} for issue, count in common_issues_raw]

        return {
            "agent_name": agent_name,
            "window_hours": window_hours,
            "average_score": avg_score,
            "score_distribution": distribution,
            "common_issues": common_issues,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_common_issues(
        self, agent_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get most common issues for an agent, serialized for API consumption."""
        raw = await self._store.get_common_issues(self._tenant_id, agent_name, limit=limit)
        return [{"issue": issue, "count": count} for issue, count in raw]

    async def get_system_health(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get overall system health based on critique data."""
        stats = await self._store.get_stats(self._tenant_id)

        # Calculate overall health score
        if stats["total_critiques"] == 0:
            health_score = 1.0
        else:
            # Average score across all agents
            total_score = 0.0
            count = 0

            for agent_name in stats["critiques_per_agent"]:
                avg = await self._store.get_average_score(
                    self._tenant_id, agent_name, window_hours=24
                )
                if avg > 0:
                    total_score += avg
                    count += 1

            health_score = total_score / count if count > 0 else 1.0

        return {
            "health_score": health_score,
            "status": (
                "healthy"
                if health_score > 0.7
                else "degraded" if health_score > 0.4 else "critical"
            ),
            "critique_stats": stats,
            "tenant_id": self._tenant_id,
        }

    def get_capabilities(self) -> list[str]:
        return [
            "output_quality_scoring",
            "accuracy_assessment",
            "completeness_checking",
            "safety_scanning",
            "heuristic_red_flag_detection",
            "llm_deep_critique",
            "critique_persistence",
            "feedback_loop_integration",
            "schema_validation",
        ]
