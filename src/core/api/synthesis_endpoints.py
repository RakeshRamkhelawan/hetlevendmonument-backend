# orphan:exempt reason: legacy flat file, replaced by src/core/api/v1/synthesis/ (SP-API-006)
from src.core.api.v1.synthesis.router import router  # noqa: F401
from src.core.api.v1.synthesis.dependencies import get_tenant  # noqa: F401
from src.core.api.v1.synthesis.synthesis_router import generate_synthesis  # noqa: F401
from src.core.api.v1.synthesis.synthesis_service import (  # noqa: F401
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
    generate_synthesis_content,
    generate_translation,
    get_user_id,
)
