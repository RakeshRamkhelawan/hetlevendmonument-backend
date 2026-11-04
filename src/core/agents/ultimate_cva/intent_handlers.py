"""
Intent Handlers - Handle specific command intents with LLM.

Provides dedicated handlers for different intent types that require
direct LLM responses without orchestrator involvement.

Usage:
    handlers = IntentHandlers(llm_service, tool_executor, orchestrator)
    result = await handlers.handle_knowledge_query(parsed_command, context)
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional, cast

from loguru import logger

from .models import ParsedCommand, UltimateExecutionResult
from .orchestrator_client import OrchestratorClient
from .system_prompt import get_system_prompt
from .tools import TOOL_DEFINITIONS, ToolExecutor


class IntentHandlers:
    """Handles specific intents with LLM-enhanced responses."""

    def __init__(
        self,
        llm_service: Any,  # TODO(TYPE): replace Any with concrete type
        tool_executor: ToolExecutor,
        orchestrator_client: OrchestratorClient,
    ) -> None:
        """
        Initialize intent handlers.

        Args:
            llm_service: LLM service instance
            tool_executor: Tool execute instance
            orchestrator_client: Orchestrator client instance
        """
        self.llm_service = llm_service
        self.tool_executor = tool_executor
        self.orchestrator = orchestrator_client

    async def execute_via_master_planner(
        self,
        parsed: ParsedCommand,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        cva_mode_value: str,
        current_tenant_id: str,
        model: str | None = None,
    ) -> UltimateExecutionResult:
        """
        Execute using the Plan-Execute-Observe-Adjust loop.
        This uses the Master System Prompt and ToolExecutor.
        """
        # 1. Build Dynamic Context
        current_route = context.get("route", "/")
        user_language = self._detect_language(parsed.original_text)

        tenant_ctx = context.get("tenant") or {}
        tenant_id = current_tenant_id
        platform_name = tenant_ctx.get("platform_name", "SaaS Platform")
        tenant_domain = tenant_ctx.get("domain", "generic SME")

        # 2. Generate Master Prompt
        system_prompt_text = get_system_prompt(
            platform_name=platform_name,
            tenant_id=tenant_id,
            tenant_domain=tenant_domain,
            user_language=user_language,
            current_route=current_route,
            page_context=context.get("page_context", ""),
            tool_definitions=TOOL_DEFINITIONS,
            cva_mode=cva_mode_value,
            model_id=model or "unknown",
        )

        # 3. Prepare Messages
        messages = [{"role": "system", "content": system_prompt_text}]

        # Add limited history context
        if context.get("history"):
            for msg in context["history"][-5:]:  # Last 5 messages for context
                # Ensure structure matches LLM expectations
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content:
                    messages.append({"role": role, "content": str(content)})

        # Add current user input
        messages.append({"role": "user", "content": parsed.original_text})

        # 4. Run the Plan-Execute-Observe-Adjust Loop
        execution_dict = await self._plan_execute_observe_adjust(
            messages, tenant_id, auth_token=context.get("auth_token"), model=model
        )

        # 5. Map to UltimateExecutionResult
        return UltimateExecutionResult(
            success=execution_dict.get("success", False),
            response=execution_dict.get("message", "Processed request."),
            data=execution_dict.get("data", {}),
            confidence=execution_dict.get("confidence", 0.8),
            execution_time=0.0,  # set by caller
        )

    async def _plan_execute_observe_adjust(
        self,
        messages: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        tenant_id: str,
        auth_token: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Full Plan-and-Execute + Observe-Adjust loop.
        Returns a dict suitable for UltimateExecutionResult.
        """

        # Step 1: PLAN (First LLM Call)
        plan_result = await self._call_llm_with_tools_json(messages, model=model)
        if not plan_result.get("success"):
            error_msg = plan_result.get("error", "Unknown planner error")
            return {
                "success": False,
                "message": f"I'm having trouble planning: {error_msg}",
                "data": plan_result,
            }

        payload = plan_result.get("payload", {})
        action = payload.get("action")
        action_params = payload.get("action_params") or {}
        thought_process = payload.get("thought_process", "")
        plan = payload.get("plan", [])
        # Robust message extraction
        message = payload.get("message") or payload.get("response") or payload.get("content") or ""
        confidence = payload.get("confidence", 0.8)

        # No tool action required -> Return direct response
        if not action:
            return {
                "success": True,
                "data": payload,
                "message": message,
                "confidence": confidence,
                "prompt_evaluation": payload.get("prompt_evaluation"),
            }

        # Step 2: EXECUTE (ToolExecutor)
        # Security: tenant_id is enforced inside ToolExecutor using self.current_tenant_id
        # We also pass it in params for completeness, but Executor overrides it
        execution_params = action_params.copy()
        execution_params["tenant_id"] = tenant_id
        if auth_token:
            execution_params["auth_token"] = auth_token

        logger.info(f"Agent executing tool: {action}")
        tool_result = await self.tool_executor.execute(action, execution_params)

        # Step 3: OBSERVE
        success = tool_result.get("success", False)
        empty = False

        # Specialized observation logic
        if action == "search_knowledge_base":
            empty = tool_result.get("count", 0) == 0

        # If successful and meaningful results, we are done
        if success and not empty:
            return {
                "success": True,
                "data": {
                    "tool_results": [tool_result],
                    "plan": plan,
                    "thought_process": thought_process,
                    "action": action,
                    "prompt_evaluation": payload.get("prompt_evaluation"),
                },
                "message": message,
                "confidence": confidence,
            }

        # Step 4: ADJUST (Second LLM Call with Observation)
        logger.info(f"Agent adjusting plan. Success: {success}, Empty: {empty}")

        observation_text = (
            f"Previous action '{action}' with params {action_params} "
            f"returned success={success}, empty={empty}. "
            f"Tool Output: {json.dumps(tool_result)} "
            f"Please adjust your plan and provide a helpful alternative response to the user."
        )

        adjust_messages = messages + [
            {
                "role": "assistant",  # Use 'assistant' (OpenAI/DeepSeek standard), not 'model'
                "content": json.dumps(payload),  # Inject previous thought
            },
            {
                "role": "user",  # Using user role to simulate "system observation" feedback
                "content": "OBSERVATION FROM SYSTEM: " + observation_text,
            },
        ]

        adjust_result = await self._call_llm_with_tools_json(adjust_messages, model=model)

        if not adjust_result.get("success"):
            # Fallback to original message if adjustment fails
            return {
                "success": True,
                "message": message + "\n\n(I tried to adjust my plan but encountered an error.)",
                "data": {"tool_result": tool_result},
            }

        adjusted_payload = adjust_result.get("payload", {})

        return {
            "success": True,
            "data": {
                "tool_results": [tool_result],
                "adjusted": adjusted_payload,
                "original_plan": plan,
                "original_thought_process": thought_process,
                "final_thought": adjusted_payload.get("thought_process"),
            },
            "message": adjusted_payload.get("message", message),
            "confidence": adjusted_payload.get("confidence", confidence),
            "prompt_evaluation": adjusted_payload.get("prompt_evaluation"),
        }

    async def _call_llm_with_tools_json(
        self,
        messages: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        temperature: float = 0.3,
        model: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Call LLM and parse the STRICT JSON response.
        """
        try:
            raw_response = await self.llm_service.generate_with_tools(
                messages=messages,
                tools=TOOL_DEFINITIONS,
                temperature=temperature,
                model_id=model,
            )

            # Extract content.
            content = raw_response.get("content") or raw_response.get("message")

            if not content:
                logger.error("LLM returned empty content")
                return {"success": False, "error": "Empty response"}

            # Parse JSON with robust cleaning
            parsed: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            if isinstance(content, dict):
                parsed = content
            else:
                import re

                # 1. Extract <think> blocks (DeepSeek R1/V3)
                think_match = re.search(r"<think>(.*?)</think>", content, flags=re.DOTALL)
                reasoning_content = think_match.group(1).strip() if think_match else None

                # Strip it for JSON parsing
                clean_content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

                # 2. Extract JSON block if present
                json_block = re.search(r"```json\s*(.*?)\s*```", clean_content, re.DOTALL)
                if json_block:
                    clean_content = json_block.group(1).strip()
                else:
                    # 3. Fallback: Find first '{' and last '}'
                    # This handles cases where Reasoner chats before the JSON
                    start_idx = clean_content.find("{")
                    end_idx = clean_content.rfind("}")
                    if start_idx != -1 and end_idx != -1:
                        clean_content = clean_content[start_idx : end_idx + 1]

                # 4. Attempt Parse
                try:
                    parsed = json.loads(clean_content)
                    # Inject reasoning if captured and not already present
                    if reasoning_content and not parsed.get("reasoning"):
                        parsed["reasoning"] = reasoning_content

                except json.JSONDecodeError as json_err:
                    logger.warning(
                        "Failed to parse JSON from LLM: {}. Content start: {}...",
                        json_err,
                        content[:100],
                    )

                    # 5. Last Ditch Effort: Regex-extract top-level keys if JSON is totally broken
                    # This is dangerous but better than failure for simple keys
                    message_match = re.search(r'"message":\s*"(.*?)"', clean_content)
                    fallback_msg = message_match.group(1) if message_match else clean_content

                    parsed = {
                        "message": fallback_msg,
                        "action": None,
                        "confidence": 0.5,
                        "thought_process": "JSON Fixup Applied: Model output malformed JSON.",
                        "reasoning": reasoning_content,  # Include captured reasoning even in fallback
                        "prompt_evaluation": None,
                    }

            return {"success": True, "payload": parsed}

        except Exception as e:
            logger.error("LLM call failed: {}", e)
            return {"success": False, "error": str(e)}

    async def handle_agent_management(self, context: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Handle agent management requests."""
        agents = await self.orchestrator.get_agents_data()
        return {
            "success": True,
            "data": agents,
            "command_type": "agent_management",
        }

    def create_clarification_result(
        self, parsed: ParsedCommand, performance_metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> UltimateExecutionResult:
        """Create result for clarification requests."""
        clarification = parsed.suggested_clarification or "Please provide more details"

        return UltimateExecutionResult(
            success=False,
            response={
                "needs_clarification": True,
                "clarification": clarification,
                "action": {
                    "type": "navigate",
                    "label": "Yes, Help Me",
                    "route": "/cva?message=Help me",
                },
            },
            confidence=parsed.confidence,
            execution_time=0.1,
            suggestions=[clarification],
            performance_metrics=performance_metrics,
        )

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

    async def handle_knowledge_query(
        self,
        parsed_command: ParsedCommand,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        model: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Handle knowledge queries with direct LLM routing."""
        try:
            prompt = self._build_knowledge_prompt(parsed_command.original_text)
            response = await self._call_llm(prompt, temperature=0.3, max_tokens=500, model=model)
            content = self._extract_content(response)

            return {
                "success": True,
                "response": content,
                "command_type": "knowledge_query",
                "source": "direct_llm",
                "llm_provider": response.get("provider", "unknown"),
                "confidence": parsed_command.confidence,
            }
        except Exception as e:
            logger.error(f"Knowledge query failed: {e}")
            return self._error_response("knowledge_query", str(e))

    async def handle_direct_question(
        self,
        parsed_command: ParsedCommand,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        model: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Handle direct questions with immediate LLM response."""
        try:
            # Use System Prompt for full context awareness
            tenant_ctx = context.get("tenant") or {}
            system_prompt = get_system_prompt(
                platform_name=tenant_ctx.get("platform_name", "SaaS Platform"),
                tenant_id=context.get("tenant_id", "generic"),
                tenant_domain=tenant_ctx.get("domain", "generic SME"),
                user_language=self._detect_language(parsed_command.original_text),
                current_route=context.get("route", "/"),
                page_context=context.get("page_context", ""),
                tool_definitions=TOOL_DEFINITIONS,
            )
            full_prompt = f"{system_prompt}\n\nUser: {parsed_command.original_text}"

            # Call LLM with Tools
            response = await self._call_llm(
                full_prompt,
                temperature=0.7,
                max_tokens=500,
                tools=TOOL_DEFINITIONS,
                model=model,
            )

            # Check for Function Calls (Requires execution by Agent layer)
            if response.get("requires_function_execution"):
                return {
                    "success": True,
                    "response": response.get("content", ""),  # Could be empty if pure function call
                    "command_type": "tool_execution",  # Signal to Agent
                    "source": "llm_tool",
                    "llm_provider": response.get("provider", "unknown"),
                    "confidence": parsed_command.confidence,
                    "function_calls": response.get("function_calls", []),
                }

            content = self._extract_content(response)

            return {
                "success": True,
                "response": content,
                "command_type": "direct_question",
                "source": "direct_llm",
                "llm_provider": response.get("provider", "unknown"),
                "confidence": parsed_command.confidence,
            }
        except Exception as e:
            logger.error(f"Direct question failed: {e}")
            return self._error_response("direct_question", str(e))

    def _build_knowledge_prompt(self, question: str) -> str:
        """Build prompt for knowledge queries."""
        return (
            "You are a knowledgeable assistant. "
            "Answer this factual question directly and concisely:\n\n"
            f"Question: {question}\n\n"
            "Provide a clear, accurate answer using ASCII-only characters."
        )

    async def _call_llm(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 500,
        tools: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        model: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Call LLM service with given parameters."""
        return cast(
            dict[str, Any],  # TODO(TYPE): replace Any with concrete type
            await self.llm_service.generate_response(
                prompt=prompt,
                provider=self.llm_service.default_provider,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                model_id=model,
            ),
        )

    def _extract_content(self, response: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Extract content from LLM response."""
        if isinstance(response, dict):
            return cast(str, response.get("content", ""))
        return cast(str, getattr(response, "content", str(response)))

    def _error_response(self, command_type: str, error: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create standardized error response."""
        return {
            "success": False,
            "error": error,
            "fallback": "Please try rephrasing your question",
            "command_type": command_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
