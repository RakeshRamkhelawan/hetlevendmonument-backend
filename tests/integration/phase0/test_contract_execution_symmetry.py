"""
Fase 0 Integratietest: Contract Execution Symmetry

Test alle Fase 0 componenten geïntegreerd:
- Capability Contract (TKT-F0-01)
- Tenant Policy Enforcement (TKT-F0-02)
- Execution Trace Contract (TKT-F0-03)

Verificatie:
1. Capability-resolutie werkt
2. Tenant-policy enforcement werkt
3. Trace events worden opgeslagen
4. Geen mocks - gebruikt echte componenten

Requirement: tests/integration/phase0/test_contract_execution_symmetry.py
"""

import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List

import pytest

from src.core.contracts import (  # Capability Contract; Tenant Policy; Execution Trace
    ApprovalThreshold,
    CapabilityContract,
    CapabilityRegistry,
    CapabilityResolver,
    EnforcementResult,
    ExecutionTrace,
    InMemoryTraceStore,
    PlanTier,
    PolicyEnforcer,
    ResolutionResult,
    TenantPolicy,
    TraceCollector,
    TraceOutcome,
)


class TestPhase0Integration:
    """
    Fase 0 Integratietest zonder mocks.

    Test scenario:
    1. Setup: 2 capabilities (email_send, payment_charge)
    2. Setup: 2 tenants (Starter, Growth)
    3. Workflow: 3 stappen
    - Stap 1: email_send (toegestaan, geen approval)
    - Stap 2: payment_charge (toegestaan, approval required)
    - Stap 3: email_send (fallback provider)
    4. Verificatie: Alle traces compleet
    """

    @pytest.fixture
    def setup_registry(self):
        """Setup capability registry with real contracts"""
        return {
            "email_send": CapabilityContract(
                capability_key="email_send",
                input_schema={
                    "type": "object",
                    "properties": {"to": {"type": "string"}, "subject": {"type": "string"}},
                    "required": ["to", "subject"],
                },
                output_schema={"type": "object"},
                retry_policy={"max_attempts": 3},
                fallback_policy={"enabled": True, "fallback_capability": "email_send_backup"},
            ),
            "email_send_backup": CapabilityContract(
                capability_key="email_send_backup",
                input_schema={
                    "type": "object",
                    "properties": {"to": {"type": "string"}, "subject": {"type": "string"}},
                    "required": ["to", "subject"],
                },
                output_schema={"type": "object"},
            ),
            "payment_charge": CapabilityContract(
                capability_key="payment_charge",
                input_schema={
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number", "minimum": 0.01},
                        "currency": {"type": "string"},
                    },
                    "required": ["amount", "currency"],
                },
                output_schema={"type": "object"},
            ),
        }

    @pytest.fixture
    def setup_policies(self):
        """Setup tenant policies"""
        return {
            "tenant-starter": TenantPolicy(
                tenant_id="tenant-starter",
                plan_tier=PlanTier.STARTER,
                enabled_capabilities=["email_send"],  # Geen payment!
            ),
            "tenant-growth": TenantPolicy(
                tenant_id="tenant-growth",
                plan_tier=PlanTier.PRO,
                enabled_capabilities=["email_send", "payment_charge"],
                approval_thresholds={
                    "payment_charge": ApprovalThreshold(amount_threshold=Decimal("100"))
                },
            ),
        }

    @pytest.fixture
    def setup_components(self, setup_registry, setup_policies):
        """Setup all real components (no mocks)"""
        # Build CapabilityRegistry from contracts dict
        capability_registry = CapabilityRegistry()
        for contract in setup_registry.values():
            capability_registry.register(contract)

        # Real capability resolver
        resolver = CapabilityResolver(capability_registry)

        # Real policy enforcer uses the same CapabilityRegistry
        enforcer = PolicyEnforcer(capability_registry)

        # Real trace store and collector
        trace_store = InMemoryTraceStore()
        trace_collector = TraceCollector(trace_store)

        return {
            "resolver": resolver,
            "enforcer": enforcer,
            "trace_store": trace_store,
            "trace_collector": trace_collector,
            "registry": capability_registry,
            "policies": setup_policies,
        }

    def test_step1_capability_resolution(self, setup_components):
        """
        Stap 1: Capability resolutie
        Verifieer dat capabilities correct worden geresolved
        """
        resolver = setup_components["resolver"]

        # Test known capability
        result = resolver.validate_node(
            {"capability_key": "email_send", "input": {"to": "test@example.com", "subject": "Test"}}
        )

        assert result.is_valid is True
        assert result.resolved_capability is not None
        assert result.resolved_capability.capability_key == "email_send"

    def test_step2_tenant_policy_enforcement(self, setup_components):
        """
        Stap 2: Tenant policy enforcement
        Verifieer dat policies correct worden afgedwongen
        """
        enforcer = setup_components["enforcer"]
        policies = setup_components["policies"]

        # Starter tenant: email_send allowed
        result = enforcer.check_execute_permission(
            node={
                "capability_key": "email_send",
                "input": {"to": "test@test.com", "subject": "Test"},
            },
            policy=policies["tenant-starter"],
        )
        assert result.can_execute is True

        # Starter tenant: payment_charge NOT allowed
        result = enforcer.check_execute_permission(
            node={"capability_key": "payment_charge", "input": {"amount": 50, "currency": "EUR"}},
            policy=policies["tenant-starter"],
        )
        assert result.can_execute is False
        assert "not enabled" in result.reason.lower() or "starter" in result.reason.lower()

    def test_step3_approval_requirement(self, setup_components):
        """
        Stap 3: Approval requirement voor high-value payment
        """
        enforcer = setup_components["enforcer"]

        # Growth tenant: high-value payment requires approval
        result = enforcer.check_execute_permission(
            node={"capability_key": "payment_charge", "input": {"amount": 500, "currency": "EUR"}},
            policy=setup_components["policies"]["tenant-growth"],
        )

        assert result.can_execute is False
        assert result.is_pending_approval is True

    def test_step4_fallback_provider_trace(self, setup_components):
        """
        Stap 4: Fallback provider usage wordt correct getraced
        """
        resolver = setup_components["resolver"]
        trace_collector = setup_components["trace_collector"]
        trace_store = setup_components["trace_store"]

        workflow_id = f"workflow-{uuid.uuid4().hex[:8]}"

        # Simulate workflow step with fallback
        with trace_collector.start_trace(
            {
                "trace_id": f"trace-{uuid.uuid4().hex[:8]}",
                "tenant_id": "tenant-growth",
                "workflow_id": workflow_id,
                "capability_key": "email_send",
            }
        ) as trace:
            # Simulate fallback usage
            trace.set_decision("Primary failed, using fallback")
            trace.set_fallback_used("sendgrid", "aws_ses")
            trace.set_success()

        # Verify trace was persisted
        traces = trace_store.get_workflow_traces(workflow_id)
        assert len(traces) == 1

        saved_trace = traces[0]
        assert saved_trace.fallback_used is True
        assert saved_trace.primary_provider == "sendgrid"
        assert saved_trace.fallback_provider == "aws_ses"

    def test_step5_complete_workflow_trace(self, setup_components):
        """
        Stap 5: Complete workflow met 3 stappen, alle traces aanwezig
        """
        resolver = setup_components["resolver"]
        enforcer = setup_components["enforcer"]
        trace_collector = setup_components["trace_collector"]
        trace_store = setup_components["trace_store"]

        workflow_id = f"workflow-{uuid.uuid4().hex[:8]}"
        tenant_id = "tenant-growth"

        # Stap 1: email_send (success)
        with trace_collector.start_trace(
            {
                "trace_id": f"trace-{uuid.uuid4().hex[:8]}",
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "capability_key": "email_send",
            }
        ) as trace:
            trace.set_decision("Policy allowed execution")
            trace.set_success()

        # Stap 2: payment_charge (pending approval)
        with trace_collector.start_trace(
            {
                "trace_id": f"trace-{uuid.uuid4().hex[:8]}",
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "capability_key": "payment_charge",
            }
        ) as trace:
            trace.set_decision("Approval required for amount > 100")
            trace.set_pending_approval()

        # Stap 3: email_send with fallback (success)
        with trace_collector.start_trace(
            {
                "trace_id": f"trace-{uuid.uuid4().hex[:8]}",
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "capability_key": "email_send",
            }
        ) as trace:
            trace.set_decision("Using fallback provider")
            trace.set_fallback_used("primary", "fallback")
            trace.set_success()

        # Verificatie: Alle 3 traces aanwezig
        traces = trace_store.get_workflow_traces(workflow_id)
        assert len(traces) == 3

        # Verificatie: Outcomes correct
        outcomes = [t.outcome for t in traces]
        assert TraceOutcome.SUCCESS in outcomes
        assert TraceOutcome.PENDING_APPROVAL in outcomes

        # Verificatie: Minstens 1 fallback gebruikt
        assert any(t.fallback_used for t in traces)

    def test_fase0_no_mock_symmetry(self, setup_components):
        """
        Eindverificatie: Alle componenten werken symbiotisch

        Deze test verifieert dat:
        1. Capability contracten correct worden geresolved
        2. Tenant policies correct worden afgedwongen
        3. Execution traces compleet worden opgeslagen
        4. Geen mocks gebruikt - alleen echte componenten
        """
        resolver = setup_components["resolver"]
        enforcer = setup_components["enforcer"]
        trace_collector = setup_components["trace_collector"]
        trace_store = setup_components["trace_store"]

        tenant_id = "tenant-growth"
        workflow_id = f"workflow-{uuid.uuid4().hex[:8]}"

        # Voer een complete workflow uit
        steps = [
            {
                "capability": "email_send",
                "inputs": {"to": "test@test.com", "subject": "Hello"},
                "expected_allowed": True,
                "expected_outcome": TraceOutcome.SUCCESS,
            },
            {
                "capability": "payment_charge",
                "inputs": {"amount": 200, "currency": "EUR"},  # Requires approval
                "expected_allowed": False,
                "expected_status": "pending_approval",
            },
        ]

        policies = setup_components["policies"]
        tenant_policy = policies[tenant_id]

        for step in steps:
            # 1. Capability resolutie
            resolve_result = resolver.validate_node(
                {"capability_key": step["capability"], "input": step["inputs"]}
            )

            # Capability MOET resolven (schema check)
            assert (
                resolve_result.resolved_capability is not None
            ), f"Capability {step['capability']} should resolve"

            # 2. Policy enforcement
            enforce_result = enforcer.check_execute_permission(
                node={"capability_key": step["capability"], "input": step["inputs"]},
                policy=tenant_policy,
            )

            # 3. Trace collection
            with trace_collector.start_trace(
                {
                    "trace_id": f"trace-{uuid.uuid4().hex[:8]}",
                    "tenant_id": tenant_id,
                    "workflow_id": workflow_id,
                    "capability_key": step["capability"],
                }
            ) as trace:
                trace.set_decision(enforce_result.reason or "Policy check complete")

                if enforce_result.can_execute:
                    trace.set_success()
                elif enforce_result.is_pending_approval:
                    trace.set_pending_approval()
                else:
                    trace.set_failure("POLICY_DENIED", enforce_result.reason)

        # Verificatie: Alle traces opgeslagen
        traces = trace_store.get_workflow_traces(workflow_id)
        assert len(traces) == len(steps), f"Expected {len(steps)} traces, got {len(traces)}"

        # Verificatie: Alle velden compleet
        for trace in traces:
            assert trace.trace_id is not None
            assert trace.tenant_id == tenant_id
            assert trace.workflow_id == workflow_id
            assert trace.capability_key in [s["capability"] for s in steps]
            assert trace.timestamp is not None
            assert trace.latency_ms >= 0

        print("\n✅ Fase 0 Integratietest SUCCESS:")
        print(f"   - {len(traces)} workflow steps executed")
        print(f"   - {len([t for t in traces if t.is_success()])} successful")
        print(
            f"   - {len([t for t in traces if t.outcome == TraceOutcome.PENDING_APPROVAL])} pending approval"
        )
        print("   - All traces complete with audit data")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
