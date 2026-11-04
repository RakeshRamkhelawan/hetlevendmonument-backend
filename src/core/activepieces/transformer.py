import re
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple

# Bron voor beide grenzen: upstream docs/install/reference/breaking-changes.mdx (tag 0.92.1).
# Vanaf 0.82.0 haalt de server `~`/`^` van pieceVersion af, dus "~0.0.0" wordt de
# niet-bestaande versie "0.0.0". Vanaf 0.85.4 is een stap `{output, ...}` en niet meer de
# uitvoer zelf; op 0.81.4 is `step_1['output']` daarom leeg, dus de vorm hangt af van de
# serverversie.
PINNED_PIECE_VERSIONS_SINCE = (0, 82, 0)
WRAPPED_STEP_OUTPUT_SINCE = (0, 85, 4)
LEGACY_PIECE_VERSION = "~0.0.0"
TRIGGER_STEP_NAME = "trigger"

_FlowJson = dict[str, Any]  # TODO(TYPE): replace Any with concrete type

_MUSTACHE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_STRING_LITERAL = re.compile(r"""('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")""")
_ALREADY_WRAPPED = re.compile(r"""\s*(\[\s*['"]output['"]\s*\]|\.output\b)""")


def parse_ap_version(version: str) -> tuple[int, int, int]:
    """'0.92.1' -> (0, 92, 1). Een voorvoegsel 'v' en een achtervoegsel als '-rc1' tellen niet."""
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version.strip())
    if match is None:
        raise ValueError(f"Onbekend ActivePieces-versieformaat: {version!r}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def rewrite_step_references(text: str, step_names: set[str]) -> str:
    """Zet `{{step.x}}` om naar `{{step['output'].x}}`, zoals de upstream-migratie van 0.85.4.

    Alleen binnen `{{ }}`, niet in stringliterals, en niet als de verwijzing al `['output']`
    of `.output` heeft (idempotent).
    """
    if not step_names:
        return text
    names = "|".join(sorted((re.escape(n) for n in step_names), key=len, reverse=True))
    reference = re.compile(rf"(?<![\w$.\]])({names})(?=\s*[.\[])")

    def _rewrite_token(token: re.Match[str]) -> str:
        code = token.group(1)
        literals = [m.span() for m in _STRING_LITERAL.finditer(code)]

        def _wrap(match: re.Match[str]) -> str:
            inside_literal = any(start <= match.start() < end for start, end in literals)
            if inside_literal or _ALREADY_WRAPPED.match(code, match.end()):
                return match.group(0)
            return f"{match.group(1)}['output']"

        return "{{" + reference.sub(_wrap, code) + "}}"

    return _MUSTACHE.sub(_rewrite_token, text)


def _rewrite_value(value: object, step_names: set[str]) -> object:
    if isinstance(value, str):
        return rewrite_step_references(value, step_names)
    if isinstance(value, dict):
        return {k: _rewrite_value(v, step_names) for k, v in value.items()}
    if isinstance(value, list):
        return [_rewrite_value(v, step_names) for v in value]
    return value


class FlowTransformer:
    """
    Transformer for converting React Flow graphs to ActivePieces flow JSON.
    Adheres to the Focus Builder 2.0 Reference Implementation.
    """

    @staticmethod
    def react_flow_to_activepieces(
        react_flow_data: _FlowJson,
        *,
        piece_versions: Mapping[str, str] | None = None,
        server_version: str | None = None,
    ) -> _FlowJson:
        """
        Convert React Flow graph to AP JSON.

        Zonder ``piece_versions`` blijft het oude ``~0.0.0`` staan; dat werkt alleen tot 0.82.
        Met ``piece_versions`` (naam -> exacte versie uit ``/pieces``) krijgt elke stap een
        exacte versie. ``server_version`` bepaalt de vorm van stapverwijzingen.
        """
        server = parse_ap_version(server_version) if server_version else None
        if piece_versions is None and server is not None and server >= PINNED_PIECE_VERSIONS_SINCE:
            raise ValueError(
                f"ActivePieces {server_version} pint piece-versies (sinds 0.82): "
                "geef piece_versions mee, anders wordt '~0.0.0' de versie '0.0.0'"
            )

        def _piece_version(piece_name: str) -> str:
            if piece_versions is None:
                return LEGACY_PIECE_VERSION
            version = piece_versions.get(piece_name)
            if not version:
                raise ValueError(
                    f"Geen versie bekend voor {piece_name} in de ActivePieces-catalogus"
                )
            return version

        wrap_step_output = server is not None and server >= WRAPPED_STEP_OUTPUT_SINCE
        nodes = react_flow_data.get("nodes", [])
        edges = react_flow_data.get("edges", [])

        # Build adjacency list
        adjacency: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for edge in edges:
            adjacency[edge["source"]] = edge["target"]

        # Build node map for easy access
        node_map = {node["id"]: node for node in nodes}

        # Determine Root Nodes (Trigger Candidate)
        incoming_edges = {edge["target"] for edge in edges}
        root_nodes = [node for node in nodes if node["id"] not in incoming_edges]

        candidate_trigger = root_nodes[0] if root_nodes else None

        # Valid Trigger Agents
        TRIGGER_AGENTS = {"webhook_trigger", "schedule_agent"}

        real_trigger_node = None

        if candidate_trigger:
            agent = (
                candidate_trigger.get("data", {}).get("name")
                or candidate_trigger.get("agent_name")
                or candidate_trigger.get("data", {}).get("agent_name")
                or ""
            )
            if agent in TRIGGER_AGENTS:
                real_trigger_node = candidate_trigger

        # Build Actions
        actions: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        # Include candidate in actions if it wasn't a real trigger
        action_nodes = [n for n in nodes if n != real_trigger_node]

        # Build edge map keyed by (source, sourceHandle) for branch routing
        edge_by_handle: dict[tuple[str, str | None], str] = {}
        for edge in edges:
            key = (edge["source"], edge.get("sourceHandle"))
            edge_by_handle[key] = edge["target"]

        for node in action_nodes:
            node_id = node["id"]
            node_type = node.get("type", "action")
            agent_name = (
                node.get("data", {}).get("name")
                or node.get("agent_name")
                or node.get("data", {}).get("agent_name")
                or ""
            )
            node_label = (
                node.get("data", {}).get("title")
                or node.get("label")
                or node.get("data", {}).get("label")
                or f"Step {node_id}"
            )
            node_config = (
                node.get("data", {}).get("config")
                or node.get("config")
                or node.get("data", {}).get("config")
                or {}
            )

            # Look up next action ID (default edge)
            next_node_id = adjacency.get(node_id)

            if node_type == "branch":
                # BRANCH action: route success/failure to different targets
                conditions = node.get("data", {}).get("conditions", [])
                success_target = edge_by_handle.get((node_id, "success"))
                failure_target = edge_by_handle.get((node_id, "failure"))

                actions[node_id] = {
                    "displayName": node_label,
                    "name": node_id,
                    "type": "BRANCH",
                    "settings": {"conditions": conditions},
                    "nextAction": next_node_id,
                    "onSuccessAction": success_target,
                    "onFailureAction": failure_target,
                    "valid": True,
                }

            elif node_type == "loop":
                # LOOP_ON_ITEMS action: iterate over a collection
                items_expr = node.get("data", {}).get("items") or node_config.get("items", "")
                loop_body_target = edge_by_handle.get((node_id, "loop-body")) or edge_by_handle.get(
                    (node_id, "body")
                )

                actions[node_id] = {
                    "displayName": node_label,
                    "name": node_id,
                    "type": "LOOP_ON_ITEMS",
                    "settings": {"items": items_expr},
                    "nextAction": next_node_id,
                    "firstLoopAction": loop_body_target,
                    "valid": True,
                }

            else:
                # Standard PIECE action
                piece_name, action_name = FlowTransformer._map_agent_to_piece(agent_name)

                actions[node_id] = {
                    "displayName": node_label,
                    "name": node_id,
                    "type": "PIECE",
                    "settings": {
                        "pieceName": piece_name,
                        "pieceVersion": _piece_version(piece_name),
                        "actionName": action_name,
                        "input": node_config,
                    },
                    "nextAction": next_node_id,
                    "valid": True,
                }

        # Build Trigger
        trigger_settings: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        trigger_type = "EMPTY"
        trigger_display_name = "Manual Trigger"

        if real_trigger_node:
            t_agent = (
                real_trigger_node.get("data", {}).get("name")
                or real_trigger_node.get("agent_name")
                or real_trigger_node.get("data", {}).get("agent_name")
                or ""
            )
            t_config = (
                real_trigger_node.get("data", {}).get("config")
                or real_trigger_node.get("config")
                or real_trigger_node.get("data", {}).get("config")
                or {}
            )
            t_piece, t_trigger = FlowTransformer._map_agent_to_piece(t_agent)

            if "schedule" in t_piece:
                trigger_type = "PIECE_TRIGGER"
                trigger_display_name = "Schedule"
            else:
                trigger_type = "PIECE_TRIGGER"
                trigger_display_name = real_trigger_node.get("data", {}).get(
                    "title"
                ) or real_trigger_node.get("label", "Trigger")

            trigger_settings = {
                "pieceName": t_piece,
                "triggerName": t_trigger,
                "input": t_config,
            }
            if piece_versions is not None:
                trigger_settings["pieceVersion"] = _piece_version(t_piece)

        ap_trigger = {
            "name": real_trigger_node["id"] if real_trigger_node else "trigger",
            "type": trigger_type,
            "displayName": trigger_display_name,
            "settings": trigger_settings,
            "nextAction": (
                adjacency.get(real_trigger_node["id"])
                if real_trigger_node
                else (candidate_trigger["id"] if candidate_trigger else None)
            ),
            "valid": True,
        }

        if wrap_step_output:
            step_names = set(actions) | {TRIGGER_STEP_NAME, str(ap_trigger["name"])}
            for action in actions.values():
                settings = action["settings"]
                if "input" in settings:
                    settings["input"] = _rewrite_value(settings["input"], step_names)

        # Assemble Flow
        return {
            "displayName": react_flow_data.get("name", "SanskritiSetu Workflow"),
            "description": react_flow_data.get("description", ""),
            "trigger": ap_trigger,
            "actions": actions,
            "valid": True,
        }

    @staticmethod
    def _map_agent_to_piece(agent_name: str) -> tuple[str, str]:
        """
        Map SanskritiSetu agent name to ActivePieces piece.
        """
        mapping = {
            # New naming convention
            "email": ("@activepieces/piece-gmail", "send_email"),
            "webhook": ("@activepieces/piece-webhook", "webhook_trigger"),
            "schedule": ("@activepieces/piece-schedule", "cron_expression"),
            "slack": ("@activepieces/piece-slack", "send_message"),
            "openai": ("@activepieces/piece-openai", "ask_chatgpt"),
            # Legacy mapping
            "email_agent": ("@activepieces/piece-gmail", "send_email"),
            "slack_agent": ("@activepieces/piece-slack", "send_message"),
            "http_request": ("@activepieces/piece-http", "send_request"),
            "webhook_trigger": ("@activepieces/piece-webhook", "webhook_trigger"),
            "schedule_agent": ("@activepieces/piece-schedule", "cron_expression"),
            "llm_summarizer": ("@activepieces/piece-openai", "ask_chatgpt"),
            "sentiment_analyzer": ("@activepieces/piece-openai", "ask_chatgpt"),
            "content_generator": ("@activepieces/piece-openai", "ask_chatgpt"),
            "database_query": ("@activepieces/piece-postgres", "run_query"),
            "data_transformer": ("@activepieces/piece-data-mapper", "map_data"),
            "notification_agent": ("@activepieces/piece-discord", "send_message"),
            "github_integration": ("@activepieces/piece-github", "create_issue"),
            "jira_integration": ("@activepieces/piece-jira-cloud", "create_issue"),
        }

        if agent_name.startswith("ap_"):
            piece_name = agent_name[3:]
            return (f"@activepieces/piece-{piece_name}", "default_action")

        return mapping.get(agent_name, ("@activepieces/piece-code", "run_code"))
