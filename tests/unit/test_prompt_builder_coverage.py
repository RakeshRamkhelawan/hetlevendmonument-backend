"""
Comprehensive tests for src/core/generation/prompt_builder.py
Coverage target: 100% of prompt builder system
"""

from dataclasses import dataclass
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.core.generation.prompt_builder import (
    PromptBuilder,
    PromptBuildResult,
    PromptContext,
    PromptStrategy,
    PromptTemplate,
    PromptVariable,
    create_prompt_builder,
)


class TestPromptStrategyEnum:
    """Test PromptStrategy enum"""

    def test_all_strategies_exist(self):
        """Test all strategy types are defined"""
        assert PromptStrategy.SIMPLE.value == "simple"
        assert PromptStrategy.DETAILED.value == "detailed"
        assert PromptStrategy.CONVERSATIONAL.value == "conversational"
        assert PromptStrategy.INSTRUCTIONAL.value == "instructional"
        assert PromptStrategy.ANALYTICAL.value == "analytical"
        assert PromptStrategy.CREATIVE.value == "creative"
        assert PromptStrategy.TECHNICAL.value == "technical"
        assert PromptStrategy.CONTEXTUAL.value == "contextual"


class TestPromptVariable:
    """Test PromptVariable dataclass"""

    def test_variable_creation_with_all_fields(self):
        """Test creating variable with all fields"""
        var = PromptVariable(
            name="test_var",
            description="Test variable",
            required=True,
            default_value="default",
            validation_pattern=r"^\w+$",
            transformation_func=str.upper,
        )

        assert var.name == "test_var"
        assert var.description == "Test variable"
        assert var.required is True
        assert var.default_value == "default"
        assert var.validation_pattern == r"^\w+$"
        assert var.transformation_func == str.upper

    def test_variable_defaults(self):
        """Test variable default values"""
        var = PromptVariable(name="test", description="Test")

        assert var.required is True
        assert var.default_value is None
        assert var.validation_pattern is None
        assert var.transformation_func is None


class TestPromptTemplate:
    """Test PromptTemplate dataclass"""

    def test_template_creation(self):
        """Test creating prompt template"""
        template = PromptTemplate(
            name="test_template",
            template="Hello {name}!",
            variables=[PromptVariable("name", "User name")],
            strategy=PromptStrategy.SIMPLE,
        )

        assert template.name == "test_template"
        assert template.template == "Hello {name}!"
        assert len(template.variables) == 1
        assert template.strategy == PromptStrategy.SIMPLE

    def test_template_defaults(self):
        """Test template default values"""
        template = PromptTemplate(name="test", template="Test")

        assert template.variables == []
        assert template.strategy == PromptStrategy.SIMPLE
        assert template.metadata == {}
        assert template.examples == []


class TestPromptContext:
    """Test PromptContext dataclass"""

    def test_context_creation(self):
        """Test creating prompt context"""
        context = PromptContext(
            user_intent="test intent",
            domain="test domain",
            complexity_level="high",
            tone="formal",
            audience="experts",
            constraints=["constraint1", "constraint2"],
            preferences={"key": "value"},
        )

        assert context.user_intent == "test intent"
        assert context.domain == "test domain"
        assert context.complexity_level == "high"
        assert context.tone == "formal"
        assert context.audience == "experts"
        assert len(context.constraints) == 2
        assert context.preferences == {"key": "value"}

    def test_context_defaults(self):
        """Test context default values"""
        context = PromptContext(user_intent="test", domain="test")

        assert context.complexity_level == "medium"
        assert context.tone == "neutral"
        assert context.audience == "general"
        assert context.constraints == []
        assert context.preferences == {}


class TestPromptBuilder:
    """Test PromptBuilder class"""

    def test_initialization(self):
        """Test PromptBuilder initialization"""
        builder = PromptBuilder()

        assert builder.cache_layer is None
        assert len(builder.templates) > 0
        assert len(builder.strategy_handlers) == 8
        assert len(builder.optimization_rules) == 3
        assert builder.stats["prompts_built"] == 0

    def test_initialization_with_cache(self):
        """Test PromptBuilder initialization with cache"""
        cache = Mock()
        builder = PromptBuilder(cache_layer=cache)

        assert builder.cache_layer == cache

    def test_default_templates_loaded(self):
        """Test default templates are loaded"""
        builder = PromptBuilder()

        assert "simple_question" in builder.templates
        assert "detailed_analysis" in builder.templates
        assert "conversation" in builder.templates
        assert "technical_instruction" in builder.templates
        assert "creative_generation" in builder.templates
        assert "contextual_assistance" in builder.templates


class TestBuildPrompt:
    """Test build_prompt method"""

    def test_build_simple_prompt_success(self):
        """Test building simple prompt successfully"""
        builder = PromptBuilder()

        result = builder.build_prompt(
            template_name="simple_question", variables={"question": "What is Python?"}
        )

        assert isinstance(result, PromptBuildResult)
        assert "What is Python?" in result.prompt
        assert result.template_used == "simple_question"
        assert result.quality_score > 0

    def test_build_with_cache_miss(self):
        """Test building prompt with cache miss"""
        cache = Mock()
        cache.get.return_value = None
        builder = PromptBuilder(cache_layer=cache)

        result = builder.build_prompt(
            template_name="simple_question", variables={"question": "Test?"}
        )

        cache.get.assert_called_once()
        cache.set.assert_called_once()
        assert builder.stats["cache_misses"] == 1

    def test_build_with_cache_hit(self):
        """Test building prompt with cache hit"""
        cached_result = PromptBuildResult(
            prompt="Cached prompt",
            template_used="simple_question",
            variables_used={},
            strategy=PromptStrategy.SIMPLE,
            context=PromptContext("", ""),
            quality_score=85.0,
        )

        cache = Mock()
        cache.get.return_value = cached_result
        builder = PromptBuilder(cache_layer=cache)

        result = builder.build_prompt(
            template_name="simple_question", variables={"question": "Test?"}
        )

        assert result == cached_result
        assert builder.stats["cache_hits"] == 1

    def test_build_with_invalid_template(self):
        """Test building with non-existent template"""
        builder = PromptBuilder()

        result = builder.build_prompt(template_name="nonexistent", variables={})

        assert "Error building prompt" in result.prompt
        assert result.quality_score == 0.0
        assert len(result.warnings) > 0

    def test_build_with_missing_required_variable(self):
        """Test building with missing required variable"""
        builder = PromptBuilder()

        result = builder.build_prompt(template_name="simple_question", variables={})

        assert "Error building prompt" in result.prompt
        assert "Required variable 'question' not provided" in result.prompt

    def test_build_with_strategy_override(self):
        """Test building with strategy override"""
        builder = PromptBuilder()

        result = builder.build_prompt(
            template_name="simple_question",
            variables={"question": "Test?"},
            strategy=PromptStrategy.ANALYTICAL,
        )

        assert result.strategy == PromptStrategy.ANALYTICAL

    def test_build_with_context(self):
        """Test building prompt with context"""
        builder = PromptBuilder()
        context = PromptContext(user_intent="learn", domain="programming", complexity_level="high")

        result = builder.build_prompt(
            template_name="simple_question",
            variables={"question": "Test?"},
            context=context,
        )

        assert result.context == context

    def test_build_updates_stats(self):
        """Test building prompt updates statistics"""
        builder = PromptBuilder()

        builder.build_prompt(template_name="simple_question", variables={"question": "Test?"})

        assert builder.stats["prompts_built"] == 1
        assert "simple_question" in builder.stats["template_uses"]
        assert builder.stats["template_uses"]["simple_question"] == 1


class TestVariableProcessing:
    """Test _process_variables method"""

    def test_process_with_provided_values(self):
        """Test processing variables with provided values"""
        builder = PromptBuilder()
        template = PromptTemplate(
            name="test",
            template="{var1} {var2}",
            variables=[
                PromptVariable("var1", "Test var 1"),
                PromptVariable("var2", "Test var 2"),
            ],
        )

        processed = builder._process_variables(template, {"var1": "value1", "var2": "value2"})

        assert processed["var1"] == "value1"
        assert processed["var2"] == "value2"

    def test_process_with_default_values(self):
        """Test processing variables with defaults"""
        builder = PromptBuilder()
        template = PromptTemplate(
            name="test",
            template="{var1}",
            variables=[PromptVariable("var1", "Test", required=False, default_value="default")],
        )

        processed = builder._process_variables(template, {})

        assert processed["var1"] == "default"

    def test_process_with_validation_pattern_success(self):
        """Test variable validation pattern success"""
        builder = PromptBuilder()
        template = PromptTemplate(
            name="test",
            template="{var}",
            variables=[PromptVariable("var", "Test", validation_pattern=r"^\d+$")],
        )

        processed = builder._process_variables(template, {"var": "123"})

        assert processed["var"] == "123"

    def test_process_with_validation_pattern_failure(self):
        """Test variable validation pattern failure"""
        builder = PromptBuilder()
        template = PromptTemplate(
            name="test",
            template="{var}",
            variables=[PromptVariable("var", "Test", validation_pattern=r"^\d+$")],
        )

        with pytest.raises(ValueError, match="does not match validation pattern"):
            builder._process_variables(template, {"var": "abc"})

    def test_process_with_transformation_function(self):
        """Test variable transformation function"""
        builder = PromptBuilder()
        template = PromptTemplate(
            name="test",
            template="{var}",
            variables=[PromptVariable("var", "Test", transformation_func=str.upper)],
        )

        processed = builder._process_variables(template, {"var": "hello"})

        assert processed["var"] == "HELLO"

    def test_process_with_transformation_error(self):
        """Test variable transformation error handling"""
        builder = PromptBuilder()

        def failing_transform(value):
            raise Exception("Transform failed")

        template = PromptTemplate(
            name="test",
            template="{var}",
            variables=[PromptVariable("var", "Test", transformation_func=failing_transform)],
        )

        processed = builder._process_variables(template, {"var": "value"})

        # Should keep original value on transformation failure
        assert processed["var"] == "value"


class TestStrategyHandlers:
    """Test strategy-specific handlers"""

    def test_simple_strategy(self):
        """Test simple strategy handler"""
        builder = PromptBuilder()
        context = PromptContext("test", "test")

        result = builder._handle_simple_strategy("Test prompt", context)

        assert result == "Test prompt"

    def test_detailed_strategy_with_context(self):
        """Test detailed strategy with context"""
        builder = PromptBuilder()
        context = PromptContext(
            user_intent="test",
            domain="programming",
            complexity_level="high",
            constraints=["constraint1"],
        )

        result = builder._handle_detailed_strategy("Test prompt", context)

        assert "Domain: programming" in result
        assert "Complexity Level: high" in result
        assert "Constraints: constraint1" in result
        assert "Test prompt" in result

    def test_conversational_strategy(self):
        """Test conversational strategy"""
        builder = PromptBuilder()
        context = PromptContext("test", "test")

        result = builder._handle_conversational_strategy("Test prompt", context)

        assert "I'd be happy to help" in result
        assert "Test prompt" in result
        assert context.tone == "friendly"

    def test_instructional_strategy(self):
        """Test instructional strategy"""
        builder = PromptBuilder()
        context = PromptContext("test", "test")

        result = builder._handle_instructional_strategy("Test prompt", context)

        assert "follow these instructions" in result
        assert "Test prompt" in result

    def test_analytical_strategy(self):
        """Test analytical strategy"""
        builder = PromptBuilder()
        context = PromptContext("test", "test")

        result = builder._handle_analytical_strategy("Test prompt", context)

        assert "Key observations" in result
        assert "Test prompt" in result

    def test_creative_strategy(self):
        """Test creative strategy"""
        builder = PromptBuilder()
        context = PromptContext("test", "test")

        result = builder._handle_creative_strategy("Test prompt", context)

        assert "creative" in result.lower()
        assert "Test prompt" in result

    def test_technical_strategy(self):
        """Test technical strategy"""
        builder = PromptBuilder()
        context = PromptContext("test", "test")

        result = builder._handle_technical_strategy("Test prompt", context)

        assert "technically accurate" in result
        assert "Test prompt" in result

    def test_contextual_strategy_with_audience(self):
        """Test contextual strategy with audience"""
        builder = PromptBuilder()
        context = PromptContext("test", "test", audience="experts")

        result = builder._handle_contextual_strategy("Test prompt", context)

        assert "experts" in result
        assert "Test prompt" in result

    def test_contextual_strategy_without_audience(self):
        """Test contextual strategy without audience"""
        builder = PromptBuilder()
        context = PromptContext("test", "test", audience="")

        result = builder._handle_contextual_strategy("Test prompt", context)

        assert result == "Test prompt"


class TestOptimization:
    """Test prompt optimization"""

    def test_optimize_removes_redundancy(self):
        """Test optimization removes redundant phrases"""
        builder = PromptBuilder()

        optimized, suggestions = builder._optimize_prompt("Please please help")

        # Should remove redundant 'please'
        assert "please please" not in optimized.lower()

    def test_optimize_structure(self):
        """Test optimization improves structure"""
        builder = PromptBuilder()

        optimized, suggestions = builder._optimize_prompt("Test.No space")

        # Should add space after period
        assert ". N" in optimized or ".N" not in optimized

    def test_optimize_length_too_long(self):
        """Test optimization suggests shortening long prompts"""
        builder = PromptBuilder()
        long_prompt = "Test " * 500

        _, suggestions = builder._optimize_prompt(long_prompt)

        assert any("shortening" in s for s in suggestions)

    def test_optimize_length_too_short(self):
        """Test optimization suggests adding context for short prompts"""
        builder = PromptBuilder()

        _, suggestions = builder._optimize_prompt("Test")

        assert any("adding more context" in s for s in suggestions)


class TestQualityScore:
    """Test quality score calculation"""

    def test_quality_score_good_length(self):
        """Test quality score for good length prompt"""
        builder = PromptBuilder()
        template = PromptTemplate("test", "{var}", variables=[PromptVariable("var", "test")])
        prompt = "This is a well-formed prompt with good length. " * 5

        score = builder._calculate_quality_score(prompt, template, None)

        assert score > 0

    def test_quality_score_with_structure(self):
        """Test quality score considers structure"""
        builder = PromptBuilder()
        template = PromptTemplate("test", "{var}", variables=[PromptVariable("var", "test")])
        prompt = """
        Well-structured prompt:
        1. First point
        2. Second point
        - Bullet one
        - Bullet two
        """

        score = builder._calculate_quality_score(prompt, template, None)

        assert score > 20  # Should score for structure

    def test_quality_score_with_context_relevance(self):
        """Test quality score considers context relevance"""
        builder = PromptBuilder()
        template = PromptTemplate("test", "{var}", variables=[PromptVariable("var", "test")])
        context = PromptContext("learn programming", "programming")
        prompt = "Learn programming basics with practical examples."

        score = builder._calculate_quality_score(prompt, template, context)

        assert score > 0


class TestTemplateManagement:
    """Test template management methods"""

    def test_add_template(self):
        """Test adding custom template"""
        builder = PromptBuilder()
        template = PromptTemplate(name="custom_template", template="Custom: {text}")

        builder.add_template(template)

        assert "custom_template" in builder.templates
        assert builder.templates["custom_template"] == template

    def test_remove_template(self):
        """Test removing template"""
        builder = PromptBuilder()

        builder.remove_template("simple_question")

        assert "simple_question" not in builder.templates

    def test_get_available_templates(self):
        """Test getting available templates"""
        builder = PromptBuilder()

        templates = builder.get_available_templates()

        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_get_template_existing(self):
        """Test getting existing template"""
        builder = PromptBuilder()

        template = builder.get_template("simple_question")

        assert template is not None
        assert template.name == "simple_question"

    def test_get_template_nonexistent(self):
        """Test getting non-existent template"""
        builder = PromptBuilder()

        template = builder.get_template("nonexistent")

        assert template is None


class TestStatistics:
    """Test statistics tracking"""

    def test_get_stats(self):
        """Test getting statistics"""
        builder = PromptBuilder()

        stats = builder.get_stats()

        assert "prompts_built" in stats
        assert "cache_hits" in stats
        assert "cache_misses" in stats
        assert "template_uses" in stats
        assert "strategy_uses" in stats
        assert "average_quality_score" in stats

    def test_reset_stats(self):
        """Test resetting statistics"""
        builder = PromptBuilder()

        # Build some prompts
        builder.build_prompt("simple_question", {"question": "Test?"})

        # Reset
        builder.reset_stats()

        assert builder.stats["prompts_built"] == 0
        assert builder.stats["cache_hits"] == 0
        assert builder.stats["template_uses"] == {}
        assert builder.stats["average_quality_score"] == 0.0


class TestFactoryFunction:
    """Test create_prompt_builder factory"""

    def test_create_without_cache(self):
        """Test creating builder without cache"""
        builder = create_prompt_builder()

        assert isinstance(builder, PromptBuilder)
        assert builder.cache_layer is None

    def test_create_with_cache(self):
        """Test creating builder with cache"""
        cache = Mock()
        builder = create_prompt_builder(cache_layer=cache)

        assert isinstance(builder, PromptBuilder)
        assert builder.cache_layer == cache
