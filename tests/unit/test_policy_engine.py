import os
import sys

import pytest

# Ensure src is in path
sys.path.append(os.getcwd())

from src.core.governance.policy_engine import (
    ActionContext,
    PolicyEngine,
    PolicyRiskLevel,
    PolicyRule,
)


class TestAllowPolicy:
    """Tests for allowed actions."""

    @pytest.mark.asyncio
    async def test_allow_policy_permits_action(self):
        """Test that explicitly allowed actions are permitted."""
        engine = PolicyEngine(rules={})

        # Add tenant rule to allow specific action
        engine.add_tenant_rule(
            PolicyRule(
                action_pattern="custom_action",
                allowed=True,
                reason="Explicitly allowed by tenant policy",
            )
        )

        context = ActionContext(
            action_name="custom_action",
            parameters={},
            risk_level=PolicyRiskLevel.LOW,
        )
        result = await engine.validate_action(context)
        assert result.allowed is True
        assert "Explicitly allowed" in result.reason

    @pytest.mark.asyncio
    async def test_default_allow_standard_ops(self):
        """Test that standard operations (query, analyze, respond) are allowed by default."""
        engine = PolicyEngine(rules={})

        for action in ["query", "analyze", "respond", "search", "read"]:
            context = ActionContext(
                action_name=action,
                parameters={},
                risk_level=PolicyRiskLevel.LOW,
            )
            result = await engine.validate_action(context)
            assert result.allowed is True, f"Action '{action}' should be allowed by default"
            assert result.requires_approval is False

    @pytest.mark.asyncio
    async def test_higher_priority_rule_wins(self):
        """Test that higher priority rules override lower priority ones."""
        engine = PolicyEngine(rules={})

        # Add low priority deny rule
        engine.add_tenant_rule(
            PolicyRule(
                action_pattern="test_action",
                allowed=False,
                reason="Low priority deny",
                priority=10,
            )
        )

        # Add high priority allow rule
        engine.add_tenant_rule(
            PolicyRule(
                action_pattern="test_action",
                allowed=True,
                reason="High priority allow",
                priority=100,
            )
        )

        context = ActionContext(
            action_name="test_action",
            parameters={},
            risk_level=PolicyRiskLevel.LOW,
        )
        result = await engine.validate_action(context)
        assert result.allowed is True
        assert "High priority allow" in result.reason

    @pytest.mark.asyncio
    async def test_tenant_policy_overrides_default(self):
        """Test that tenant-specific rules override default behavior."""
        engine = PolicyEngine(rules={})

        # Override query to be denied
        engine.add_tenant_rule(
            PolicyRule(action_pattern="query", allowed=False, reason="Tenant disabled queries")
        )

        context = ActionContext(
            action_name="query",
            parameters={},
            risk_level=PolicyRiskLevel.LOW,
        )
        result = await engine.validate_action(context)
        assert result.allowed is False
        assert "Tenant disabled" in result.reason


class TestDenyPolicy:
    """Tests for deny-by-default behavior."""

    @pytest.mark.asyncio
    async def test_no_matching_rules_denies(self):
        """Test that unknown actions are denied by default."""
        engine = PolicyEngine(rules={})

        context = ActionContext(
            action_name="unknown_malicious_action",
            parameters={},
            risk_level=PolicyRiskLevel.HIGH,
        )
        result = await engine.validate_action(context)
        assert result.allowed is False
        assert "denied by default" in result.reason

    @pytest.mark.asyncio
    async def test_deny_policy_blocks_system_files(self):
        """Test that system file access is blocked."""
        engine = PolicyEngine(rules={})

        context = ActionContext(
            action_name="read_file",
            parameters={"path": "/etc/passwd"},
            risk_level=PolicyRiskLevel.HIGH,
        )
        result = await engine.validate_action(context)
        assert result.allowed is False
        assert "system paths" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_deny_private_ips(self):
        """Test that private IP access is blocked."""
        engine = PolicyEngine(rules={})

        for ip in ["127.0.0.1", "10.0.0.1", "192.168.1.1", "0.0.0.0"]:
            context = ActionContext(
                action_name="http_request",
                parameters={"url": f"http://{ip}/api"},
                risk_level=PolicyRiskLevel.HIGH,
            )
            result = await engine.validate_action(context)
            assert result.allowed is False, f"Private IP {ip} should be blocked"
            assert "private ip" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_deny_blocked_domains(self):
        """Test that blocked domains are denied."""
        engine = PolicyEngine(rules={"blocked_domains": ["malware.com", "phishing.net"]})

        context = ActionContext(
            action_name="http_request",
            parameters={"url": "https://malware.com/api/steal"},
            risk_level=PolicyRiskLevel.HIGH,
        )
        result = await engine.validate_action(context)
        assert result.allowed is False
        assert "malware.com" in result.reason

    @pytest.mark.asyncio
    async def test_require_approval_for_high_risk(self):
        """Test that high-risk actions require approval."""
        engine = PolicyEngine(rules={"require_approval_actions": ["execute_payment"]})

        context = ActionContext(
            action_name="execute_payment",
            parameters={"amount": 50},
            risk_level=PolicyRiskLevel.CRITICAL,
        )
        result = await engine.validate_action(context)
        assert result.allowed is True  # Allowed but requires approval
        assert result.requires_approval is True
        assert "Manual approval required" in result.reason

    @pytest.mark.asyncio
    async def test_critical_risk_requires_approval(self):
        """Test that CRITICAL risk level actions always require approval."""
        engine = PolicyEngine(rules={})

        context = ActionContext(
            action_name="delete_database",
            parameters={},
            risk_level=PolicyRiskLevel.CRITICAL,
        )
        result = await engine.validate_action(context)
        assert result.allowed is True  # Allowed but requires approval
        assert result.requires_approval is True


class TestWildcardMatching:
    """Tests for wildcard pattern matching."""

    @pytest.mark.asyncio
    async def test_wildcard_prefix_match(self):
        """Test that action patterns with wildcards work."""
        engine = PolicyEngine(rules={})

        engine.add_tenant_rule(
            PolicyRule(
                action_pattern="query_*",
                allowed=True,
                reason="All query actions allowed",
            )
        )

        for action in ["query_users", "query_orders", "query_products"]:
            context = ActionContext(
                action_name=action,
                parameters={},
                risk_level=PolicyRiskLevel.LOW,
            )
            result = await engine.validate_action(context)
            assert result.allowed is True, f"Action '{action}' should match 'query_*'"


class TestPathTraversalProtection:
    """Tests for path traversal protection."""

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self):
        """Test that path traversal attempts are blocked."""
        engine = PolicyEngine(rules={})

        for path in ["../../../etc/passwd", "..\\..\\windows\\system32"]:
            context = ActionContext(
                action_name="read_file",
                parameters={"path": path},
                risk_level=PolicyRiskLevel.HIGH,
            )
            result = await engine.validate_action(context)
            assert result.allowed is False, f"Path traversal '{path}' should be blocked"


class TestDefaultLists:
    """Tests for default allow/deny lists."""

    def test_get_default_allow_actions(self):
        """Test getting default allow actions."""
        engine = PolicyEngine()
        actions = engine.get_default_allow_actions()
        assert "query" in actions
        assert "analyze" in actions
        assert "respond" in actions

    def test_get_default_deny_patterns(self):
        """Test getting default deny patterns."""
        engine = PolicyEngine()
        patterns = engine.get_default_deny_patterns()
        assert "file_system_access" in patterns
        assert "network_access_private" in patterns
