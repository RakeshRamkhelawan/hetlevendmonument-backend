# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Workflow builder sub-router (SP-API-003 Dag 2).

Routes:
    POST /api/v1/builder/keywords
    POST /api/v1/builder/suggest
    GET  /api/v1/builder/tools
    GET  /api/v1/builder/tools/{tool_id}
"""

import logging
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.auth.api_deps import get_current_user_dependency as get_current_user
from .dependencies import LLMService

router = APIRouter(
    prefix="/api/v1/builder",
    tags=["Workflow Builder"],
    dependencies=[Depends(get_current_user)],
)
logger = logging.getLogger(__name__)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class KeywordRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class KeywordResponse(BaseModel):
    keywords: list[str]
    confidence: float


class SuggestNodesRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)
    currentNodes: list[str] = Field(default_factory=list)
    phase: str = Field(default="discover")
    conversationLayer: int = Field(
        default=1, ge=1, le=3, description="1=Plan, 2=Refine, 3=Generate"
    )
    originalPlan: dict[str, Any] | None = Field(default=None, description="For Layer 2/3")


class GhostNodeSuggestion(BaseModel):
    id: str
    title: str
    description: str
    icon: str
    phase: str
    confidence: float
    suggestedPosition: dict[str, int]
    sourceKeyword: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class SuggestNodesResponse(BaseModel):
    suggestions: list[GhostNodeSuggestion] = Field(default_factory=list)
    message: str
    keywords: list[str]
    layer: int = 1
    plan_text: str | None = None
    phases: dict[str, list[str]] | None = None
    clarification_questions: list[str] | None = None


class InputType(str, Enum):
    STRING = "string"
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    SELECT = "select"
    JSON = "json"


class InputOption(BaseModel):
    label: str
    value: Any  # TODO(TYPE): replace Any with concrete type


class InputProperty(BaseModel):
    name: str
    label: str
    type: InputType
    description: str | None = None
    required: bool = True
    default: Any | None = None  # TODO(TYPE): replace Any with concrete type
    options: list[InputOption] | None = None
    placeholder: str | None = None


class NativeTool(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    category: str
    phase: str
    inputs: list[InputProperty] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


class ToolCatalogResponse(BaseModel):
    tools: list[NativeTool]
    categories: list[str]


# =============================================================================
# KEYWORD EXTRACTION
# =============================================================================

KEYWORD_PATTERNS: dict[str, list[str]] = {
    "email": ["email", "mail", "send", "notify", "notification"],
    "data": ["data", "database", "store", "save", "fetch", "get"],
    "ai": ["ai", "llm", "generate", "analyze", "summarize", "translate"],
    "social": ["social", "post", "tweet", "linkedin", "facebook", "instagram"],
    "report": ["report", "dashboard", "analytics", "chart", "metrics"],
    "webhook": ["webhook", "api", "http", "request", "endpoint"],
    "schedule": ["schedule", "cron", "timer", "recurring", "daily", "weekly"],
    "seo": ["seo", "keyword", "ranking", "search", "optimize"],
    "content": ["content", "blog", "article", "write", "copy"],
    "workflow": ["workflow", "automate", "automation", "flow", "process"],
}


def extract_keywords(text: str) -> list[str]:
    """Extract workflow-related keywords from text."""
    text_lower = text.lower()
    found: list[str] = []
    for category, patterns in KEYWORD_PATTERNS.items():
        for pattern in patterns:
            if pattern in text_lower:
                found.append(category)
                break
    return list(set(found))


# =============================================================================
# TOOL CATALOG
# =============================================================================

NATIVE_TOOLS: list[NativeTool] = [
    NativeTool(
        id="tool_email_send",
        name="Send Email",
        description="Send an email notification to specified recipients",
        icon="[email]",
        category="Communication",
        phase="distribute",
        inputs=[
            InputProperty(
                name="to",
                label="To Email",
                type=InputType.STRING,
                required=True,
                placeholder="user@example.com",
            ),
            InputProperty(
                name="subject",
                label="Subject",
                type=InputType.STRING,
                required=True,
                placeholder="Welcome aboard!",
            ),
            InputProperty(
                name="body",
                label="Email Body",
                type=InputType.TEXT,
                required=True,
                description="Supports HTML or plain text",
            ),
        ],
        outputs=["sent_status"],
    ),
    NativeTool(
        id="tool_llm_generate",
        name="AI Generate",
        description="Generate content using AI language models",
        icon="[ai]",
        category="AI",
        phase="create",
        inputs=[
            InputProperty(
                name="prompt",
                label="System Prompt",
                type=InputType.TEXT,
                required=True,
                description="Instructions for the AI",
            ),
            InputProperty(
                name="model",
                label="Model",
                type=InputType.SELECT,
                required=True,
                default="gpt-4",
                options=[
                    InputOption(label="GPT-4o", value="gpt-4o"),
                    InputOption(label="Gemini Pro", value="gemini-pro"),
                    InputOption(label="Claude 3.5 Sonnet", value="claude-3-5-sonnet"),
                ],
            ),
            InputProperty(
                name="temperature",
                label="Creativity (0-1)",
                type=InputType.NUMBER,
                required=False,
                default=0.7,
            ),
        ],
        outputs=["generated_text"],
    ),
    NativeTool(
        id="tool_data_fetch",
        name="Fetch Data",
        description="Retrieve data from external sources (API)",
        icon="[data]",
        category="Data",
        phase="discover",
        inputs=[
            InputProperty(
                name="url",
                label="API URL",
                type=InputType.STRING,
                required=True,
                placeholder="https://api.example.com/data",
            ),
            InputProperty(
                name="method",
                label="Method",
                type=InputType.SELECT,
                required=True,
                default="GET",
                options=[
                    InputOption(label="GET", value="GET"),
                    InputOption(label="POST", value="POST"),
                ],
            ),
            InputProperty(
                name="headers",
                label="Headers (JSON)",
                type=InputType.JSON,
                required=False,
                description='{"Authorization": "Bearer ..."}',
            ),
        ],
        outputs=["data"],
    ),
    NativeTool(
        id="tool_webhook_trigger",
        name="Webhook Trigger",
        description="Start workflow when webhook is called",
        icon="[webhook]",
        category="Triggers",
        phase="discover",
        inputs=[
            InputProperty(
                name="path",
                label="Unique Path",
                type=InputType.STRING,
                required=False,
                description="Auto-generated if empty",
            )
        ],
        outputs=["payload"],
    ),
    NativeTool(
        id="tool_seo_analyze",
        name="SEO Analysis",
        description="Analyze content for SEO optimization",
        icon="[seo]",
        category="SEO",
        phase="analyze",
        inputs=[
            InputProperty(
                name="content", label="Content / URL", type=InputType.STRING, required=True
            ),
            InputProperty(
                name="target_keywords",
                label="Target Keywords",
                type=InputType.STRING,
                required=True,
                description="Comma separated",
            ),
        ],
        outputs=["seo_score", "recommendations"],
    ),
    NativeTool(
        id="tool_social_post",
        name="Social Media Post",
        description="Post content to social media platforms",
        icon="[social]",
        category="Social",
        phase="distribute",
        inputs=[
            InputProperty(
                name="platform",
                label="Platform",
                type=InputType.SELECT,
                required=True,
                options=[
                    InputOption(label="Twitter / X", value="twitter"),
                    InputOption(label="LinkedIn", value="linkedin"),
                    InputOption(label="Facebook", value="facebook"),
                ],
            ),
            InputProperty(name="content", label="Post Content", type=InputType.TEXT, required=True),
            InputProperty(
                name="media_url", label="Image/Video URL", type=InputType.STRING, required=False
            ),
        ],
        outputs=["post_url"],
    ),
    NativeTool(
        id="tool_report_generate",
        name="Generate Report",
        description="Create a report from collected data",
        icon="[report]",
        category="Reports",
        phase="create",
        inputs=[
            InputProperty(
                name="data_source", label="Data Source", type=InputType.STRING, required=True
            ),
            InputProperty(
                name="format",
                label="Format",
                type=InputType.SELECT,
                required=True,
                default="pdf",
                options=[
                    InputOption(label="PDF", value="pdf"),
                    InputOption(label="HTML", value="html"),
                    InputOption(label="Excel", value="xlsx"),
                ],
            ),
        ],
        outputs=["report"],
    ),
    NativeTool(
        id="tool_schedule_cron",
        name="Schedule Task",
        description="Run workflow on a schedule",
        icon="[schedule]",
        category="Triggers",
        phase="discover",
        inputs=[
            InputProperty(
                name="cron_expression",
                label="Cron Expression",
                type=InputType.STRING,
                required=True,
                default="0 9 * * *",
                description="Every day at 9 AM",
            ),
            InputProperty(
                name="timezone",
                label="Timezone",
                type=InputType.STRING,
                required=False,
                default="UTC",
            ),
        ],
        outputs=["trigger_time"],
    ),
]

_KEYWORD_TO_TOOL: dict[str, str] = {
    "email": "tool_email_send",
    "ai": "tool_llm_generate",
    "data": "tool_data_fetch",
    "webhook": "tool_webhook_trigger",
    "seo": "tool_seo_analyze",
    "social": "tool_social_post",
    "report": "tool_report_generate",
    "schedule": "tool_schedule_cron",
    "content": "tool_llm_generate",
}


def get_tool_by_keyword(keyword: str) -> NativeTool | None:
    """Find the best matching tool for a keyword."""
    tool_id = _KEYWORD_TO_TOOL.get(keyword)
    if tool_id:
        return next((t for t in NATIVE_TOOLS if t.id == tool_id), None)
    return None


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.post("/keywords", response_model=KeywordResponse)
async def extract_keywords_endpoint(request: KeywordRequest) -> KeywordResponse:
    """Real-time keyword extraction from user input."""
    keywords = extract_keywords(request.text)
    return KeywordResponse(keywords=keywords, confidence=0.8 if keywords else 0.0)


@router.post("/suggest", response_model=SuggestNodesResponse)
async def suggest_nodes(request: SuggestNodesRequest) -> SuggestNodesResponse:
    """Analyze user prompt and suggest workflow nodes."""
    try:
        keywords = extract_keywords(request.prompt)
        suggestions: list[GhostNodeSuggestion] = []

        for i, keyword in enumerate(keywords):
            tool = get_tool_by_keyword(keyword)
            if tool and tool.id not in request.currentNodes:
                suggestions.append(
                    GhostNodeSuggestion(
                        id="ghost_%s_%s" % (keyword, i),
                        title=tool.name,
                        description=tool.description,
                        icon=tool.icon,
                        phase=tool.phase,
                        confidence=0.85,
                        suggestedPosition={"x": 300 + (i * 250), "y": 100},
                        sourceKeyword=keyword,
                    )
                )

        if not suggestions:
            try:
                # Hier werd de prompt van de gebruiker naar het platformtaalmodel gestuurd, zonder
                # tenant en zonder dat het antwoord ergens gebruikt werd: de suggestie hieronder staat
                # er onafhankelijk van. Weg (brief 2026-10-19, ADR-041 B14).
                suggestions.append(
                    GhostNodeSuggestion(
                        id="ghost_ai_1",
                        title="AI Generate",
                        description="Generate content based on: %s..." % request.prompt[:50],
                        icon="[ai]",
                        phase="create",
                        confidence=0.7,
                        suggestedPosition={"x": 300, "y": 100},
                        sourceKeyword="ai",
                    )
                )
            except Exception as e:
                logger.warning("LLM suggestion failed: %s: %s", type(e).__name__, e)

        if suggestions:
            message = "I found %s tool%s that could help. Accept or modify them as needed." % (
                len(suggestions),
                "s" if len(suggestions) > 1 else "",
            )
        else:
            message = "I couldn't find specific tools for your request. Try describing what you want to achieve in more detail."

        return SuggestNodesResponse(
            suggestions=suggestions,
            message=message,
            keywords=keywords,
        )

    except Exception as e:
        logger.error("Suggest nodes error: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate suggestions") from e


@router.get("/tools", response_model=ToolCatalogResponse)
async def get_tool_catalog() -> ToolCatalogResponse:
    """Fetch all available tools (white-labeled ActivePieces)."""
    categories = list({t.category for t in NATIVE_TOOLS})
    return ToolCatalogResponse(tools=NATIVE_TOOLS, categories=sorted(categories))


@router.get("/tools/{tool_id}", response_model=NativeTool)
async def get_tool_details(tool_id: str) -> NativeTool:
    """Get details for a specific tool."""
    tool = next((t for t in NATIVE_TOOLS if t.id == tool_id), None)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool
