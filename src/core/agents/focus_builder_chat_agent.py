"""
FocusBuilderChatAgent -- Manages a single Focus Builder WebSocket chat session.

Responsibilities:
- Conversation history per session
- Socratic onboarding: ask up to 3 clarifying questions before generating
- Digital Twin profile injection into LLM system prompt
- Proposal lifecycle: track pending_proposals per proposal_id
- Stream node_proposed events via WebSocket send_json callback
- Observe accept/reject events (optional, degrades gracefully)
"""

import asyncio
import re
import uuid
from collections.abc import Callable
from typing import Any, Optional, TypedDict

from loguru import logger

from src.core.agents.proactive_suggestions import Suggestion, get_suggestions
from src.core.services.focus_builder_service import save_accepted_workflow
from src.core.services.workflow_generator_service import WorkflowGeneratorAgent


async def get_connected_apps(tenant_id: int) -> list[str]:
    """De namen van de live aangesloten apps van deze tenant.

    **Waarom niet meer uit de Redis-cache (audit 2026-08-30).** De vorige versie las
    `focus_builder:agents:tenant_<id>` en gaf bij een KOUDE cache `[]` terug -- niet te
    onderscheiden van "deze tenant heeft geen enkele integratie". Dat is dezelfde faalvorm
    die dit project elders al meermaals heeft gehad: een storing die zich voordoet als een
    geldige uitkomst.

    Nu dezelfde bron die `_build_generation_prompt()` al gebruikt: de app-connections van het
    Activepieces-project van de tenant, via de ene toegangsweg (`ActivePiecesClient`). Een fout
    daar (geen verbinding voor de tenant, server onbereikbaar) komt hier als fout aan en wordt NIET
    meer stil een `[]`: de aanroepers vangen hem zelf op en loggen hem. Het is EEN bron voor beide
    plekken, niet twee die uiteen kunnen lopen.

    Geeft namen terug (`appName`), niet id's: de suggestietabel in `proactive_suggestions.py`
    matcht op naam en doet dat hoofdletterongevoelig.
    """
    from src.core.activepieces.tenant_utils import fetch_live_connections

    verbindingen = await fetch_live_connections(tenant_id)
    namen: list[str] = []
    for verbinding in verbindingen:
        naam = verbinding.get("appName") or verbinding.get("id")
        if naam:
            namen.append(str(naam))
    return namen


class IntakeContext(TypedDict):
    trigger: str | None
    doel: str | None
    output: str | None


def extract_keywords(intake: IntakeContext) -> list[str]:
    """Extract meaningful keywords from trigger/doel/output fields."""
    text = " ".join(filter(None, [intake.get("trigger"), intake.get("doel"), intake.get("output")]))
    stopwords = {
        "de",
        "het",
        "een",
        "naar",
        "via",
        "op",
        "in",
        "en",
        "of",
        "met",
        "voor",
        "bij",
    }
    return [w.lower() for w in re.split(r"\W+", text) if w and w.lower() not in stopwords]


def infer_departments(intake: IntakeContext) -> list[str]:
    """Map doel text to likely department IDs."""
    doel = (intake.get("doel") or "").lower()
    mapping = {
        "debiteur": "finance_treasury",
        "factuur": "finance_treasury",
        "rapport": "data_ai_governance",
        "analyse": "data_ai_governance",
        "email": "sales_marketing",
        "slack": "sales_marketing",
        "klant": "customer_experience",
        "support": "customer_experience",
        "hr": "hr_culture",
        "medewerker": "hr_culture",
        "security": "it_security",
        "incident": "it_security",
    }
    return list({dept for kw, dept in mapping.items() if kw in doel})


def filter_agents(
    intake: IntakeContext,
    all_agents: list[Any],  # TODO(TYPE): replace Any with concrete type
    live_conns: list[Any],  # TODO(TYPE): replace Any with concrete type
    twin_profile: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
    """Score and rank agents; return top 30 (fallback: alphabetical top-30 if all score 0)."""
    keywords = extract_keywords(intake)
    inferred_depts = infer_departments(intake)
    live_app_ids = {c["id"] for c in live_conns}
    scores: dict[str, int] = {}

    for agent in all_agents:
        score = 0
        name_lower = agent["name"].lower()
        desc_lower = agent.get("description", "").lower()
        dept_lower = agent.get("department", "").lower()
        score += sum(2 for kw in keywords if kw in name_lower)
        score += sum(1 for kw in keywords if kw in desc_lower)
        score += sum(1 for kw in keywords if kw in dept_lower)
        if agent.get("department") in inferred_depts:
            score += 5
        if any(ri in live_app_ids for ri in agent.get("required_integrations", [])):
            score += 10
        if agent["id"] in twin_profile.get("preferred_agents", []):
            score += 8
        scores[agent["id"]] = score

    ranked = sorted(all_agents, key=lambda a: scores[a["id"]], reverse=True)
    top = ranked[:30]
    # If all scores are 0 -- no meaningful match, return alphabetical top-30
    if all(scores[a["id"]] == 0 for a in top):
        return sorted(all_agents, key=lambda a: a["name"])[:30]
    return top


class FocusBuilderChatAgent:
    """
    Manages one WS chat session for the Focus Builder.

    Args:
        user_id:      Integer user ID (from JWT)
        tenant_id:    Integer tenant ID
        user_id_str:  String user identifier for twin profile lookup
        db:           AsyncSession for DB queries
        send_json:    Async callable that sends a JSON dict over the WebSocket
        restore_conversation_id: Existing conversation_id for reconnects
    """

    MAX_CLARIFYING_QUESTIONS = 1

    # Intake question texts (Dutch)
    _INTAKE_QUESTIONS = {
        "trigger": "Wanneer of waardoor moet deze workflow starten -- op een tijdstip, via een webhook, of handmatig?",
        "doel": "Wat moet er precies gebeuren -- welke data verwerkt, welk proces uitgevoerd?",
        "output": "Waar moet het resultaat naartoe -- email, Slack, een dashboard, of een bestand?",
    }

    def __init__(
        self,
        user_id: int,
        tenant_id: int,
        user_id_str: str,
        db: Any,  # TODO(TYPE): replace Any with concrete type
        send_json: Callable[[dict[str, Any]], Any],  # TODO(TYPE): replace Any with concrete type
        restore_conversation_id: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.user_id_str = user_id_str
        self.db = db
        self.send_json = send_json
        # Restore existing conversation_id on reconnect, or create a new one
        self._is_restore = restore_conversation_id is not None
        self.conversation_id = restore_conversation_id or str(uuid.uuid4())
        self._message_history: list[
            dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        ] = []  # TODO(TYPE): replace Any with concrete type
        self._pending_proposals: dict[
            str, list[dict[str, Any]]
        ] = {}  # TODO(TYPE): replace Any with concrete type
        self._proposal_intakes: dict[
            str, dict[str, Any]
        ] = {}  # snapshot per proposal_id  # TODO(TYPE): replace Any with concrete type
        self._question_count = 0
        self._twin_profile: dict[str, Any] | None = (
            None  # TODO(TYPE): replace Any with concrete type
        )
        self._intake_context: dict[str, Any] | None = (
            None  # TODO(TYPE): replace Any with concrete type
        )
        self._connected_apps: list[str] = []
        self._active_template_id: str | None = None
        self._pending_template_generation: bool = False

    # -------------------------------------------------------------------------
    # Session lifecycle
    # -------------------------------------------------------------------------

    async def start_session(self) -> None:
        """Send session_init on WebSocket connect; greeting only for new sessions."""
        self._twin_profile = await self._load_twin_profile()

        # De aangesloten apps ophalen met een HARDE bovengrens (audit 2026-08-30).
        #
        # `fetch_live_connections()` heeft zelf al een timeout, maar dit is het openen van
        # het chatscherm: als de Activepieces-kant traag of onbereikbaar is, mag de gebruiker
        # daar nooit op wachten. Vandaar de tweede grens hier. Mislukt het, dan is de lijst
        # leeg en gaat de sessie gewoon door -- zonder suggesties, met een melding in het log,
        # zodat het verschil tussen "geen integraties" en "niet opgehaald" naspeurbaar blijft.
        try:
            self._connected_apps = await asyncio.wait_for(
                get_connected_apps(self.tenant_id), timeout=3.0
            )
        except Exception as exc:
            logger.warning(f"session_init_apps_fetch_failed tenant={self.tenant_id} error={exc}")
            self._connected_apps = []

        suggesties: list[Suggestion] = get_suggestions(self._connected_apps)

        twin_samenvatting = None
        if self._twin_profile:
            twin_samenvatting = {
                "preferred_integrations": (self._twin_profile.get("coding_style") or {}).get(
                    "preferred_integrations", []
                ),
                "observation_count": self._twin_profile.get("observation_count", 0),
            }

        # Deze drie velden leest `frontend/src/hooks/useFocusBuilderWS.ts:109-111`. Ze zijn
        # tussen 2026-08-2x en 2026-08-30 niet verstuurd; de frontend viel stil terug op lege
        # waarden en de suggestiechips konden nooit verschijnen. Bewaakt door
        # `tests/architecture/test_focus_builder_ws_contract.py`.
        await self.send_json(
            {
                "type": "session_init",
                "conversation_id": self.conversation_id,
                "connected_apps": self._connected_apps,
                "twin_summary": twin_samenvatting,
                "proactive_suggestions": suggesties,
            }
        )

        # Skip greeting when reconnecting to an existing session
        if self._is_restore:
            return

        greeting = self._build_greeting()
        await self.send_json(
            {
                "type": "text_chunk",
                "content": greeting,
                "proposal_id": None,
                "has_learning_chip": bool(self._twin_profile),
            }
        )
        self._message_history.append({"role": "assistant", "content": greeting})

    # -------------------------------------------------------------------------
    # Message handling
    # -------------------------------------------------------------------------

    async def handle_message(self, content: str) -> None:
        """
        Handle an incoming chat message.

        Run LLM-based intake to extract trigger/doel/output.
        Ask focused questions until all fields are present (max 3).
        Then optionally suggest a template match, then generate.
        """
        self._message_history.append({"role": "user", "content": content})
        await self.send_json({"type": "thinking"})

        if self._question_count < self.MAX_CLARIFYING_QUESTIONS:
            ctx, question = await self._run_intake(content)
            # Accumulate fields across turns
            if self._intake_context is None:
                self._intake_context = ctx
            else:
                for field in ("trigger", "doel", "output"):
                    if ctx is not None and not self._intake_context.get(field) and ctx.get(field):
                        self._intake_context[field] = ctx[field]
        else:
            question = None
            if self._intake_context is None:
                self._intake_context = {"trigger": None, "doel": None, "output": None}

        if question:
            # Determine which step we're on
            missing_field = next(
                (
                    f
                    for f in ("trigger", "doel", "output")
                    if not (self._intake_context or {}).get(f)
                ),
                "trigger",
            )
            step_num = self._question_count + 1
            self._question_count += 1
            self._message_history.append({"role": "assistant", "content": question})
            await self.send_json(
                {
                    "type": "intake_question",
                    "content": question,
                    "step": missing_field,
                    "progress": step_num,
                }
            )
        else:
            # Check for template match before generating
            template = await self._find_matching_template()
            if template and not self._pending_template_generation:
                self._pending_template_generation = True
                await self.send_json(
                    {
                        "type": "template_match",
                        "template_name": template.get("name", ""),
                        "template_id": template.get("id", ""),
                    }
                )
                # Generation will resume when handle_template_action is called
            else:
                await self._generate()

    # -------------------------------------------------------------------------
    # Proposal lifecycle
    # -------------------------------------------------------------------------

    async def accept_proposal(
        self, proposal_id: str
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Return nodes for this proposal; persist to DB; log to Digital Twin."""
        nodes = self._pending_proposals.pop(proposal_id, [])
        intake = self._proposal_intakes.pop(proposal_id, self._intake_context or {})

        try:
            await save_accepted_workflow(
                user_id=self.user_id,
                tenant_id=self.tenant_id,
                proposal_id=proposal_id,
                name=None,
                nodes=nodes,
                edges=[],
                intake_context=intake,
                template_id=self._active_template_id,
                db=self.db,
            )
        except Exception as exc:
            logger.warning("focus_builder_accept_save_failed", error=str(exc))

        await self._log_acceptance_to_twin(proposal_id, nodes)
        logger.info(
            "focus_builder_proposal_accepted",
            proposal_id=proposal_id,
            node_count=len(nodes),
        )
        return nodes

    def reject_proposal(self, proposal_id: str) -> None:
        """Remove proposal from pending without saving."""
        self._pending_proposals.pop(proposal_id, None)
        logger.info(
            "focus_builder_proposal_rejected",
            proposal_id=proposal_id,
            user_id=self.user_id,
        )

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    async def _generate(self) -> None:
        """Call WorkflowGeneratorAgent with enriched context (filtered agents, twin, recent workflows)."""
        system_context = await self._build_generation_prompt()
        history_lines = [
            f"{'Gebruiker' if m['role'] == 'user' else 'Assistent'}: {m['content']}"
            for m in self._message_history
        ]
        full_prompt = system_context + "\n\nGesprekgeschiedenis:\n" + "\n".join(history_lines)

        current_proposal_nodes: list[
            dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        ] = []  # TODO(TYPE): replace Any with concrete type
        current_proposal_id: str | None = None

        async def stream_callback(
            event: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        ) -> None:  # TODO(TYPE): replace Any with concrete type
            nonlocal current_proposal_id, current_proposal_nodes
            etype = event.get("type")
            if etype == "node_proposed":
                pid = event.get("proposal_id", "")
                if current_proposal_id is None:
                    current_proposal_id = pid
                current_proposal_nodes.append(event["node"])
                await self.send_json(event)
            elif etype == "node_explanation":
                await self.send_json(event)
            elif etype == "proposal_complete":
                pid = event.get("proposal_id", current_proposal_id or "")
                if pid and current_proposal_nodes:
                    self._pending_proposals[pid] = current_proposal_nodes.copy()
                    # Snapshot intake for this proposal
                    self._proposal_intakes[pid] = dict(self._intake_context or {})
                await self.send_json(event)
            elif etype == "suggestion_chip":
                await self.send_json(event)

        agent = WorkflowGeneratorAgent(
            tenant_id=self.tenant_id,
            correlation_id=self.conversation_id[:8],
        )
        await agent.generate_workflow(user_prompt=full_prompt, stream_callback=stream_callback)

    async def _build_generation_prompt(self) -> str:
        """Build enriched system prompt with filtered agents, live connections, twin profile, recent workflows."""
        # Fetch live connections
        try:
            from src.core.activepieces.tenant_utils import fetch_live_connections

            live_conns = await fetch_live_connections(self.tenant_id)
        except Exception:
            live_conns = []

        # Filter agents
        try:
            from src.core.als.agents.focus_builder_agents import _get_internal_agents

            filtered = filter_agents(
                intake=self._intake_context or {},  # type: ignore[arg-type]
                all_agents=_get_internal_agents(),
                live_conns=live_conns,
                twin_profile=self._twin_profile or {},
            )
        except Exception:
            filtered = []

        # Recent workflows
        recent_summary = ""
        try:
            from sqlalchemy import select as sa_select

            from src.core.learning.twin_models import FocusBuilderAcceptedWorkflow

            result = await self.db.execute(
                sa_select(FocusBuilderAcceptedWorkflow)
                .where(
                    FocusBuilderAcceptedWorkflow.user_id == self.user_id,
                    FocusBuilderAcceptedWorkflow.tenant_id == self.tenant_id,
                )
                .order_by(FocusBuilderAcceptedWorkflow.created_at.desc())
                .limit(3)
            )
            recent = result.scalars().all()
            if recent:
                recent_summary = "\n\nEerdere workflows van deze gebruiker:\n" + "\n".join(
                    f"- {r.name or r.proposal_id}: {[n.get('type', '?') for n in (r.nodes or [])]}"
                    for r in recent
                )
        except Exception:
            pass

        lines = [
            "Je bent een Nederlandse workflow-assistent. Genereer een workflow met onderstaande agents.",
            f"\nBeschikbare agents (top-30 op relevantie): {[a['id'] for a in filtered]}",
        ]
        if live_conns:
            live_names = [c.get("appName", c.get("id", "?")) for c in live_conns]
            lines.append(f"Live Activepieces-verbindingen van deze tenant: {live_names}")
        if self._twin_profile:
            style = self._twin_profile.get("coding_style") or {}
            if style.get("preferred_integrations"):
                lines.append(f"Gebruikersvoorkeur: {', '.join(style['preferred_integrations'])}")
        lines.append(recent_summary)
        return "\n".join(lines)

    async def _track_in_twin(
        self,
        behavior_type: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Track a behavior observation via the Digital Twin."""
        from src.core.learning.services.twin_service_factory import (
            create_practical_twin_service,
        )

        service = await create_practical_twin_service(db=self.db, tenant_id=self.tenant_id)
        await service.track_behavior(
            user_id=self.user_id_str,
            tenant_id=self.tenant_id,
            session_id=self.conversation_id,
            behavior_type=behavior_type,
            context=context,
        )

    async def _log_acceptance_to_twin(
        self,
        proposal_id: str,
        nodes: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        try:
            agent_ids = [n.get("type", "") for n in nodes]
            await self._track_in_twin(
                behavior_type="focus_builder.workflow_accepted",
                context={
                    "event": "workflow_accepted",
                    "proposal_id": proposal_id,
                    "agents": agent_ids,
                },
            )
        except Exception as exc:
            logger.debug("focus_builder_twin_log_failed", error=str(exc))

    async def handle_node_updated(
        self,
        node_id: str,
        old_agent_id: str,
        new_agent_id: str,
        workflow_id: int | None = None,
    ) -> None:
        """Record agent swap in Digital Twin profile."""
        try:
            await self._track_in_twin(
                behavior_type="focus_builder.agent_swap",
                context={
                    "event": "agent_swap",
                    "node_id": node_id,
                    "old_agent_id": old_agent_id,
                    "new_agent_id": new_agent_id,
                },
            )
        except Exception as exc:
            logger.debug("focus_builder_node_updated_twin_failed", error=str(exc))

    async def handle_template_action(self, action: str, template_id: str) -> None:
        """Resume generation after user responds to template_match event."""
        self._pending_template_generation = False
        if action == "accept":
            self._active_template_id = template_id
        else:
            self._active_template_id = None
        await self._generate()

    async def handle_refine(
        self,
        content: str,
        current_nodes: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Refine an existing workflow based on user feedback.

        Appends a refine message (with current node context) to history then
        triggers a new generation pass.
        """
        node_summary = ", ".join(
            n.get("data", {}).get("title", n.get("id", "?")) for n in current_nodes[:10]
        )
        refine_msg = f"[Verfijnen] Huidige nodes: [{node_summary}]\nVerzoek: {content}"
        self._message_history.append({"role": "user", "content": refine_msg})
        await self.send_json({"type": "thinking"})
        await self._generate()

    async def handle_explain(self, node_id: str, node_title: str, node_type: str) -> None:
        """Send a node_explanation WS event with an LLM-generated description."""
        explanation, confidence = await self._explain_node_llm(node_title, node_type)
        await self.send_json(
            {
                "type": "node_explanation",
                "node_id": node_id,
                "content": explanation,
                "confidence": confidence,
                "confidence_reason": None if confidence == "high" else "LLM unavailable",
            }
        )

    async def _explain_node_llm(self, node_title: str, node_type: str) -> tuple[str, str]:
        """Generate a Dutch plain-language explanation for a workflow node.

        Returns (explanation, confidence) where confidence is 'high' on LLM
        success and 'low' on fallback so the frontend can show an uncertainty indicator.
        """
        system_prompt = (
            "Je bent een workflow-uitlegger. Geef een korte Nederlandse uitleg "
            "(2-3 zinnen) van wat dit workflow-onderdeel doet. "
            "Gebruik heldere taal voor niet-technische gebruikers."
        )
        user_msg = f"Type: {node_type}\nNaam: {node_title}"
        try:
            gen = WorkflowGeneratorAgent(
                tenant_id=self.tenant_id,
                correlation_id=self.conversation_id[:8],
            )
            raw = await gen._call_llm(system_prompt, user_msg)
            if isinstance(raw, str) and raw.strip():
                return raw.strip(), "high"
        except Exception:
            pass
        fallback = f"Dit onderdeel ({node_title}) verwerkt {node_type}-taken in de workflow."
        return fallback, "low"

    async def _run_intake(
        self, content: str
    ) -> tuple[dict[str, Any] | None, str | None]:  # TODO(TYPE): replace Any with concrete type
        """
        Use LLM to extract trigger/doel/output from user input.
        Returns (intake_context, question_to_ask | None).
        None question means all fields present -> go generate.
        Falls back to "generate immediately" if LLM call fails.
        """
        ctx = await self._call_intake_llm(content)
        # Check which fields are missing (prioritised order)
        for field in ("trigger", "doel", "output"):
            if not ctx.get(field):
                return ctx, self._INTAKE_QUESTIONS[field]
        return ctx, None  # All present -- proceed to generation

    async def _call_intake_llm(
        self, content: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Lightweight LLM call to extract IntakeContext JSON.
        Returns dict with trigger/doel/output (any can be None).
        Falls back to all-None on error.
        """
        system_prompt = (
            "Je bent een intake-assistent voor een workflow-builder. "
            "Extraheer uit de gebruikersinput drie velden als JSON:\n"
            '{"trigger": "<wanneer/waardoor -- null als onbekend>", '
            '"doel": "<wat moet er gebeuren -- null als onbekend>", '
            '"output": "<waar naartoe -- null als onbekend>"}\n'
            "Geef ALLEEN geldige JSON terug. Geen uitleg."
        )
        try:
            import json as _json

            gen = WorkflowGeneratorAgent(
                tenant_id=self.tenant_id, correlation_id=self.conversation_id[:8]
            )
            raw = await gen._call_llm(system_prompt, content)
            if isinstance(raw, dict) and "trigger" in raw:
                return raw
            # _call_llm may return the parsed dict or raw JSON string depending on provider
            if isinstance(raw, str):
                return _json.loads(raw)
            return {"trigger": None, "doel": None, "output": None}
        except Exception:
            return {"trigger": None, "doel": None, "output": None}

    async def _find_matching_template(
        self,
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Find a matching template based on current intake_context. Returns None if no match."""
        if not self._intake_context:
            return None
        try:
            from src.core.services.template_registry import TemplateRegistry

            registry = TemplateRegistry()
            templates = registry.list_templates()
            if not templates:
                return None
            keywords = extract_keywords(self._intake_context)  # type: ignore[arg-type]
            THRESHOLD = 2  # minimum keyword overlaps
            best = None
            best_score = 0
            for tpl in templates:
                tpl_text = (tpl.name + " " + (tpl.description or "")).lower()
                overlap = sum(1 for w in keywords if w in tpl_text)
                if overlap > best_score:
                    best_score = overlap
                    best = tpl
            if best and best_score >= THRESHOLD:
                return {"name": best.name, "id": best.template_id}
            return None
        except Exception:
            return None

    async def _load_twin_profile(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Load the Digital Twin profile for this user, return {} on error."""
        try:
            from src.core.learning.services.twin_service_factory import (
                create_practical_twin_service,
            )

            service = await create_practical_twin_service(db=self.db, tenant_id=self.tenant_id)
            return await service.get_profile(
                user_id=self.user_id_str,
                tenant_id=self.tenant_id,
                db=self.db,
            )
        except Exception as exc:
            logger.warning(
                "focus_builder_twin_profile_load_failed",
                user_id=self.user_id,
                error=str(exc),
            )
            return {}

    def _build_greeting(self) -> str:
        if not self._twin_profile:
            return (
                "Goedendag! Ik ben uw AI-assistent voor workflows. "
                "Vertel mij wat u wilt automatiseren en ik bouw het voor u."
            )
        obs = self._twin_profile.get("observation_count", 0)
        if obs > 0:
            return (
                "Welkom terug! Ik ken uw voorkeuren al -- "
                "vertel mij welke workflow u nu wilt bouwen."
            )
        return (
            "Goedendag! Ik ben uw AI-assistent voor workflows. "
            "Vertel mij wat u wilt automatiseren en ik bouw het voor u."
        )

    def _build_system_context(self) -> str:
        if not self._twin_profile:
            return (
                "Je bent een workflow-bouwassistent. "
                "Genereer een workflow op basis van de gebruikersinstructie."
            )

        lines = ["Je kent deze gebruiker:"]
        style = self._twin_profile.get("coding_style") or {}
        if style.get("preferred_integrations"):
            lines.append(f"- Geeft voorkeur aan: {', '.join(style['preferred_integrations'])}")
        if style.get("always_adds"):
            lines.append(f"- Voegt altijd toe: {', '.join(style['always_adds'])}")
        lines.append(f"- Help-stijl: {self._twin_profile.get('optimal_help_style', 'direct')}")
        lines.append("\nGenereer met deze voorkeuren meegenomen.")
        return "\n".join(lines)
