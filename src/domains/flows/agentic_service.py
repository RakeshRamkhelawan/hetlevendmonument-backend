import json
import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

from src.domains.flows.models import ReactFlowGraph

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.core.services.llm.tenant_deur import TenantTaalmodel
    from src.core.llm.llm_client import LLMProvider

from pydantic import BaseModel, Field


class _PackMatch(Protocol):
    pack_id: str
    pack_name: str
    confidence: object
    can_use_as_is: bool
    suggested_customizations: Iterable[str]
    match_score: float


class _PackIntentMatcher(Protocol):
    async def find_best_pack_match(
        self, tenant_id: int, prompt: str
    ) -> _PackMatch | None: ...

    async def get_pack_template_as_flow(
        self, tenant_id: int, pack_id: str
    ) -> dict[str, object] | None: ...

# --- Pydantic Models for Planning Phase ---

# --- Pydantic Models for Planning Phase (V4 Simplified) ---

# --- Strict Builder Models (User Req: Pillar 2) ---


class BuilderNodeData(BaseModel):
    title: str = Field(..., description="User facing title (Required)")
    description: str | None = Field(None, description="Longer description")
    label: str | None = None  # Backwards compatibility/ReactFlow internal
    subLabel: str | None = None
    icon: str | None = None
    name: str | None = None
    status: str = "pending"
    config: dict[str, object] = Field(
        default_factory=dict, description="Tool configuration (inputs)"
    )


class BuilderNode(BaseModel):
    id: str
    type: str
    position: dict[str, float]
    data: BuilderNodeData
    phase: str = "create"


# --------------------------------------------------


class AutomationStep(BaseModel):
    id: str = Field(..., description="Unique technical ID (s1, s2, etc)")
    type: Literal["ACTION", "WAIT", "CONDITION"] = Field(..., description="Logic type")
    description: str = Field(..., description="Action description")


class AutomationPlan(BaseModel):
    trigger: str = Field(..., description="The event description that starts the flow")
    steps: list[AutomationStep] = Field(..., description="List of automation steps")
    summary: str = Field(..., description="Short summary")


# --- Memory/Session Store (MVP In-Memory) ---
# --- Memory/Session Store (Global/Singleton for MVP) ---
GLOBAL_SESSION_STORE: dict[str, dict[str, object]] = {}


class InMemorySessionStore:
    def __init__(self) -> None:
        # Bind to global store
        self._store = GLOBAL_SESSION_STORE

    async def save_context(
        self,
        session_id: str,
        key: str,
        value: object,
    ) -> None:
        if session_id not in self._store:
            self._store[session_id] = {}
        self._store[session_id][key] = value

    async def get_context(self, session_id: str, key: str) -> object | None:
        return self._store.get(session_id, {}).get(key)

    async def get_history(self, session_id: str) -> list[dict[str, str]]:
        history = cast(list[dict[str, str]], self._store.get(session_id, {}).get("history", []))
        return history

    async def add_history(self, session_id: str, role: str, content: str) -> None:
        if session_id not in self._store:
            self._store[session_id] = {}
        if "history" not in self._store[session_id]:
            self._store[session_id]["history"] = []
        cast(list[dict[str, str]], self._store[session_id]["history"]).append(
            {"role": role, "content": content}
        )


class AgenticFlowService:
    """
    Service responsible for converting natural language prompts into executable Flow structures.
    Acts as the "Brain" of the Focus Builder Digital Twin.
    V4 Architecture: Interactive 3-Layer (Analysis -> Confirmation -> Construction).
    """

    def __init__(self, llm_service: Any = None, tenant_id: int | None = None) -> None:
        self._llm = llm_service
        self._tenant_id = tenant_id
        self.memory_store = InMemorySessionStore()

    async def _get_llm(self) -> "TenantTaalmodel":
        """Het taalmodel van de TENANT van dit verzoek (ADR-041 B14), geen platformstandaard.

        Een meegegeven `llm_service` (een test) gaat voor. Een `provider=` of `model=` in het verzoek
        wordt genegeerd: de tenant kiest zijn model, het verzoek niet.
        """
        if not self._llm:
            from src.core.services.llm.tenant_deur import TenantTaalmodel

            self._llm = TenantTaalmodel(self._tenant_id)
        return cast("TenantTaalmodel", self._llm)

    # --- V4 INTERACTIVE PIPELINE ---

    async def start_interactive_session(self, prompt: str, session_id: str) -> str:
        """
        Step 1: Interpretation & Analysis (Pure Text).
        Analyzes intent without forcing JSON structure.
        Uses Conversation History for context awareness.
        """
        # Fetch History
        history = await self.memory_store.get_history(session_id)

        # Format History for Prompt
        context_str: str = ""
        if history:
            context_str = "GESCHIEDENIS:\n" + "\n".join(
                [f"{msg['role']}: {msg['content']}" for msg in history[-5:]]
            )  # Limit to last 5 turns

        input_msg = f"""
        {context_str}

        NIEUWE GEBRUIKERSVRAAG: "{prompt}"

        TAAK:
        1. Analyseer de vraag in de context van de geschiedenis.
        2. Als de gebruiker akkoord gaat met een eerder plan (bijv. "Ja", "Prima", "Goed"), bevestig dit dan en leg uit wat er gaat gebeuren.
        3. Als het een nieuwe vraag is:
            - Vat de intentie samen.
            - Identificeer de hoofdrolspelers (Actoren).
            - Som de waarschijnlijke automatiseringsstappen op (in natuurlijke taal).
            - Vraag aan het eind expliciet of je hiervan een workflow moet bouwen.

        Antwoord in een behulpzame, professionele toon (Nederlands). GEEN JSON.
        """

        # Save User Input to History
        await self.memory_store.add_history(session_id, "User", prompt)

        # Save User Intent (Last Prompt) for Planner
        await self.memory_store.save_context(session_id, "user_intent", prompt)

        llm = await self._get_llm()

        response = await llm.generate_response(input_msg)

        if not response.get("success", False):
            raise ValueError(f"AI Analysis Failed: {response.get('error')}")

        analysis_text: str = response.get("content", "")

        # Save Analysis to History & Context
        await self.memory_store.add_history(session_id, "AI", analysis_text)
        await self.memory_store.save_context(session_id, "analysis", analysis_text)

        return analysis_text

    async def execute_approved_plan(self, session_id: str) -> dict[str, object]:
        """
        Step 2 & 3: Planning & Construction.
        Triggered when user confirms ("Ja").
        """
        # Retrieve context. For "execute", we need the ORIGINAL INTENT, not the confirmation "Ja".
        # We need to look back in history to find the actual request?
        # OR we rely on 'analysis' which supposedly contains the plan summary?

        # Fetch history to find the actual intent if 'user_intent' is just "Prima"
        history = await self.memory_store.get_history(session_id)

        # Logic: If 'user_intent' is short (confirmation), look back for the real prompt.
        current_intent = await self.memory_store.get_context(session_id, "user_intent")

        # Heuristic: If prompt is very short, it's likely a confirmation. Use the previous user message.
        if history and len(str(current_intent)) < 10:
            # Find last User message that was NOT the current one
            # [..., User: "Make flow", AI: "Plan...", User: "Prima"]
            # We want "Make flow".
            for msg in reversed(history[:-1]):  # Skip last one (Prima)
                if msg["role"] == "User":
                    current_intent = msg["content"]
                    break

        analysis = await self.memory_store.get_context(session_id, "analysis")

        if not current_intent:
            # Fallback if session lost: return error asking user to re-state
            return {
                "type": "error",
                "message": "Sessie verlopen of niet gevonden. Kun je je vraag opnieuw stellen?",
            }

        # Step 3: Targeted Planning (Strict JSON Mode)
        planning_prompt = f"""
        CONTEXT:
        Gebruiker wil: {current_intent}
        Analyse: {analysis}

        TAAK:
        Zet de bovenstaande analyse om in een strikt AutomationPlan (JSON).
        Gebruik alleen de stappen die nodig zijn voor de flowchart.

        OUTPUT JSON SCHEMA:
        {{
          "trigger": "Beschrijving van start event",
          "steps": [ {{ "id": "s1", "type": "ACTION|WAIT|CONDITION", "description": "..." }} ],
          "summary": "Korte samenvatting"
        }}
        """

        llm = await self._get_llm()

        plan_response = await llm.generate_response(planning_prompt)

        if not plan_response.get("success", False):
            return {
                "type": "error",
                "message": f"Planning mislukt: {plan_response.get('error')}",
            }

        content = plan_response.get("content", "")

        try:
            # Robust JSON extraction
            raw_json = json.loads(self._extract_json_block(content))
            plan = AutomationPlan(**raw_json)

            # --- FALLBACK CHECK (User Requirement 3) ---
            if not plan.steps:
                return {
                    "type": "assistant_message",  # Treat as chat message, not error
                    "message": "Ik kan hier geen duidelijke stappen voor een workflow uit halen. Zal ik het proces alleen tekstueel verder uitwerken?",
                }

            # Python Logic: Plan -> ReactFlow Graph
            flow_graph = self.steps_to_reactflow(plan)

            return {
                "type": "flow_generated",
                "data": flow_graph,
                "message": "Ik heb de workflow voor je op het canvas gezet.",
            }

        except Exception as e:
            logger.error(f"Execution Error: {e}", exc_info=True)
            return {
                "type": "error",
                "message": "Fout bij genereren workflow.",
            }

    async def generate_flow_from_prompt(
        self,
        prompt: str,
        provider: str | None = None,
        model: str | None = None,
        status_callback: Callable[[str], Awaitable[None]] | None = None,
        tenant_id: int | None = None,
    ) -> dict[str, object]:
        """
        Generate a complete ReactFlow graph from a natural language prompt.
        Uses complete_json() with ReactFlowGraph schema for structured output.
        """
        try:
            # === Phase 0: Domain Pack Matching ===
            if tenant_id:
                if status_callback:
                    await status_callback("Checking for existing templates...")

                matcher: _PackIntentMatcher | None = None
                pack_match: _PackMatch | None = None
                get_pack_intent_matcher: object | None = None
                try:
                    import src.core.services.pack_intent_matcher as _pm_module

                    get_pack_intent_matcher = getattr(_pm_module, "get_pack_intent_matcher", None)
                except ImportError:
                    pass

                if get_pack_intent_matcher is not None:
                    matcher_obj = await cast(
                        Callable[[], Awaitable[_PackIntentMatcher]], get_pack_intent_matcher
                    )()
                    if matcher_obj is not None:
                        matcher = matcher_obj
                        pack_match = await matcher.find_best_pack_match(tenant_id, prompt)

                if matcher is not None and pack_match and pack_match.confidence in ["exact", "high", "medium"]:
                    logger.info(
                        "Found matching pack '%s' with %s confidence",
                        pack_match.pack_name,
                        pack_match.confidence,
                    )

                    if status_callback:
                        await status_callback(f"Found template: {pack_match.pack_name}")

                    flow_graph = await matcher.get_pack_template_as_flow(
                        tenant_id,
                        pack_match.pack_id,
                    )

                    if flow_graph:
                        if pack_match.can_use_as_is:
                            message = f"Loaded '{pack_match.pack_name}' template. Ready to use!"
                        else:
                            customizations_text = "\n".join(
                                [f"  - {c}" for c in pack_match.suggested_customizations]
                            )
                            message = (
                                f"Loaded '{pack_match.pack_name}' template as starting point.\n\n"
                                f"Suggested customizations:\n"
                                f"{customizations_text}"
                            )

                        metadata = cast(dict[str, object], flow_graph["metadata"])
                        metadata["pack_match"] = {
                            "pack_id": pack_match.pack_id,
                            "confidence": getattr(
                                pack_match.confidence, "value", str(pack_match.confidence)
                            ),
                            "match_score": pack_match.match_score,
                            "can_use_as_is": pack_match.can_use_as_is,
                        }

                        logger.info(
                            "PACK TEMPLATE USED: %s (%s nodes)",
                            pack_match.pack_name,
                            len(cast(list[object], flow_graph.get("nodes", []))),
                        )

                        return {
                            "success": True,
                            "data": {"react_flow_graph": flow_graph},
                            "message": message,
                        }

                if status_callback:
                    await status_callback(
                        "No existing template found, generating custom workflow..."
                    )

            # === Phase 1: AI Generation via complete_json() ===
            if status_callback:
                await status_callback("Analyzing process requirements...")

            llm = await self._get_llm()

            from src.core.llm.llm_client import LLMMessage

            system_prompt = (
                "You are an Automation Architect. "
                "Analyze the user request and produce a valid ReactFlow graph. "
                "Output ONLY valid JSON matching the ReactFlowGraph schema with nodes and edges. "
                "Each node must have id, type, position {x, y}, and data. "
                "Each edge must have id, source, and target."
            )
            user_msg = f"tenant_id: {tenant_id or 'unknown'}. Request: {prompt}"

            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_msg),
            ]

            if status_callback:
                await status_callback("Generating workflow graph...")

            response = await llm.complete_json(
                messages=messages,
                schema=ReactFlowGraph,
            )

            if not response.success:
                error_msg = response.error_message or "Unknown LLM Error"
                logger.error("Workflow generation failed: %s", error_msg)
                return {
                    "success": False,
                    "error": {
                        "code": "LLM_GENERATION_FAILED",
                        "message": "Het genereren van de workflow is mislukt.",
                    },
                }

            content = response.content
            if not content:
                return {
                    "success": False,
                    "error": {
                        "code": "LLM_GENERATION_FAILED",
                        "message": "LLM returned empty content.",
                    },
                }

            try:
                raw_json = json.loads(content)
            except json.JSONDecodeError:
                json_str = self._extract_json_block(content)
                raw_json = json.loads(json_str)

            graph = ReactFlowGraph(**raw_json)

            if status_callback:
                await status_callback(f"Workflow generated with {len(graph.nodes)} nodes.")

            return {
                "success": True,
                "data": {
                    "react_flow_graph": graph.model_dump(),
                },
            }

        except Exception as e:
            logger.critical("Workflow generation failed: %s", e, exc_info=True)
            return {
                "success": False,
                "error": {
                    "code": "LLM_GENERATION_FAILED",
                    "message": "Het genereren van de workflow is mislukt.",
                },
            }

    async def plan_automation_from_prompt(
        self, prompt: str, provider: str | None = None, model: str | None = None
    ) -> AutomationPlan:
        """
        Phase 1: Strategic Planning.
        Extracts intent into a structured Pydantic object using JSON Mode.
        """
        system_prompt = """
        You are an Automation Architect.
        Analyze the user request and map it to a linear automation plan.

        CRITICAL INSTRUCTION:
        Output ONLY valid JSON.
        DO NOT use Markdown coding blocks.
        DO NOT add any text, titles, or explanations outside the JSON.

        OUTPUT JSON SCHEMA (Strict):
        {
          "trigger": "User submits form",
          "steps": [
            {"id": "s1", "type": "ACTION", "description": "Send email"},
            {"id": "s2", "type": "CONDITION", "description": "If amount > 100"}
          ],
          "summary": "Form to Email flow with condition"
        }
        """

        user_msg = f"Request: {prompt}"
        llm = await self._get_llm()

        response = await llm.generate_response(
            prompt=user_msg,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
        )

        # Helper to check success
        if not response.get("success", False):
            error_msg = response.get("error", "Unknown LLM Error")
            logger.error(f"V2 PLANNER: LLM Generation Failed: {error_msg}")
            raise ValueError(f"AI Provider Error: {error_msg}")

        content = response.get("content", "")
        if not content:
            logger.error("V2 PLANNER: Recevied EMPTY content from LLM!")
            raise ValueError("LLM returned empty content.")

        logger.warning(
            f"V2 PLANNER RAW CONTENT: {content[:500]}..."
        )  # WARNING to ensure visibility

        try:
            # 1. Try Direct Parse
            raw_json = json.loads(content)
        except json.JSONDecodeError:
            # 2. Fallback to extraction utils
            json_str = self._extract_json_block(content)
            raw_json = json.loads(json_str)

        return AutomationPlan(**raw_json)

    def steps_to_reactflow(self, plan: AutomationPlan) -> dict[str, object]:
        """
        Phase 2: Drafting.
        Determistically converts AutomationPlan (V4 Simplified) to ReactFlow JSON.
        Now uses strict BuilderNode models.
        """
        if not plan.steps:
            return {
                "nodes": [],
                "edges": [],
                "explanation": "ERROR: No automation steps could be derived from this request.",
            }

        nodes: list[dict[str, object]] = []
        edges: list[dict[str, object]] = []
        y_cursor = 200
        x_center = 250

        # 1. Create Trigger Node
        trigger_id = "trigger_1"

        trigger_node = BuilderNode(
            id=trigger_id,
            type="trigger",
            position={"x": x_center, "y": 50},
            data=BuilderNodeData(
                title=plan.trigger,
                description="Start Event",
                label=plan.trigger,
                name="webhook",
            ),
        )
        nodes.append(trigger_node.model_dump())

        previous_id = trigger_id

        # 2. Map Steps
        for i, step in enumerate(plan.steps):
            node_id = f"node_{step.id}_{i}"

            # Icon & Name Inference
            icon = "activity"
            node_name = "action"  # Default fallback
            step_type = step.type
            desc_lower = step.description.lower()

            if step_type == "WAIT":
                icon = "clock"
                node_name = "schedule"  # Or delay, AP uses schedule for simple delays sometimes or a dedicated delay piece
            elif step_type == "CONDITION":
                icon = "git-branch"
                node_name = "condition"
            else:
                # ACTION: Infer from keywords
                if "mail" in desc_lower or "bericht" in desc_lower:
                    icon = "mail"
                    node_name = "email"
                elif "slack" in desc_lower or "teams" in desc_lower:
                    icon = "message-square"
                    node_name = "slack"
                elif "crm" in desc_lower or "klant" in desc_lower:
                    icon = "users"
                    node_name = "crm"
                elif "data" in desc_lower or "opslaan" in desc_lower:
                    icon = "database"
                    node_name = "database_query"
                elif "github" in desc_lower or "issue" in desc_lower:
                    icon = "github"
                    node_name = "github_integration"

            node = BuilderNode(
                id=node_id,
                type="action",
                phase="create",
                position={"x": x_center, "y": y_cursor},
                data=BuilderNodeData(
                    title=step.description,
                    description=step.description,
                    label=step.description,
                    subLabel=step_type,
                    icon=icon,
                    name=node_name,
                    status="pending",
                ),
            )
            nodes.append(node.model_dump())

            # Create Edge
            edges.append(
                {
                    "id": f"e_{previous_id}_{node_id}",
                    "source": previous_id,
                    "target": node_id,
                    "animated": True,
                }
            )

            previous_id = node_id
            y_cursor += 150

        return {"nodes": nodes, "edges": edges, "explanation": plan.summary}

    async def _legacy_generate_flow(
        self,
        prompt: str,
        provider: str | None = None,
        model: str | None = None,
        status_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, object]:
        """
        LEGACY LOGIC: Single-Shot Generation + Repair Loop.
        Maintained as fallback for complex cases where Plan V1 fails.
        """
        # ... (provider resolution logic handled by caller or kept simple here) ...
        llm = await self._get_llm()

        system_prompt = """
        You are an expert Workflow Automation Engineer acting as a 'Digital Twin'.

        Your ONLY task:
        Return a single JSON object that matches EXACTLY this schema:

        {
          "nodes": [ ... ],
          "edges": [ ... ],
          "explanation": "..."
        }

        Hard constraints:
        - Output MUST be valid JSON only.
        - Do NOT include markdown blocks.
        - Do NOT write ANY text before or after the JSON.
        - Do NOT include comments.
        - Do NOT wrap the JSON in any additional fields or objects.
        - If you cannot generate the workflow, return:
          { "nodes": [], "edges": [], "explanation": "ERROR: <reason>" }

        CRITICAL RULES FOR "HUMAN-CENTRIC" UI:
        1. **Labels MUST match Intent:** Do NOT use technical names like "Webhook Trigger". Use "Start als email binnenkomt" or "Wacht op formulier".
        2. **Descriptions:** Add a short, friendly description for each node in the `data` field.
        3. **Structure:** Always start with a Trigger. Connect all nodes sequentially.
        4. **Internal Names:** Use technical keys for `name` (e.g., 'webhook', 'send_email', 'chatgpt') but KEEP THEM HIDDEN in the `data` object.

        TARGET JSON STRUCTURE EXAMPLE:
        {
          "nodes": [
            {
                "id": "trigger_1",
                "type": "trigger",
                "data": {
                    "label": "Start: Nieuwe Lead",
                    "name": "webhook",
                    "description": "Luistert naar Typeform inzendingen"
                },
                "position": { "x": 100, "y": 100 }
            },
            {
                "id": "action_1",
                "type": "action",
                "data": {
                    "label": "Stuur Welkomstmail",
                    "name": "email",
                    "action": "send_email",
                    "description": "Stuurt bevestiging naar klant"
                },
                "position": { "x": 100, "y": 300 }
            }
          ],
          "edges": [
            { "id": "e1", "source": "trigger_1", "target": "action_1" }
          ],
          "explanation": "Ik heb een flow voor je klaargezet die start bij een nieuwe lead en direct een email stuurt."
        }
        """

        try:
            # Step 1: Initial Generation
            response = await llm.generate_response(
                prompt=prompt,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.get("content", "")
            logger.info(f"LLM Raw Content Length: {len(content)}")

            # Step 2: Validation & Repair Loop
            MAX_REPAIRS = 2
            attempts: int = 0
            current_content = content
            workflow_data: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

            while attempts <= MAX_REPAIRS:
                try:
                    # A. Robust Extraction
                    json_str = self._extract_json_block(current_content)
                    workflow_data = json.loads(json_str)

                    # B. Structural Key Check
                    if "nodes" not in workflow_data:
                        detected_keys = list(workflow_data.keys())
                        error_type = "Unknown"
                        if "phases" in detected_keys or "tasks" in detected_keys:
                            error_type = "Project Plan"
                        elif "sql" in detected_keys or "query" in detected_keys:
                            error_type = "SQL Query"
                        try:
                            # Allow parsing project plans as input for repair
                            repair_input = json.dumps(workflow_data)
                        except:
                            repair_input = current_content

                        raise ValueError(
                            f"Schema Mismatch (Type: {error_type}). Missing 'nodes' key."
                        )

                    # C. Pydantic Validation (Strict Types & Unique IDs)
                    # We create a temporary dict to validate against the model
                    validate_graph = {
                        "nodes": workflow_data.get("nodes", []),
                        "edges": workflow_data.get("edges", []),
                    }
                    ReactFlowGraph.model_validate(validate_graph)

                    # If we get here, it's valid!
                    logger.info(f"Validation Success after {attempts} repairs.")
                    return workflow_data

                except Exception as e:
                    attempts += 1
                    logger.warning(f"Validation Failed (Attempt {attempts}/{MAX_REPAIRS + 1}): {e}")

                    if attempts > MAX_REPAIRS:
                        logger.error("Max repair attempts reached. Returning safe error output.")
                        return {
                            "nodes": [],
                            "edges": [],
                            "explanation": "Er kon geen geldige workflow worden gemaakt. Probeer je verzoek duidelijker te omschrijven.",
                        }

                    # Trigger Repair
                    # If we have partial json, use it, otherwise use raw text
                    repair_input_content = (
                        json.dumps(workflow_data)
                        if workflow_data and "nodes" in workflow_data
                        else current_content
                    )
                    # If simple parser error, might need raw content. safe bet: pass check result logic

                    if status_callback:
                        await status_callback(
                            f"Wait... I'm fixing the structure (Repair {attempts}/{MAX_REPAIRS})..."
                        )

                    workflow_data = await self._attempt_repair(current_content, prompt)
                    # Log Repair Result
                    logger.info(
                        f"REPAIR RESULT: nodes={len(workflow_data.get('nodes', []))}, "
                        f"edges={len(workflow_data.get('edges', []))}, keys={list(workflow_data.keys())}"
                    )
                    # The repair returns a DICT. We need to serialize it back to string for the loop's 'extraction' step
                    # OR just use the dict directly in next iteration?
                    # The loop expects 'current_content' string for extraction.
                    # Let's shortcut: The repair returns a dict. We can assume it's JSON.
                    # Updated loop strategy: 'current_content' is just a carrier, but 'workflow_data' is what we check.
                    # FIX: simpler to convert result back to json str to reuse the loop's extraction logic,
                    # OR refactor loop to take dict. Refactoring loop to take dict is cleaner.

                    # Actually, _attempt_repair returns a Dict.
                    # So for the next iteration, we can skip extraction if we set a flag, or just dump it.
                    current_content = json.dumps(workflow_data)

            return workflow_data

        except Exception as e:
            logger.error(f"Agentic Flow Generation Critical Failure: {e}")
            raise e

    async def _attempt_repair(
        self,
        bad_content: str,
        original_prompt: str,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Self-Healing Layer:
        Takes invalid output and forces it into the strict ReactFlow Schema using a minimalist 'Repair Agent'.
        """
        logger.info("--- Engaging Repair Agent ---")
        llm = await self._get_llm()

        # Minimalist Repair Prompt (Contract-Design)
        repair_prompt = """
        You are a JSON Repair Bot.

        INPUT: Raw text or invalid JSON from a failed generation attempt.
        TARGET: Valid ReactFlow JSON Schema.

        INSTRUCTIONS:
        1. Extract the AUTOMATION INTENT from the input.
        2. Map it to 'nodes' and 'edges'.
        3. DISCARD all other fields (like 'phases', 'stakeholders', 'timelines').
        4. Output MUST contain ONLY: {"nodes": [...], "edges": [...], "explanation": "..."}
        """

        user_msg = f"""
        ORIGINAL REQUEST: {original_prompt}

        FAILED OUTPUT TO FIX:
        {bad_content[:4000]}
        """

        response = await llm.generate_response(
            prompt=user_msg,
            messages=[
                {"role": "system", "content": repair_prompt},
                {"role": "user", "content": user_msg},
            ],
        )

        content = response.get("content", "")
        # Recursively use extract_json_block to handle potential markdown in repair response
        try:
            json_str = self._extract_json_block(content)
            result = cast(dict[str, object], json.loads(json_str))
        except Exception:
            # If repair returned unparseable output, fallback to empty
            result = {}

        # 4. Repair Guard: Inject empty structure if keys missing
        if "nodes" not in result or "edges" not in result:
            logger.warning(
                f"Repair result missing keys, injecting empty structure. Keys: {list(result.keys())}"
            )
            result = {
                "nodes": result.get("nodes", []),
                "edges": result.get("edges", []),
                "explanation": result.get("explanation")
                or "ERROR: Repair agent could not infer a valid automation flow.",
            }

        logger.info(f"Repair Agent finished. Result keys: {list(result.keys())}")
        return result

    def _extract_json_block(self, raw: str) -> str:
        """
        Robustly extract JSON from potentially 'chatty' LLM output.
        Strategies:
        1. Parse distinct JSON directly.
        2. Extract content between first '{' and last '}'.
        3. Extract content within markdown code fences.
        """
        raw = raw.strip()

        # 1. Attempt direct parsing
        try:
            json.loads(raw)
            return raw
        except Exception:
            pass

        # 2. Extract between braces (handles text before/after JSON)
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = raw[start : end + 1]
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                pass

        # 2b. Regex Fallback (Last Resort for conversational wrapping)
        try:
            import re

            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                candidate = match.group(0)
                try:
                    json.loads(candidate)
                    return candidate
                except:
                    pass
        except:
            pass

        # 3. Fallback: Markdown code fences
        if "```json" in raw:
            block = raw.split("```json", 1)[1]
            block = block.split("```", 1)[0]
            return block.strip()
        if "```" in raw:
            block = raw.split("```", 1)[1]
            block = block.split("```", 1)[0]
            return block.strip()

        raise ValueError(
            f"Could not extract valid JSON from LLM response. Content start: {raw[:50]}..."
        )
