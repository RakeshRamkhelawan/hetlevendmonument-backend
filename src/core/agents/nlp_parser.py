#!/usr/bin/env python3
"""
Enhanced NLP Parser for CVA Agent with M-MDP Integration
Replaces simple keyword matching with intelligent intent classification
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger("EnhancedNLP")


class IntentType(Enum):
    """Classification of user intents with M-MDP extensions"""

    GREETING = "greeting"
    CONVERSATION = "conversation"
    SYSTEM_STATUS = "system_status"
    AGENT_MANAGEMENT = "agent_management"
    TASK_MANAGEMENT = "task_management"
    PERFORMANCE_MONITORING = "performance_monitoring"
    SYSTEM_CONTROL = "system_control"
    LEARNING_MANAGEMENT = "learning_management"  # M-MDP specific
    META_LEARNING = "meta_learning"  # M-MDP specific
    SAFETY_MONITORING = "safety_monitoring"  # M-MDP specific
    PREDICTION_REQUEST = "prediction_request"  # M-MDP specific
    MULTI_COMMAND = "multi_command"
    UNKNOWN = "unknown"


@dataclass
class ExtractedParameters:
    """Structured parameter extraction from user input"""

    agent_name: str | None = None
    task_description: str | None = None
    priority_level: str | None = None  # urgent, normal, low
    capability_type: str | None = None
    time_frame: str | None = None
    quantity: int | None = None
    learning_type: str | None = None  # M-MDP: ppo, meta, safety
    safety_level: str | None = None  # M-MDP: low, medium, high, critical


@dataclass
class ParsedCommand:
    """Result of NLP parsing with confidence scoring"""

    intent: IntentType
    api_command: str
    parameters: ExtractedParameters
    confidence: float  # 0.0 - 1.0
    original_text: str
    suggested_clarification: str | None = None


class EnhancedNLPParser:
    """
    Production-ready NLP parser with intent classification and parameter extraction
    Enhanced for M-MDP learning system integration
    """

    def __init__(self) -> None:
        # Enhanced intent patterns with confidence scoring and M-MDP support
        self.intent_patterns = {
            IntentType.SYSTEM_STATUS: [
                (
                    r"(?:show|display|get)\s+(?:system\s+)?(?:status|health|dashboard)",
                    0.9,
                ),
                (r"(?:what.s|how.s)\s+(?:the\s+)?(?:system|health|status)", 0.8),
                (r"(?:system|health|status|dashboard)\s+(?:check|info|report)", 0.8),
                (r"hoe\s+(?:is|staat)\s+(?:het\s+)?(?:systeem|system)", 0.9),  # Dutch
                (r"mmdp\s+(?:status|health|system)", 0.9),  # M-MDP specific
            ],
            IntentType.AGENT_MANAGEMENT: [
                (r"(?:show|list|get)\s+(?:all\s+)?agents?", 0.9),
                (r"(?:what|which)\s+agents?\s+(?:are\s+)?(?:active|running)", 0.8),
                (r"agent\s+(?:status|list|info)", 0.8),
                (r"(?:laat|toon)\s+(?:alle\s+)?agents?\s+zien", 0.9),  # Dutch
                (r"coordinator?\s+agents?", 0.8),  # M-MDP specific
            ],
            IntentType.TASK_MANAGEMENT: [
                (r"assign\s+(?:a\s+)?task\s+to\s+(\w+)", 0.9),
                (r"create\s+(?:a\s+)?(?:new\s+)?task\s+for\s+(\w+)", 0.8),
                (r"(?:show|get|list)\s+(?:task\s+)?(?:status|tasks)", 0.8),
                (r"(?:urgent|high\s+priority)\s+task", 0.7),
                (r"taak\s+(?:toewijzen|maken)\s+voor", 0.8),  # Dutch
                (r"multi.?agent\s+task", 0.8),  # M-MDP specific
            ],
            IntentType.PERFORMANCE_MONITORING: [
                (r"(?:show|get|display)\s+performance\s+(?:metrics|stats)", 0.9),
                (r"(?:system\s+)?(?:performance|metrics|statistics)", 0.8),
                (r"(?:how\s+(?:fast|slow)|response\s+time)", 0.7),
                (r"(?:prestatie|performance)\s+(?:gegevens|metrics)", 0.8),  # Dutch
                (r"cache\s+(?:hit\s+rate|performance)", 0.8),  # Enhanced
                (r"prediction\s+(?:accuracy|performance)", 0.9),  # M-MDP specific
            ],
            IntentType.SYSTEM_CONTROL: [
                (r"(?:start|stop|restart)\s+(?:the\s+)?system", 0.9),
                (r"(?:optimize|tune)\s+(?:the\s+)?system", 0.8),
                (r"(?:system\s+)?(?:optimization|cleanup)", 0.7),
                (
                    r"(?:optimaliseer|herstart)\s+(?:het\s+)?(?:systeem|system)",
                    0.8,
                ),  # Dutch
                (r"scale\s+(?:agents?|system)", 0.8),  # Enhanced
            ],
            IntentType.LEARNING_MANAGEMENT: [  # M-MDP specific
                (r"(?:start|stop|pause)\s+(?:learning|training)", 0.9),
                (r"(?:show|get)\s+(?:learning|training)\s+(?:progress|status)", 0.8),
                (r"(?:adjust|tune)\s+(?:learning|training)\s+parameters", 0.8),
                (r"(?:ppo|reinforcement)\s+learning", 0.9),
                (r"experience\s+(?:buffer|replay)", 0.8),
                (r"reward\s+(?:system|calculation)", 0.8),
            ],
            IntentType.META_LEARNING: [  # M-MDP specific
                (r"meta.?learning\s+(?:status|progress)", 0.9),
                (r"(?:strategy|task)\s+transfer", 0.8),
                (r"few.?shot\s+learning", 0.8),
                (r"learning\s+(?:optimization|strategy)", 0.8),
                (r"adaptive\s+(?:learning|parameters)", 0.7),
            ],
            IntentType.SAFETY_MONITORING: [  # M-MDP specific
                (r"safety\s+(?:status|check|violations)", 0.9),
                (r"constraint\s+(?:violations|system)", 0.8),
                (r"rollback\s+(?:system|mechanism)", 0.8),
                (r"human\s+approval\s+(?:gate|system)", 0.8),
                (r"testing\s+framework", 0.7),
            ],
        }

        # Parameter extraction patterns with M-MDP extensions
        self.parameter_patterns = {
            "agent_name": [
                r"(?:to|for)\s+(\w+)(?:\s+agent)?",
                r"agent\s+(\w+)",
                r"(\w+)\s+agent",
                r"coordinator\s+(\w+)",  # M-MDP
            ],
            "priority_level": [
                r"(urgent|high\s+priority|critical)",
                r"(normal|medium|standard)",
                r"(low\s+priority|low|minor)",
            ],
            "task_description": [
                r'task\s+["\']([^"\']+)["\']',
                r"task:\s*(.+?)(?:\s+for|\s+to|$)",
            ],
            "capability_type": [
                r"(?:for|with)\s+(content|analysis|community|strategic|learning|safety)\s+(?:capability|work)",
                r"(content|data|analysis|community|learning|coordination)\s+task",
            ],
            "quantity": [
                r"(\d+)\s+(?:tasks?|agents?|items?)",
            ],
            "learning_type": [  # M-MDP specific
                r"(ppo|meta|safety|transfer|few.?shot)\s+learning",
                r"learning\s+(?:type|method)\s+(\w+)",
            ],
            "safety_level": [  # M-MDP specific
                r"safety\s+level\s+(low|medium|high|critical)",
                r"(critical|high|medium|low)\s+safety",
            ],
        }

        # Multi-command detection patterns
        self.multi_command_patterns = [
            r"(?:and|then|also|plus)",
            r"(?:,\s*(?:and\s+)?(?:show|get|list|assign))",
        ]

    def parse(self, user_input: str) -> ParsedCommand:
        """
        Main parsing method - converts natural language to structured command
        """
        user_input = user_input.strip().lower()
        logger.debug(f"Parsing input: {user_input}")

        # Check for multi-command first
        if self._is_multi_command(user_input):
            return self._parse_multi_command(user_input)

        # Single command parsing
        best_intent, best_confidence, best_command = self._classify_intent(user_input)
        parameters = self._extract_parameters(user_input, best_intent)

        # Generate clarification if confidence is low
        clarification = self._generate_clarification(best_intent, best_confidence, parameters)

        return ParsedCommand(
            intent=best_intent,
            api_command=best_command,
            parameters=parameters,
            confidence=best_confidence,
            original_text=user_input,
            suggested_clarification=clarification,
        )

    def _classify_intent(self, user_input: str) -> tuple[IntentType, float, str]:
        """Classify user intent using pattern matching with confidence scoring"""
        best_intent = IntentType.UNKNOWN
        best_confidence = 0.0
        best_command = "unknown_command"

        for intent_type, patterns in self.intent_patterns.items():
            for pattern, base_confidence in patterns:
                match = re.search(pattern, user_input, re.IGNORECASE)
                if match:
                    # Adjust confidence based on pattern specificity
                    confidence = base_confidence
                    if len(match.group(0)) / len(user_input) > 0.7:  # High coverage
                        confidence += 0.1

                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_intent = intent_type
                        best_command = self._intent_to_command(intent_type)

        return best_intent, best_confidence, best_command

    def _extract_parameters(self, user_input: str, intent: IntentType) -> ExtractedParameters:
        """Extract structured parameters from user input"""
        params = ExtractedParameters()

        for param_name, patterns in self.parameter_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, user_input, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    setattr(params, param_name, value)
                    break

        # Intent-specific parameter processing
        if intent == IntentType.TASK_MANAGEMENT:
            # If no explicit description found, use everything after "task"
            if not params.task_description:
                task_match = re.search(r"task\s+(.+?)(?:\s+for|\s+to|$)", user_input, re.IGNORECASE)
                if task_match:
                    params.task_description = task_match.group(1)

        # M-MDP specific parameter processing
        if intent == IntentType.LEARNING_MANAGEMENT:
            if not params.learning_type:
                # Default to ppo if not specified
                params.learning_type = "ppo"

        if intent == IntentType.SAFETY_MONITORING:
            if not params.safety_level:
                # Default to medium if not specified
                params.safety_level = "medium"

        return params

    def _is_multi_command(self, user_input: str) -> bool:
        """Detect if input contains multiple commands"""
        for pattern in self.multi_command_patterns:
            if re.search(pattern, user_input, re.IGNORECASE):
                return True
        return False

    def _parse_multi_command(self, user_input: str) -> ParsedCommand:
        """Handle multi-command parsing"""
        # For now, suggest breaking down the command
        return ParsedCommand(
            intent=IntentType.MULTI_COMMAND,
            api_command="multi_command_detected",
            parameters=ExtractedParameters(),
            confidence=0.8,
            original_text=user_input,
            suggested_clarification="I detected multiple commands. Please break this down into separate requests for better accuracy.",
        )

    def _intent_to_command(self, intent: IntentType) -> str:
        """Map intent types to API commands with M-MDP support"""
        intent_command_map = {
            IntentType.SYSTEM_STATUS: "get_system_dashboard",
            IntentType.AGENT_MANAGEMENT: "get_active_agents",
            IntentType.TASK_MANAGEMENT: "assign_task",
            IntentType.PERFORMANCE_MONITORING: "get_performance_metrics",
            IntentType.SYSTEM_CONTROL: "optimize_system",
            IntentType.LEARNING_MANAGEMENT: "manage_learning_system",  # M-MDP
            IntentType.META_LEARNING: "get_meta_learning_status",  # M-MDP
            IntentType.SAFETY_MONITORING: "check_safety_status",  # M-MDP
        }
        return intent_command_map.get(intent, "unknown_command")

    def _generate_clarification(
        self, intent: IntentType, confidence: float, parameters: ExtractedParameters
    ) -> str | None:
        """Generate clarification questions for ambiguous inputs"""
        if confidence < 0.6:
            return f"I'm not sure what you want to do (confidence: {confidence:.1%}). Could you rephrase your request?"

        # Intent-specific clarifications
        if intent == IntentType.TASK_MANAGEMENT and not parameters.agent_name:
            return "Which agent should I assign this task to? (e.g., 'content agent', 'analysis agent')"

        if intent == IntentType.TASK_MANAGEMENT and not parameters.task_description:
            return "What task should I assign? Please provide more details."

        # M-MDP specific clarifications
        if intent == IntentType.LEARNING_MANAGEMENT and not parameters.learning_type:
            return (
                "Which learning system? (e.g., 'ppo learning', 'meta learning', 'safety learning')"
            )

        if intent == IntentType.SAFETY_MONITORING and not parameters.safety_level:
            return "What safety level should I check? (low, medium, high, critical)"

        return None


# Enhanced testing for M-MDP capabilities
if __name__ == "__main__":
    parser = EnhancedNLPParser()

    test_inputs = [
        "show me the system status",
        "assign urgent task to content agent",
        "list all active agents and show performance metrics",
        "hoe is het systeem?",  # Dutch
        "create task for analysis capability",
        "what's the response time?",
        "start ppo learning",  # M-MDP
        "show meta learning progress",  # M-MDP
        "check safety violations",  # M-MDP
        "get prediction accuracy",  # M-MDP
        "stop learning system",  # M-MDP
        "vague input here",  # Should trigger clarification
    ]

    print("=== ENHANCED NLP PARSER TEST RESULTS (M-MDP Edition) ===")
    for test_input in test_inputs:
        result = parser.parse(test_input)
        print(f"\nInput: '{test_input}'")
        print(f"Intent: {result.intent.value}")
        print(f"Command: {result.api_command}")
        print(f"Confidence: {result.confidence:.1%}")
        print(f"Parameters: {result.parameters}")
        if result.suggested_clarification:
            print(f"Clarification: {result.suggested_clarification}")
