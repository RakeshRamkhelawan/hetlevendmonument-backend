"""
Prompt Builder - Advanced prompt construction and optimization system
ASCII-only compliance enforced
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict
from collections.abc import Callable

logger = logging.getLogger(__name__)


class PromptBuilderStats(TypedDict):
    """Typed statistics dictionary for PromptBuilder."""

    prompts_built: int
    cache_hits: int
    cache_misses: int
    template_uses: dict[str, int]
    strategy_uses: dict[str, int]
    average_quality_score: float


class PromptStrategy(Enum):
    """Prompt building strategies for different use cases."""

    SIMPLE = "simple"
    DETAILED = "detailed"
    CONVERSATIONAL = "conversational"
    INSTRUCTIONAL = "instructional"
    ANALYTICAL = "analytical"
    CREATIVE = "creative"
    TECHNICAL = "technical"
    CONTEXTUAL = "contextual"


@dataclass
class PromptVariable:
    """Variable definition for prompt templates."""

    name: str
    description: str
    required: bool = True
    default_value: Any = None
    validation_pattern: str | None = None
    transformation_func: (
        Callable[[str | int | float | bool | None], str | int | float | bool | None] | None
    ) = None


@dataclass
class PromptTemplate:
    """Template definition for prompt construction."""

    name: str
    template: str
    variables: list[PromptVariable] = field(default_factory=list)
    strategy: PromptStrategy = PromptStrategy.SIMPLE
    metadata: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    examples: list[str] = field(default_factory=list)


@dataclass
class PromptContext:
    """Context information for prompt building."""

    user_intent: str
    domain: str
    complexity_level: str = "medium"
    tone: str = "neutral"
    audience: str = "general"
    constraints: list[str] = field(default_factory=list)
    preferences: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


@dataclass
class PromptBuildResult:
    """Result of prompt building operation."""

    prompt: str
    template_used: str
    variables_used: dict[str, str | int | float | bool | None]
    strategy: PromptStrategy
    context: PromptContext
    quality_score: float
    suggestions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PromptBuilder:
    """
    Advanced prompt construction system for M-MDP architecture.
    Builds optimized prompts based on context, strategy, and templates.
    """

    def __init__(self, cache_layer: Any = None) -> None:
        """Initialize the prompt builder."""
        self.cache_layer = cache_layer
        self.templates: dict[str, PromptTemplate] = {}
        self.strategy_handlers: dict[PromptStrategy, Callable[[str, PromptContext], str]] = {}
        self.optimization_rules: list[Callable[[str], tuple[str, list[str]]]] = []
        self.stats: PromptBuilderStats = {
            "prompts_built": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "template_uses": {},
            "strategy_uses": {},
            "average_quality_score": 0.0,
        }

        # Initialize default templates and strategies
        self._initialize_default_templates()
        self._initialize_strategy_handlers()
        self._initialize_optimization_rules()

        logger.info("PromptBuilder initialized with template and strategy support")

    def _initialize_default_templates(self) -> None:
        """Initialize default prompt templates."""

        # Simple question template
        self.templates["simple_question"] = PromptTemplate(
            name="simple_question",
            template="Question: {question}\n\nPlease provide a clear and concise answer.",
            variables=[PromptVariable("question", "The question to answer", required=True)],
            strategy=PromptStrategy.SIMPLE,
        )

        # Detailed analysis template
        self.templates["detailed_analysis"] = PromptTemplate(
            name="detailed_analysis",
            template="""Analyze the following topic: {topic}

Context: {context}

Please provide a detailed analysis covering:
1. Overview and key concepts
2. Important considerations
3. Practical implications
4. Recommendations

Analysis:""",
            variables=[
                PromptVariable("topic", "Topic to analyze", required=True),
                PromptVariable("context", "Background context", required=True),
            ],
            strategy=PromptStrategy.ANALYTICAL,
        )

        # Conversational template
        self.templates["conversation"] = PromptTemplate(
            name="conversation",
            template="""Hi! I'm here to help you with {subject}.

{user_message}

How can I assist you today?""",
            variables=[
                PromptVariable("subject", "Subject area", required=True),
                PromptVariable("user_message", "User's message", required=True),
            ],
            strategy=PromptStrategy.CONVERSATIONAL,
        )

        # Technical instruction template
        self.templates["technical_instruction"] = PromptTemplate(
            name="technical_instruction",
            template="""Technical Task: {task}

Requirements:
{requirements}

Context:
{technical_context}

Please provide step-by-step instructions including:
- Prerequisites
- Detailed steps
- Expected outcomes
- Troubleshooting tips

Instructions:""",
            variables=[
                PromptVariable("task", "Technical task description", required=True),
                PromptVariable("requirements", "Task requirements", required=True),
                PromptVariable("technical_context", "Technical context", required=True),
            ],
            strategy=PromptStrategy.TECHNICAL,
        )

        # Creative generation template
        self.templates["creative_generation"] = PromptTemplate(
            name="creative_generation",
            template="""Creative Request: {creative_task}

Style: {style}
Tone: {tone}
Target Audience: {audience}

Additional Guidelines:
{guidelines}

Please create engaging content that meets these specifications:""",
            variables=[
                PromptVariable("creative_task", "Creative task description", required=True),
                PromptVariable("style", "Writing style", default_value="engaging"),
                PromptVariable("tone", "Content tone", default_value="friendly"),
                PromptVariable("audience", "Target audience", default_value="general"),
                PromptVariable("guidelines", "Additional guidelines", default_value=""),
            ],
            strategy=PromptStrategy.CREATIVE,
        )

        # Contextual assistance template
        self.templates["contextual_assistance"] = PromptTemplate(
            name="contextual_assistance",
            template="""Context: {situation_context}

User Goal: {user_goal}

Current State: {current_state}
Desired Outcome: {desired_outcome}

Constraints:
{constraints}

Please provide contextually appropriate assistance that takes into account the specific situation and constraints.""",
            variables=[
                PromptVariable("situation_context", "Situational context", required=True),
                PromptVariable("user_goal", "User's goal", required=True),
                PromptVariable("current_state", "Current situation", required=True),
                PromptVariable("desired_outcome", "Desired result", required=True),
                PromptVariable(
                    "constraints", "Any constraints", default_value="None specified"
                ),  # TODO(TYPE): replace Any with concrete type
            ],
            strategy=PromptStrategy.CONTEXTUAL,
        )

    def _initialize_strategy_handlers(self) -> None:
        """Initialize strategy-specific handlers."""

        self.strategy_handlers[PromptStrategy.SIMPLE] = self._handle_simple_strategy
        self.strategy_handlers[PromptStrategy.DETAILED] = self._handle_detailed_strategy
        self.strategy_handlers[PromptStrategy.CONVERSATIONAL] = self._handle_conversational_strategy
        self.strategy_handlers[PromptStrategy.INSTRUCTIONAL] = self._handle_instructional_strategy
        self.strategy_handlers[PromptStrategy.ANALYTICAL] = self._handle_analytical_strategy
        self.strategy_handlers[PromptStrategy.CREATIVE] = self._handle_creative_strategy
        self.strategy_handlers[PromptStrategy.TECHNICAL] = self._handle_technical_strategy
        self.strategy_handlers[PromptStrategy.CONTEXTUAL] = self._handle_contextual_strategy

    def _initialize_optimization_rules(self) -> None:
        """Initialize prompt optimization rules."""

        def clarity_optimization(prompt: str) -> tuple[str, list[str]]:
            """Optimize prompt for clarity."""
            suggestions: list[str] = []
            optimized_prompt = prompt

            # Remove redundant phrases
            redundant_patterns = [
                (r"\bplease please\b", "please"),
                (r"\bvery very\b", "very"),
                (r"\band and\b", "and"),
            ]

            for pattern, replacement in redundant_patterns:
                if re.search(pattern, optimized_prompt, re.IGNORECASE):
                    optimized_prompt = re.sub(
                        pattern, replacement, optimized_prompt, flags=re.IGNORECASE
                    )
                    suggestions.append(f"Removed redundant phrase: {pattern}")

            return optimized_prompt, suggestions

        def structure_optimization(prompt: str) -> tuple[str, list[str]]:
            """Optimize prompt structure."""
            suggestions: list[str] = []
            lines = prompt.split("\n")
            optimized_lines: list[str] = []
            for line in lines:
                # Ensure proper spacing after punctuation
                line = re.sub(r"([.!?])([A-Z])", r"\1 \2", line)

                # Ensure consistent bullet point formatting
                line = re.sub(r"^[-*+]\s*", "- ", line)

                optimized_lines.append(line)

            optimized_prompt = "\n".join(optimized_lines)

            if optimized_prompt != prompt:
                suggestions.append("Improved formatting and structure")

            return optimized_prompt, suggestions

        def length_optimization(prompt: str) -> tuple[str, list[str]]:
            """Optimize prompt length."""
            suggestions: list[str] = []
            # Check if prompt is too long or too short
            if len(prompt) > 2000:
                suggestions.append("Consider shortening the prompt for better focus")
            elif len(prompt) < 50:
                suggestions.append("Consider adding more context for better results")

            return prompt, suggestions

        self.optimization_rules = [
            clarity_optimization,
            structure_optimization,
            length_optimization,
        ]

    def build_prompt(
        self,
        template_name: str,
        variables: dict[str, str | int | float | bool | None],
        context: PromptContext | None = None,
        strategy: PromptStrategy | None = None,
    ) -> PromptBuildResult:
        """
        Build a prompt using specified template and variables.

        Args:
            template_name: Name of the template to use
            variables: Variables to substitute in template
            context: Context information for prompt building
            strategy: Override strategy for this build

        Returns:
            PromptBuildResult with built prompt and metadata
        """
        try:
            # Check cache first
            cache_key = self._generate_cache_key(template_name, variables, context, strategy)
            if self.cache_layer:
                cached_result = self.cache_layer.get(f"prompt_{cache_key}")
                if cached_result:
                    self.stats["cache_hits"] += 1
                    logger.debug(f"Cache hit for prompt build: {cache_key}")
                    return cached_result  # type: ignore[no-any-return]  # NOTE: cache returns Any

                self.stats["cache_misses"] += 1

            # Get template
            if template_name not in self.templates:
                raise ValueError(f"Template '{template_name}' not found")

            template = self.templates[template_name]

            # Use template strategy if not overridden
            if strategy is None:
                strategy = template.strategy

            # Validate and process variables
            processed_variables = self._process_variables(template, variables)

            # Build base prompt from template
            base_prompt = self._substitute_variables(template.template, processed_variables)

            # Apply strategy-specific enhancements
            enhanced_prompt = self._apply_strategy(
                base_prompt, strategy, context or PromptContext("", "")
            )

            # Optimize the prompt
            optimized_prompt, optimization_suggestions = self._optimize_prompt(enhanced_prompt)

            # Calculate quality score
            quality_score = self._calculate_quality_score(optimized_prompt, template, context)

            # Create result
            result = PromptBuildResult(
                prompt=optimized_prompt,
                template_used=template_name,
                variables_used=processed_variables,
                strategy=strategy,
                context=context or PromptContext("", ""),
                quality_score=quality_score,
                suggestions=optimization_suggestions,
            )

            # Cache result
            if self.cache_layer:
                self.cache_layer.set(f"prompt_{cache_key}", result, ttl=3600)

            # Update statistics
            self._update_stats(template_name, strategy, quality_score)

            logger.debug(
                f"Built prompt using template '{template_name}' with quality score {quality_score:.2f}"
            )
            return result

        except Exception as e:
            error_msg = f"Prompt building error: {str(e)}"
            logger.error(error_msg)

            return PromptBuildResult(
                prompt=f"Error building prompt: {error_msg}",
                template_used=template_name,
                variables_used=variables,
                strategy=strategy or PromptStrategy.SIMPLE,
                context=context or PromptContext("", ""),
                quality_score=0.0,
                warnings=[error_msg],
            )

    def _process_variables(
        self,
        template: PromptTemplate,
        variables: dict[str, str | int | float | bool | None],
    ) -> dict[str, str | int | float | bool | None]:
        """Process and validate template variables."""
        processed: dict[str, str | int | float | bool | None] = {}
        for var in template.variables:
            value = variables.get(var.name, var.default_value)

            # Check required variables
            if var.required and value is None:
                raise ValueError(f"Required variable '{var.name}' not provided")

            # Apply validation pattern if specified
            if var.validation_pattern and value is not None:
                if not re.match(var.validation_pattern, str(value)):
                    raise ValueError(f"Variable '{var.name}' does not match validation pattern")

            # Apply transformation function if specified
            if var.transformation_func and value is not None:
                try:
                    value = var.transformation_func(value)
                except Exception as e:
                    logger.warning(f"Variable transformation failed for '{var.name}': {e}")

            processed[var.name] = value

        return processed

    def _substitute_variables(
        self, template: str, variables: dict[str, str | int | float | bool | None]
    ) -> str:
        """Substitute variables in template string."""
        result = template

        for name, value in variables.items():
            placeholder = f"{{{name}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value) if value is not None else "")

        return result

    def _apply_strategy(self, prompt: str, strategy: PromptStrategy, context: PromptContext) -> str:
        """Apply strategy-specific enhancements to the prompt."""
        if strategy in self.strategy_handlers:
            return self.strategy_handlers[strategy](prompt, context)
        return prompt

    def _handle_simple_strategy(self, prompt: str, context: PromptContext) -> str:
        """Handle simple strategy - minimal modifications."""
        return prompt

    def _handle_detailed_strategy(self, prompt: str, context: PromptContext) -> str:
        """Handle detailed strategy - add comprehensive context."""
        enhancements: list[str] = []
        if context.domain:
            enhancements.append(f"Domain: {context.domain}")

        if context.complexity_level:
            enhancements.append(f"Complexity Level: {context.complexity_level}")

        if context.constraints:
            enhancements.append(f"Constraints: {', '.join(context.constraints)}")

        if enhancements:
            enhanced_context = "\n".join(enhancements)
            return f"{enhanced_context}\n\n{prompt}"

        return prompt

    def _handle_conversational_strategy(self, prompt: str, context: PromptContext) -> str:
        """Handle conversational strategy - add friendly tone."""
        if context.tone == "neutral":
            context.tone = "friendly"

        conversational_elements = [
            "I'd be happy to help you with this!",
            "Let me work through this step by step.",
            "Feel free to ask if you need any clarification!",
        ]

        return f"{prompt}\n\n{conversational_elements[0]}"

    def _handle_instructional_strategy(self, prompt: str, context: PromptContext) -> str:
        """Handle instructional strategy - add structured guidance."""
        instruction_header = "Please follow these instructions carefully:"
        instruction_footer = "Let me know if you need any clarification on these steps."

        return f"{instruction_header}\n\n{prompt}\n\n{instruction_footer}"

    def _handle_analytical_strategy(self, prompt: str, context: PromptContext) -> str:
        """Handle analytical strategy - add analytical framework."""
        analytical_framework = """
Please structure your analysis using this framework:
1. Key observations
2. Pattern identification
3. Cause-effect relationships
4. Implications and conclusions
"""
        return f"{prompt}\n{analytical_framework}"

    def _handle_creative_strategy(self, prompt: str, context: PromptContext) -> str:
        """Handle creative strategy - encourage creativity."""
        creative_encouragement = """
Feel free to be creative and think outside the box.
Consider multiple perspectives and don't be afraid to explore innovative ideas.
"""
        return f"{prompt}\n{creative_encouragement}"

    def _handle_technical_strategy(self, prompt: str, context: PromptContext) -> str:
        """Handle technical strategy - add technical precision."""
        technical_guidance = """
Please provide technically accurate and precise information.
Include relevant technical details, specifications, and best practices.
"""
        return f"{prompt}\n{technical_guidance}"

    def _handle_contextual_strategy(self, prompt: str, context: PromptContext) -> str:
        """Handle contextual strategy - emphasize context awareness."""
        if context.audience:
            audience_note = f"Note: Please tailor your response for {context.audience} audience."
            return f"{prompt}\n\n{audience_note}"

        return prompt

    def _optimize_prompt(self, prompt: str) -> tuple[str, list[str]]:
        """Apply optimization rules to improve prompt quality."""
        optimized_prompt = prompt
        all_suggestions: list[str] = []
        for rule in self.optimization_rules:
            try:
                optimized_prompt, suggestions = rule(optimized_prompt)
                all_suggestions.extend(suggestions)
            except Exception as e:
                logger.warning(f"Optimization rule failed: {e}")

        return optimized_prompt, all_suggestions

    def _calculate_quality_score(
        self, prompt: str, template: PromptTemplate, context: PromptContext | None
    ) -> float:
        """Calculate quality score for the built prompt."""
        score = 0.0
        max_score = 100.0

        # Length score (20 points)
        length = len(prompt)
        if 100 <= length <= 1000:
            score += 20
        elif 50 <= length < 100 or 1000 < length <= 2000:
            score += 15
        else:
            score += 10

        # Clarity score (20 points)
        clarity_indicators = [
            r"\?",  # Contains questions
            r"[.!]",  # Contains clear statements
            r":\s*$",  # Contains structured lists
        ]

        clarity_score = sum(
            5 for pattern in clarity_indicators if re.search(pattern, prompt, re.MULTILINE)
        )
        score += min(clarity_score, 20)

        # Structure score (20 points)
        structure_indicators = [
            (r"\n\s*\n", 5),  # Paragraph breaks
            (r"^\s*[-*+]\s", 5),  # Bullet points
            (r"^\s*\d+\.\s", 5),  # Numbered lists
            (r"[:\-]", 5),  # Colons and dashes
        ]

        for pattern, points in structure_indicators:
            if re.search(pattern, prompt, re.MULTILINE):
                score += points

        # Context relevance score (20 points)
        if context:
            relevance_score = 0
            if context.domain and context.domain.lower() in prompt.lower():
                relevance_score += 10
            if context.user_intent and any(
                word in prompt.lower() for word in context.user_intent.lower().split()
            ):
                relevance_score += 10
            score += relevance_score

        # Template utilization score (20 points)
        if template.variables:
            utilized_vars = sum(1 for var in template.variables if f"{{{var.name}}}" not in prompt)
            utilization_percentage = utilized_vars / len(template.variables)
            score += utilization_percentage * 20

        return min(score, max_score)

    def _generate_cache_key(
        self,
        template_name: str,
        variables: dict[str, str | int | float | bool | None],
        context: PromptContext | None,
        strategy: PromptStrategy | None,
    ) -> str:
        """Generate cache key for the prompt build operation."""
        key_data = {
            "template": template_name,
            "variables": variables,
            "context": context.__dict__ if context else {},
            "strategy": strategy.value if strategy else None,
        }

        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode("ascii"), usedforsecurity=False).hexdigest()

    def _update_stats(
        self, template_name: str, strategy: PromptStrategy, quality_score: float
    ) -> None:
        """Update prompt building statistics."""
        self.stats["prompts_built"] += 1

        # Update template usage
        if template_name not in self.stats["template_uses"]:
            self.stats["template_uses"][template_name] = 0
        self.stats["template_uses"][template_name] += 1

        # Update strategy usage
        strategy_name = strategy.value
        if strategy_name not in self.stats["strategy_uses"]:
            self.stats["strategy_uses"][strategy_name] = 0
        self.stats["strategy_uses"][strategy_name] += 1

        # Update average quality score
        current_avg = self.stats["average_quality_score"]
        count = self.stats["prompts_built"]
        self.stats["average_quality_score"] = ((current_avg * (count - 1)) + quality_score) / count

    def add_template(self, template: PromptTemplate) -> None:
        """Add a custom prompt template."""
        self.templates[template.name] = template
        logger.info(f"Added prompt template: {template.name}")

    def remove_template(self, template_name: str) -> None:
        """Remove a prompt template."""
        if template_name in self.templates:
            del self.templates[template_name]
            logger.info(f"Removed prompt template: {template_name}")

    def get_available_templates(self) -> list[str]:
        """Get list of available template names."""
        return list(self.templates.keys())

    def get_template(self, template_name: str) -> PromptTemplate | None:
        """Get a specific template by name."""
        return self.templates.get(template_name)

    def get_stats(self) -> PromptBuilderStats:
        """Get prompt building statistics."""
        return self.stats.copy()

    def reset_stats(self) -> None:
        """Reset prompt building statistics."""
        self.stats = {
            "prompts_built": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "template_uses": {},
            "strategy_uses": {},
            "average_quality_score": 0.0,
        }
        logger.info("Prompt building statistics reset")


def create_prompt_builder(cache_layer: Any = None) -> PromptBuilder:
    """Factory function to create a PromptBuilder instance."""
    return PromptBuilder(cache_layer=cache_layer)
