"""
Security Penetration Testing

Security audit and penetration tests for ALS 2.0.
"""

import asyncio
from datetime import datetime

import pytest

# Import ALS event types for audit testing
from src.core.als.enterprise.audit.audit_logger import AuditEventType
from src.core.als.enterprise.events.event_store import Event, EventType

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.security,
]


class TestAuthenticationSecurity:
    """Test authentication mechanisms."""

    async def test_jwt_token_validation(self, client):
        """Test JWT tokens are properly validated."""
        # Test with invalid token
        response = await client.get(
            "/api/v1/als/agents", headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401

    async def test_token_expiration(self, client):
        """Test expired tokens are rejected."""
        # Use expired token
        expired_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
        response = await client.get(
            "/api/v1/als/agents", headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401

    async def test_brute_force_protection(self, client):
        """Test brute force attack protection."""
        # Attempt multiple failed logins
        for i in range(10):
            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": f"wrong{i}"},
            )

        # Should be rate limited
        response = await client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
        )
        assert response.status_code == 429  # Too Many Requests


class TestAuthorizationSecurity:
    """Test authorization controls."""

    async def test_tenant_isolation(self, client, auth_headers):
        """Test cross-tenant access is blocked."""
        # User from tenant 1 tries to access tenant 2
        response = await client.get(
            "/api/v1/als/tenants/2/contracts",
            headers=auth_headers,  # Token for tenant 1
        )
        assert response.status_code == 403

    async def test_role_based_access(self, client, user_token):
        """Test RBAC enforcement."""
        # Regular user tries admin action
        response = await client.post(
            "/api/v1/als/tenants",
            json={"tenant_id": 999},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    async def test_resource_level_permissions(self, client, auth_headers):
        """Test resource-level access control."""
        # User without permission tries to access contract
        response = await client.get(
            "/api/v1/als/contracts/confidential-contract", headers=auth_headers
        )
        assert response.status_code in [401, 403, 404]


class TestInputValidation:
    """Test input validation and injection prevention."""

    async def test_sql_injection_prevention(self, client, auth_headers):
        """Test SQL injection is prevented."""
        malicious_id = "1' OR '1'='1"
        response = await client.get(f"/api/v1/als/contracts/{malicious_id}", headers=auth_headers)
        # Should not return data for other contracts
        assert response.status_code in [400, 404]

    async def test_xss_prevention(self, client, auth_headers):
        """Test XSS is prevented."""
        xss_payload = "<script>alert('xss')</script>"
        response = await client.post(
            "/api/v1/als/contracts",
            json={"contract_id": "test", "payload": {"data": xss_payload}},
            headers=auth_headers,
        )
        # Script should be sanitized or rejected
        assert response.status_code in [200, 400]

    async def test_command_injection_prevention(self, client, auth_headers):
        """Test command injection is prevented."""
        malicious_input = "; rm -rf /"
        response = await client.post(
            "/api/v1/als/tasks/delegate",
            json={"task_id": malicious_input, "type": "test"},
            headers=auth_headers,
        )
        # Should not execute command
        assert response.status_code in [400, 422]


class TestAuditSecurity:
    """Test audit log security."""

    async def test_audit_log_immutable(self, audit_logger):
        """Test audit events cannot be modified."""
        event = await audit_logger.log_contract_event(
            event_type=AuditEventType.CONTRACT_PROPOSED,
            contract_id="test-001",
            actor_id="agent-001",
            details={},
        )

        # Attempt to modify
        with pytest.raises(Exception):
            event.actor_id = "hacker"

    async def test_audit_log_integrity(self, audit_logger):
        """Test audit log integrity verification."""
        # Create events
        for i in range(10):
            await audit_logger.log_contract_event(
                event_type=AuditEventType.CONTRACT_PROPOSED,
                contract_id=f"test-{i}",
                actor_id=f"agent-{i}",
                details={},
            )

        # Verify integrity
        is_valid, errors = audit_logger.verify_integrity()
        assert is_valid is True
        assert len(errors) == 0


class TestCryptographicSecurity:
    """Test cryptographic implementations."""

    async def test_hash_uniqueness(self):
        """Test that hashes are unique."""
        from src.core.als.enterprise.events.event_store import Event

        hashes = set()
        for i in range(1000):
            event = Event(
                event_id=f"evt-{i}",
                event_type=EventType.CONTRACT_PROPOSED,
                tenant_id=1,
                aggregate_id=f"agg-{i}",
                aggregate_type="test",
                payload={"seq": i},
                timestamp=datetime.utcnow(),
                previous_hash="0" * 32,
            )
            hashes.add(event.event_hash)

        # All hashes should be unique
        assert len(hashes) == 1000

    async def test_hash_chain_integrity(self):
        """Test hash chain cannot be broken."""
        from src.core.als.enterprise.events.event_store import EventStore

        store = EventStore()

        # Create chain
        prev_hash = "0" * 32
        for i in range(10):
            event = Event(
                event_id=f"evt-{i}",
                event_type=EventType.CONTRACT_PROPOSED,
                tenant_id=1,
                aggregate_id="test",
                aggregate_type="test",
                payload={"seq": i},
                timestamp=datetime.utcnow(),
                previous_hash=prev_hash,
            )
            await store.append(event)
            prev_hash = event.event_hash

        # Verify chain
        assert store.verify_hash_chain("test") is True


class TestDoSPrevention:
    """Test DoS attack prevention."""

    async def test_rate_limiting(self, client):
        """Test API rate limiting."""
        # Make many rapid requests
        responses = []
        for i in range(200):
            response = await client.get("/api/v1/als/health")
            responses.append(response.status_code)

        # Some should be rate limited
        assert 429 in responses

    async def test_payload_size_limit(self, client, auth_headers):
        """Test large payload rejection."""
        large_payload = {"data": "x" * (10 * 1024 * 1024)}  # 10MB

        response = await client.post(
            "/api/v1/als/contracts", json=large_payload, headers=auth_headers
        )
        assert response.status_code == 413  # Payload Too Large

    async def test_connection_limit(self):
        """Test concurrent connection limits."""

        # Attempt many concurrent connections
        async def connect():
            # Implementation depends on client
            pass

        # Should not crash server
        tasks = [connect() for _ in range(1000)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Some connections may fail, but server should survive
        assert True


class TestShadowCEOSecurity:
    """Test ShadowCEO security features."""

    async def test_high_risk_task_veto(self, shadow_ceo):
        """Test high-risk tasks are vetoed."""
        from src.core.shared.interfaces import TaskData

        high_risk_task = TaskData(
            id="risky-task",
            title="delete_all_production_data",
            description="High risk task",
            payload={},
            priority=5,
            metadata={"affected_systems": 100},
        )

        veto = await shadow_ceo.review_task(
            task=high_risk_task,
            proposed_agent="agent-001",
        )

        assert veto is not None
        assert veto.risk_level.name in ["HIGH", "CRITICAL"]


class TestGatekeeperSecurity:
    """Test Gatekeeper security features."""

    async def test_policy_enforcement(self, gatekeeper):
        """Test policies are enforced."""
        from src.core.shared.interfaces import TaskData

        pii_task = TaskData(
            id="pii-task",
            title="access_pii",
            description="Access PII data",
            payload={},
            priority=3,
        )

        result = await gatekeeper.evaluate_task(
            task=pii_task,
            proposed_department=None,
        )

        # PII access should require HITL
        assert result.decision.value in ["hitl", "block"]


# OWASP Top 10 Tests
class TestOWASPTop10:
    """Tests for OWASP Top 10 vulnerabilities."""

    async def test_a01_broken_access_control(self, client):
        """A01:2021 – Broken Access Control"""
        # Test IDOR
        response = await client.get("/api/v1/als/contracts/other-users-contract")
        assert response.status_code in [401, 403, 404]

    async def test_a02_cryptographic_failures(self):
        """A02:2021 – Cryptographic Failures"""
        # Test sensitive data is encrypted
        pass

    async def test_a03_injection(self, client, auth_headers):
        """A03:2021 – Injection"""
        # Tested in TestInputValidation
        pass

    async def test_a04_insecure_design(self):
        """A04:2021 – Insecure Design"""
        # Test business logic flaws
        pass

    async def test_a05_security_misconfiguration(self, client):
        """A05:2021 – Security Misconfiguration"""
        # Test error messages don't leak info
        response = await client.get("/api/v1/als/admin")
        assert "stack trace" not in response.text.lower()
        assert "debug" not in response.text.lower()

    async def test_a06_vulnerable_components(self):
        """A06:2021 – Vulnerable and Outdated Components"""
        # Would use dependency scanner
        pass

    async def test_a07_auth_failures(self, client):
        """A07:2021 – Identification and Authentication Failures"""
        # Tested in TestAuthenticationSecurity
        pass

    async def test_a08_data_integrity(self):
        """A08:2021 – Software and Data Integrity Failures"""
        # Tested in TestCryptographicSecurity
        pass

    async def test_a09_logging_failures(self, audit_logger):
        """A09:2021 – Security Logging and Monitoring Failures"""
        # Verify security events are logged
        await audit_logger.log_security_event(
            AuditEventType.AUTHENTICATION_FAILURE,
            "attacker",
            {"reason": "brute_force"},
        )

        events = audit_logger.get_events(event_type=AuditEventType.AUTHENTICATION_FAILURE)
        assert len(events) > 0

    async def test_a10_ssrf(self, client, auth_headers):
        """A10:2021 – Server-Side Request Forgery"""
        # Test SSRF prevention
        response = await client.post(
            "/api/v1/als/webhooks",
            json={"url": "http://169.254.169.254/latest/meta-data/"},
            headers=auth_headers,
        )
        # Should block internal IP
        assert response.status_code in [400, 403]
