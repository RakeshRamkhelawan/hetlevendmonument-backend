"""
Focus Builder Suggestion Service

AI-powered node suggestion service for Focus Mode Builder.
Uses LLM to analyze workflow context and suggest relevant nodes.

Based on Perplexity best practices for 2024-2025:
- Redis caching with SHA256 hash
- Multi-LLM fallback (Gemini -> DeepSeek)
- Prometheus metrics
- Phase-aware suggestions
"""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from enum import Enum
from typing import Any, cast

from pydantic import BaseModel, Field

from src.core.services.llm.tenant_deur import TenantTaalmodel

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================


class WorkflowPhase(str, Enum):
    """Phases in Focus Mode workflow building"""

    DISCOVER = "discover"
    ANALYZE = "analyze"
    CREATE = "create"
    DISTRIBUTE = "distribute"


class NodeCategory(str, Enum):
    """Categories of workflow nodes"""

    TRIGGER = "trigger"
    DATA = "data"
    AI = "ai"
    INTEGRATION = "integration"
    LOGIC = "logic"
    OUTPUT = "output"


# ============================================================================
# Pydantic Models
# ============================================================================


class WorkflowNode(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """Existing node in workflow"""

    id: str
    type: str
    label: str
    phase: str | None = None
    config: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


class GhostNodeSuggestion(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """AI-suggested ghost node"""

    id: str = Field(..., description="Unique suggestion ID")
    type: str = Field(..., description="Node type (trigger, data, ai, etc.)")
    label: str = Field(..., description="Human-readable label")
    agent_name: str = Field(..., description="Agent to use for this node")
    description: str = Field(..., description="Why this node is suggested")
    phase: WorkflowPhase = Field(..., description="Which phase this belongs to")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    config: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    connect_after: str | None = Field(default=None, description="Node ID to connect after")


class SuggestionRequest(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """Request for node suggestions"""

    prompt: str = Field(..., min_length=3, max_length=1000)
    current_nodes: list[str] = Field(default_factory=list, description="IDs of current nodes")
    phase: WorkflowPhase = Field(default=WorkflowPhase.DISCOVER)
    workflow_context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class SuggestionResponse(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """Response with ghost node suggestions"""

    success: bool
    message: str
    suggestions: list[GhostNodeSuggestion] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    generation_time_ms: float = 0
    cache_hit: bool = False
    llm_provider: str | None = None


# ============================================================================
# Agent Registry (for suggestion context)
# ============================================================================

AVAILABLE_AGENTS = [
    # Triggers
    {
        "name": "schedule_agent",
        "type": "trigger",
        "phase": "discover",
        "description": "Schedule tasks with cron expressions",
    },
    {
        "name": "webhook_trigger",
        "type": "trigger",
        "phase": "discover",
        "description": "Trigger on incoming webhooks",
    },
    {
        "name": "file_watcher",
        "type": "trigger",
        "phase": "discover",
        "description": "Watch for file changes",
    },
    # Data
    {
        "name": "database_query",
        "type": "data",
        "phase": "discover",
        "description": "Query PostgreSQL/MySQL databases",
    },
    {
        "name": "http_request",
        "type": "data",
        "phase": "discover",
        "description": "Make HTTP/REST API calls",
    },
    {
        "name": "file_reader",
        "type": "data",
        "phase": "discover",
        "description": "Read files (CSV, JSON, XML)",
    },
    # AI/Analysis
    {
        "name": "llm_summarizer",
        "type": "ai",
        "phase": "analyze",
        "description": "Summarize text with LLM",
    },
    {
        "name": "sentiment_analyzer",
        "type": "ai",
        "phase": "analyze",
        "description": "Analyze sentiment of text",
    },
    {
        "name": "entity_extractor",
        "type": "ai",
        "phase": "analyze",
        "description": "Extract entities from text",
    },
    {
        "name": "classifier",
        "type": "ai",
        "phase": "analyze",
        "description": "Classify content into categories",
    },
    # Create/Transform
    {
        "name": "data_transformer",
        "type": "logic",
        "phase": "create",
        "description": "Transform data formats",
    },
    {
        "name": "content_generator",
        "type": "ai",
        "phase": "create",
        "description": "Generate content with AI",
    },
    {
        "name": "template_renderer",
        "type": "logic",
        "phase": "create",
        "description": "Render templates with data",
    },
    {
        "name": "image_processor",
        "type": "logic",
        "phase": "create",
        "description": "Process and manipulate images",
    },
    # Distribution
    {
        "name": "slack_agent",
        "type": "integration",
        "phase": "distribute",
        "description": "Send messages to Slack",
    },
    {
        "name": "email_agent",
        "type": "integration",
        "phase": "distribute",
        "description": "Send emails via SMTP",
    },
    {
        "name": "notification_agent",
        "type": "integration",
        "phase": "distribute",
        "description": "Send push notifications",
    },
    {
        "name": "github_integration",
        "type": "integration",
        "phase": "distribute",
        "description": "Interact with GitHub API",
    },
    {
        "name": "jira_integration",
        "type": "integration",
        "phase": "distribute",
        "description": "Create/update JIRA issues",
    },
    {
        "name": "webhook_sender",
        "type": "output",
        "phase": "distribute",
        "description": "Send outgoing webhooks",
    },
]


# ============================================================================
# Keyword Detection
# ============================================================================

KEYWORD_PATTERNS = {
    # Triggers
    "schedule": [
        "daily",
        "weekly",
        "hourly",
        "cron",
        "every",
        "scheduled",
        "timer",
        "interval",
    ],
    "webhook": ["webhook", "api call", "incoming", "trigger", "event"],
    # Data sources
    "database": ["database", "db", "sql", "query", "postgres", "mysql", "data"],
    "api": ["api", "rest", "http", "fetch", "request", "endpoint"],
    "file": ["file", "csv", "json", "xml", "read", "import", "upload"],
    # AI/Analysis
    "summarize": ["summarize", "summary", "tldr", "condense", "brief"],
    "sentiment": ["sentiment", "emotion", "feeling", "positive", "negative"],
    "classify": ["classify", "categorize", "sort", "label", "tag"],
    # Integrations
    "slack": ["slack", "channel", "message", "notify team"],
    "email": ["email", "mail", "send", "inbox", "smtp"],
    "github": ["github", "repo", "repository", "commit", "pr", "pull request"],
    "jira": ["jira", "ticket", "issue", "sprint", "agile"],
}


def detect_keywords(text: str) -> list[str]:
    """Detect keywords from user input"""
    text_lower = text.lower()
    detected: list[str] = []
    for category, keywords in KEYWORD_PATTERNS.items():
        for keyword in keywords:
            if keyword in text_lower:
                if category not in detected:
                    detected.append(category)
                break

    return detected


# ============================================================================
# Cache Utilities
# ============================================================================


def generate_cache_key(prompt: str, nodes: list[str], phase: str, tenant_id: int) -> str:
    """Generate cache key using SHA256 hash"""
    data = json.dumps(
        {
            "prompt": prompt.strip().lower(),
            "nodes": sorted(nodes),
            "phase": phase,
            "tenant_id": tenant_id,
        },
        sort_keys=True,
    )
    return f"focus_suggest:{hashlib.sha256(data.encode()).hexdigest()[:16]}"


# ============================================================================
# Focus Suggestion Service
# ============================================================================


class FocusSuggestionService:
    """
    AI-powered suggestion service for Focus Mode Builder.

    Features:
    - Multi-LLM support (Gemini, DeepSeek)
    - Redis caching
    - Phase-aware suggestions
    - Keyword detection
    - Ghost node positioning
    """

    def __init__(self, tenant_id: int = 1, correlation_id: str | None = None) -> None:
        self.tenant_id = tenant_id
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        self.redis_client: Any = None
        self.cache_ttl = 300  # 5 minutes

        # Initialize LLM client
        self._init_llm_client()

        # Try to initialize Redis
        self._init_redis()

    def _init_llm_client(self) -> None:
        """Het taalmodel is de keuze van de TENANT (ADR-041 B14): een deur, geen eigen client.

        Hier stond Gemini en, als terugval op het bestaan van een sleutel, DeepSeek: de promptteksten van
        een klant gingen naar een leverancier die hij niet koos. `llm_provider` wordt na een aanroep gezet op
        de verwerker die het antwoord gaf, of op `regels` als er een regelgebaseerd antwoord kwam.
        """
        self._taalmodel = TenantTaalmodel(self.tenant_id)
        self.llm_provider = "onbekend"

    def _init_redis(self) -> None:
        """Initialize Redis client for caching"""
        try:
            import asyncio
            from src.core.typing import create_async_redis_client

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            self.redis_client = asyncio.get_event_loop().run_until_complete(
                create_async_redis_client(redis_url)
            )
            logger.info(f"[{self.correlation_id}] Redis cache initialized")
        except Exception as e:
            logger.warning(f"[{self.correlation_id}] Redis unavailable: {e}")
            self.redis_client = None

    async def get_suggestions(self, request: SuggestionRequest) -> SuggestionResponse:
        """
        Generate ghost node suggestions based on user prompt.

        Args:
            request: SuggestionRequest with prompt, current nodes, and phase

        Returns:
            SuggestionResponse with ghost nodes and keywords
        """
        start_time = time.time()

        # Detect keywords
        keywords = detect_keywords(request.prompt)

        # Check cache
        cache_key = generate_cache_key(
            request.prompt,
            request.current_nodes,
            request.phase.value,
            self.tenant_id,
        )

        cached = await self._get_cached(cache_key)
        if cached:
            cached["cache_hit"] = True
            cached["generation_time_ms"] = (time.time() - start_time) * 1000
            return SuggestionResponse(**cached)

        # Generate suggestions
        try:
            suggestions = await self._generate_llm_suggestions(request, keywords)

            # Position ghost nodes
            suggestions = self._position_ghost_nodes(suggestions, len(request.current_nodes))

            response_data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "success": True,
                "message": f"Generated {len(suggestions)} suggestions based on your input.",
                "suggestions": [s.dict() for s in suggestions],
                "keywords": keywords,
                "generation_time_ms": (time.time() - start_time) * 1000,
                "cache_hit": False,
                "llm_provider": self.llm_provider,
            }

            # Cache result
            await self._set_cached(cache_key, response_data)

            return SuggestionResponse(**response_data)

        except Exception as e:
            logger.error(f"[{self.correlation_id}] Suggestion generation failed: {e}")
            return SuggestionResponse(
                success=False,
                message="Failed to generate suggestions",
                suggestions=[],
                keywords=keywords,
                generation_time_ms=(time.time() - start_time) * 1000,
            )

    async def _generate_llm_suggestions(
        self, request: SuggestionRequest, keywords: list[str]
    ) -> list[GhostNodeSuggestion]:
        """Generate suggestions using LLM"""

        system_prompt = self._build_system_prompt(request.phase)
        user_prompt = f"""User request: "{request.prompt}"

Current workflow phase: {request.phase.value}
Existing nodes: {len(request.current_nodes)}
Detected keywords: {", ".join(keywords) if keywords else "none"}

Generate 2-4 ghost node suggestions that would help complete this workflow.
Return ONLY valid JSON array."""

        try:
            response = await self._taalmodel.tekst(
                user_prompt, systeem=system_prompt, temperature=0.4, max_tokens=1500
            )

            # Parse response
            suggestions = self._parse_llm_response(response, request.phase)
            self.llm_provider = await self._taalmodel.provider_naam()
            return suggestions

        except Exception as e:
            logger.error(
                f"[{self.correlation_id}] LLM call failed ({type(e).__name__}): "
                "regelgebaseerde suggesties, geen ander model"
            )
            # Geen ander MODEL: de regelgebaseerde suggesties zijn vaste sjablonen en heten zo in het antwoord.
            self.llm_provider = "regels"
            return self._generate_rule_based_suggestions(request, keywords)

    def _build_system_prompt(self, phase: WorkflowPhase) -> str:
        """Build system prompt for LLM"""
        agents_json = json.dumps(AVAILABLE_AGENTS, indent=2)

        return f"""You are a workflow architect AI. Generate ghost node suggestions for a workflow builder.

**Available Agents:**
{agents_json}

**Current Phase:** {phase.value}
- discover: Data collection, triggers, sources
- analyze: AI processing, analysis, extraction
- create: Content generation, transformation
- distribute: Output, notifications, integrations

**Output Format (STRICT JSON array only):**
[
  {{
    "id": "ghost_1",
    "type": "trigger|data|ai|logic|integration|output",
    "label": "Human-readable name",
    "agent_name": "exact_agent_name_from_list",
    "description": "Why this node helps",
    "phase": "{phase.value}",
    "confidence": 0.85,
    "config": {{}}
  }}
]

Return 2-4 suggestions. Use ONLY agent names from the list. Return ONLY JSON, no markdown."""

    def _parse_llm_response(self, response: str, phase: WorkflowPhase) -> list[GhostNodeSuggestion]:
        """Parse LLM response into GhostNodeSuggestion objects"""
        # Remove markdown code blocks
        if response.startswith("```"):
            if "```json" in response:
                json_start = response.find("```json") + 7
            else:
                json_start = response.find("```") + 3
            json_end = response.rfind("```")
            if json_end > json_start:
                response = response[json_start:json_end].strip()

        try:
            data = json.loads(response)
            if not isinstance(data, list):
                data = [data]

            suggestions: list[GhostNodeSuggestion] = []
            for item in data:
                try:
                    # Ensure phase is valid
                    item_phase = item.get("phase", phase.value)
                    if item_phase not in [p.value for p in WorkflowPhase]:
                        item_phase = phase.value

                    suggestions.append(
                        GhostNodeSuggestion(
                            id=item.get("id", f"ghost_{uuid.uuid4().hex[:8]}"),
                            type=item.get("type", "logic"),
                            label=item.get("label", "Suggested Node"),
                            agent_name=item.get("agent_name", "data_transformer"),
                            description=item.get("description", "AI-suggested node"),
                            phase=WorkflowPhase(item_phase),
                            config=item.get("config", {}),
                            confidence=float(item.get("confidence", 0.7)),
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to parse suggestion: {e}")
                    continue

            return suggestions

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON: {e}")
            return []

    def _generate_rule_based_suggestions(
        self, request: SuggestionRequest, keywords: list[str]
    ) -> list[GhostNodeSuggestion]:
        """Generate suggestions based on keywords (fallback)"""
        suggestions: list[GhostNodeSuggestion] = []
        # Map keywords to agents
        keyword_agent_map = {
            "schedule": ("schedule_agent", "trigger", "Schedule-based trigger"),
            "webhook": ("webhook_trigger", "trigger", "Incoming webhook trigger"),
            "database": ("database_query", "data", "Query your database"),
            "api": ("http_request", "data", "Make API requests"),
            "summarize": ("llm_summarizer", "ai", "Summarize with AI"),
            "sentiment": ("sentiment_analyzer", "ai", "Analyze sentiment"),
            "slack": ("slack_agent", "integration", "Send to Slack"),
            "email": ("email_agent", "integration", "Send email"),
            "github": ("github_integration", "integration", "GitHub integration"),
            "jira": ("jira_integration", "integration", "JIRA integration"),
        }

        for keyword in keywords[:3]:  # Max 3 suggestions from keywords
            if keyword in keyword_agent_map:
                agent_name, node_type, description = keyword_agent_map[keyword]
                agent = next((a for a in AVAILABLE_AGENTS if a["name"] == agent_name), None)

                if agent:
                    suggestions.append(
                        GhostNodeSuggestion(
                            id=f"ghost_{uuid.uuid4().hex[:8]}",
                            type=node_type,
                            label=agent["description"].split()[0] + " Node",
                            agent_name=agent_name,
                            description=description,
                            phase=WorkflowPhase(agent.get("phase", request.phase.value)),
                            confidence=0.75,
                        )
                    )

        # Add phase-appropriate default if no keywords matched
        if not suggestions:
            phase_defaults = {
                WorkflowPhase.DISCOVER: (
                    "schedule_agent",
                    "trigger",
                    "Start with a trigger",
                ),
                WorkflowPhase.ANALYZE: ("llm_summarizer", "ai", "Add AI analysis"),
                WorkflowPhase.CREATE: (
                    "data_transformer",
                    "logic",
                    "Transform your data",
                ),
                WorkflowPhase.DISTRIBUTE: (
                    "slack_agent",
                    "integration",
                    "Send results",
                ),
            }

            agent_name, node_type, description = phase_defaults[request.phase]
            suggestions.append(
                GhostNodeSuggestion(
                    id=f"ghost_{uuid.uuid4().hex[:8]}",
                    type=node_type,
                    label=f"Suggested {request.phase.value.capitalize()} Node",
                    agent_name=agent_name,
                    description=description,
                    phase=request.phase,
                    confidence=0.6,
                )
            )

        return suggestions

    def _position_ghost_nodes(
        self, suggestions: list[GhostNodeSuggestion], existing_count: int
    ) -> list[GhostNodeSuggestion]:
        """Position ghost nodes on canvas"""
        base_x = 100 + (existing_count % 3) * 200
        base_y = 100 + (existing_count // 3) * 150

        for i, suggestion in enumerate(suggestions):
            suggestion.position = {
                "x": base_x + (i % 2) * 200,
                "y": base_y + (i // 2) * 150 + 50,  # Offset from existing
            }

        return suggestions

    async def _get_cached(
        self, key: str
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get cached response"""
        if not self.redis_client:
            return None

        try:
            cached = await self.redis_client.get(key)
            if cached:
                return cast(
                    dict[str, Any], json.loads(cached)  # TODO(TYPE): replace Any with concrete type
                )  # TODO(TYPE): replace Any with concrete type
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")

        return None

    async def _set_cached(
        self, key: str, data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Cache response"""
        if not self.redis_client:
            return

        try:
            await self.redis_client.setex(key, self.cache_ttl, json.dumps(data))
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")


# ============================================================================
# Factory Function
# ============================================================================


async def create_focus_suggestion_service(
    tenant_id: int = 1, correlation_id: str | None = None
) -> FocusSuggestionService:
    """Factory function to create FocusSuggestionService"""
    return FocusSuggestionService(tenant_id=tenant_id, correlation_id=correlation_id)
