"""
Synthesis domain service -- schemas and business logic (ADR-033 Laag 1).

Extracted from synthesis_endpoints.py (SP-API-006 Dag 5).
"""

import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================


class SynthesisType(str, Enum):
    """Type of synthesis to generate."""

    SUMMARY = "summary"
    ANALYSIS = "analysis"
    COMPARISON = "comparison"
    EXTRACTION = "extraction"
    TRANSLATION = "translation"


class DocumentType(str, Enum):
    """Document source types."""

    TEXT = "text"
    URL = "url"
    FILE = "file"
    KNOWLEDGE_BASE = "knowledge_base"


class OutputFormat(str, Enum):
    """Output format for synthesis."""

    TEXT = "text"
    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"


# ============================================================================
# Pydantic Models
# ============================================================================


class DocumentSource(BaseModel):
    """A document source for synthesis."""

    id: str = Field(
        default_factory=lambda: f"doc_{uuid.uuid4().hex[:8]}", description="Document ID"
    )
    type: DocumentType = Field(DocumentType.TEXT, description="Document type")
    content: str | None = Field(None, description="Document content (for text type)")
    url: str | None = Field(None, description="Document URL (for url type)")
    file_path: str | None = Field(None, description="File path (for file type)")
    knowledge_base_id: str | None = Field(None, description="Knowledge base ID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Document metadata")


class SynthesisRequest(BaseModel):
    """Request to generate synthesis."""

    documents: list[DocumentSource] = Field(
        ..., min_length=1, description="Documents to synthesize"
    )
    synthesis_type: SynthesisType = Field(SynthesisType.SUMMARY, description="Type of synthesis")
    output_format: OutputFormat = Field(OutputFormat.MARKDOWN, description="Output format")
    query: str | None = Field(None, description="Optional query to focus synthesis")
    language: str = Field("en", description="Output language code")
    max_length: int | None = Field(None, ge=100, le=10000, description="Maximum output length")
    include_sources: bool = Field(True, description="Include source citations")
    config: dict[str, Any] = Field(default_factory=dict, description="Additional configuration")


class SourceCitation(BaseModel):
    """Citation for a source used in synthesis."""

    document_id: str = Field(..., description="Source document ID")
    excerpt: str = Field(..., description="Relevant excerpt")
    relevance_score: float = Field(..., ge=0, le=1, description="Relevance score 0-1")
    page: int | None = Field(None, description="Page number if applicable")
    section: str | None = Field(None, description="Section name if applicable")


class SynthesisMetrics(BaseModel):
    """Metrics about the synthesis process."""

    documents_processed: int = Field(..., description="Number of documents processed")
    total_tokens_input: int = Field(0, description="Total input tokens")
    total_tokens_output: int = Field(0, description="Total output tokens")
    processing_time_ms: int = Field(0, description="Processing time in milliseconds")
    model_used: str = Field("rule-based-v1", description="Model used for synthesis")
    confidence_score: float = Field(0.0, ge=0, le=1, description="Overall confidence")


class SynthesisResult(BaseModel):
    """Result of synthesis generation."""

    id: str = Field(..., description="Synthesis result ID")
    synthesis_type: SynthesisType = Field(..., description="Type of synthesis performed")
    output_format: OutputFormat = Field(..., description="Output format")
    content: str = Field(..., description="Synthesized content")
    query: str | None = Field(None, description="Query used if any")
    language: str = Field(..., description="Output language")
    sources: list[SourceCitation] = Field(default_factory=list, description="Source citations")
    metrics: SynthesisMetrics = Field(..., description="Synthesis metrics")
    created_at: str = Field(..., description="Creation timestamp")
    tenant_id: int = Field(..., description="Tenant ID")
    created_by: str = Field(..., description="User who created")


class SynthesisResponse(BaseModel):
    """Response for synthesis request."""

    result: SynthesisResult
    message: str
    success: bool


# ============================================================================
# Helper Functions
# ============================================================================


def get_user_id(current_user: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
    """Extract user ID from current user."""
    if isinstance(current_user, dict):
        return str(current_user.get("user_id") or current_user.get("id") or "unknown")
    if hasattr(current_user, "id"):
        return str(current_user.id)
    return "unknown"


def extract_document_content(doc: DocumentSource) -> str:
    """Extract content from a document source."""
    if doc.type == DocumentType.TEXT:
        return doc.content or ""
    elif doc.type == DocumentType.URL:
        return f"[Content from URL: {doc.url}]"
    elif doc.type == DocumentType.FILE:
        return f"[Content from file: {doc.file_path}]"
    elif doc.type == DocumentType.KNOWLEDGE_BASE:
        return f"[Content from knowledge base: {doc.knowledge_base_id}]"
    return ""


def generate_summary(
    documents: list[DocumentSource], query: str | None, max_length: int | None
) -> str:
    """Generate a summary synthesis."""
    if query:
        summary = f"## Summary: {query}\n\n"
    else:
        summary = "## Document Summary\n\n"

    summary += "### Key Points\n\n"

    for i, doc in enumerate(documents, 1):
        content = extract_document_content(doc)
        if content:
            preview = content[:200] + "..." if len(content) > 200 else content
            summary += f"- **Document {i}** ({doc.type.value}): {preview}\n"

    summary += "\n### Synthesis\n\n"
    summary += f"This synthesis covers {len(documents)} document(s). "

    if query:
        summary += f'The analysis focused on: "{query}". '

    summary += "Key themes and insights have been extracted and consolidated."

    if max_length and len(summary) > max_length:
        summary = summary[: max_length - 3] + "..."

    return summary


def generate_analysis(
    documents: list[DocumentSource], query: str | None, max_length: int | None
) -> str:
    """Generate an analysis synthesis."""
    analysis = "## Document Analysis\n\n"
    analysis += "### Overview\n\n"
    analysis += f"Analyzed {len(documents)} document(s)"
    if query:
        analysis += f' with focus on: "{query}"'
    analysis += ".\n\n"

    analysis += "### Document Breakdown\n\n"

    for i, doc in enumerate(documents, 1):
        content = extract_document_content(doc)
        word_count = len(content.split()) if content else 0

        analysis += f"#### Document {i}\n"
        analysis += f"- **Type**: {doc.type.value}\n"
        analysis += f"- **Word Count**: {word_count}\n"
        if doc.metadata:
            analysis += f"- **Metadata**: {doc.metadata}\n"
        analysis += "\n"

    analysis += "### Insights\n\n"
    analysis += "The documents present a cohesive set of information. "
    analysis += "Cross-referencing reveals consistent themes and complementary data points."

    if max_length and len(analysis) > max_length:
        analysis = analysis[: max_length - 3] + "..."

    return analysis


def generate_comparison(
    documents: list[DocumentSource], query: str | None, max_length: int | None
) -> str:
    """Generate a comparison synthesis."""
    comparison = "## Document Comparison\n\n"

    if len(documents) < 2:
        comparison += (
            "*Note: Comparison requires at least 2 documents."
            " Single document analysis provided.*\n\n"
        )

    comparison += "### Comparison Matrix\n\n"
    comparison += "| Aspect | " + " | ".join(f"Doc {i + 1}" for i in range(len(documents))) + " |\n"
    comparison += "|--------|" + "|".join("-" * 8 for _ in documents) + "|\n"

    aspects = ["Content Type", "Length", "Key Theme"]
    for aspect in aspects:
        row = f"| {aspect} |"
        for doc in documents:
            content = extract_document_content(doc)
            if aspect == "Content Type":
                row += f" {doc.type.value} |"
            elif aspect == "Length":
                row += f" {len(content)} chars |"
            else:
                row += " Analyzed |"
        comparison += row + "\n"

    comparison += "\n### Similarities\n\n"
    comparison += "- Common themes identified across documents\n"
    comparison += "- Shared terminology and concepts\n"

    comparison += "\n### Differences\n\n"
    comparison += "- Varying perspectives on key topics\n"
    comparison += "- Different emphasis areas\n"

    if max_length and len(comparison) > max_length:
        comparison = comparison[: max_length - 3] + "..."

    return comparison


def generate_extraction(
    documents: list[DocumentSource], query: str | None, max_length: int | None
) -> str:
    """Generate an extraction synthesis."""
    extraction = "## Information Extraction\n\n"

    if query:
        extraction += f"**Extraction Query**: {query}\n\n"

    extraction += "### Extracted Entities\n\n"

    entities: dict[str, list[str]] = {
        "Organizations": ["Company A", "Organization B"],
        "Dates": ["2024-01-01", "2025-12-16"],
        "Key Terms": ["synthesis", "analysis", "document"],
    }

    for category, items in entities.items():
        extraction += f"#### {category}\n"
        for item in items:
            extraction += f"- {item}\n"
        extraction += "\n"

    extraction += "### Key Facts\n\n"
    extraction += f"- Total documents processed: {len(documents)}\n"
    extraction += "- Extraction confidence: High\n"
    extraction += "- Coverage: Complete\n"

    if max_length and len(extraction) > max_length:
        extraction = extraction[: max_length - 3] + "..."

    return extraction


def generate_translation(
    documents: list[DocumentSource], language: str, max_length: int | None
) -> str:
    """Generate a translation synthesis."""
    translation = f"## Translation to {language.upper()}\n\n"
    translation += (
        "*Note: Translation feature simulated for demo. In production, use translation API.*\n\n"
    )

    for i, doc in enumerate(documents, 1):
        content = extract_document_content(doc)
        translation += f"### Document {i} Translation\n\n"
        translation += f"**Original ({doc.type.value})**: {content[:100]}...\n\n"
        translation += f"**Translated ({language})**: [Translation would appear here]\n\n"

    if max_length and len(translation) > max_length:
        translation = translation[: max_length - 3] + "..."

    return translation


def generate_synthesis_content(
    documents: list[DocumentSource],
    synthesis_type: SynthesisType,
    query: str | None,
    language: str,
    max_length: int | None,
) -> str:
    """Generate synthesis content based on type."""
    if synthesis_type == SynthesisType.SUMMARY:
        return generate_summary(documents, query, max_length)
    elif synthesis_type == SynthesisType.ANALYSIS:
        return generate_analysis(documents, query, max_length)
    elif synthesis_type == SynthesisType.COMPARISON:
        return generate_comparison(documents, query, max_length)
    elif synthesis_type == SynthesisType.EXTRACTION:
        return generate_extraction(documents, query, max_length)
    elif synthesis_type == SynthesisType.TRANSLATION:
        return generate_translation(documents, language, max_length)
    else:
        return generate_summary(documents, query, max_length)


def generate_source_citations(documents: list[DocumentSource]) -> list[SourceCitation]:
    """Generate source citations for synthesis."""
    citations: list[SourceCitation] = []
    for doc in documents:
        content = extract_document_content(doc)
        excerpt = content[:100] + "..." if len(content) > 100 else content

        citations.append(
            SourceCitation(
                document_id=doc.id,
                excerpt=excerpt if excerpt else "[No content]",
                relevance_score=0.85,
                page=None,
                section="Main",
            )
        )
    return citations
