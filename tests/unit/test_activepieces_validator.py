"""
Unit tests for ActivePieces validator module
"""

import pytest

from src.core.activepieces.validator import (
    ConnectionValidator,
    FlowValidator,
    PieceValidator,
    validate_connection,
    validate_flow,
    validate_react_flow,
)


class TestFlowValidator:
    """Test cases for FlowValidator"""

    def test_validate_flow_name_valid(self):
        """Test valid flow name"""
        result = FlowValidator.validate_flow_name("My Workflow")
        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_flow_name_empty(self):
        """Test empty flow name"""
        result = FlowValidator.validate_flow_name("")
        assert result.valid is False
        assert "Flow name is required" in result.errors

    def test_validate_flow_name_whitespace(self):
        """Test whitespace-only flow name"""
        result = FlowValidator.validate_flow_name("   ")
        assert result.valid is False

    def test_validate_flow_name_too_long(self):
        """Test flow name exceeding max length"""
        long_name = "x" * 101
        result = FlowValidator.validate_flow_name(long_name)
        assert result.valid is False
        assert "too long" in result.errors[0]

    def test_validate_flow_name_special_chars(self):
        """Test flow name with special characters (warning only)"""
        result = FlowValidator.validate_flow_name("My Workflow @#$%")
        assert result.valid is True  # Still valid, just warning
        assert len(result.warnings) == 1

    def test_validate_trigger_valid_webhook(self):
        """Test valid webhook trigger"""
        trigger = {"type": "WEBHOOK", "settings": {"url": "https://example.com/webhook"}}
        result = FlowValidator.validate_trigger(trigger)
        assert result.valid is True

    def test_validate_trigger_valid_schedule(self):
        """Test valid schedule trigger"""
        trigger = {"type": "SCHEDULE", "settings": {"cronExpression": "0 0 * * *"}}
        result = FlowValidator.validate_trigger(trigger)
        assert result.valid is True

    def test_validate_trigger_schedule_no_cron(self):
        """Test schedule trigger without cron expression"""
        trigger = {"type": "SCHEDULE", "settings": {}}
        result = FlowValidator.validate_trigger(trigger)
        assert result.valid is True  # Warning, not error
        assert len(result.warnings) == 1

    def test_validate_trigger_invalid_type(self):
        """Test trigger with invalid type"""
        trigger = {"type": "INVALID_TYPE", "settings": {}}
        result = FlowValidator.validate_trigger(trigger)
        assert result.valid is False
        assert "Invalid trigger type" in result.errors[0]

    def test_validate_trigger_empty(self):
        """Test empty trigger"""
        result = FlowValidator.validate_trigger({})
        assert result.valid is False
        assert "Trigger is required" in result.errors

    def test_validate_action_valid_piece(self):
        """Test valid piece action"""
        action = {
            "type": "PIECE",
            "settings": {"pieceName": "@activepieces/piece-gmail", "actionName": "send_email"},
        }
        result = FlowValidator.validate_action(action, "step_1")
        assert result.valid is True

    def test_validate_action_piece_missing_name(self):
        """Test piece action without pieceName"""
        action = {"type": "PIECE", "settings": {"actionName": "send_email"}}
        result = FlowValidator.validate_action(action, "step_1")
        assert result.valid is False
        assert "requires pieceName" in result.errors[0]

    def test_validate_action_invalid_type(self):
        """Test action with invalid type"""
        action = {"type": "INVALID", "settings": {}}
        result = FlowValidator.validate_action(action, "step_1")
        assert result.valid is False
        assert "Invalid action type" in result.errors[0]

    def test_validate_flow_complete(self):
        """Test complete flow validation"""
        flow = {
            "displayName": "Test Flow",
            "trigger": {"type": "WEBHOOK", "settings": {}, "nextAction": "step_1"},
            "actions": {
                "step_1": {
                    "type": "PIECE",
                    "settings": {
                        "pieceName": "@activepieces/piece-gmail",
                        "actionName": "send_email",
                    },
                    "nextAction": "step_2",
                },
                "step_2": {
                    "type": "PIECE",
                    "settings": {
                        "pieceName": "@activepieces/piece-slack",
                        "actionName": "send_message",
                    },
                },
            },
        }
        result = FlowValidator.validate_flow(flow)
        assert result.valid is True

    def test_validate_flow_orphaned_actions(self):
        """Test flow with orphaned actions (warning)"""
        flow = {
            "displayName": "Test Flow",
            "trigger": {"type": "WEBHOOK", "settings": {}, "nextAction": "step_1"},
            "actions": {
                "step_1": {
                    "type": "PIECE",
                    "settings": {"pieceName": "gmail", "actionName": "send"},
                },
                "orphan": {
                    "type": "PIECE",
                    "settings": {"pieceName": "slack", "actionName": "send"},
                },
            },
        }
        result = FlowValidator.validate_flow(flow)
        assert result.valid is True  # Warning, not error
        assert len(result.warnings) == 1
        assert "Orphaned actions" in result.warnings[0]


class TestConnectionValidator:
    """Test cases for ConnectionValidator"""

    def test_validate_connection_valid(self):
        """Test valid connection"""
        from src.core.activepieces.schemas import ConnectionCreate

        data = ConnectionCreate(
            name="My Gmail", app_name="gmail", project_id="proj_123", value={"api_key": "secret123"}
        )
        result = ConnectionValidator.validate_connection_create(data)
        assert result.valid is True

    def test_validate_connection_empty_name(self):
        """Test connection without name"""
        from src.core.activepieces.schemas import ConnectionCreate

        data = ConnectionCreate(name="", app_name="gmail", project_id="proj_123", value={})
        result = ConnectionValidator.validate_connection_create(data)
        assert result.valid is False
        assert "Connection name is required" in result.errors

    def test_validate_connection_gmail_no_token(self):
        """Test Gmail connection without access token (warning)"""
        from src.core.activepieces.schemas import ConnectionCreate

        data = ConnectionCreate(name="My Gmail", app_name="gmail", project_id="proj_123", value={})
        result = ConnectionValidator.validate_connection_create(data)
        assert result.valid is True  # Warning, not error
        assert len(result.warnings) == 1

    def test_sanitize_connection_value(self):
        """Test sanitizing connection values"""
        value = {
            "api_key": "secret123",
            "token": "bearer_token",
            "public_key": "public123",
            "password": "mypassword",
        }
        sanitized = ConnectionValidator.sanitize_connection_value(value)

        assert sanitized["api_key"] == "***REDACTED***"
        assert sanitized["token"] == "***REDACTED***"
        assert sanitized["password"] == "***REDACTED***"
        assert sanitized["public_key"] == "public123"


class TestPieceValidator:
    """Test cases for PieceValidator"""

    def test_validate_piece_compatibility_valid(self):
        """Test valid piece compatibility"""
        result = PieceValidator.validate_piece_compatibility("@activepieces/piece-gmail", "1.0.0")
        assert result.valid is True

    def test_validate_piece_compatibility_deprecated(self):
        """Test deprecated piece"""
        result = PieceValidator.validate_piece_compatibility("legacy_deprecated", "1.0.0")
        assert result.valid is False
        assert "deprecated" in result.errors[0].lower()

    def test_validate_action_config_gmail(self):
        """Test Gmail action config validation"""
        config = {"to": "test@example.com", "subject": "Hello"}
        result = PieceValidator.validate_action_config(
            "@activepieces/piece-gmail", "send_email", config
        )
        assert result.valid is True

    def test_validate_action_config_gmail_missing_to(self):
        """Test Gmail action without 'to' field"""
        config = {"subject": "Hello"}
        result = PieceValidator.validate_action_config(
            "@activepieces/piece-gmail", "send_email", config
        )
        assert result.valid is False
        assert "'to' field" in result.errors[0]

    def test_validate_action_config_http_no_url(self):
        """Test HTTP action without URL"""
        config = {"method": "POST"}
        result = PieceValidator.validate_action_config(
            "@activepieces/piece-http", "send_request", config
        )
        assert result.valid is False
        assert "'url'" in result.errors[0]


class TestConvenienceFunctions:
    """Test convenience functions"""

    def test_validate_flow_function(self):
        """Test validate_flow convenience function"""
        flow = {"displayName": "Test", "trigger": {"type": "WEBHOOK", "settings": {}}}
        result = validate_flow(flow)
        assert hasattr(result, "valid")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")

    def test_validate_react_flow_function(self):
        """Test validate_react_flow convenience function"""
        react_flow = {
            "nodes": [{"id": "1", "type": "trigger", "data": {}, "position": {"x": 0, "y": 0}}],
            "edges": [],
        }
        result = validate_react_flow(react_flow)
        assert hasattr(result, "valid")

    def test_validate_connection_function(self):
        """Test validate_connection convenience function"""
        from src.core.activepieces.schemas import ConnectionCreate

        data = ConnectionCreate(name="Test", app_name="gmail", project_id="proj_123", value={})
        result = validate_connection(data)
        assert hasattr(result, "valid")
