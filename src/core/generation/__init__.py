"""
Core Generation Module - Content and response generation system
Provides text generation, template processing, and dynamic content creation
ASCII-only compliance enforced
"""

from typing import Any

from .content_generator import (
    ContentGenerator,
    ContentType,
    GenerationRequest,
    GenerationResult,
    create_content_generator,
)
from .prompt_builder import PromptBuilder, PromptStrategy, PromptTemplate, PromptVariable
from .response_formatter import FormattingOptions, FormatType, ResponseFormatter
from .template_engine import Template, TemplateContext, TemplateEngine, TemplateVariable
from .text_processor import ProcessingRule, TextProcessor, TextTransformation

__all__ = [
    "ContentGenerator",
    "GenerationRequest",
    "GenerationResult",
    "ContentType",
    "create_content_generator",
    "TemplateEngine",
    "Template",
    "TemplateContext",
    "TemplateVariable",
    "ResponseFormatter",
    "FormatType",
    "FormattingOptions",
    "PromptBuilder",
    "PromptTemplate",
    "PromptVariable",
    "PromptStrategy",
    "TextProcessor",
    "ProcessingRule",
    "TextTransformation",
]
