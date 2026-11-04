"""
ActivePieces Validation Module

Validates flows, connections, and configurations for ActivePieces compatibility.
"""

import re
from typing import Any, Dict, List, Optional, Tuple, cast

from pydantic import BaseModel, Field, ValidationError, validator

from src.core.activepieces.models import APAction, APFlow, APTrigger, ReactFlowGraph
from src.core.activepieces.schemas import ConnectionCreate


class ValidationResult(BaseModel):
    """Result of a validation operation"""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


class FlowValidator:
    """Validator for ActivePieces flow definitions"""

    # Valid trigger types in ActivePieces
    VALID_TRIGGER_TYPES = {"WEBHOOK", "SCHEDULE", "PIECE_TRIGGER", "EMPTY"}

    # Valid action types
    VALID_ACTION_TYPES = {"PIECE", "BRANCH", "LOOP_ON_ITEMS", "CODE", "FILTER"}

    # Maximum flow name length
    MAX_FLOW_NAME_LENGTH = 100

    @staticmethod
    def validate_flow_name(name: str) -> ValidationResult:
        """Validate a flow name"""
        result = ValidationResult(valid=True)

        if not name or not name.strip():
            result.add_error("Flow name is required")
            return result

        if len(name) > FlowValidator.MAX_FLOW_NAME_LENGTH:
            result.add_error(
                f"Flow name too long ({len(name)} chars, max {FlowValidator.MAX_FLOW_NAME_LENGTH})"
            )

        # Check for invalid characters
        if not re.match(r"^[\w\s\-\_\.]+$", name):
            result.add_warning(
                "Flow name contains special characters. "
                "Only alphanumeric, spaces, hyphens, underscores, and dots are recommended."
            )

        return result

    @staticmethod
    def validate_trigger(trigger: dict[str, Any]) -> ValidationResult:  # TODO(TYPE): replace Any with concrete type
        """Validate an ActivePieces trigger definition"""
        result = ValidationResult(valid=True)

        if not trigger:
            result.add_error("Trigger is required")
            return result

        trigger_type = trigger.get("type", "")
        if trigger_type not in FlowValidator.VALID_TRIGGER_TYPES:
            result.add_error(
                f"Invalid trigger type: {trigger_type}. "
                f"Must be one of: {', '.join(FlowValidator.VALID_TRIGGER_TYPES)}"
            )

        # Validate trigger settings based on type
        settings = trigger.get("settings", {})

        if trigger_type == "SCHEDULE":
            if not settings.get("cronExpression"):
                result.add_warning("SCHEDULE trigger without cron expression")

        elif trigger_type == "PIECE_TRIGGER":
            if not settings.get("pieceName"):
                result.add_error("PIECE_TRIGGER requires pieceName in settings")
            if not settings.get("triggerName"):
                result.add_error("PIECE_TRIGGER requires triggerName in settings")

        return result

    @staticmethod
    def validate_action(action: dict[str, Any], action_id: str = "") -> ValidationResult:  # TODO(TYPE): replace Any with concrete type
        """Validate an ActivePieces action definition"""
        result = ValidationResult(valid=True)

        if not action:
            result.add_error(f"Action {action_id}: Action definition is empty")
            return result

        action_type = action.get("type", "")
        if action_type not in FlowValidator.VALID_ACTION_TYPES:
            result.add_error(
                f"Action {action_id}: Invalid action type: {action_type}. "
                f"Must be one of: {', '.join(FlowValidator.VALID_ACTION_TYPES)}"
            )

        # Validate settings
        settings = action.get("settings", {})

        if action_type == "PIECE":
            if not settings.get("pieceName"):
                result.add_error(f"Action {action_id}: PIECE action requires pieceName")
            if not settings.get("actionName"):
                result.add_error(f"Action {action_id}: PIECE action requires actionName")

        elif action_type == "BRANCH":
            if "conditions" not in settings:
                result.add_warning(f"Action {action_id}: BRANCH without conditions")

        elif action_type == "LOOP_ON_ITEMS":
            if not settings.get("items"):
                result.add_error(f"Action {action_id}: LOOP_ON_ITEMS requires items expression")

        return result

    @classmethod
    def validate_flow(cls, flow: dict[str, Any]) -> ValidationResult:  # TODO(TYPE): replace Any with concrete type
        """Validate a complete ActivePieces flow"""
        result = ValidationResult(valid=True)

        # Validate flow name
        display_name = flow.get("displayName", "")
        name_result = cls.validate_flow_name(display_name)
        result.errors.extend(name_result.errors)
        result.warnings.extend(name_result.warnings)
        if not name_result.valid:
            result.valid = False

        # Validate trigger
        trigger = flow.get("trigger", {})
        trigger_result = cls.validate_trigger(trigger)
        result.errors.extend(trigger_result.errors)
        result.warnings.extend(trigger_result.warnings)
        if not trigger_result.valid:
            result.valid = False

        # Validate actions
        actions = flow.get("actions", {})
        for action_id, action in actions.items():
            action_result = cls.validate_action(action, action_id)
            result.errors.extend(action_result.errors)
            result.warnings.extend(action_result.warnings)
            if not action_result.valid:
                result.valid = False

        # Check for orphaned actions (not reachable from trigger)
        action_ids = set(actions.keys())
        reachable = cls._get_reachable_actions(trigger, actions)
        orphaned = action_ids - reachable

        if orphaned:
            result.add_warning(
                f"Orphaned actions detected (not reachable from trigger): {', '.join(orphaned)}"
            )

        return result

    @staticmethod
    def _get_reachable_actions(trigger: dict[str, Any], actions: dict[str, Any]) -> set[str]:  # TODO(TYPE): replace Any with concrete type
        """Get all action IDs reachable from the trigger"""
        reachable: set[str] = set()
        to_visit: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Start from trigger's next action
        if trigger.get("nextAction"):
            to_visit.append(trigger["nextAction"])

        # Also check branch/loop actions
        if trigger.get("onSuccessAction"):
            to_visit.append(trigger["onSuccessAction"])
        if trigger.get("onFailureAction"):
            to_visit.append(trigger["onFailureAction"])
        if trigger.get("firstLoopAction"):
            to_visit.append(trigger["firstLoopAction"])

        while to_visit:
            current_id = to_visit.pop()
            if current_id in reachable:
                continue

            reachable.add(current_id)
            action = actions.get(current_id, {})

            # Add next actions
            if action.get("nextAction"):
                to_visit.append(action["nextAction"])
            if action.get("onSuccessAction"):
                to_visit.append(action["onSuccessAction"])
            if action.get("onFailureAction"):
                to_visit.append(action["onFailureAction"])
            if action.get("firstLoopAction"):
                to_visit.append(action["firstLoopAction"])

        return reachable

    @classmethod
    def validate_react_flow(cls, react_flow: dict[str, Any]) -> ValidationResult:  # TODO(TYPE): replace Any with concrete type
        """Validate a React Flow graph before transformation"""
        result = ValidationResult(valid=True)

        nodes = react_flow.get("nodes", [])
        edges = react_flow.get("edges", [])

        if not nodes:
            result.add_error("React Flow graph has no nodes")
            return result

        # Check for at least one trigger node
        trigger_nodes = [n for n in nodes if n.get("type") == "trigger"]
        if not trigger_nodes:
            result.add_warning(
                "No explicit trigger node found. First node will be used as trigger."
            )

        # Check for disconnected nodes
        connected_node_ids = set()
        for edge in edges:
            connected_node_ids.add(edge.get("source"))
            connected_node_ids.add(edge.get("target"))

        all_node_ids = {n.get("id") for n in nodes}
        disconnected = all_node_ids - connected_node_ids

        # First node doesn't need incoming edge
        root_candidates = all_node_ids - {e.get("target") for e in edges}
        disconnected = disconnected - root_candidates

        if disconnected:
            result.add_warning(f"Disconnected nodes detected: {', '.join(disconnected)}")

        # Check for circular references
        if cls._has_circular_reference(nodes, edges):
            result.add_error("Circular reference detected in flow")

        return result

    @staticmethod
    def _has_circular_reference(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Check if the flow has circular references"""
        # Build adjacency list
        adjacency: dict[str | None, list[str | None]] = {}
        for edge in edges:
            source: str | None = edge.get("source")
            target: str | None = edge.get("target")
            if source is not None:
                if source not in adjacency:
                    adjacency[source] = []
                adjacency[source].append(target)

        # DFS to detect cycles
        visited: set[str] = set()
        recursion_stack: set[str] = set()

        def has_cycle(node_id: str) -> bool:
            visited.add(node_id)
            recursion_stack.add(node_id)

            for neighbor in adjacency.get(node_id, []):
                if neighbor is None:
                    continue
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in recursion_stack:
                    return True

            recursion_stack.remove(node_id)
            return False

        for node in nodes:
            node_id: str | None = node.get("id")
            if node_id is None:
                continue
            if node_id not in visited:
                if has_cycle(node_id):
                    return True

        return False


class ConnectionValidator:
    """Validator for ActivePieces connections"""

    # Sensitive fields that should be encrypted
    SENSITIVE_FIELDS = {"api_key", "token", "password", "secret", "private_key"}

    @staticmethod
    def validate_connection_create(data: ConnectionCreate) -> ValidationResult:
        """Validate a connection creation request"""
        result = ValidationResult(valid=True)

        if not data.name or not data.name.strip():
            result.add_error("Connection name is required")

        if not data.app_name or not data.app_name.strip():
            result.add_error("App name is required")

        if not data.project_id:
            result.add_error("Project ID is required")

        if data.value is None:
            result.add_error("Connection value/configuration is required")

        # Validate that sensitive fields are present for common apps
        value = data.value

        if data.app_name.lower() in ["gmail", "google", "google_sheets"]:
            if "access_token" not in value and "refresh_token" not in value:
                result.add_warning(
                    "Google connections typically require access_token or refresh_token"
                )

        if data.app_name.lower() == "slack":
            if "token" not in value and "bot_token" not in value:
                result.add_warning("Slack connections typically require a bot token")

        return result

    @staticmethod
    def sanitize_connection_value(value: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Sanitize connection value by masking sensitive fields"""
        sanitized: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for key, val in value.items():
            if any(sensitive in key.lower() for sensitive in ConnectionValidator.SENSITIVE_FIELDS):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = val
        return sanitized


class PieceValidator:
    """Validator for ActivePieces pieces/integrations"""

    @staticmethod
    def validate_piece_compatibility(piece_name: str, piece_version: str) -> ValidationResult:
        """Validate if a piece is compatible with our system"""
        result = ValidationResult(valid=True)

        # Check for required version format (semver)
        if not re.match(r"^[\d]+\.[\d]+\.[\d]+$", piece_version):
            result.add_warning(f"Non-semver version format: {piece_version}")

        # Known problematic pieces
        PROBLEMATIC_PIECES = {"legacy_deprecated", "test_piece"}

        base_name = piece_name.replace("@activepieces/piece-", "")
        if base_name in PROBLEMATIC_PIECES:
            result.add_error(f"Piece '{piece_name}' is deprecated or unsupported")

        return result

    @staticmethod
    def validate_action_config(
        piece_name: str, action_name: str, config: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> ValidationResult:
        """Validate action configuration for a specific piece"""
        result = ValidationResult(valid=True)

        # Gmail-specific validation
        if "gmail" in piece_name.lower() and action_name == "send_email":
            if not config.get("to"):
                result.add_error("Gmail send_email requires 'to' field")
            if not config.get("subject"):
                result.add_warning("Gmail send_email without subject")

        # Slack-specific validation
        if "slack" in piece_name.lower() and action_name == "send_message":
            if not config.get("channel") and not config.get("user"):
                result.add_error("Slack send_message requires 'channel' or 'user'")

        # HTTP request validation
        if "http" in piece_name.lower():
            if not config.get("url"):
                result.add_error("HTTP request requires 'url'")
            if config.get("method", "GET").upper() not in [
                "GET",
                "POST",
                "PUT",
                "DELETE",
                "PATCH",
            ]:
                result.add_error(f"Invalid HTTP method: {config.get('method')}")

        return result


# Convenience functions
def validate_flow(flow: dict[str, Any]) -> ValidationResult:  # TODO(TYPE): replace Any with concrete type
    """Convenience function to validate a flow"""
    return FlowValidator.validate_flow(flow)


def validate_react_flow(react_flow: dict[str, Any]) -> ValidationResult:  # TODO(TYPE): replace Any with concrete type
    """Convenience function to validate a React Flow graph"""
    return FlowValidator.validate_react_flow(react_flow)


def validate_connection(data: ConnectionCreate) -> ValidationResult:
    """Convenience function to validate a connection"""
    return ConnectionValidator.validate_connection_create(data)
