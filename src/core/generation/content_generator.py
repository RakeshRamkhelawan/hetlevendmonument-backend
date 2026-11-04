"""
Content Generator - Advanced content generation with multiple strategies
Implements intelligent content creation for various types and contexts
"""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, cast
from collections.abc import Awaitable, Callable

from src.core.caching.cache_layer import cached
from src.core.knowledge.knowledge_manager import knowledge_manager
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)


class ContentType(Enum):
    """Types of content that can be generated"""

    TEXT_RESPONSE = "text_response"
    DOCUMENTATION = "documentation"
    CODE_SNIPPET = "code_snippet"
    EXPLANATION = "explanation"
    SUMMARY = "summary"
    ANALYSIS = "analysis"
    RECOMMENDATION = "recommendation"
    REPORT = "report"
    INSTRUCTION = "instruction"
    CONVERSATION = "conversation"


class GenerationStrategy(Enum):
    """Content generation strategies"""

    TEMPLATE_BASED = "template_based"
    KNOWLEDGE_BASED = "knowledge_based"
    CONTEXT_AWARE = "context_aware"
    STRUCTURED = "structured"
    CONVERSATIONAL = "conversational"


class QualityLevel(Enum):
    """Quality levels for generated content"""

    BASIC = "basic"
    STANDARD = "standard"
    HIGH = "high"
    PREMIUM = "premium"


@dataclass
class GenerationRequest:
    """Request for content generation"""

    request_id: str
    content_type: ContentType
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    requirements: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    strategy: GenerationStrategy = GenerationStrategy.CONTEXT_AWARE
    quality_level: QualityLevel = QualityLevel.STANDARD
    max_length: int = 1000
    template_name: str | None = None
    variables: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    constraints: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary"""
        return {
            "request_id": self.request_id,
            "content_type": self.content_type.value,
            "context": self.context,
            "requirements": self.requirements,
            "strategy": self.strategy.value,
            "quality_level": self.quality_level.value,
            "max_length": self.max_length,
            "template_name": self.template_name,
            "variables": self.variables,
            "constraints": self.constraints,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class GenerationResult:
    """Result of content generation"""

    request_id: str
    content: str
    content_type: ContentType
    quality_score: float
    generation_time: float
    strategy_used: GenerationStrategy
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary"""
        return {
            "request_id": self.request_id,
            "content": self.content,
            "content_type": self.content_type.value,
            "quality_score": self.quality_score,
            "generation_time": self.generation_time,
            "strategy_used": self.strategy_used.value,
            "metadata": self.metadata,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "created_at": self.created_at.isoformat(),
        }


class ContentTemplate:
    """Template for structured content generation"""

    def __init__(self, template_id: str, content_type: ContentType, template_text: str) -> None:
        self.template_id = template_id
        self.content_type = content_type
        self.template_text = template_text
        self.variables = self._extract_variables()

    def _extract_variables(self) -> list[str]:
        """Extract variables from template text"""
        # Find all variables in format {variable_name}
        pattern = r"\{([^}]+)\}"
        variables = re.findall(pattern, self.template_text)
        return cast(list[str], list(set(variables)))

    def render(self, variables: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Render template with provided variables"""
        rendered_text = self.template_text

        for var_name, var_value in variables.items():
            placeholder = "{{{var_name}}}"
            if placeholder in rendered_text:
                # Ensure ASCII compliance
                str_value = str(var_value).encode("ascii", errors="ignore").decode("ascii")
                rendered_text = rendered_text.replace(placeholder, str_value)

        return rendered_text


class ContentQualityAssessor:
    """Assesses the quality of generated content"""

    def __init__(self) -> None:
        self.quality_metrics: dict[
            str, Callable[[str, GenerationRequest], Awaitable[tuple[float, list[str], list[str]]]]
        ] = {
            "readability": self._assess_readability,
            "completeness": self._assess_completeness,
            "relevance": self._assess_relevance,
            "structure": self._assess_structure,
            "accuracy": self._assess_accuracy,
        }

    async def assess_quality(
        self, content: str, request: GenerationRequest
    ) -> tuple[float, list[str], list[str]]:
        """Assess content quality and provide feedback"""
        try:
            scores: dict[str, float] = {}
            warnings: list[str] = []
            suggestions: list[str] = []
            # Run quality assessments
            for metric_name, assessment_func in self.quality_metrics.items():
                try:
                    score, metric_warnings, metric_suggestions = await assessment_func(
                        content, request
                    )
                    scores[metric_name] = score
                    warnings.extend(metric_warnings)
                    suggestions.extend(metric_suggestions)
                except Exception as e:
                    logger.warning(f"Quality assessment failed for {metric_name}: {e}")
                    scores[metric_name] = 0.5  # Default score

            # Calculate overall quality score
            overall_score = sum(scores.values()) / len(scores) if scores else 0.5

            return overall_score, warnings, suggestions

        except Exception as e:
            logger.error(f"Quality assessment failed: {e}")
            return 0.5, ["Quality assessment failed"], []

    async def _assess_readability(
        self, content: str, request: GenerationRequest
    ) -> tuple[float, list[str], list[str]]:
        """Assess content readability"""
        warnings: list[str] = []
        suggestions: list[str] = []
        try:
            # Simple readability metrics
            sentences = content.split(".")
            words = content.split()

            if not sentences or not words:
                return 0.0, ["Content is empty"], ["Add meaningful content"]

            avg_sentence_length = len(words) / len(sentences)
            avg_word_length = sum(len(word) for word in words) / len(words)

            # Score based on sentence and word length
            sentence_score = (
                1.0 if avg_sentence_length < 20 else max(0.3, 1.0 - (avg_sentence_length - 20) / 30)
            )
            word_score = 1.0 if avg_word_length < 6 else max(0.3, 1.0 - (avg_word_length - 6) / 10)

            readability_score = (sentence_score + word_score) / 2

            if avg_sentence_length > 25:
                warnings.append("Some sentences are very long")
                suggestions.append("Consider breaking long sentences into shorter ones")

            if avg_word_length > 8:
                suggestions.append("Consider using simpler vocabulary")

            return readability_score, warnings, suggestions

        except Exception as e:
            logger.error(f"Readability assessment failed: {e}")
            return 0.5, [], []

    async def _assess_completeness(
        self, content: str, request: GenerationRequest
    ) -> tuple[float, list[str], list[str]]:
        """Assess content completeness"""
        warnings: list[str] = []
        suggestions: list[str] = []
        try:
            content_length = len(content)
            required_length = request.requirements.get("min_length", 50)
            max_length = request.max_length

            # Length-based completeness
            if content_length < required_length:
                completeness_score = content_length / required_length
                warnings.append(
                    f"Content is shorter than required ({content_length} < {required_length})"
                )
                suggestions.append("Add more details to meet length requirements")
            elif content_length > max_length:
                completeness_score = 0.8  # Penalize for being too long
                warnings.append(f"Content exceeds maximum length ({content_length} > {max_length})")
                suggestions.append("Consider condensing the content")
            else:
                completeness_score = 1.0

            # Check for required elements
            required_elements = request.requirements.get("required_elements", [])
            missing_elements: list[str] = []
            for element in required_elements:
                if element.lower() not in content.lower():
                    missing_elements.append(element)

            if missing_elements:
                completeness_score *= 0.7  # Penalty for missing elements
                warnings.append(f"Missing required elements: {', '.join(missing_elements)}")
                suggestions.append(f"Include information about: {', '.join(missing_elements)}")

            return completeness_score, warnings, suggestions

        except Exception as e:
            logger.error(f"Completeness assessment failed: {e}")
            return 0.5, [], []

    async def _assess_relevance(
        self, content: str, request: GenerationRequest
    ) -> tuple[float, list[str], list[str]]:
        """Assess content relevance to request"""
        warnings: list[str] = []
        suggestions: list[str] = []
        try:
            # Extract key terms from context
            context_terms: list[str] = []
            for key, value in request.context.items():
                if isinstance(value, str):
                    context_terms.extend(value.lower().split())

            if not context_terms:
                return 0.7, [], []  # Default score if no context terms

            # Count mentions of context terms in content
            content_lower = content.lower()
            mentioned_terms = sum(1 for term in context_terms if term in content_lower)

            if context_terms:
                relevance_score = min(1.0, mentioned_terms / len(set(context_terms)))
            else:
                relevance_score = 0.7

            if relevance_score < 0.5:
                warnings.append("Content may not be relevant to the given context")
                suggestions.append("Ensure content addresses the main topics from the context")

            return relevance_score, warnings, suggestions

        except Exception as e:
            logger.error(f"Relevance assessment failed: {e}")
            return 0.5, [], []

    async def _assess_structure(
        self, content: str, request: GenerationRequest
    ) -> tuple[float, list[str], list[str]]:
        """Assess content structure and organization"""
        warnings: list[str] = []
        suggestions: list[str] = []
        try:
            # Check for paragraphs
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            sentences = [s.strip() for s in content.split(".") if s.strip()]

            structure_score = 1.0

            # Paragraph structure
            if len(paragraphs) == 1 and len(content) > 300:
                structure_score *= 0.8
                suggestions.append("Consider breaking content into multiple paragraphs")

            # Sentence variety
            if sentences:
                sentence_lengths = [len(s.split()) for s in sentences]
                if sentence_lengths:
                    length_variance = max(sentence_lengths) - min(sentence_lengths)
                    if length_variance < 3:
                        structure_score *= 0.9
                        suggestions.append("Vary sentence length for better flow")

            # Check for lists or bullet points if content type suggests it
            if request.content_type in [ContentType.INSTRUCTION, ContentType.ANALYSIS]:
                if "-" not in content and "*" not in content and "1." not in content:
                    suggestions.append("Consider using bullet points or numbered lists for clarity")

            return structure_score, warnings, suggestions

        except Exception as e:
            logger.error(f"Structure assessment failed: {e}")
            return 0.5, [], []

    async def _assess_accuracy(
        self, content: str, request: GenerationRequest
    ) -> tuple[float, list[str], list[str]]:
        """Assess content accuracy (basic checks)"""
        warnings: list[str] = []
        suggestions: list[str] = []
        try:
            # Basic accuracy checks
            accuracy_score = 1.0

            # Check for contradictions (simple pattern matching)
            contradiction_patterns = [
                (r"\b(not|never|no)\b.*\b(always|definitely|certainly)\b", 0.1),
                (r"\b(impossible|cannot)\b.*\b(possible|can)\b", 0.1),
                (r"\b(true|correct)\b.*\b(false|incorrect|wrong)\b", 0.1),
            ]

            for pattern, penalty in contradiction_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    accuracy_score -= penalty
                    warnings.append("Potential contradiction detected in content")

            # Check for unsupported claims (words that indicate certainty without evidence)
            certainty_words = [
                "definitely",
                "certainly",
                "absolutely",
                "guaranteed",
                "proven",
            ]
            certainty_count = sum(1 for word in certainty_words if word in content.lower())

            if certainty_count > 2:
                accuracy_score *= 0.9
                suggestions.append("Consider qualifying strong statements with evidence")

            return max(0.0, accuracy_score), warnings, suggestions

        except Exception as e:
            logger.error(f"Accuracy assessment failed: {e}")
            return 0.5, [], []


class ContentGenerationEngine:
    """Core content generation engine with multiple strategies"""

    def __init__(self) -> None:
        self.templates: dict[str, ContentTemplate] = {}
        self.generation_strategies: dict[
            GenerationStrategy, Callable[[GenerationRequest], Awaitable[str]]
        ] = {
            GenerationStrategy.TEMPLATE_BASED: self._generate_template_based,
            GenerationStrategy.KNOWLEDGE_BASED: self._generate_knowledge_based,
            GenerationStrategy.CONTEXT_AWARE: self._generate_context_aware,
            GenerationStrategy.STRUCTURED: self._generate_structured,
            GenerationStrategy.CONVERSATIONAL: self._generate_conversational,
        }
        self._load_default_templates()

    async def generate_content(self, request: GenerationRequest) -> str:
        """Generate content using specified strategy"""
        try:
            if request.strategy in self.generation_strategies:
                generation_func = self.generation_strategies[request.strategy]
                content = await generation_func(request)
            else:
                # Fallback to context-aware generation
                content = await self._generate_context_aware(request)

            # Ensure ASCII compliance
            ascii_content = content.encode("ascii", errors="ignore").decode("ascii")

            # Trim to max length if needed
            if len(ascii_content) > request.max_length:
                ascii_content = ascii_content[: request.max_length - 3] + "..."

            return ascii_content

        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            return f"Content generation error: {str(e)}"

    async def _generate_template_based(self, request: GenerationRequest) -> str:
        """Generate content using templates"""
        try:
            template_name = request.template_name
            if not template_name:
                # Select default template based on content type
                template_name = f"default_{request.content_type.value}"

            if template_name in self.templates:
                template = self.templates[template_name]
                content = template.render(request.variables)
            else:
                # Create basic template on the fly
                content = self._create_basic_template(request)

            return content

        except Exception as e:
            logger.error(f"Template-based generation failed: {e}")
            return self._generate_fallback_content(request)

    async def _generate_knowledge_based(self, request: GenerationRequest) -> str:
        """Generate content using knowledge base"""
        try:
            # Search knowledge base for relevant information
            search_query = request.context.get("topic", "general information")

            knowledge_results = await knowledge_manager.search_knowledge(
                query=search_query, limit=5, similarity_threshold=0.6
            )

            if knowledge_results:
                # Synthesize content from knowledge results
                content_parts: list[str] = []
                for result in knowledge_results[:3]:  # Use top 3 results
                    content_parts.append(result.entry.content[:200])  # First 200 chars

                content = self._synthesize_knowledge_content(content_parts, request)
            else:
                content = self._generate_fallback_content(request)

            return content

        except Exception as e:
            logger.error(f"Knowledge-based generation failed: {e}")
            return self._generate_fallback_content(request)

    async def _generate_context_aware(self, request: GenerationRequest) -> str:
        """Generate content with context awareness"""
        try:
            context = request.context
            content_type = request.content_type

            # Build content based on context and type
            if content_type == ContentType.TEXT_RESPONSE:
                content = self._generate_text_response(context, request)
            elif content_type == ContentType.DOCUMENTATION:
                content = self._generate_documentation(context, request)
            elif content_type == ContentType.EXPLANATION:
                content = self._generate_explanation(context, request)
            elif content_type == ContentType.SUMMARY:
                content = self._generate_summary(context, request)
            elif content_type == ContentType.ANALYSIS:
                content = self._generate_analysis(context, request)
            elif content_type == ContentType.RECOMMENDATION:
                content = self._generate_recommendation(context, request)
            else:
                content = self._generate_generic_content(context, request)

            return content

        except Exception as e:
            logger.error(f"Context-aware generation failed: {e}")
            return self._generate_fallback_content(request)

    async def _generate_structured(self, request: GenerationRequest) -> str:
        """Generate structured content with clear organization"""
        try:
            context = request.context
            content_parts: list[str] = []
            # Introduction
            intro = context.get(
                "introduction",
                f"This document covers {context.get('topic', 'the requested topic')}.",
            )
            content_parts.append(f"Introduction:\n{intro}\n")

            # Main content sections
            sections = context.get("sections", ["Overview", "Details", "Conclusion"])
            for i, section in enumerate(sections, 1):
                section_content = context.get(f"section_{i}", f"Content for {section}.")
                content_parts.append(f"{i}. {section}:\n{section_content}\n")

            # Conclusion
            conclusion = context.get("conclusion", "This concludes the information provided.")
            content_parts.append(f"Conclusion:\n{conclusion}")

            content = "\n".join(content_parts)
            return content

        except Exception as e:
            logger.error(f"Structured generation failed: {e}")
            return self._generate_fallback_content(request)

    async def _generate_conversational(self, request: GenerationRequest) -> str:
        """Generate conversational content"""
        try:
            context = request.context
            user_input = context.get("user_input", "")
            conversation_history: list[str] = cast(list[str], context.get("history", []))

            # Generate conversational response
            if user_input:
                content = self._generate_conversational_response(
                    user_input, conversation_history, request
                )
            else:
                content = "I'd be happy to help! What would you like to know?"

            return content

        except Exception as e:
            logger.error(f"Conversational generation failed: {e}")
            return "I apologize, but I'm having trouble generating a response right now."

    def _generate_text_response(self, context: dict[str, Any], request: GenerationRequest) -> str:  # TODO(TYPE): replace Any with concrete type
        """Generate a text response"""
        topic = context.get("topic", "the requested topic")
        user_question = context.get("question", "")

        if user_question:
            return f"Regarding your question about {topic}: {user_question}\n\nHere is the information you requested. {topic} is an important subject that requires careful consideration. Based on the available information, I can provide you with relevant details and insights."
        else:
            return f"Here is information about {topic}. This topic covers various aspects that are important to understand. The key points include relevant details and practical applications."

    def _generate_documentation(self, context: dict[str, Any], request: GenerationRequest) -> str:  # TODO(TYPE): replace Any with concrete type
        """Generate documentation content"""
        title = context.get("title", "Documentation")
        description = context.get("description", "System documentation")

        return f"# {title}\n\n## Overview\n{description}\n\n## Features\n- Feature 1: Core functionality\n- Feature 2: Advanced capabilities\n- Feature 3: Integration options\n\n## Usage\nThis documentation provides comprehensive information about the system and its capabilities."

    def _generate_explanation(self, context: dict[str, Any], request: GenerationRequest) -> str:  # TODO(TYPE): replace Any with concrete type
        """Generate explanation content"""
        concept = context.get("concept", "the concept")
        level = context.get("level", "basic")

        if level == "advanced":
            return f"Advanced Explanation of {concept}:\n\nThis concept involves complex interactions and sophisticated mechanisms. The underlying principles demonstrate intricate relationships between various components and subsystems."
        else:
            return f"Explanation of {concept}:\n\n{concept} is a fundamental concept that can be understood through its basic principles. The key aspects include essential elements and practical applications."

    def _generate_summary(self, context: dict[str, Any], request: GenerationRequest) -> str:  # TODO(TYPE): replace Any with concrete type
        """Generate summary content"""
        source = context.get("source", "the provided information")
        key_points = context.get("key_points", ["Point 1", "Point 2", "Point 3"])

        summary = f"Summary of {source}:\n\n"
        for i, point in enumerate(key_points, 1):
            summary += f"{i}. {point}\n"

        summary += (
            "\nConclusion: This summary captures the essential information and main takeaways."
        )
        return summary

    def _generate_analysis(self, context: dict[str, Any], request: GenerationRequest) -> str:  # TODO(TYPE): replace Any with concrete type
        """Generate analysis content"""
        subject = context.get("subject", "the data")
        metrics = context.get("metrics", {})

        analysis = f"Analysis of {subject}:\n\n"
        analysis += "Key Findings:\n"

        if metrics:
            for metric, value in metrics.items():
                analysis += f"- {metric}: {value}\n"
        else:
            analysis += "- Primary observation: Significant patterns detected\n"
            analysis += "- Secondary observation: Notable trends identified\n"
            analysis += "- Tertiary observation: Important correlations found\n"

        analysis += "\nConclusion: The analysis reveals important insights for decision-making."
        return analysis

    def _generate_recommendation(self, context: dict[str, Any], request: GenerationRequest) -> str:  # TODO(TYPE): replace Any with concrete type
        """Generate recommendation content"""
        situation = context.get("situation", "the current situation")
        goals = context.get("goals", ["Improve efficiency", "Reduce costs", "Enhance quality"])

        recommendation = f"Recommendations for {situation}:\n\n"

        for i, goal in enumerate(goals, 1):
            recommendation += f"{i}. To achieve {goal}:\n"
            recommendation += "   - Implement targeted improvements\n"
            recommendation += "   - Monitor progress regularly\n"
            recommendation += "   - Adjust strategies as needed\n\n"

        recommendation += (
            "These recommendations provide a structured approach to achieving your objectives."
        )
        return recommendation

    def _generate_generic_content(self, context: dict[str, Any], request: GenerationRequest) -> str:  # TODO(TYPE): replace Any with concrete type
        """Generate generic content"""
        topic = context.get("topic", "the requested information")
        return f"Information about {topic}:\n\nThis content provides relevant details and insights related to your request. The information is structured to be informative and useful for your specific needs."

    def _generate_conversational_response(
        self, user_input: str, history: list[str], request: GenerationRequest
    ) -> str:
        """Generate conversational response"""
        # Simple conversational response generation
        if "hello" in user_input.lower() or "hi" in user_input.lower():
            return "Hello! How can I help you today?"
        elif "thank" in user_input.lower():
            return "You're welcome! Is there anything else I can help you with?"
        elif "?" in user_input:
            return f"That's a great question about {user_input[:50]}... Let me provide you with some information on that topic."
        else:
            return f"I understand you're interested in {user_input[:50]}... Here's what I can tell you about that."

    def _synthesize_knowledge_content(
        self, content_parts: list[str], request: GenerationRequest
    ) -> str:
        """Synthesize content from knowledge base results"""
        if not content_parts:
            return self._generate_fallback_content(request)

        synthesis = "Based on the available knowledge:\n\n"

        for i, part in enumerate(content_parts, 1):
            synthesis += f"{i}. {part.strip()}\n\n"

        synthesis += "This information provides a comprehensive overview of the topic."
        return synthesis

    def _create_basic_template(self, request: GenerationRequest) -> str:
        """Create basic template for content type"""
        content_type = request.content_type
        context = request.context

        basic_templates = {
            ContentType.TEXT_RESPONSE: "Response: {response_text}",
            ContentType.DOCUMENTATION: "# {title}\n\n{content}",
            ContentType.EXPLANATION: "Explanation of {topic}:\n\n{explanation}",
            ContentType.SUMMARY: "Summary:\n\n{summary_content}",
            ContentType.ANALYSIS: "Analysis Results:\n\n{analysis_results}",
            ContentType.RECOMMENDATION: "Recommendations:\n\n{recommendations}",
        }

        template_text = basic_templates.get(content_type, "{content}")

        # Fill template with context variables
        filled_template = template_text
        for key, value in context.items():
            placeholder = "{{{key}}}"
            if placeholder in filled_template:
                filled_template = filled_template.replace(placeholder, str(value))

        return filled_template

    def _generate_fallback_content(self, request: GenerationRequest) -> str:
        """Generate fallback content when other methods fail"""
        return f"Content for {request.content_type.value} request. This is a basic response that addresses your request for information."

    def _load_default_templates(self) -> None:
        """Load default content templates"""
        try:
            # Default templates for various content types
            templates = {
                "default_text_response": ContentTemplate(
                    "default_text_response",
                    ContentType.TEXT_RESPONSE,
                    "Here is the information you requested about {topic}. {content}",
                ),
                "default_documentation": ContentTemplate(
                    "default_documentation",
                    ContentType.DOCUMENTATION,
                    "# {title}\n\n## Overview\n{overview}\n\n## Details\n{details}",
                ),
                "default_summary": ContentTemplate(
                    "default_summary",
                    ContentType.SUMMARY,
                    "Summary of {source}:\n\n{key_points}\n\nConclusion: {conclusion}",
                ),
            }

            self.templates.update(templates)
            logger.debug(f"Loaded {len(templates)} default templates")

        except Exception as e:
            logger.warning(f"Failed to load default templates: {e}")


class ContentGenerator:
    """
    Main content generator that coordinates all generation activities
    """

    def __init__(self) -> None:
        self.generation_engine = ContentGenerationEngine()
        self.quality_assessor = ContentQualityAssessor()
        self.generation_history: list[GenerationResult] = []
        self._initialized = False
        self._stats: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "content_generated": 0,
            "average_quality_score": 0.0,
            "average_generation_time": 0.0,
            "content_types_used": {},
        }

    async def initialize(self) -> bool:
        """Initialize content generator"""
        try:
            self._initialized = True
            logger.info("Content Generator initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize content generator: {e}")
            return False

    async def generate_content(self, request: GenerationRequest) -> GenerationResult:
        """Generate content based on request"""
        if not self._initialized:
            await self.initialize()

        start_time = time.time()

        try:
            # Generate content
            content = await self.generation_engine.generate_content(request)

            # Assess quality
            (
                quality_score,
                warnings,
                suggestions,
            ) = await self.quality_assessor.assess_quality(content, request)

            generation_time = time.time() - start_time

            # Create result
            result = GenerationResult(
                request_id=request.request_id,
                content=content,
                content_type=request.content_type,
                quality_score=quality_score,
                generation_time=generation_time,
                strategy_used=request.strategy,
                warnings=warnings,
                suggestions=suggestions,
                metadata={
                    "request_strategy": request.strategy.value,
                    "quality_level": request.quality_level.value,
                    "content_length": len(content),
                    "template_used": request.template_name,
                },
            )

            # Store result
            self.generation_history.append(result)
            self._update_stats(result)

            logger.info(f"Content generated: {request.request_id}, quality: {quality_score:.2f}")
            return result

        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            return GenerationResult(
                request_id=request.request_id,
                content=f"Generation failed: {str(e)}",
                content_type=request.content_type,
                quality_score=0.0,
                generation_time=time.time() - start_time,
                strategy_used=request.strategy,
                warnings=[f"Generation error: {str(e)}"],
                metadata={"error": True},
            )

    @cached(ttl=300, key_prefix="generation_stats")
    async def get_generation_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get content generation statistics"""
        try:
            if not self.generation_history:
                return {
                    "content_generated": 0,
                    "average_quality_score": 0.0,
                    "average_generation_time": 0.0,
                }

            quality_scores = [r.quality_score for r in self.generation_history]
            generation_times = [r.generation_time for r in self.generation_history]

            content_types: dict[str, int] = {}
            for result in self.generation_history:
                content_type = result.content_type.value
                content_types[content_type] = content_types.get(content_type, 0) + 1

            return {
                "content_generated": len(self.generation_history),
                "average_quality_score": sum(quality_scores) / len(quality_scores),
                "average_generation_time": sum(generation_times) / len(generation_times),
                "content_types_distribution": content_types,
                "high_quality_content_percentage": len([s for s in quality_scores if s > 0.8])
                / len(quality_scores)
                * 100,
                "recent_generation_count_24h": len(
                    [
                        r
                        for r in self.generation_history
                        if r.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)
                    ]
                ),
            }

        except Exception as e:
            logger.error(f"Failed to get generation stats: {e}")
            return {}

    def _update_stats(self, result: GenerationResult) -> None:
        """Update generation statistics"""
        self._stats["content_generated"] += 1

        # Update average quality score
        current_avg_quality = self._stats["average_quality_score"]
        count = self._stats["content_generated"]
        self._stats["average_quality_score"] = (
            (current_avg_quality * (count - 1)) + result.quality_score
        ) / count

        # Update average generation time
        current_avg_time = self._stats["average_generation_time"]
        self._stats["average_generation_time"] = (
            (current_avg_time * (count - 1)) + result.generation_time
        ) / count

        # Update content types used
        content_type = result.content_type.value
        self._stats["content_types_used"][content_type] = (
            self._stats["content_types_used"].get(content_type, 0) + 1
        )


# Factory function
async def create_content_generator() -> ContentGenerator:
    """Create and initialize content generator"""
    generator = ContentGenerator()
    await generator.initialize()
    return generator


# Global generator instance
_global_generator: ContentGenerator | None = None


async def get_content_generator() -> ContentGenerator:
    """Get global content generator instance"""
    global _global_generator

    if _global_generator is None:
        _global_generator = await create_content_generator()

    return _global_generator
