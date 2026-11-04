"""
Comprehensive tests for Synthesis API Endpoints
================================================

100% coverage tests for:
- POST /api/v1/synthesis - Generate synthesis from documents
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Import the module under test
from src.core.api.synthesis_endpoints import (  # Enums; Pydantic models; Helper functions; Endpoints; Router
    DocumentSource,
    DocumentType,
    OutputFormat,
    SourceCitation,
    SynthesisMetrics,
    SynthesisRequest,
    SynthesisResponse,
    SynthesisResult,
    SynthesisType,
    extract_document_content,
    generate_analysis,
    generate_comparison,
    generate_extraction,
    generate_source_citations,
    generate_summary,
    generate_synthesis,
    generate_synthesis_content,
    generate_translation,
    get_tenant,
    get_user_id,
    router,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    """Mock database session"""
    return AsyncMock()


@pytest.fixture
def mock_user():
    """Mock current user"""
    return {"user_id": "test_user_123", "email": "test@example.com"}


@pytest.fixture
def sample_text_document():
    """Sample text document"""
    return DocumentSource(
        id="doc_1",
        type=DocumentType.TEXT,
        content="This is sample text content for testing synthesis.",
    )


@pytest.fixture
def sample_url_document():
    """Sample URL document"""
    return DocumentSource(id="doc_2", type=DocumentType.URL, url="https://example.com/document.pdf")


@pytest.fixture
def sample_file_document():
    """Sample file document"""
    return DocumentSource(id="doc_3", type=DocumentType.FILE, file_path="/path/to/document.txt")


@pytest.fixture
def sample_kb_document():
    """Sample knowledge base document"""
    return DocumentSource(id="doc_4", type=DocumentType.KNOWLEDGE_BASE, knowledge_base_id="kb_123")


# ============================================================================
# Enum Tests
# ============================================================================


class TestEnums:
    """Test all enum classes"""

    def test_synthesis_type_values(self):
        """Test SynthesisType enum values"""
        assert SynthesisType.SUMMARY == "summary"
        assert SynthesisType.ANALYSIS == "analysis"
        assert SynthesisType.COMPARISON == "comparison"
        assert SynthesisType.EXTRACTION == "extraction"
        assert SynthesisType.TRANSLATION == "translation"

    def test_document_type_values(self):
        """Test DocumentType enum values"""
        assert DocumentType.TEXT == "text"
        assert DocumentType.URL == "url"
        assert DocumentType.FILE == "file"
        assert DocumentType.KNOWLEDGE_BASE == "knowledge_base"

    def test_output_format_values(self):
        """Test OutputFormat enum values"""
        assert OutputFormat.TEXT == "text"
        assert OutputFormat.MARKDOWN == "markdown"
        assert OutputFormat.JSON == "json"
        assert OutputFormat.HTML == "html"


# ============================================================================
# Pydantic Model Tests
# ============================================================================


class TestPydanticModels:
    """Test all Pydantic model classes"""

    def test_document_source_text(self):
        """Test DocumentSource with text type"""
        doc = DocumentSource(type=DocumentType.TEXT, content="Sample content")
        assert doc.type == DocumentType.TEXT
        assert doc.content == "Sample content"
        assert doc.id.startswith("doc_")

    def test_document_source_url(self):
        """Test DocumentSource with URL type"""
        doc = DocumentSource(type=DocumentType.URL, url="https://example.com")
        assert doc.type == DocumentType.URL
        assert doc.url == "https://example.com"

    def test_document_source_file(self):
        """Test DocumentSource with file type"""
        doc = DocumentSource(type=DocumentType.FILE, file_path="/path/to/file.txt")
        assert doc.type == DocumentType.FILE
        assert doc.file_path == "/path/to/file.txt"

    def test_document_source_kb(self):
        """Test DocumentSource with knowledge base type"""
        doc = DocumentSource(type=DocumentType.KNOWLEDGE_BASE, knowledge_base_id="kb_123")
        assert doc.type == DocumentType.KNOWLEDGE_BASE
        assert doc.knowledge_base_id == "kb_123"

    def test_document_source_with_metadata(self):
        """Test DocumentSource with metadata"""
        doc = DocumentSource(
            type=DocumentType.TEXT,
            content="Content",
            metadata={"author": "Test", "date": "2024-01-01"},
        )
        assert doc.metadata["author"] == "Test"

    def test_synthesis_request_minimal(self):
        """Test SynthesisRequest with minimal fields"""
        doc = DocumentSource(type=DocumentType.TEXT, content="Test")
        request = SynthesisRequest(documents=[doc])
        assert len(request.documents) == 1
        assert request.synthesis_type == SynthesisType.SUMMARY
        assert request.output_format == OutputFormat.MARKDOWN

    def test_synthesis_request_full(self):
        """Test SynthesisRequest with all fields"""
        doc = DocumentSource(type=DocumentType.TEXT, content="Test")
        request = SynthesisRequest(
            documents=[doc],
            synthesis_type=SynthesisType.ANALYSIS,
            output_format=OutputFormat.JSON,
            query="Focus on key points",
            language="nl",
            max_length=500,
            include_sources=False,
            config={"temperature": 0.7},
        )
        assert request.synthesis_type == SynthesisType.ANALYSIS
        assert request.query == "Focus on key points"
        assert request.language == "nl"
        assert request.max_length == 500
        assert request.include_sources is False

    def test_source_citation_creation(self):
        """Test SourceCitation model"""
        citation = SourceCitation(
            document_id="doc_1",
            excerpt="Sample excerpt",
            relevance_score=0.95,
            page=5,
            section="Introduction",
        )
        assert citation.document_id == "doc_1"
        assert citation.relevance_score == 0.95
        assert citation.page == 5

    def test_synthesis_metrics_creation(self):
        """Test SynthesisMetrics model"""
        metrics = SynthesisMetrics(
            documents_processed=3,
            total_tokens_input=1000,
            total_tokens_output=200,
            processing_time_ms=150,
            model_used="gpt-4",
            confidence_score=0.92,
        )
        assert metrics.documents_processed == 3
        assert metrics.confidence_score == 0.92

    def test_synthesis_metrics_defaults(self):
        """Test SynthesisMetrics default values"""
        metrics = SynthesisMetrics(documents_processed=1)
        assert metrics.total_tokens_input == 0
        assert metrics.total_tokens_output == 0
        assert metrics.processing_time_ms == 0
        assert metrics.model_used == "rule-based-v1"
        assert metrics.confidence_score == 0.0

    def test_synthesis_result_creation(self):
        """Test SynthesisResult model"""
        metrics = SynthesisMetrics(documents_processed=1)
        result = SynthesisResult(
            id="synth_123",
            synthesis_type=SynthesisType.SUMMARY,
            output_format=OutputFormat.MARKDOWN,
            content="# Summary\n\nContent here",
            language="en",
            metrics=metrics,
            created_at="2024-01-01T00:00:00Z",
            tenant_id=1,
            created_by="user_123",
        )
        assert result.id == "synth_123"
        assert result.synthesis_type == SynthesisType.SUMMARY

    def test_synthesis_response_creation(self):
        """Test SynthesisResponse model"""
        metrics = SynthesisMetrics(documents_processed=1)
        result = SynthesisResult(
            id="synth_123",
            synthesis_type=SynthesisType.SUMMARY,
            output_format=OutputFormat.MARKDOWN,
            content="Content",
            language="en",
            metrics=metrics,
            created_at="2024-01-01T00:00:00Z",
            tenant_id=1,
            created_by="user_123",
        )
        response = SynthesisResponse(result=result, message="Success", success=True)
        assert response.success is True
        assert response.message == "Success"


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestHelperFunctions:
    """Test helper functions"""

    @pytest.mark.asyncio
    async def test_get_tenant_success(self):
        """Test get_tenant with valid tenant"""
        with patch("src.core.api.v1.synthesis.dependencies.get_current_tenant_id") as mock:
            mock.return_value = 1
            result = await get_tenant()
            assert result == 1

    @pytest.mark.asyncio
    async def test_get_tenant_missing(self):
        """Test get_tenant with missing tenant"""
        with patch("src.core.api.v1.synthesis.dependencies.get_current_tenant_id") as mock:
            mock.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await get_tenant()
            assert exc_info.value.status_code == 400
            assert "Tenant context required" in str(exc_info.value.detail)

    def test_get_user_id_from_dict_user_id(self):
        """Test get_user_id with dict containing user_id"""
        user = {"user_id": "test_user"}
        assert get_user_id(user) == "test_user"

    def test_get_user_id_from_dict_id(self):
        """Test get_user_id with dict containing id"""
        user = {"id": "test_user"}
        assert get_user_id(user) == "test_user"

    def test_get_user_id_from_object(self):
        """Test get_user_id with object having id attribute"""
        user = MagicMock()
        user.id = "object_user"
        assert get_user_id(user) == "object_user"

    def test_get_user_id_unknown(self):
        """Test get_user_id with unknown structure"""
        user = {"email": "test@test.com"}
        assert get_user_id(user) == "unknown"

    def test_get_user_id_no_id_attribute(self):
        """Test get_user_id with object without id attribute"""

        class NoIdUser:
            pass

        user = NoIdUser()
        assert get_user_id(user) == "unknown"


# ============================================================================
# Extract Document Content Tests
# ============================================================================


class TestExtractDocumentContent:
    """Test extract_document_content function"""

    def test_extract_text_content(self, sample_text_document):
        """Test extracting text content"""
        content = extract_document_content(sample_text_document)
        assert content == "This is sample text content for testing synthesis."

    def test_extract_text_empty(self):
        """Test extracting empty text content"""
        doc = DocumentSource(type=DocumentType.TEXT, content=None)
        content = extract_document_content(doc)
        assert content == ""

    def test_extract_url_content(self, sample_url_document):
        """Test extracting URL content (simulated)"""
        content = extract_document_content(sample_url_document)
        assert "Content from URL" in content
        assert "example.com" in content

    def test_extract_file_content(self, sample_file_document):
        """Test extracting file content (simulated)"""
        content = extract_document_content(sample_file_document)
        assert "Content from file" in content
        assert "/path/to/document.txt" in content

    def test_extract_kb_content(self, sample_kb_document):
        """Test extracting knowledge base content (simulated)"""
        content = extract_document_content(sample_kb_document)
        assert "Content from knowledge base" in content
        assert "kb_123" in content


# ============================================================================
# Synthesis Generation Tests
# ============================================================================


class TestGenerateSummary:
    """Test generate_summary function"""

    def test_summary_single_document(self, sample_text_document):
        """Test summary with single document"""
        summary = generate_summary([sample_text_document], None, None)
        assert "Document Summary" in summary
        assert "Key Points" in summary
        assert "Document 1" in summary

    def test_summary_with_query(self, sample_text_document):
        """Test summary with query"""
        summary = generate_summary([sample_text_document], "Focus on testing", None)
        assert "Focus on testing" in summary

    def test_summary_with_max_length(self, sample_text_document):
        """Test summary with max length"""
        summary = generate_summary([sample_text_document], None, 100)
        assert len(summary) <= 100

    def test_summary_multiple_documents(self, sample_text_document, sample_url_document):
        """Test summary with multiple documents"""
        summary = generate_summary([sample_text_document, sample_url_document], None, None)
        assert "Document 1" in summary
        assert "Document 2" in summary
        assert "2 document(s)" in summary


class TestGenerateAnalysis:
    """Test generate_analysis function"""

    def test_analysis_single_document(self, sample_text_document):
        """Test analysis with single document"""
        analysis = generate_analysis([sample_text_document], None, None)
        assert "Document Analysis" in analysis
        assert "Overview" in analysis
        assert "Document Breakdown" in analysis

    def test_analysis_with_query(self, sample_text_document):
        """Test analysis with query"""
        analysis = generate_analysis([sample_text_document], "Test focus", None)
        assert "Test focus" in analysis

    def test_analysis_with_max_length(self, sample_text_document):
        """Test analysis with max length"""
        analysis = generate_analysis([sample_text_document], None, 150)
        assert len(analysis) <= 150

    def test_analysis_shows_word_count(self, sample_text_document):
        """Test analysis shows word count"""
        analysis = generate_analysis([sample_text_document], None, None)
        assert "Word Count" in analysis

    def test_analysis_with_metadata(self):
        """Test analysis includes metadata when present"""
        doc = DocumentSource(
            type=DocumentType.TEXT,
            content="Test content",
            metadata={"author": "Test Author", "version": "1.0"},
        )
        analysis = generate_analysis([doc], None, None)
        assert "Metadata" in analysis


class TestGenerateComparison:
    """Test generate_comparison function"""

    def test_comparison_single_document(self, sample_text_document):
        """Test comparison with single document (shows note)"""
        comparison = generate_comparison([sample_text_document], None, None)
        assert "Document Comparison" in comparison
        assert "requires at least 2 documents" in comparison

    def test_comparison_multiple_documents(self, sample_text_document, sample_url_document):
        """Test comparison with multiple documents"""
        comparison = generate_comparison([sample_text_document, sample_url_document], None, None)
        assert "Comparison Matrix" in comparison
        assert "Similarities" in comparison
        assert "Differences" in comparison

    def test_comparison_with_max_length(self, sample_text_document, sample_url_document):
        """Test comparison with max length"""
        comparison = generate_comparison([sample_text_document, sample_url_document], None, 200)
        assert len(comparison) <= 200


class TestGenerateExtraction:
    """Test generate_extraction function"""

    def test_extraction_basic(self, sample_text_document):
        """Test basic extraction"""
        extraction = generate_extraction([sample_text_document], None, None)
        assert "Information Extraction" in extraction
        assert "Extracted Entities" in extraction
        assert "Key Facts" in extraction

    def test_extraction_with_query(self, sample_text_document):
        """Test extraction with query"""
        extraction = generate_extraction([sample_text_document], "Extract names", None)
        assert "Extract names" in extraction

    def test_extraction_with_max_length(self, sample_text_document):
        """Test extraction with max length"""
        extraction = generate_extraction([sample_text_document], None, 200)
        assert len(extraction) <= 200


class TestGenerateTranslation:
    """Test generate_translation function"""

    def test_translation_basic(self, sample_text_document):
        """Test basic translation"""
        translation = generate_translation([sample_text_document], "nl", None)
        assert "Translation to NL" in translation
        assert "Document 1 Translation" in translation

    def test_translation_different_language(self, sample_text_document):
        """Test translation to different language"""
        translation = generate_translation([sample_text_document], "de", None)
        assert "Translation to DE" in translation

    def test_translation_with_max_length(self, sample_text_document):
        """Test translation with max length"""
        translation = generate_translation([sample_text_document], "fr", 150)
        assert len(translation) <= 150


class TestGenerateSynthesisContent:
    """Test generate_synthesis_content function"""

    def test_synthesis_content_summary(self, sample_text_document):
        """Test synthesis content for summary type"""
        content = generate_synthesis_content(
            [sample_text_document], SynthesisType.SUMMARY, None, "en", None
        )
        assert "Summary" in content

    def test_synthesis_content_analysis(self, sample_text_document):
        """Test synthesis content for analysis type"""
        content = generate_synthesis_content(
            [sample_text_document], SynthesisType.ANALYSIS, None, "en", None
        )
        assert "Analysis" in content

    def test_synthesis_content_comparison(self, sample_text_document):
        """Test synthesis content for comparison type"""
        content = generate_synthesis_content(
            [sample_text_document], SynthesisType.COMPARISON, None, "en", None
        )
        assert "Comparison" in content

    def test_synthesis_content_extraction(self, sample_text_document):
        """Test synthesis content for extraction type"""
        content = generate_synthesis_content(
            [sample_text_document], SynthesisType.EXTRACTION, None, "en", None
        )
        assert "Extraction" in content

    def test_synthesis_content_translation(self, sample_text_document):
        """Test synthesis content for translation type"""
        content = generate_synthesis_content(
            [sample_text_document], SynthesisType.TRANSLATION, None, "nl", None
        )
        assert "Translation" in content


class TestGenerateSourceCitations:
    """Test generate_source_citations function"""

    def test_citations_single_document(self, sample_text_document):
        """Test citations for single document"""
        citations = generate_source_citations([sample_text_document])
        assert len(citations) == 1
        assert citations[0].document_id == "doc_1"
        assert citations[0].relevance_score == 0.85

    def test_citations_multiple_documents(self, sample_text_document, sample_url_document):
        """Test citations for multiple documents"""
        citations = generate_source_citations([sample_text_document, sample_url_document])
        assert len(citations) == 2

    def test_citations_long_content_truncated(self):
        """Test that long content is truncated in excerpt"""
        long_content = "A" * 200
        doc = DocumentSource(type=DocumentType.TEXT, content=long_content)
        citations = generate_source_citations([doc])
        assert len(citations[0].excerpt) <= 103  # 100 + "..."

    def test_citations_empty_content(self):
        """Test citations with empty content"""
        doc = DocumentSource(type=DocumentType.TEXT, content="")
        citations = generate_source_citations([doc])
        assert citations[0].excerpt == "[No content]"


# ============================================================================
# Endpoint Tests
# ============================================================================


class TestSynthesisEndpoint:
    """Test generate_synthesis endpoint"""

    @pytest.mark.asyncio
    async def test_synthesis_summary(self, mock_db, mock_user, sample_text_document):
        """Test generating summary synthesis"""
        request = SynthesisRequest(
            documents=[sample_text_document], synthesis_type=SynthesisType.SUMMARY
        )

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert response.success is True
        assert response.result.synthesis_type == SynthesisType.SUMMARY
        assert "Summary" in response.result.content

    @pytest.mark.asyncio
    async def test_synthesis_analysis(self, mock_db, mock_user, sample_text_document):
        """Test generating analysis synthesis"""
        request = SynthesisRequest(
            documents=[sample_text_document], synthesis_type=SynthesisType.ANALYSIS
        )

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert response.result.synthesis_type == SynthesisType.ANALYSIS
        assert "Analysis" in response.result.content

    @pytest.mark.asyncio
    async def test_synthesis_comparison(
        self, mock_db, mock_user, sample_text_document, sample_url_document
    ):
        """Test generating comparison synthesis"""
        request = SynthesisRequest(
            documents=[sample_text_document, sample_url_document],
            synthesis_type=SynthesisType.COMPARISON,
        )

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert response.result.synthesis_type == SynthesisType.COMPARISON

    @pytest.mark.asyncio
    async def test_synthesis_extraction(self, mock_db, mock_user, sample_text_document):
        """Test generating extraction synthesis"""
        request = SynthesisRequest(
            documents=[sample_text_document],
            synthesis_type=SynthesisType.EXTRACTION,
            query="Extract key entities",
        )

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert response.result.synthesis_type == SynthesisType.EXTRACTION

    @pytest.mark.asyncio
    async def test_synthesis_translation(self, mock_db, mock_user, sample_text_document):
        """Test generating translation synthesis"""
        request = SynthesisRequest(
            documents=[sample_text_document],
            synthesis_type=SynthesisType.TRANSLATION,
            language="nl",
        )

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert response.result.synthesis_type == SynthesisType.TRANSLATION
        assert response.result.language == "nl"

    @pytest.mark.asyncio
    async def test_synthesis_with_sources(self, mock_db, mock_user, sample_text_document):
        """Test synthesis includes sources when requested"""
        request = SynthesisRequest(documents=[sample_text_document], include_sources=True)

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert len(response.result.sources) > 0

    @pytest.mark.asyncio
    async def test_synthesis_without_sources(self, mock_db, mock_user, sample_text_document):
        """Test synthesis excludes sources when not requested"""
        request = SynthesisRequest(documents=[sample_text_document], include_sources=False)

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert len(response.result.sources) == 0

    @pytest.mark.asyncio
    async def test_synthesis_with_query(self, mock_db, mock_user, sample_text_document):
        """Test synthesis with query parameter"""
        request = SynthesisRequest(
            documents=[sample_text_document], query="Focus on testing aspects"
        )

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert response.result.query == "Focus on testing aspects"

    @pytest.mark.asyncio
    async def test_synthesis_with_max_length(self, mock_db, mock_user, sample_text_document):
        """Test synthesis with max length"""
        request = SynthesisRequest(documents=[sample_text_document], max_length=200)

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert len(response.result.content) <= 200

    @pytest.mark.asyncio
    async def test_synthesis_metrics(self, mock_db, mock_user, sample_text_document):
        """Test synthesis metrics are populated"""
        request = SynthesisRequest(documents=[sample_text_document])

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert response.result.metrics.documents_processed == 1
        assert response.result.metrics.total_tokens_input > 0
        assert response.result.metrics.total_tokens_output > 0

    @pytest.mark.asyncio
    async def test_synthesis_tenant_isolation(self, mock_db, mock_user, sample_text_document):
        """Test synthesis includes correct tenant_id"""
        request = SynthesisRequest(documents=[sample_text_document])

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=42, current_user=mock_user
        )

        assert response.result.tenant_id == 42

    @pytest.mark.asyncio
    async def test_synthesis_created_by(self, mock_db, mock_user, sample_text_document):
        """Test synthesis includes correct created_by"""
        request = SynthesisRequest(documents=[sample_text_document])

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert response.result.created_by == "test_user_123"

    @pytest.mark.asyncio
    async def test_synthesis_multiple_documents(
        self,
        mock_db,
        mock_user,
        sample_text_document,
        sample_url_document,
        sample_file_document,
    ):
        """Test synthesis with multiple documents"""
        request = SynthesisRequest(
            documents=[sample_text_document, sample_url_document, sample_file_document]
        )

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert response.result.metrics.documents_processed == 3
        assert "3 document(s)" in response.message

    @pytest.mark.asyncio
    async def test_synthesis_all_output_formats(self, mock_db, mock_user, sample_text_document):
        """Test synthesis with different output formats"""
        for output_format in OutputFormat:
            request = SynthesisRequest(
                documents=[sample_text_document], output_format=output_format
            )

            response = await generate_synthesis(
                request=request, db=mock_db, tenant_id=1, current_user=mock_user
            )

            assert response.result.output_format == output_format


# ============================================================================
# Router Tests
# ============================================================================


class TestRouter:
    """Test router configuration"""

    def test_router_prefix(self):
        """Test router has correct prefix"""
        # Legacy shim exports composite router (no prefix); sub-router carries /api/v1
        from src.core.api.v1.synthesis.synthesis_router import router as sub_router
        assert sub_router.prefix == "/api/v1"

    def test_router_tags(self):
        """Test router has correct tags"""
        # Tags are no longer set on the synthesis router in ADR-033 refactor
        assert router.tags == []

    def test_synthesis_route_registered(self):
        """Test synthesis route is registered"""
        routes = [route.path for route in router.routes]
        assert any("synthesis" in path for path in routes)

    def test_synthesis_endpoint_method(self):
        """Test synthesis endpoint only accepts POST"""
        for route in router.routes:
            if hasattr(route, "path") and "synthesis" in route.path:
                assert "POST" in route.methods


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegrationScenarios:
    """Test complete workflow scenarios"""

    @pytest.mark.asyncio
    async def test_full_synthesis_workflow(self, mock_db, mock_user):
        """Test complete synthesis workflow"""
        # Create multiple documents
        docs = [
            DocumentSource(type=DocumentType.TEXT, content="First document about AI."),
            DocumentSource(type=DocumentType.TEXT, content="Second document about ML."),
            DocumentSource(type=DocumentType.TEXT, content="Third document about data."),
        ]

        # Generate summary
        request = SynthesisRequest(
            documents=docs,
            synthesis_type=SynthesisType.SUMMARY,
            query="Summarize AI and ML concepts",
            include_sources=True,
        )

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert response.success
        assert response.result.metrics.documents_processed == 3
        assert len(response.result.sources) == 3

    @pytest.mark.asyncio
    async def test_synthesis_all_types(self, mock_db, mock_user, sample_text_document):
        """Test all synthesis types work correctly"""
        for synthesis_type in SynthesisType:
            request = SynthesisRequest(
                documents=[sample_text_document], synthesis_type=synthesis_type
            )

            response = await generate_synthesis(
                request=request, db=mock_db, tenant_id=1, current_user=mock_user
            )

            assert response.success
            assert response.result.synthesis_type == synthesis_type

    @pytest.mark.asyncio
    async def test_synthesis_all_document_types(self, mock_db, mock_user):
        """Test synthesis with all document types"""
        docs = [
            DocumentSource(type=DocumentType.TEXT, content="Text content"),
            DocumentSource(type=DocumentType.URL, url="https://example.com"),
            DocumentSource(type=DocumentType.FILE, file_path="/path/to/file"),
            DocumentSource(type=DocumentType.KNOWLEDGE_BASE, knowledge_base_id="kb_1"),
        ]

        request = SynthesisRequest(documents=docs)

        response = await generate_synthesis(
            request=request, db=mock_db, tenant_id=1, current_user=mock_user
        )

        assert response.success
        assert response.result.metrics.documents_processed == 4
