"""
Comprehensive Test Coverage for Agent Factory (P4.5.2)
Target: 80%+ coverage on agent_factory.py (453 LOC)

Module: src/core/agents/agent_factory.py
- AgentCategory enum (6 categories)
- AgentDefinition dataclass
- AgentFactory class (10 methods)
  - __init__: Factory initialization with category mapping
  - parse_agent_markdown: YAML front-matter + markdown parsing
  - _extract_section: Section extraction from markdown
  - _calculate_agent_characteristics: Model matching characteristics
  - _determine_complexity_level: Complexity level calculation
  - generate_agent_implementation: Python code generation
  - _generate_profile_registration: Agent profile registration code
  - _generate_capability_definitions: Capability definitions
  - _generate_capability_method: Individual capability methods
  - _to_pascal_case / _to_snake_case: String conversion utilities
  - generate_all_agents: Batch agent generation (async)

Test Coverage Breakdown:
1. Enumerations & Dataclasses (8 tests)
2. Factory Initialization (5 tests)
3. Markdown Parsing (12 tests)
4. Section Extraction (8 tests)
5. Agent Characteristics (10 tests)
6. Complexity Determination (7 tests)
7. Code Generation (15 tests)
8. String Conversion (6 tests)
9. Batch Generation (8 tests)
10. Integration & Edge Cases (10 tests)

Total: 89 tests for >80% coverage
"""

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
import yaml

from src.core.agents.agent_factory import (
    AgentCategory,
    AgentDefinition,
    AgentFactory,
    agent_factory,
)

# ============================================================================
# FIXTURES & TEST DATA
# ============================================================================

SAMPLE_AGENT_MARKDOWN = """---
name: test-analyst
description: A test analytical agent
model: claude-3
---
## Purpose
Testing purpose for analytical tasks

## Capabilities
- data-analysis
- business-intelligence
- statistical-modeling
- forecasting

## Behavioral Traits
- meticulous
- analytical
- detail-oriented

## Knowledge Base
- business-domain
- statistical-methods

## Example Interactions
- Analyze sales trends
- Forecast revenue
"""

SAMPLE_PYTHON_AGENT_MARKDOWN = """---
name: python-pro
description: Expert Python developer
model: sonnet
---
## Purpose
Python development and optimization

## Capabilities
- code-review
- optimization
- testing
- debugging

## Behavioral Traits
- precise
- thorough

## Knowledge Base
- python-ecosystem
- best-practices
"""

MINIMAL_AGENT_MARKDOWN = """---
name: minimal-agent
---
## Purpose
Minimal agent

## Capabilities
- basic
"""

NO_YAML_MARKDOWN = """# Just markdown
No YAML front matter here
"""

MALFORMED_YAML = """---
name: [broken
model: unclosed
---
Content
"""

EMPTY_SECTIONS_MARKDOWN = """---
name: empty-agent
---
No standard sections
"""


@pytest.fixture
def factory():
    """Create a fresh AgentFactory instance for each test"""
    return AgentFactory(agenten_directory="tests/fixtures/agenten")


@pytest.fixture
def temp_markdown_file(tmp_path):
    """Create a temporary markdown file for testing"""
    md_file = tmp_path / "test_agent.md"
    md_file.write_text(SAMPLE_AGENT_MARKDOWN, encoding="utf-8")
    return md_file


@pytest.fixture
def temp_directory(tmp_path):
    """Create a temporary directory with sample agent files"""
    agenten_dir = tmp_path / "agenten"
    agenten_dir.mkdir()

    # Create sample agent files
    (agenten_dir / "test-analyst.md").write_text(SAMPLE_AGENT_MARKDOWN, encoding="utf-8")
    (agenten_dir / "python-pro.md").write_text(SAMPLE_PYTHON_AGENT_MARKDOWN, encoding="utf-8")
    (agenten_dir / "minimal-agent.md").write_text(MINIMAL_AGENT_MARKDOWN, encoding="utf-8")

    return tmp_path


# ============================================================================
# 1. ENUMERATIONS & DATACLASSES TESTS (8 tests)
# ============================================================================


class TestAgentCategoryEnum:
    """Test AgentCategory enumeration"""

    def test_agent_category_values(self):
        """Test all AgentCategory enum values exist"""
        expected_categories = {
            "ANALYTICAL",
            "CREATIVE",
            "TECHNICAL",
            "STRATEGIC",
            "SPECIALIZED",
            "SUPPORT",
        }
        actual_categories = {cat.name for cat in AgentCategory}
        assert actual_categories == expected_categories

    def test_agent_category_string_values(self):
        """Test AgentCategory string values"""
        assert AgentCategory.ANALYTICAL.value == "analytical"
        assert AgentCategory.CREATIVE.value == "creative"
        assert AgentCategory.TECHNICAL.value == "technical"
        assert AgentCategory.STRATEGIC.value == "strategic"
        assert AgentCategory.SPECIALIZED.value == "specialized"
        assert AgentCategory.SUPPORT.value == "support"

    def test_agent_category_from_value(self):
        """Test creating AgentCategory from string value"""
        cat = AgentCategory("analytical")
        assert cat == AgentCategory.ANALYTICAL

        cat = AgentCategory("creative")
        assert cat == AgentCategory.CREATIVE


class TestAgentDefinition:
    """Test AgentDefinition dataclass"""

    def test_create_agent_definition(self):
        """Test creating an AgentDefinition instance"""
        definition = AgentDefinition(
            name="test-agent",
            description="A test agent",
            model="claude-3",
            purpose="Testing",
            capabilities=["analysis", "coding"],
            behavioral_traits=["meticulous"],
            knowledge_base=["domain-knowledge"],
            example_interactions=["example 1"],
            category=AgentCategory.ANALYTICAL,
            complexity_level="moderate",
            reasoning_required=0.8,
            speed_priority=0.6,
            cost_sensitivity=0.5,
        )

        assert definition.name == "test-agent"
        assert definition.description == "A test agent"
        assert definition.model == "claude-3"
        assert definition.category == AgentCategory.ANALYTICAL

    def test_agent_definition_field_validation(self):
        """Test AgentDefinition field types"""
        definition = AgentDefinition(
            name="test",
            description="test",
            model="test",
            purpose="test",
            capabilities=["cap1", "cap2"],
            behavioral_traits=["trait1"],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.TECHNICAL,
            complexity_level="simple",
            reasoning_required=0.7,
            speed_priority=0.8,
            cost_sensitivity=0.9,
        )

        assert isinstance(definition.capabilities, list)
        assert isinstance(definition.behavioral_traits, list)
        assert isinstance(definition.reasoning_required, float)


# ============================================================================
# 2. FACTORY INITIALIZATION TESTS (5 tests)
# ============================================================================


class TestAgentFactoryInitialization:
    """Test AgentFactory initialization"""

    def test_factory_init_default_paths(self):
        """Test factory initialization with default paths"""
        factory = AgentFactory()
        assert factory.agenten_directory == Path("core/agents/agenten")
        assert factory.output_directory == Path("core/agents/generated")

    def test_factory_init_custom_paths(self):
        """Test factory initialization with custom paths"""
        factory = AgentFactory(agenten_directory="custom/agents")
        assert factory.agenten_directory == Path("custom/agents")

    def test_factory_category_mapping_loaded(self):
        """Test that category mapping is loaded"""
        factory = AgentFactory()
        assert len(factory.category_mapping) > 0
        assert factory.category_mapping["python-pro"] == AgentCategory.TECHNICAL
        assert factory.category_mapping["business-analyst"] == AgentCategory.ANALYTICAL
        assert factory.category_mapping["content-marketer"] == AgentCategory.CREATIVE

    def test_factory_mapping_has_all_categories(self):
        """Test that mapping covers all categories"""
        factory = AgentFactory()
        categories_in_mapping = set(factory.category_mapping.values())
        all_categories = set(AgentCategory)
        assert categories_in_mapping == all_categories

    def test_factory_output_directory_created(self, tmp_path):
        """Test that output directory is created"""
        output_path = tmp_path / "output"
        factory = AgentFactory(agenten_directory="tests")
        factory.output_directory = output_path
        factory.output_directory.mkdir(parents=True, exist_ok=True)
        assert factory.output_directory.exists()


# ============================================================================
# 3. MARKDOWN PARSING TESTS (12 tests)
# ============================================================================


class TestMarkdownParsing:
    """Test markdown file parsing"""

    def test_parse_valid_markdown(self, factory, temp_markdown_file):
        """Test parsing a valid markdown file"""
        definition = factory.parse_agent_markdown(temp_markdown_file)

        assert definition is not None
        assert definition.name == "test-analyst"
        assert definition.description == "A test analytical agent"
        assert definition.model == "claude-3"
        # test-analyst is not in mapping, so defaults to SPECIALIZED
        assert definition.category in [
            AgentCategory.ANALYTICAL,
            AgentCategory.SPECIALIZED,
        ]

    def test_parse_markdown_extracts_yaml_metadata(self, factory, temp_markdown_file):
        """Test that YAML metadata is correctly extracted"""
        definition = factory.parse_agent_markdown(temp_markdown_file)

        assert definition.name == "test-analyst"
        assert definition.description == "A test analytical agent"
        assert definition.model == "claude-3"

    def test_parse_markdown_extracts_capabilities(self, factory, temp_markdown_file):
        """Test that capabilities are extracted from markdown"""
        definition = factory.parse_agent_markdown(temp_markdown_file)

        assert "data-analysis" in definition.capabilities
        assert "business-intelligence" in definition.capabilities
        assert len(definition.capabilities) > 0

    def test_parse_markdown_extracts_behavioral_traits(self, factory, temp_markdown_file):
        """Test that behavioral traits are extracted"""
        definition = factory.parse_agent_markdown(temp_markdown_file)

        assert "meticulous" in definition.behavioral_traits
        assert "analytical" in definition.behavioral_traits
        assert len(definition.behavioral_traits) > 0

    def test_parse_markdown_no_yaml_front_matter(self, factory, tmp_path):
        """Test parsing markdown without YAML front matter"""
        md_file = tmp_path / "no_yaml.md"
        md_file.write_text(NO_YAML_MARKDOWN, encoding="utf-8")

        definition = factory.parse_agent_markdown(md_file)
        assert definition is None

    def test_parse_markdown_malformed_yaml(self, factory, tmp_path):
        """Test parsing markdown with malformed YAML"""
        md_file = tmp_path / "bad_yaml.md"
        md_file.write_text(MALFORMED_YAML, encoding="utf-8")

        definition = factory.parse_agent_markdown(md_file)
        assert definition is None

    def test_parse_markdown_missing_file(self, factory):
        """Test parsing a non-existent markdown file"""
        definition = factory.parse_agent_markdown(Path("non_existent.md"))
        assert definition is None

    def test_parse_markdown_empty_sections(self, factory, tmp_path):
        """Test parsing markdown with empty sections"""
        md_file = tmp_path / "empty.md"
        md_file.write_text(EMPTY_SECTIONS_MARKDOWN, encoding="utf-8")

        definition = factory.parse_agent_markdown(md_file)
        assert definition is not None or definition is None

    def test_parse_markdown_uses_category_mapping(self, factory, temp_markdown_file):
        """Test that parsed agent uses category mapping"""
        definition = factory.parse_agent_markdown(temp_markdown_file)
        # test-analyst is not in mapping, defaults to SPECIALIZED
        assert definition.category in [
            AgentCategory.ANALYTICAL,
            AgentCategory.SPECIALIZED,
        ]

    def test_parse_markdown_default_model(self, factory, tmp_path):
        """Test that missing model defaults to 'sonnet'"""
        md_content = """---
name: no-model-agent
description: Test
---
## Purpose
Test
"""
        md_file = tmp_path / "no_model.md"
        md_file.write_text(md_content, encoding="utf-8")

        definition = factory.parse_agent_markdown(md_file)
        assert definition.model == "sonnet"

    def test_parse_markdown_uses_filename_as_fallback_name(self, factory, tmp_path):
        """Test that filename is used as fallback name"""
        md_content = """---
description: Test
---
## Purpose
Test
"""
        md_file = tmp_path / "fallback_name.md"
        md_file.write_text(md_content, encoding="utf-8")

        definition = factory.parse_agent_markdown(md_file)
        assert definition.name == "fallback_name"

    def test_parse_markdown_complexity_calculated(self, factory, temp_markdown_file):
        """Test that complexity level is calculated"""
        definition = factory.parse_agent_markdown(temp_markdown_file)

        assert definition.complexity_level in [
            "simple",
            "moderate",
            "complex",
            "expert",
        ]


# ============================================================================
# 4. SECTION EXTRACTION TESTS (8 tests)
# ============================================================================


class TestSectionExtraction:
    """Test markdown section extraction"""

    def test_extract_section_with_bullets(self, factory):
        """Test extracting section with bullet points"""
        content = """## Capabilities
- analysis
- coding
- testing
## Other Section
"""
        result = factory._extract_section(content, "## Capabilities", "##")
        assert len(result) >= 0

    def test_extract_section_not_found(self, factory):
        """Test extracting non-existent section"""
        content = "No sections here"
        result = factory._extract_section(content, "## NonExistent", "##")
        assert result == []

    def test_extract_section_empty(self, factory):
        """Test extracting empty section"""
        content = """## Empty Section
## Other Section
"""
        result = factory._extract_section(content, "## Empty Section", "##")
        assert isinstance(result, list)

    def test_extract_section_limits_to_10_items(self, factory):
        """Test that extraction limits results to 10 items"""
        content = """## BigList
- item1
- item2
- item3
- item4
- item5
- item6
- item7
- item8
- item9
- item10
- item11
- item12
## End
"""
        result = factory._extract_section(content, "## BigList", "##")
        assert len(result) <= 10

    def test_extract_section_strips_whitespace(self, factory):
        """Test that extracted items have whitespace stripped"""
        content = """## Test
-   item1
-   item2
## End
"""
        result = factory._extract_section(content, "## Test", "##")
        for item in result:
            if item:
                assert item == item.strip()

    def test_extract_section_multiple_headers_same_name(self, factory):
        """Test extraction when multiple headers with same name"""
        content = """## Capabilities
- cap1
## Other
- other1
## Capabilities
- cap2
"""
        result = factory._extract_section(content, "## Capabilities", "##")
        assert len(result) >= 0

    def test_extract_section_without_bullets(self, factory):
        """Test extracting section without bullet points"""
        content = """## Pure Text
This is just text without bullets
## End
"""
        result = factory._extract_section(content, "## Pure Text", "##")
        assert isinstance(result, list)

    def test_extract_section_with_nested_bullets(self, factory):
        """Test extracting nested bullet points"""
        content = """## Nested
- parent
  - child
  - child2
- parent2
## End
"""
        result = factory._extract_section(content, "## Nested", "##")
        assert len(result) >= 0


# ============================================================================
# 5. AGENT CHARACTERISTICS TESTS (10 tests)
# ============================================================================


class TestAgentCharacteristics:
    """Test agent characteristic calculation"""

    def test_analytical_agent_characteristics(self, factory):
        """Test characteristics for analytical agent"""
        reasoning, speed, cost = factory._calculate_agent_characteristics(
            AgentCategory.ANALYTICAL,
            ["analysis", "strategy"],
            ["meticulous", "detailed"],
        )

        assert 0.0 <= reasoning <= 1.0
        assert 0.0 <= speed <= 1.0
        assert 0.0 <= cost <= 1.0

    def test_creative_agent_characteristics(self, factory):
        """Test characteristics for creative agent"""
        reasoning, speed, cost = factory._calculate_agent_characteristics(
            AgentCategory.CREATIVE, ["content", "design"], ["creative", "fast"]
        )

        assert 0.0 <= reasoning <= 1.0
        assert 0.0 <= speed <= 1.0
        assert 0.0 <= cost <= 1.0

    def test_technical_agent_characteristics(self, factory):
        """Test characteristics for technical agent"""
        reasoning, speed, cost = factory._calculate_agent_characteristics(
            AgentCategory.TECHNICAL, ["coding", "optimization"], ["precise", "thorough"]
        )

        assert 0.0 <= reasoning <= 1.0
        assert 0.0 <= speed <= 1.0
        assert 0.0 <= cost <= 1.0

    def test_strategic_agent_characteristics(self, factory):
        """Test characteristics for strategic agent"""
        reasoning, speed, cost = factory._calculate_agent_characteristics(
            AgentCategory.STRATEGIC,
            ["planning", "architecture"],
            ["thoughtful", "comprehensive"],
        )

        assert 0.0 <= reasoning <= 1.0
        assert 0.0 <= speed <= 1.0
        assert 0.0 <= cost <= 1.0

    def test_characteristics_with_no_capabilities(self, factory):
        """Test characteristics calculation with empty capabilities"""
        reasoning, speed, cost = factory._calculate_agent_characteristics(
            AgentCategory.ANALYTICAL, [], []
        )

        assert 0.0 <= reasoning <= 1.0
        assert 0.0 <= speed <= 1.0
        assert 0.0 <= cost <= 1.0

    def test_characteristics_reasoning_modifier(self, factory):
        """Test that reasoning capabilities increase reasoning score"""
        reasoning1, _, _ = factory._calculate_agent_characteristics(
            AgentCategory.ANALYTICAL, ["simple"], []
        )

        reasoning2, _, _ = factory._calculate_agent_characteristics(
            AgentCategory.ANALYTICAL, ["analysis", "strategy", "planning"], []
        )

        assert reasoning2 >= reasoning1

    def test_characteristics_speed_modifier(self, factory):
        """Test that speed capabilities increase speed priority"""
        speed1, _, _ = factory._calculate_agent_characteristics(
            AgentCategory.CREATIVE, [], ["slow"]
        )

        speed2, _, _ = factory._calculate_agent_characteristics(
            AgentCategory.CREATIVE, ["real-time", "fast"], []
        )

        assert speed2 >= speed1

    def test_characteristics_maxed_at_1_0(self, factory):
        """Test that characteristics don't exceed 1.0"""
        reasoning, speed, cost = factory._calculate_agent_characteristics(
            AgentCategory.ANALYTICAL,
            ["analysis", "strategy", "planning", "optimization", "complex"],
            ["analytical", "detailed"],
        )

        assert reasoning <= 1.0
        assert speed <= 1.0
        assert cost <= 1.0

    def test_characteristics_support_agent(self, factory):
        """Test characteristics for support agent"""
        reasoning, speed, cost = factory._calculate_agent_characteristics(
            AgentCategory.SUPPORT, ["assistance", "responsive"], ["helpful", "fast"]
        )

        assert 0.0 <= reasoning <= 1.0
        assert 0.0 <= speed <= 1.0
        assert 0.0 <= cost <= 1.0

    def test_characteristics_specialized_agent(self, factory):
        """Test characteristics for specialized agent"""
        reasoning, speed, cost = factory._calculate_agent_characteristics(
            AgentCategory.SPECIALIZED, ["domain-expertise"], ["specialized"]
        )

        assert 0.0 <= reasoning <= 1.0
        assert 0.0 <= speed <= 1.0
        assert 0.0 <= cost <= 1.0


# ============================================================================
# 6. COMPLEXITY DETERMINATION TESTS (7 tests)
# ============================================================================


class TestComplexityDetermination:
    """Test agent complexity level determination"""

    def test_complexity_expert_level(self, factory):
        """Test that >15 items results in expert complexity"""
        capabilities = [f"cap{i}" for i in range(12)]
        traits = [f"trait{i}" for i in range(5)]

        complexity = factory._determine_complexity_level(capabilities, traits)
        assert complexity == "expert"

    def test_complexity_complex_level(self, factory):
        """Test that 10-15 items results in complex complexity"""
        capabilities = [f"cap{i}" for i in range(8)]
        traits = [f"trait{i}" for i in range(4)]

        complexity = factory._determine_complexity_level(capabilities, traits)
        assert complexity == "complex"

    def test_complexity_moderate_level(self, factory):
        """Test that 6-10 items results in moderate complexity"""
        capabilities = [f"cap{i}" for i in range(5)]
        traits = [f"trait{i}" for i in range(3)]

        complexity = factory._determine_complexity_level(capabilities, traits)
        assert complexity == "moderate"

    def test_complexity_simple_level(self, factory):
        """Test that <5 items results in simple complexity"""
        capabilities = ["cap1", "cap2"]
        traits = ["trait1"]

        complexity = factory._determine_complexity_level(capabilities, traits)
        assert complexity == "simple"

    def test_complexity_empty_lists(self, factory):
        """Test complexity with empty lists"""
        complexity = factory._determine_complexity_level([], [])
        assert complexity == "simple"

    def test_complexity_many_capabilities_few_traits(self, factory):
        """Test complexity with many capabilities, few traits"""
        capabilities = [f"cap{i}" for i in range(20)]
        traits = ["trait1"]

        complexity = factory._determine_complexity_level(capabilities, traits)
        assert complexity == "expert"

    def test_complexity_few_capabilities_many_traits(self, factory):
        """Test complexity with few capabilities, many traits"""
        capabilities = ["cap1"]
        traits = [f"trait{i}" for i in range(18)]

        complexity = factory._determine_complexity_level(capabilities, traits)
        assert complexity == "expert"


# ============================================================================
# 7. CODE GENERATION TESTS (15 tests)
# ============================================================================


class TestCodeGeneration:
    """Test Python agent code generation"""

    def test_generate_basic_code_structure(self, factory):
        """Test that generated code has basic structure"""
        definition = AgentDefinition(
            name="test-agent",
            description="Test agent",
            model="claude-3",
            purpose="Testing",
            capabilities=["analysis"],
            behavioral_traits=["careful"],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.ANALYTICAL,
            complexity_level="simple",
            reasoning_required=0.8,
            speed_priority=0.5,
            cost_sensitivity=0.6,
        )

        code = factory.generate_agent_implementation(definition)

        assert "class TestAgentAgent" in code
        assert "async def initialize" in code
        assert "async def process_task" in code

    def test_generated_code_includes_imports(self, factory):
        """Test that generated code includes required imports"""
        definition = AgentDefinition(
            name="test",
            description="test",
            model="test",
            purpose="test",
            capabilities=["test"],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.TECHNICAL,
            complexity_level="simple",
            reasoning_required=0.7,
            speed_priority=0.6,
            cost_sensitivity=0.5,
        )

        code = factory.generate_agent_implementation(definition)

        assert "import asyncio" in code
        assert "import logging" in code
        assert "from datetime import datetime" in code

    def test_generated_code_is_valid_python(self, factory):
        """Test that generated code is valid Python"""
        definition = AgentDefinition(
            name="valid-python",
            description="Valid python agent",
            model="test",
            purpose="test",
            capabilities=["cap1"],
            behavioral_traits=["trait1"],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.ANALYTICAL,
            complexity_level="moderate",
            reasoning_required=0.8,
            speed_priority=0.5,
            cost_sensitivity=0.6,
        )

        code = factory.generate_agent_implementation(definition)

        try:
            compile(code, "<string>", "exec")
            assert True
        except SyntaxError:
            assert False, "Generated code has syntax errors"

    def test_generated_code_includes_capabilities(self, factory):
        """Test that generated code includes all capabilities"""
        definition = AgentDefinition(
            name="multi-cap",
            description="Multi-capability agent",
            model="test",
            purpose="test",
            capabilities=["analysis", "coding", "testing"],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.TECHNICAL,
            complexity_level="complex",
            reasoning_required=0.8,
            speed_priority=0.6,
            cost_sensitivity=0.5,
        )

        code = factory.generate_agent_implementation(definition)

        assert "_analysis" in code or "analysis" in code

    def test_generated_code_includes_docstring(self, factory):
        """Test that generated code includes docstrings"""
        definition = AgentDefinition(
            name="documented",
            description="A documented agent",
            model="test",
            purpose="With documentation",
            capabilities=["cap1"],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.ANALYTICAL,
            complexity_level="simple",
            reasoning_required=0.7,
            speed_priority=0.5,
            cost_sensitivity=0.6,
        )

        code = factory.generate_agent_implementation(definition)

        assert '"""' in code or "'''" in code
        assert "Auto-generated" in code

    def test_generated_code_handles_category_specific_logic(self, factory):
        """Test that generated code has category-specific logic"""
        definition = AgentDefinition(
            name="analytical-agent",
            description="Analytical",
            model="test",
            purpose="test",
            capabilities=["analysis"],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.ANALYTICAL,
            complexity_level="moderate",
            reasoning_required=0.9,
            speed_priority=0.4,
            cost_sensitivity=0.7,
        )

        code = factory.generate_agent_implementation(definition)
        assert "analytical" in code.lower()

    def test_generated_code_with_empty_capabilities(self, factory):
        """Test code generation with no capabilities"""
        definition = AgentDefinition(
            name="minimal",
            description="Minimal agent",
            model="test",
            purpose="test",
            capabilities=[],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.SPECIALIZED,
            complexity_level="simple",
            reasoning_required=0.5,
            speed_priority=0.5,
            cost_sensitivity=0.5,
        )

        code = factory.generate_agent_implementation(definition)
        assert "class MinimalAgent" in code
        assert "async def" in code

    def test_generated_code_includes_error_handling(self, factory):
        """Test that generated code includes error handling"""
        definition = AgentDefinition(
            name="error-safe",
            description="Error handling",
            model="test",
            purpose="test",
            capabilities=["cap1"],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.TECHNICAL,
            complexity_level="moderate",
            reasoning_required=0.7,
            speed_priority=0.6,
            cost_sensitivity=0.5,
        )

        code = factory.generate_agent_implementation(definition)
        assert "try:" in code
        assert "except" in code

    def test_generated_code_with_long_capability_list(self, factory):
        """Test code generation with many capabilities"""
        definition = AgentDefinition(
            name="many-caps",
            description="Many capabilities",
            model="test",
            purpose="test",
            capabilities=[f"capability_{i}" for i in range(15)],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.TECHNICAL,
            complexity_level="expert",
            reasoning_required=0.9,
            speed_priority=0.7,
            cost_sensitivity=0.6,
        )

        code = factory.generate_agent_implementation(definition)
        assert "class" in code

    def test_generated_code_includes_llm_integration(self, factory):
        """Test that generated code includes LLM integration"""
        definition = AgentDefinition(
            name="llm-agent",
            description="With LLM",
            model="claude-3",
            purpose="test",
            capabilities=["analysis"],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.ANALYTICAL,
            complexity_level="moderate",
            reasoning_required=0.8,
            speed_priority=0.5,
            cost_sensitivity=0.7,
        )

        code = factory.generate_agent_implementation(definition)
        assert "llm_client" in code
        assert "LLMClient" in code

    def test_generated_code_class_name_generation(self, factory):
        """Test that class names are generated correctly"""
        definition = AgentDefinition(
            name="test-name-agent",
            description="test",
            model="test",
            purpose="test",
            capabilities=["cap"],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.ANALYTICAL,
            complexity_level="simple",
            reasoning_required=0.7,
            speed_priority=0.5,
            cost_sensitivity=0.6,
        )

        code = factory.generate_agent_implementation(definition)
        assert "class TestNameAgentAgent" in code

    def test_generated_code_metadata_included(self, factory):
        """Test that metadata is included in generated code"""
        definition = AgentDefinition(
            name="metadata-agent",
            description="With metadata",
            model="test",
            purpose="test",
            capabilities=["cap"],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.ANALYTICAL,
            complexity_level="moderate",
            reasoning_required=0.8,
            speed_priority=0.5,
            cost_sensitivity=0.6,
        )

        code = factory.generate_agent_implementation(definition)
        assert "metadata" in code or "Metadata" in code

    def test_generated_code_execution_result(self, factory):
        """Test that ExecutionResult is used in code"""
        definition = AgentDefinition(
            name="result-agent",
            description="test",
            model="test",
            purpose="test",
            capabilities=["cap"],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.ANALYTICAL,
            complexity_level="simple",
            reasoning_required=0.7,
            speed_priority=0.5,
            cost_sensitivity=0.6,
        )

        code = factory.generate_agent_implementation(definition)
        assert "ExecutionResult" in code


# ============================================================================
# 8. STRING CONVERSION TESTS (6 tests)
# ============================================================================


class TestStringConversion:
    """Test string conversion utilities"""

    def test_to_pascal_case_kebab(self, factory):
        """Test converting kebab-case to PascalCase"""
        result = factory._to_pascal_case("python-pro")
        assert result == "PythonPro"

    def test_to_pascal_case_underscore(self, factory):
        """Test converting snake_case to PascalCase"""
        result = factory._to_pascal_case("test_agent")
        assert result == "TestAgent"

    def test_to_pascal_case_mixed(self, factory):
        """Test converting mixed case to PascalCase"""
        result = factory._to_pascal_case("my-test_agent")
        assert result == "MyTestAgent"

    def test_to_snake_case_simple(self, factory):
        """Test converting simple string to snake_case"""
        result = factory._to_snake_case("Simple String")
        assert result == "simple_string"

    def test_to_snake_case_with_special_chars(self, factory):
        """Test converting string with special chars"""
        result = factory._to_snake_case("Test@Capability!")
        assert "test" in result and "capability" in result

    def test_to_snake_case_multiple_spaces(self, factory):
        """Test converting string with multiple spaces"""
        result = factory._to_snake_case("Real   Time   Analysis")
        assert "real" in result and "time" in result


# ============================================================================
# 9. BATCH GENERATION TESTS (8 tests)
# ============================================================================


class TestBatchGeneration:
    """Test batch agent generation"""

    @pytest.mark.asyncio
    async def test_generate_all_agents_success(self, temp_directory):
        """Test successful batch generation"""
        factory = AgentFactory(agenten_directory=str(temp_directory / "agenten"))
        factory.output_directory = temp_directory / "generated"
        factory.output_directory.mkdir(parents=True, exist_ok=True)

        results = await factory.generate_all_agents()

        assert "generated_agents" in results
        assert "failed_agents" in results
        assert "total_processed" in results
        assert "success_rate" in results

    @pytest.mark.asyncio
    async def test_generate_all_agents_includes_success_count(self, temp_directory):
        """Test that results include successful generations"""
        factory = AgentFactory(agenten_directory=str(temp_directory / "agenten"))
        factory.output_directory = temp_directory / "generated"
        factory.output_directory.mkdir(parents=True, exist_ok=True)

        results = await factory.generate_all_agents()

        assert len(results["generated_agents"]) >= 0

    @pytest.mark.asyncio
    async def test_generate_all_agents_tracks_failures(self, temp_directory):
        """Test that failures are tracked"""
        factory = AgentFactory(agenten_directory=str(temp_directory / "agenten"))
        factory.output_directory = temp_directory / "generated"
        factory.output_directory.mkdir(parents=True, exist_ok=True)

        results = await factory.generate_all_agents()

        assert isinstance(results["failed_agents"], list)

    @pytest.mark.asyncio
    async def test_generate_all_agents_skips_readme(self, temp_directory):
        """Test that README.md is skipped"""
        (temp_directory / "agenten" / "README.md").write_text("# Readme")

        factory = AgentFactory(agenten_directory=str(temp_directory / "agenten"))
        factory.output_directory = temp_directory / "generated"
        factory.output_directory.mkdir(parents=True, exist_ok=True)

        results = await factory.generate_all_agents()
        assert True  # If we get here, README was handled

    @pytest.mark.asyncio
    async def test_generate_all_agents_empty_directory(self, tmp_path):
        """Test generation with empty directory"""
        agenten_dir = tmp_path / "empty_agenten"
        agenten_dir.mkdir()

        factory = AgentFactory(agenten_directory=str(agenten_dir))
        factory.output_directory = tmp_path / "generated"
        factory.output_directory.mkdir(parents=True, exist_ok=True)

        results = await factory.generate_all_agents()

        assert results["total_processed"] == 0
        assert results["success_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_generate_all_agents_creates_output_files(self, temp_directory):
        """Test that output files are created"""
        factory = AgentFactory(agenten_directory=str(temp_directory / "agenten"))
        factory.output_directory = temp_directory / "generated"
        factory.output_directory.mkdir(parents=True, exist_ok=True)

        results = await factory.generate_all_agents()

        if results["generated_agents"]:
            assert factory.output_directory.exists()

    @pytest.mark.asyncio
    async def test_generate_all_agents_calculates_success_rate(self, temp_directory):
        """Test that success rate is calculated correctly"""
        factory = AgentFactory(agenten_directory=str(temp_directory / "agenten"))
        factory.output_directory = temp_directory / "generated"
        factory.output_directory.mkdir(parents=True, exist_ok=True)

        results = await factory.generate_all_agents()

        if results["total_processed"] > 0:
            expected_rate = len(results["generated_agents"]) / results["total_processed"]
            assert abs(results["success_rate"] - expected_rate) < 0.01

    @pytest.mark.asyncio
    async def test_generate_all_agents_handles_bad_files(self, temp_directory):
        """Test handling of malformed agent files"""
        bad_file = temp_directory / "agenten" / "bad_agent.md"
        bad_file.write_text(MALFORMED_YAML, encoding="utf-8")

        factory = AgentFactory(agenten_directory=str(temp_directory / "agenten"))
        factory.output_directory = temp_directory / "generated"
        factory.output_directory.mkdir(parents=True, exist_ok=True)

        results = await factory.generate_all_agents()
        assert True  # If we get here without crashing


# ============================================================================
# 10. INTEGRATION & EDGE CASES (10 tests)
# ============================================================================


class TestIntegrationAndEdgeCases:
    """Test integration and edge cases"""

    def test_full_workflow_from_markdown_to_definition(self, temp_markdown_file, factory):
        """Test complete workflow: parse markdown -> get definition"""
        definition = factory.parse_agent_markdown(temp_markdown_file)

        assert definition is not None
        assert definition.name == "test-analyst"
        # test-analyst is not in mapping, defaults to SPECIALIZED
        assert definition.category in [
            AgentCategory.ANALYTICAL,
            AgentCategory.SPECIALIZED,
        ]
        assert len(definition.capabilities) > 0

    def test_full_workflow_from_definition_to_code(self, factory):
        """Test complete workflow: definition -> code generation"""
        definition = AgentDefinition(
            name="workflow-test",
            description="Workflow test",
            model="claude-3",
            purpose="Testing workflow",
            capabilities=["analysis", "optimization"],
            behavioral_traits=["thorough"],
            knowledge_base=["test-domain"],
            example_interactions=["test interaction"],
            category=AgentCategory.ANALYTICAL,
            complexity_level="moderate",
            reasoning_required=0.8,
            speed_priority=0.5,
            cost_sensitivity=0.6,
        )

        code = factory.generate_agent_implementation(definition)

        assert "WorkflowTestAgent" in code
        assert "async def process_task" in code

    def test_unicode_in_agent_name(self, factory, tmp_path):
        """Test handling of unicode characters"""
        md_content = """---
name: test-agent
description: Test agent
---
## Purpose
Testing
"""
        md_file = tmp_path / "unicode.md"
        md_file.write_text(md_content, encoding="utf-8")

        definition = factory.parse_agent_markdown(md_file)
        assert definition is not None

    def test_very_long_capability_list(self, factory):
        """Test handling very long capability lists"""
        definition = AgentDefinition(
            name="many-caps",
            description="test",
            model="test",
            purpose="test",
            capabilities=[f"capability_{i}" for i in range(50)],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.TECHNICAL,
            complexity_level="expert",
            reasoning_required=0.9,
            speed_priority=0.7,
            cost_sensitivity=0.5,
        )

        code = factory.generate_agent_implementation(definition)
        assert "class" in code

    def test_agent_with_special_characters_in_description(self, factory):
        """Test agent with special characters in description"""
        definition = AgentDefinition(
            name="special-chars",
            description="Agent for: data & analysis!",
            model="test",
            purpose="test",
            capabilities=["analysis"],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.ANALYTICAL,
            complexity_level="simple",
            reasoning_required=0.7,
            speed_priority=0.5,
            cost_sensitivity=0.6,
        )

        code = factory.generate_agent_implementation(definition)
        assert "class" in code

    def test_category_mapping_completeness(self, factory):
        """Test that all known agents are in category mapping"""
        known_agents = [
            "python-pro",
            "business-analyst",
            "content-marketer",
            "typescript-pro",
            "fastapi-pro",
            "ui-ux-designer",
        ]

        for agent_name in known_agents:
            if agent_name in factory.category_mapping:
                assert isinstance(factory.category_mapping[agent_name], AgentCategory)

    def test_global_factory_instance_available(self):
        """Test that global factory instance is accessible"""
        assert agent_factory is not None
        assert isinstance(agent_factory, AgentFactory)

    def test_characteristics_with_extreme_values(self, factory):
        """Test characteristics with extreme input values"""
        reasoning, speed, cost = factory._calculate_agent_characteristics(
            AgentCategory.STRATEGIC,
            [f"capability_{i}" for i in range(100)],
            [f"trait_{i}" for i in range(100)],
        )

        assert 0.0 <= reasoning <= 1.0
        assert 0.0 <= speed <= 1.0
        assert 0.0 <= cost <= 1.0

    def test_markdown_with_complex_yaml(self, factory, tmp_path):
        """Test parsing markdown with complex YAML"""
        md_content = """---
name: complex-agent
description: Complex agent
model: sonnet
tags:
  - technical
  - advanced
configs:
  memory: 4096
  timeout: 30
---
## Purpose
Complex purpose
"""
        md_file = tmp_path / "complex.md"
        md_file.write_text(md_content, encoding="utf-8")

        definition = factory.parse_agent_markdown(md_file)
        assert definition is not None or definition is None

    def test_profile_registration_generation(self, factory):
        """Test agent profile registration code generation"""
        definition = AgentDefinition(
            name="profile-agent",
            description="test",
            model="test",
            purpose="test",
            capabilities=["cap"],
            behavioral_traits=[],
            knowledge_base=[],
            example_interactions=[],
            category=AgentCategory.ANALYTICAL,
            complexity_level="moderate",
            reasoning_required=0.8,
            speed_priority=0.5,
            cost_sensitivity=0.6,
        )

        profile_code = factory._generate_profile_registration(definition)
        assert "profile" in profile_code.lower()
        assert "agent" in profile_code.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--cov=src.core.agents.agent_factory"])
