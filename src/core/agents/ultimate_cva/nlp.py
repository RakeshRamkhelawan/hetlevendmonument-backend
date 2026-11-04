import asyncio
import json
import logging
from typing import Any

from .models import IntentType, ParsedCommand

logger = logging.getLogger("UltimateCVA.NLP")


class NLPHandler:
    def __init__(self, llm_service: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self.llm_service = llm_service

    async def parse_command_with_llm(self, user_input: str) -> ParsedCommand:
        """Enhanced command parsing using dynamic LLM integration"""
        try:
            # OPTIMIZATION: Check for mandatory prompt quality analysis if input is long
            # Instead of fast-tracking to STRATEGIC_PLANNING, we now perform a deeper analysis.
            is_long_prompt = len(user_input) > 100

            analysis_prompt = f"""
Analyze this user command and extract intent information:

Command: "{user_input}"

Classify the intent as one of:
- system_status: Questions about system health, dashboard, overall status
- agent_management: Questions about agents, their status, capabilities
- task_management: Creating, assigning, managing tasks
- performance_monitoring: Performance metrics, optimization requests
- system_control: Starting, stopping, controlling system operations
- strategic_planning: High-level planning, strategic decisions
- ceo_directive: Executive-level directives requiring coordination
- multi_command: Multiple commands in one request
- knowledge_query: Factual questions about people, events, dates, definitions
- direct_question: Simple questions needing immediate LLM response
- navigation: Moving between pages or UI sections

Provide response in JSON format:
{{
    "intent": "intent_type",
    "confidence": 0.85,
    "parameters": {{"key": "value"}},
    "suggested_clarification": "If ambiguous, ask for details in the SAME LANGUAGE as the command.",
    "prompt_quality_score": 0.9,
    "quality_feedback": "If score < 0.7, provide specific advice in the SAME LANGUAGE as the command."
}}
"""

            # Generate response using LLM service with timeout
            logger.info("[BRAIN] CVA: Calling LLM for intent analysis (timeout: 60s)...")
            try:
                llm_response = await asyncio.wait_for(
                    self.llm_service.generate_response(
                        prompt=analysis_prompt,
                        provider=self.llm_service.default_provider,
                        temperature=0.3,
                        max_tokens=600,
                    ),
                    timeout=60.0,
                )
            except TimeoutError:
                logger.error(
                    f"[FAIL] {self.llm_service.default_provider.value} timeout after 60s - LLM not responding"
                )
                raise TimeoutError(
                    f"{self.llm_service.default_provider.value} API timeout: Intent analysis took too long. Please verify your API key is valid."
                )

            if llm_response.get("success"):
                try:
                    # DEBUG: Log LLM response for intent analysis
                    logger.info(f"DEBUG: LLM intent analysis response: {llm_response}")

                    # Parse JSON response
                    response_content = llm_response.get("content", "{}")
                    logger.info(f"DEBUG: Response content to parse: {response_content}")

                    # Extract JSON from response if it contains other text
                    parsed_data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
                    if "{" in response_content:
                        start_idx = response_content.index("{")
                        end_idx = response_content.rindex("}") + 1
                        json_content = response_content[start_idx:end_idx]
                        parsed_data = json.loads(json_content)
                    else:
                        parsed_data = {}
                    intent_str = parsed_data.get("intent", "system_status")
                    intent = (
                        IntentType(intent_str)
                        if intent_str in [i.value for i in IntentType]
                        else IntentType.SYSTEM_STATUS
                    )

                    quality_score = parsed_data.get("prompt_quality_score", 1.0)
                    clarification = parsed_data.get("suggested_clarification")

                    # If quality is low, override suggested_clarification with quality feedback
                    if quality_score < 0.7:
                        clarification = parsed_data.get("quality_feedback", clarification)

                    return ParsedCommand(
                        original_text=user_input,
                        intent=intent,
                        confidence=parsed_data.get("confidence", 0.7),
                        parameters=parsed_data.get("parameters", {}),
                        suggested_clarification=clarification,
                    )

                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"LLM response parsing failed: {e}")
                    # Fallback to keyword-based parsing
                    return self.fallback_command_parsing(user_input)
            else:
                logger.warning("LLM analysis failed, using fallback parsing")
                return self.fallback_command_parsing(user_input)

        except Exception as e:
            logger.error(f"DEBUG: LLM intent parsing failed: {e}")
            logger.error(f"DEBUG: Falling back to keyword-based parsing for: {user_input}")
            return self.fallback_command_parsing(user_input)

    def fallback_command_parsing(self, user_input: str) -> ParsedCommand:
        """Fallback command parsing using keyword matching"""
        user_lower = user_input.lower()
        logger.info(f"DEBUG FALLBACK: Processing '{user_input}' -> '{user_lower}'")

        # Simple keyword-based intent detection
        if any(word in user_lower for word in ["status", "health", "dashboard", "system"]):
            intent = IntentType.SYSTEM_STATUS
            confidence = 0.8
            logger.info("DEBUG FALLBACK: Matched SYSTEM_STATUS")
        elif any(word in user_lower for word in ["agent", "agents"]):
            intent = IntentType.AGENT_MANAGEMENT
            confidence = 0.8
            logger.info("DEBUG FALLBACK: Matched AGENT_MANAGEMENT")
        elif any(word in user_lower for word in ["task", "assign", "create"]):
            intent = IntentType.TASK_MANAGEMENT
            confidence = 0.7
            logger.info("DEBUG FALLBACK: Matched TASK_MANAGEMENT")
        elif any(word in user_lower for word in ["performance", "optimize", "metrics"]):
            intent = IntentType.PERFORMANCE_MONITORING
            confidence = 0.7
            logger.info("DEBUG FALLBACK: Matched PERFORMANCE_MONITORING")
        elif any(
            word in user_lower
            for word in [
                "when",
                "what",
                "where",
                "who",
                "how",
                "wanneer",
                "wat",
                "waar",
                "wie",
                "hoe",
            ]
        ):
            intent = IntentType.KNOWLEDGE_QUERY
            confidence = 0.8
            logger.info("DEBUG FALLBACK: Matched KNOWLEDGE_QUERY for patterns")
        elif user_input.endswith("?"):
            intent = IntentType.DIRECT_QUESTION
            confidence = 0.6
            logger.info("DEBUG FALLBACK: Matched DIRECT_QUESTION (ends with ?)")
        else:
            # Default to UNKNOWN if no specific patterns match
            intent = IntentType.UNKNOWN
            confidence = 0.5
            logger.info("DEBUG FALLBACK: Defaulted to UNKNOWN")

        logger.info(f"DEBUG FALLBACK: Final intent={intent.value}, confidence={confidence}")

        return ParsedCommand(
            original_text=user_input,
            intent=intent,
            confidence=confidence,
            parameters={},
            suggested_clarification=(
                None
                if confidence > 0.6
                else "Could you be more specific about what you'd like to know?"
            ),
        )
