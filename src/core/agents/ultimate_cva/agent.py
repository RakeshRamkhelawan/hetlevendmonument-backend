"""
Ultimate CVA Agent - Production-Ready Dynamic Integration.

Combines: Ultimate Enhanced NLP + Perfect CVA CEO capabilities + Dynamic LLM Integration.
This module serves as the clean orchestration layer, delegating to specialized modules.

Week 2 Day 7 Implementation with real-time Google Gemini integration.
"""

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional

from src.config import get_api_base_url
from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.interfaces import BaseAgent, ExecutionResult, TaskData
from src.core.types import AgentType, TriggerType

from . import context as context_lib
from . import performance as performance_lib
from .intent_handlers import IntentHandlers
from .mode_manager import ModeManager
from .models import AgentCapabilities, CVAMode, IntentType, ParsedCommand, UltimateExecutionResult
from .nlp import NLPHandler
from .orchestrator_client import OrchestratorClient
from .tools import ToolExecutor

logger = logging.getLogger("UltimateCVA")


class UltimateCVAAgent(BaseAgent):
    """
    Ultimate CVA Agent - Next-Generation CEO of AI System with Tenant Isolation.

    Features:
    - CEO-level decision making with ultimate intelligence
    - Dynamic LLM integration with real-time Google Gemini
    - Enhanced NLP with intent classification and parameter extraction
    - Modular architecture with specialized handlers
    - [RED] CRITICAL: Strict tenant isolation for security
    """

    def __init__(
        self,
        tenant_id: int,  # [RED] CRITICAL: Required for tenant isolation
        agent_id: str = "ultimate_cva",
        api_url: str | None = None,
    ) -> None:
        super().__init__(agent_id=agent_id, agent_type=AgentType.CVA)

        # [RED] CRITICAL: Validate tenant_id
        if tenant_id is None or tenant_id <= 0:
            raise ValueError(
                f"UltimateCVAAgent requires a valid tenant_id. "
                f"Use get_tenant_id() from middleware or provide explicitly. "
                f"Received: {tenant_id}"
            )

        self.tenant_id = tenant_id
        self.current_tenant_id = str(tenant_id)  # For backward compatibility
        self.api_url = api_url if api_url else get_api_base_url()
        self.capabilities = AgentCapabilities()

        # Initialize core services
        # Het taalmodel van de TENANT van deze agent, niet het platformmodel (brief 2026-10-20, ADR-041 B14).
        self.llm_service = TenantTaalmodel(tenant_id)
        self.nlp_handler = NLPHandler(self.llm_service)
        self.orchestrator = OrchestratorClient(self.api_url)
        self.mode_manager = ModeManager(dashboard_fetcher=self.orchestrator.get_dashboard_data)
        self.tool_executor = ToolExecutor(self)  # Pass self as agent reference
        self.intent_handlers = IntentHandlers(
            self.llm_service, self.tool_executor, self.orchestrator
        )

        # State tracking
        self.execution_history: list[UltimateExecutionResult] = []
        self.context_memory: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.performance_cache: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.last_optimization = datetime.now(timezone.utc)
        self.learning_enabled = True

        # Security: Log initialization with tenant context
        logger.info(
            "Ultimate CVA Agent initialized with modular architecture",
            extra={
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "event": "cva_init",
                "security_context": "tenant_isolated",
            },
        )

    async def initialize(self) -> bool:
        """Initialize Ultimate CVA systems."""
        try:
            await self.llm_service.initialize()
            llm_status = await self.llm_service.get_service_status()
            logger.info(f"LLM Service Status: {llm_status}")

            await self.orchestrator.check_health()
            self.performance_cache = performance_lib.load_performance_cache()

            logger.info("Ultimate CVA Agent CEO initialization complete!")
            return True
        except Exception as e:
            logger.error(f"Ultimate CVA initialization failed: {e}")
            return False

    def _detect_language(self, text: str) -> str:
        """
        Simple language detection heuristic.
        """
        dutch_words = {
            "de",
            "het",
            "een",
            "en",
            "van",
            "ik",
            "je",
            "dat",
            "die",
            "in",
            "is",
        }
        words = set(text.lower().split())
        common = words.intersection(dutch_words)
        return "nl" if len(common) > 0 else "en"

    async def process_task(self, task: TaskData) -> ExecutionResult:
        """Process task - BaseAgent abstract method implementation."""
        result = await self.process_command(task.description, task.metadata)
        return ExecutionResult(
            task_id=task.id,
            success=result.success,
            result_data=result.response,
        )

    async def process_command(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        trigger_type: TriggerType | None = None,
    ) -> UltimateExecutionResult:
        """Process user command with ultimate intelligence and platform awareness."""
        start_time = datetime.now(timezone.utc)
        execution_context = context or {}

        try:
            _cmd_len = len(user_input)
            logger.info("Processing command: len=%d", _cmd_len)

            # SECURITY: set[Any] current tenant ID for ToolExecutor enforcement  # TODO(TYPE): replace with concrete type
            if execution_context.get("tenant"):
                self.current_tenant_id = execution_context["tenant"].get(
                    "tenant_id", "unknown_tenant"
                )

            # Step 1: Parse command with NLP
            nlp_start = datetime.now(timezone.utc)
            parsed = await self.nlp_handler.parse_command_with_llm(user_input)
            nlp_duration = (datetime.now(timezone.utc) - nlp_start).total_seconds()
            logger.info(
                f"NLP parsing took {nlp_duration:.2f}s. Intent: {parsed.intent.value} ({parsed.confidence:.1%})"
            )

            # Step 2: Determine and switch to optimal mode
            optimal_mode = self.mode_manager.determine_optimal_mode(parsed, trigger_type)
            await self.mode_manager.switch_mode(
                optimal_mode,
                f"Intent: {parsed.intent.value}",
                token=execution_context.get("auth_token"),
            )

            # Step 3: Handle clarification if needed
            if parsed.suggested_clarification:
                return self._create_clarification_result(parsed)

            # Step 4: Enhance context
            enhanced_ctx = context_lib.enhance_context(
                execution_context, parsed, self.execution_history
            )

            # Step 5: Execute command based on intent
            exec_start = datetime.now(timezone.utc)
            model_id = execution_context.get("model")
            result = await self._execute_by_intent(parsed, enhanced_ctx, model=model_id)
            exec_duration = (datetime.now(timezone.utc) - exec_start).total_seconds()
            logger.info(f"Execution took {exec_duration:.2f}s")

            # Step 6: Post-processing
            result_dict = asdict(result)

            exec_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.performance_cache = performance_lib.analyze_performance(
                self.performance_cache, result_dict, exec_time, parsed
            )

            if self.learning_enabled:
                self.context_memory = context_lib.update_context_memory(
                    self.context_memory, parsed, result_dict, execution_context
                )

            suggestions = context_lib.generate_intelligent_suggestions(
                parsed, result_dict, self.execution_history
            )

            # Extract prompt evaluation from result data or attribute
            final_data = result.data.copy() if (hasattr(result, "data") and result.data) else {}

            # Check if prompt_evaluation is already in data, otherwise try to get from attribute
            if "prompt_evaluation" not in final_data:
                final_data["prompt_evaluation"] = getattr(result, "prompt_evaluation", None)

            final_result = UltimateExecutionResult(
                success=result.success,
                response=result.response,
                confidence=parsed.confidence,
                execution_time=exec_time,
                suggestions=suggestions,
                performance_metrics=self._get_performance_metrics(),
                llm_provider_used=model_id or "gemini",
                data=final_data,
            )

            self._store_result(final_result)
            logger.info(f"Command executed successfully in {exec_time:.2f}s")
            return final_result

        except Exception as e:
            exec_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.error(f"Command execution failed: {e}")
            return UltimateExecutionResult(
                success=False,
                response={"error": str(e)},
                confidence=0.0,
                execution_time=exec_time,
                suggestions=[f"Error: {e}", "Try a simpler command"],
                performance_metrics=self._get_performance_metrics(),
            )

    async def _execute_by_intent(
        self,
        parsed: ParsedCommand,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        model: str | None = None,
    ) -> UltimateExecutionResult:
        """Route command execution based on intent type."""
        intent = parsed.intent

        # Most intents now route through the Master Planner (Copilot)
        if intent in [
            IntentType.DIRECT_QUESTION,
            IntentType.UNKNOWN,
            IntentType.STRATEGIC_PLANNING,
            IntentType.CEO_DIRECTIVE,
            IntentType.TASK_MANAGEMENT,
            IntentType.NAVIGATION,
            IntentType.CREATION,
            IntentType.KNOWLEDGE_QUERY,
            IntentType.SYSTEM_STATUS,
        ]:
            return await self.intent_handlers.execute_via_master_planner(
                parsed,
                context,
                self.cva_mode.value,
                self.current_tenant_id,
                model=model,
            )

        if intent == IntentType.AGENT_MANAGEMENT:
            # Logic moved to intent_handlers
            try:
                data = await self.intent_handlers.handle_agent_management(context)
                return UltimateExecutionResult(
                    success=True, response="Agent data retrieved", data=data
                )
            except Exception as e:
                logger.error(f"Agent management failed: {e}")
                return UltimateExecutionResult(success=False, response=f"Error: {str(e)}")

        # Fallback
        return UltimateExecutionResult(
            success=False,
            response=f"Unsupported intent: {intent.value}",
            confidence=0.0,
        )

    def _create_clarification_result(self, parsed: ParsedCommand) -> UltimateExecutionResult:
        """Create result for clarification requests."""
        return self.intent_handlers.create_clarification_result(
            parsed, self._get_performance_metrics()
        )

    def _get_performance_metrics(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current performance metrics."""
        return performance_lib.get_performance_metrics(
            self.execution_history,
            self.context_memory,
            self.performance_cache,
            self.last_optimization,
            self.mode_manager.current_mode,
        )

    def _store_result(self, result: UltimateExecutionResult) -> None:
        """Store execution result and cleanup old history."""
        self.execution_history.append(result)
        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-50:]

    @property
    def cva_mode(self) -> CVAMode:
        """Get current CVA mode."""
        return self.mode_manager.current_mode


async def create_ultimate_cva_agent(
    tenant_id: int = 1, api_url: str | None = None
) -> UltimateCVAAgent:
    """Create and initialize Ultimate CVA Agent."""
    agent = UltimateCVAAgent(tenant_id=tenant_id, api_url=api_url)
    if await agent.initialize():
        logger.info("Ultimate CVA Agent created and initialized successfully")
        return agent
    raise Exception("Failed to initialize Ultimate CVA Agent")
