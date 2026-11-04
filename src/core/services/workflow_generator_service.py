"""
VIBE_BE_001: WorkflowGeneratorAgent Production Service

This service wraps the POC workflow generation logic with production features:
- Multi-tenant agent filtering via tenant_id
- Retry logic with exponential backoff
- Prometheus metrics
- Structured logging with correlation IDs
- WebSocket streaming support

Based on: docs/implementation/VIBE_DETAILED_MASTERPROMPTS.md
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Literal, Any, cast
from collections.abc import Callable, Awaitable

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.services.llm.tenant_deur import TenantTaalmodel

logger = logging.getLogger(__name__)


# ============================================================================
# Surgical Mode Constants
# ============================================================================

SURGICAL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "patches": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "required": ["op", "node"],
                "properties": {
                    "op": {"type": "string", "enum": ["add", "remove", "update"]},
                    "node": {
                        "type": "object",
                        "required": ["id", "type"],
                        "properties": {
                            "id": {"type": "string"},
                            "type": {"type": "string"},
                            "data": {"type": "object"},
                        },
                    },
                },
            },
        }
    },
    "required": ["patches"],
}

SURGICAL_SYSTEM_PROMPT = (
    "Je bent een workflow editor. Je output is UITSLUITEND geldig JSON conform het opgegeven schema. "
    "Geef alleen de minimale node-wijzigingen terug die nodig zijn. "
    "Voeg geen uitleg toe buiten het JSON-object."
)


# ============================================================================
# Pydantic Models
# ============================================================================


class WorkflowNode(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """Node in workflow graph."""

    id: str = Field(..., description="Unique node ID")
    agent_name: str = Field(..., description="Agent name from registry")
    label: str = Field(..., description="Human-readable label")
    config: dict[str, object] = Field(default_factory=dict)
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})


class WorkflowEdge(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """Edge connecting two nodes."""

    id: str = Field(..., description="Unique edge ID")
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    condition: str | None = None


class WorkflowDefinition(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """Complete workflow structure."""

    name: str = Field(..., min_length=3, max_length=100)
    description: str | None = Field(None, max_length=500)
    nodes: list[WorkflowNode] = Field(..., min_length=1, max_length=50)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class GenerateWorkflowRequest(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """API request for workflow generation."""

    prompt: str = Field(..., min_length=10, max_length=2000)
    complexity: str = Field(default="medium", pattern="^(simple|medium|complex)$")
    stream: bool = Field(default=False, description="Enable WebSocket streaming")


class GenerateWorkflowResponse(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """API response for workflow generation."""

    success: bool
    workflow: dict[str, object] | None = None
    error: str | None = None
    generation_time_ms: float = 0
    correlation_id: str = ""
    is_mock: bool = False


class NodeExplanation(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    node_id: str
    explanation: str
    confidence: Literal["high", "medium", "low"] = "high"
    confidence_reason: str | None = None


class SuggestionChip(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    id: str
    label: str
    prompt: str


class WorkflowGeneratorOutput(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """Extended output schema including node explanations and suggestion chips."""

    name: str
    description: str | None = None
    nodes: list[dict[str, object]]
    edges: list[dict[str, object]] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    node_explanations: list[NodeExplanation] = Field(default_factory=list)
    suggestion_chips: list[SuggestionChip] = Field(default_factory=list)


FALLBACK_CHIPS = [
    SuggestionChip(id="retry", label="Probeer opnieuw", prompt="Genereer een nieuwe versie."),
    SuggestionChip(
        id="simplify",
        label="Vereenvoudig",
        prompt="Maak een eenvoudigere versie met max 3 stappen.",
    ),
    SuggestionChip(id="reset", label="Begin opnieuw", prompt="__reset__"),
]


# ============================================================================
# Prometheus Metrics (import when prometheus_client is available)
# ============================================================================

workflow_generation_counter: object = None
workflow_generation_duration: object = None
workflow_validation_errors: object = None

try:
    from prometheus_client import Counter, Histogram

    workflow_generation_counter = Counter(
        "vibe_workflow_generation_total",
        "Workflow generation requests",
        ["tenant_id", "status", "complexity"],
    )

    workflow_generation_duration = Histogram(
        "vibe_workflow_generation_duration_seconds",
        "Workflow generation time",
        ["tenant_id"],
        buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    )

    workflow_validation_errors = Counter(
        "vibe_workflow_validation_errors_total",
        "Validation errors",
        ["tenant_id", "error_type"],
    )

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    logger.warning("prometheus_client not installed, metrics disabled")


# ============================================================================
# Default Agent Registry (fallback when DB unavailable)
# ============================================================================

DEFAULT_AGENTS = [
    {
        "name": "schedule_agent",
        "type": "TECHNICAL",
        "description": "Schedule tasks with cron",
    },
    {"name": "slack_agent", "type": "TECHNICAL", "description": "Slack integration"},
    {"name": "email_agent", "type": "TECHNICAL", "description": "Send emails"},
    {
        "name": "llm_summarizer",
        "type": "ANALYTICAL",
        "description": "Summarize text with LLM",
    },
    {"name": "database_query", "type": "TECHNICAL", "description": "Query PostgreSQL"},
    {"name": "http_request", "type": "TECHNICAL", "description": "Make HTTP requests"},
    {"name": "file_processor", "type": "TECHNICAL", "description": "Process files"},
    {
        "name": "jira_integration",
        "type": "TECHNICAL",
        "description": "JIRA API integration",
    },
    {
        "name": "github_integration",
        "type": "TECHNICAL",
        "description": "GitHub API integration",
    },
    {
        "name": "sentiment_analyzer",
        "type": "ANALYTICAL",
        "description": "Analyze sentiment",
    },
    {
        "name": "data_transformer",
        "type": "TECHNICAL",
        "description": "Transform data formats",
    },
    {
        "name": "notification_agent",
        "type": "TECHNICAL",
        "description": "Send notifications",
    },
]


# ============================================================================
# WorkflowGeneratorAgent Service
# ============================================================================


class GeneratorValidatieFout(Exception):
    """Een voorstel van het taalmodel dat niet klopt, met een tekst voor de klant.

    Pydantic's `ValidationError` laat zich niet met een tekst bouwen (`ValidationError("...")` geeft een TypeError, dus de
    melding verdween in "LLM error: ValidationError.__new__() ..."). Deze fout draagt de Nederlandse tekst wel.
    """


class WorkflowGeneratorAgent:
    """
    Production-grade workflow generation service.

    Features:
    - Multi-tenant agent filtering
    - Retry logic with exponential backoff
    - Prometheus metrics
    - Correlation ID logging
    - WebSocket streaming support
    """

    def __init__(
        self,
        tenant_id: int = 1,
        db_session: AsyncSession | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.db_session = db_session
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        self.max_retries = 3
        self.retry_base_delay = 1.0
        self._agents_cache: list[dict[str, object]] | None = None
        self.is_mock = False

        # Het taalmodel is de keuze van de TENANT (ADR-041 B14): een deur, geen eigen client met een eigen
        # leverancier. Hier stond een keuze op `LLM_PROVIDER` en op welke sleutel er in de omgeving was
        # (Gemini, DeepSeek, Qwen, mock); bij een onbekende provider (en `mistral` was onbekend) zelfs
        # Gemini, dan DeepSeek, dan Qwen. Het verzoek van de klant ging dan naar een leverancier die hij
        # niet koos. Een storing is nu een fout en geen ander model of een namaakmodel.
        self._taalmodel = TenantTaalmodel(tenant_id)

    async def get_uitvoerbare_agents(self) -> list[dict[str, object]]:
        """De agents die een workflowstap voor deze klant echt kan uitvoeren (agentstap dag 2).

        De generator mag ALLEEN deze agents voorstellen: een voorstel met een andere agent (een koppeling, een agent uit de
        catalogus zonder uitvoering) zou een stap geven die bij het starten faalt. `get_available_agents` hieronder blijft
        de bredere lijst voor andere schermen. `importlib`: zie de koppelingsmeting van `services`.
        """
        import importlib

        stap = importlib.import_module("src.core.als.agents.workflow_stap")
        lijst = await stap.uitvoerbare_agents_voor_klant(self.tenant_id)
        return [
            {
                "name": agent["agent_id"],
                "type": "AI-agent",
                "description": f"{agent['naam']}: {agent['omschrijving']}",
                "source": "uitvoerbaar",
            }
            for agent in lijst
        ]

    async def get_available_agents(
        self,
    ) -> list[dict[str, object]]:
        """
        Get available agents for this tenant.

        Queries registered_agents table if DB session is available,
        merges with ActivePieces integrations if available,
        otherwise returns default agents.
        """
        if self._agents_cache:
            return self._agents_cache

        agents: list[dict[str, object]] = []
        # 1. Query from database with tenant filtering
        if self.db_session:
            try:
                from sqlalchemy import select

                from src.core.agents.models import RegisteredAgent

                query = select(RegisteredAgent).where(
                    RegisteredAgent.tenant_id == self.tenant_id,
                    RegisteredAgent.is_active.is_(True),
                )
                result = await self.db_session.execute(query)
                db_agents = [
                    {
                        "name": agent.name,
                        "type": agent.agent_type,
                        "description": agent.description or "",
                        "source": "database",
                    }
                    for agent in result.scalars()
                ]
                agents.extend(db_agents)
                logger.info(f"[{self.correlation_id}] Loaded {len(db_agents)} agents from DB")
            except Exception as e:
                logger.warning(f"[{self.correlation_id}] DB query failed: {e}")

        # 2. Merge ActivePieces integrations as virtual agents
        try:
            from src.core.activepieces.service import ActivePiecesService

            ap_service = ActivePiecesService()
            pieces = await ap_service.get_all_pieces()

            if pieces and isinstance(pieces, list):
                for piece in pieces[:50]:  # Limit to 50 pieces
                    if isinstance(piece, dict):
                        piece_name = piece.get("name", "unknown")
                        agents.append(
                            {
                                "name": f"ap_{piece_name}",
                                "type": "INTEGRATION",
                                "description": piece.get(
                                    "description", f"ActivePieces: {piece_name}"
                                ),
                                "source": "activepieces",
                                "piece_name": piece_name,
                                "displayName": piece.get("displayName", piece_name),
                                "logoUrl": piece.get("logoUrl"),
                                "categories": piece.get("categories", []),
                            }
                        )
                logger.info(
                    f"[{self.correlation_id}] Merged {len(pieces)} ActivePieces integrations"
                )
        except Exception as e:
            logger.debug(f"[{self.correlation_id}] ActivePieces unavailable: {e}")

        # 3. Fallback to defaults if nothing found
        if not agents:
            agents = cast(list[dict[str, object]], DEFAULT_AGENTS.copy())
            logger.info(f"[{self.correlation_id}] Using {len(agents)} default agents")
        else:
            # Add any missing default agents
            existing_names = {a["name"] for a in agents}
            for default_agent in DEFAULT_AGENTS:
                if default_agent["name"] not in existing_names:
                    agents.append({**default_agent, "source": "default"})

        self._agents_cache = agents
        return agents

    async def generate_workflow(
        self,
        user_prompt: str,
        complexity: str = "medium",
        # TODO(TYPE): replace Any with concrete type
        stream_callback: Callable[..., Awaitable[Any]]
        | None = None,  # TODO(TYPE): replace Any with concrete type
        mode: Literal["full", "surgical"] = "full",
    ) -> tuple[bool, WorkflowDefinition | None, str | None]:
        """
        Generate a workflow from natural language prompt.

        Args:
            user_prompt: Natural language description of desired workflow
            complexity: simple/medium/complex (affects node count)
            stream_callback: Optional async callback for streaming updates
            mode: "full" generates a complete new workflow; "surgical" emits targeted
                  node_patch events for incremental edits to an existing canvas.

        Returns:
            (success, workflow_definition, error_message)
            In surgical mode always returns (True, None, None) -- results are
            delivered via stream_callback.
        """
        if mode == "surgical":
            await self._generate_surgical(user_prompt, stream_callback)
            return True, None, None

        return await self._generate_full(user_prompt, complexity, stream_callback)

    async def _generate_full(
        self,
        user_prompt: str,
        complexity: str = "medium",
        # TODO(TYPE): replace Any with concrete type
        stream_callback: Callable[..., Awaitable[Any]]
        | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[bool, WorkflowDefinition | None, str | None]:
        """Full workflow generation (original logic)."""
        start_time = time.time()
        step_times: dict[str, float] = {}
        # Get available agents
        agents_start = time.time()
        agents = await self.get_uitvoerbare_agents()
        agent_names = {cast(str, agent["name"]) for agent in agents}
        step_times["get_agents"] = time.time() - agents_start
        if not agents:
            # Geen enkele agent te kiezen (pakket uit): niet het taalmodel bellen om een workflow te bedenken die niet kan
            # draaien, maar de klant vertellen wat hij moet doen.
            import importlib

            uitleg = importlib.import_module("src.core.als.agents.workflow_stap").GEEN_AGENTS_UITLEG
            if stream_callback:
                await stream_callback({"type": "generation_failed", "error": uitleg})
            return False, None, str(uitleg)
        logger.info(
            f"[{self.correlation_id}] [TIMER]  Get agents: {step_times['get_agents']:.3f}s ({len(agents)} agents)"
        )

        # Build system prompt
        prompt_start = time.time()
        system_prompt = self._build_system_prompt(agents, complexity)
        step_times["build_prompt"] = time.time() - prompt_start
        logger.info(f"[{self.correlation_id}] [TIMER]  Build prompt: {step_times['build_prompt']:.3f}s")

        # Retry loop
        last_error = None
        for attempt in range(self.max_retries):
            try:
                if stream_callback:
                    await stream_callback(
                        {
                            "type": "generation_started",
                            "attempt": attempt + 1,
                            "correlation_id": self.correlation_id,
                        }
                    )

                # Generate workflow via LLM
                llm_start = time.time()
                logger.info(
                    f"[{self.correlation_id}] [LAUNCH] Starting LLM call (attempt {attempt + 1}/{self.max_retries})..."
                )
                workflow_json = await self._call_llm(system_prompt, user_prompt)
                step_times["llm_call"] = time.time() - llm_start
                logger.info(f"[{self.correlation_id}] [TIMER]  LLM call: {step_times['llm_call']:.3f}s")

                if stream_callback:
                    await stream_callback(
                        {
                            "type": "json_generated",
                            "workflow": workflow_json,
                            "llm_time_ms": round(step_times["llm_call"] * 1000, 2),
                        }
                    )

                # Validate workflow
                validate_start = time.time()
                workflow = await self._validate_workflow(workflow_json, agent_names)
                step_times["validate"] = time.time() - validate_start
                logger.info(f"[{self.correlation_id}] [TIMER]  Validate: {step_times['validate']:.3f}s")

                # Emit node_proposed events -- one per node, with edges targeting that node
                if stream_callback and workflow:
                    # Parse extended output for explanations + chips
                    try:
                        extended = WorkflowGeneratorOutput.model_validate(workflow_json)
                        explanations = {e.node_id: e for e in extended.node_explanations}
                        chips = extended.suggestion_chips or FALLBACK_CHIPS
                    except Exception:
                        explanations = {}
                        chips = FALLBACK_CHIPS

                    edges_by_target: dict[str, list[dict[str, str]]] = {}
                    for edge in workflow.edges:
                        edges_by_target.setdefault(edge.target, []).append(
                            {"source": edge.source, "target": edge.target}
                        )
                    proposal_id = str(uuid.uuid4())
                    for node in workflow.nodes:
                        await stream_callback(
                            {
                                "type": "node_proposed",
                                "proposal_id": proposal_id,
                                "node": {
                                    "id": node.id,
                                    "type": node.agent_name,
                                    "data": {
                                        "label": node.label,
                                        **node.config,
                                        # Na de config: het taalmodel mag de gevalideerde agent niet overschrijven.
                                        # Een agentstap draait de gekozen agent met deze opdracht.
                                        "agent_id": node.agent_name,
                                        "instruction": str(node.config.get("instruction") or node.label),
                                    },
                                    "position": node.position,
                                },
                                "edges": edges_by_target.get(node.id, []),
                            }
                        )
                        # Emit explanation immediately after each node
                        expl = explanations.get(node.id)
                        if expl:
                            await stream_callback(
                                {
                                    "type": "node_explanation",
                                    "node_id": node.id,
                                    "content": expl.explanation,
                                    "confidence": expl.confidence,
                                    "confidence_reason": expl.confidence_reason,
                                    "proposal_id": proposal_id,
                                }
                            )
                    await stream_callback(
                        {
                            "type": "proposal_complete",
                            "proposal_id": proposal_id,
                            "node_count": len(workflow.nodes),
                            "explanation": (
                                f"Workflow '{workflow.name}' gegenereerd "
                                f"met {len(workflow.nodes)} nodes."
                            ),
                        }
                    )
                    # Suggestion chips directly after proposal_complete
                    await stream_callback(
                        {
                            "type": "suggestion_chip",
                            "chips": [
                                {"id": c.id, "label": c.label, "prompt": c.prompt} for c in chips
                            ],
                            "proposal_id": proposal_id,
                            "mode": "refine",
                        }
                    )

                # Record success metrics
                duration = time.time() - start_time
                self._record_metrics("success", complexity, duration)

                if stream_callback:
                    await stream_callback(
                        {
                            "type": "generation_complete",
                            "success": True,
                            "duration_ms": duration * 1000,
                        }
                    )

                logger.info(
                    f"[{self.correlation_id}] [OK] Workflow generated: "
                    f"{len(workflow.nodes)} nodes, {len(workflow.edges)} edges | "
                    f"Total: {duration:.2f}s | "
                    f"Breakdown: agents={step_times['get_agents']:.3f}s, "
                    f"prompt={step_times['build_prompt']:.3f}s, "
                    f"llm={step_times['llm_call']:.3f}s, "
                    f"validate={step_times['validate']:.3f}s"
                )

                return True, workflow, None

            except (ValidationError, GeneratorValidatieFout) as e:
                last_error = f"Validation error: {str(e)}"
                duration_so_far = time.time() - start_time
                logger.warning(
                    f"[{self.correlation_id}] [WARN]  Attempt {attempt + 1}/{self.max_retries} failed: {last_error} "
                    f"(elapsed: {duration_so_far:.2f}s)"
                )

                if attempt < self.max_retries - 1:
                    delay = self.retry_base_delay * (2**attempt)
                    logger.info(f"[{self.correlation_id}] [WAIT] Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)

            except Exception as e:
                last_error = f"LLM error: {str(e)}"
                duration_so_far = time.time() - start_time
                logger.error(
                    f"[{self.correlation_id}] [FAIL] LLM call failed: {e} (elapsed: {duration_so_far:.2f}s)"
                )

                if attempt < self.max_retries - 1:
                    delay = self.retry_base_delay * (2**attempt)
                    logger.info(f"[{self.correlation_id}] [WAIT] Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)

        # All retries exhausted
        duration = time.time() - start_time
        self._record_metrics("failed", complexity, duration)

        if stream_callback:
            await stream_callback({"type": "generation_failed", "error": last_error})

        logger.error(
            f"[{self.correlation_id}] [FAIL] Generation failed after {self.max_retries} attempts (total: {duration:.2f}s)"
        )
        return False, None, last_error

    async def _generate_surgical(
        self,
        prompt: str,
        callback: Callable[..., Awaitable[object]] | None,
    ) -> None:
        """Call LLM with surgical schema; emit node_patch events per patch op."""
        try:
            raw = await self._call_llm_surgical(prompt)

            try:
                parsed = json.loads(raw)
                patches = parsed.get("patches", [])
                if not isinstance(patches, list):
                    raise ValueError("patches must be a list")
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    f"[{self.correlation_id}] surgical_mode_invalid_llm_output raw={raw[:200]}"
                )
                if callback:
                    await callback(
                        {
                            "type": "patch_error",
                            "patch_id": "",
                            "reason": "invalid_generator_output",
                        }
                    )
                return

            for patch in patches[:10]:  # honour maxItems: 10
                patch_id = str(uuid.uuid4())[:8]
                if callback:
                    await callback(
                        {
                            "type": "node_patch",
                            "op": patch.get("op"),
                            "node": patch.get("node"),
                            "patch_id": patch_id,
                        }
                    )

        except Exception as exc:
            logger.error(f"[{self.correlation_id}] surgical_generation_failed error={exc}")
            if callback:
                await callback(
                    {
                        "type": "patch_error",
                        "patch_id": "",
                        "reason": "generation_failed",
                    }
                )

    async def _call_llm_surgical(self, prompt: str) -> str:
        """
        Issue a single LLM call for surgical mode and return raw content string.

        Dun, zodat tests deze methode kunnen vervangen zonder te weten welk model er achter zit; het model
        is de keuze van de tenant (`TenantTaalmodel`).
        """
        antwoord = await self._taalmodel.tekst(
            prompt, systeem=SURGICAL_SYSTEM_PROMPT, temperature=0.1, max_tokens=800
        )
        return antwoord.strip()

    def _build_system_prompt(
        self,
        agents: list[dict[str, object]],
        complexity: str,
    ) -> str:
        """Build Dutch system prompt with extended output schema (node_explanations + suggestion_chips)."""
        return f"""Je bent een workflow-architect AI. Zet natuurlijke taal om naar workflow JSON.

**Beschikbare agents:**
{json.dumps(agents, indent=2)}

**Outputformaat (STRIKT JSON -- geen markdown):**
{{
  "name": "workflow_naam_snake_case",
  "description": "Korte omschrijving",
  "nodes": [
    {{
      "id": "node_1",
      "agent_name": "exacte_agent_naam_uit_de_lijst",
      "label": "Leesbare naam",
      "config": {{}},
      "position": {{"x": 100, "y": 100}}
    }}
  ],
  "edges": [
    {{
      "id": "edge_1",
      "source": "node_1",
      "target": "node_2",
      "condition": null
    }}
  ],
  "metadata": {{}},
  "node_explanations": [
    {{
      "node_id": "node_1",
      "explanation": "Wat deze agent precies doet in deze workflow -- in een zin, in het Nederlands.",
      "confidence": "high",
      "confidence_reason": null
    }}
  ],
  "suggestion_chips": [
    {{
      "id": "chip_1",
      "label": "Voeg goedkeuringsstap toe",
      "prompt": "Voeg een handmatige goedkeuring toe voor de leidinggevende."
    }}
  ]
}}

**Regels:**
- Gebruik ALLEEN agentnamen uit de bovenstaande lijst
- {complexity} workflow (eenvoudig: 2-4 nodes, gemiddeld: 5-10, complex: 10-15)
- Logische stroom van begin naar eind
- Positioneer nodes met 150px tussenruimte (x: 100, 250, 400..., y: 100)
- GEEN cirkels (geen circulaire afhankelijkheden)
- GEEN losstaande nodes (alle nodes moeten verbonden zijn)
- Eerste node is altijd een trigger
- confidence: "high" als de agent duidelijk past; "low" als er betere alternatieven zijn
- 2-3 suggestion_chips met concrete vervolgacties voor de gebruiker

Geef ALLEEN geldige JSON terug."""

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        """Call the tenant's language model to generate workflow JSON."""
        logger.info(f"[{self.correlation_id}] Calling the tenant's language model...")
        api_start = time.time()
        raw_content = (
            await self._taalmodel.tekst(
                user_prompt, systeem=system_prompt, temperature=0.3, max_tokens=2000
            )
        ).strip()
        logger.info(f"[{self.correlation_id}] [OK] model response: {time.time() - api_start:.3f}s")

        # Remove markdown code blocks if present
        parse_start = time.time()
        if raw_content.startswith("```"):
            if "```json" in raw_content:
                json_start = raw_content.find("```json") + 7
            else:
                json_start = raw_content.find("```") + 3
            json_end = raw_content.rfind("```")
            if json_end > json_start:
                raw_content = raw_content[json_start:json_end].strip()

        parsed_json = json.loads(raw_content)
        parse_time = time.time() - parse_start
        logger.debug(f"[{self.correlation_id}] JSON parse: {parse_time * 1000:.1f}ms")

        return parsed_json  # type: ignore[no-any-return]  # NOTE: json.loads returns Any

    async def _validate_workflow(
        self,
        workflow_json: dict[str, object],
        valid_agent_names: set[str],
    ) -> WorkflowDefinition:
        """Validate workflow structure and business logic."""
        # Pydantic validation
        workflow = WorkflowDefinition(
            # TODO(TYPE): replace Any with concrete type
            **cast(dict[str, Any], workflow_json)
        )  # TODO(TYPE): replace Any with concrete type

        # Check agent names
        for node in workflow.nodes:
            if node.agent_name not in valid_agent_names:
                # Een voorstel met een agent die niet kan draaien wordt niet stil overgenomen (agentstap dag 2): de
                # klant leest welke agents er wel zijn.
                kiesbaar = ", ".join(sorted(valid_agent_names)) or "(geen)"
                raise GeneratorValidatieFout(
                    f"De agent '{node.agent_name}' kan nog niet in een workflow draaien. "
                    f"Kies een van deze agents: {kiesbaar}."
                )

        # Check unique node IDs
        node_ids = [node.id for node in workflow.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise GeneratorValidatieFout("Duplicate node IDs detected")

        # Check edges reference existing nodes
        node_id_set = set(node_ids)
        for edge in workflow.edges:
            if edge.source not in node_id_set:
                raise GeneratorValidatieFout(f"Edge source '{edge.source}' not found")
            if edge.target not in node_id_set:
                raise GeneratorValidatieFout(f"Edge target '{edge.target}' not found")

        # Cycle detection
        if self._has_cycle(workflow):
            raise GeneratorValidatieFout("Cycle detected - workflows must be DAG")

        # Orphan detection
        if len(workflow.nodes) > 1:
            orphans = self._find_orphaned_nodes(workflow)
            if orphans:
                raise GeneratorValidatieFout(f"Orphaned nodes: {orphans}")

        return workflow

    def _has_cycle(self, workflow: WorkflowDefinition) -> bool:
        """DFS cycle detection."""
        graph: dict[str, list[str]] = {node.id: [] for node in workflow.nodes}
        for edge in workflow.edges:
            if edge.source in graph:
                graph[edge.source].append(edge.target)

        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            for neighbor in graph.get(node_id, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(node_id)
            return False

        for node in workflow.nodes:
            if node.id not in visited:
                if dfs(node.id):
                    return True
        return False

    def _find_orphaned_nodes(self, workflow: WorkflowDefinition) -> list[str]:
        """Find disconnected nodes."""
        if len(workflow.nodes) == 1:
            return []

        connected: set[str] = set()
        for edge in workflow.edges:
            connected.add(edge.source)
            connected.add(edge.target)

        return [node.id for node in workflow.nodes if node.id not in connected]

    def _record_metrics(self, status: str, complexity: str, duration: float) -> None:
        """Record Prometheus metrics."""
        if not METRICS_AVAILABLE:
            return

        workflow_generation_counter.labels(  # type: ignore[attr-defined]
            tenant_id=str(self.tenant_id), status=status, complexity=complexity
        ).inc()

        workflow_generation_duration.labels(tenant_id=str(self.tenant_id)).observe(duration)  # type: ignore[attr-defined]


# ============================================================================
# Factory Function
# ============================================================================


async def create_workflow_generator(
    tenant_id: int = 1,
    db_session: AsyncSession | None = None,
    correlation_id: str | None = None,
) -> WorkflowGeneratorAgent:
    """
    Factory function to create WorkflowGeneratorAgent.

    Usage:
        generator = await create_workflow_generator(
            tenant_id=current_user.tenant_id,
            db_session=db
        )
        success, workflow, error = await generator.generate_workflow(
            user_prompt="Build a daily standup bot",
            complexity="simple"
        )
    """
    return WorkflowGeneratorAgent(
        tenant_id=tenant_id, db_session=db_session, correlation_id=correlation_id
    )
