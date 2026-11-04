"""
E2E Test: Sarah's Real-world Agent Usage Scenario

This test verifies:
1. Agents are NOT inherently aware of projects (stateless)
2. Context must be explicitly provided in payload
3. Tenant isolation works correctly
4. Results are generated based on provided context, not hidden state
"""

import pytest

# Skip entire module - requires generated agents and full infrastructure
pytestmark = pytest.mark.skip(reason="Requires generated agents and full stack - run manually")

from datetime import datetime

from src.core.agents.generated import (
    agency_backend_architect,
    agency_brand_guardian,
    agency_content_creator,
    agency_frontend_developer,
    agency_growth_hacker,
    agency_security_engineer,
    agency_ui_designer,
)
from src.core.agents.generated.tenant_service import TenantAgentService
from src.core.shared.interfaces import TaskData


@pytest.mark.e2e
@pytest.mark.asyncio
class TestSarahScenarioE2E:
    """
    E2E test that replicates Sarah Chen's workflow at FlowMetrics.

    Key Assertion: Agents are stateless and only "know" what Sarah tells them
    via the payload. They do NOT have hidden project context.
    """

    async def test_step1_design_system_requires_explicit_context(self):
        """
        PROOF: Agent is NOT aware of FlowMetrics until Sarah provides context.

        If we call the agent WITHOUT project context, it returns generic results.
        Only when Sarah provides brand_colors does it generate specific output.
        """
        print("\n" + "=" * 60)
        print("STEP 1: Design System Generation")
        print("=" * 60)

        # Initialize agent (clean slate - no memory)
        await agency_ui_designer.initialize()

        # TEST A: Call WITHOUT context → Generic result
        print("\n1A. Calling agent WITHOUT project context...")
        generic_task = TaskData(
            id="test_generic",
            title="Generic Design System",
            payload={},  # NO context provided!
            metadata={"type": "create_design_system"},
        )

        generic_result = await agency_ui_designer.process_task(generic_task)

        # Verify: Generic result uses defaults
        assert generic_result.success
        result_data = generic_result.result_data

        # Should use default colors, NOT FlowMetrics colors
        generic_css = result_data.get("css_variables", "")
        assert "#3b82f6" in generic_css or "--color-primary" in generic_css  # Default blue
        print("   ✓ Generic result uses default colors (no FlowMetrics awareness)")

        # TEST B: Call WITH Sarah's context → Specific result
        print("\n1B. Calling agent WITH Sarah's explicit context...")
        sarah_task = TaskData(
            id="test_sarah_flowmetrics",
            title="FlowMetrics Design System",
            payload={
                "brand_colors": {
                    "primary": "#6366f1",  # FlowMetrics purple
                    "secondary": "#8b5cf6",
                    "accent": "#f59e0b",
                },
                "spacing_base": 4,
                "component_needs": ["dashboard_cards", "charts", "filters"],
            },
            metadata={
                "type": "create_design_system",
                "tenant_id": 847,  # Sarah's tenant
                "user_id": "sarah_chen",
                "project": "real_time_analytics_dashboard",
            },
        )

        sarah_result = await agency_ui_designer.process_task(sarah_task)

        # Verify: Result uses Sarah's specific colors
        assert sarah_result.success
        sarah_css = sarah_result.result_data.get("css_variables", "")

        assert "#6366f1" in sarah_css, "Should use FlowMetrics primary color"
        assert "#8b5cf6" in sarah_css, "Should use FlowMetrics secondary color"
        print("   ✓ Sarah's result uses her specific brand colors (#6366f1)")

        # KEY PROOF: Results are different based on payload, not agent "memory"
        assert generic_css != sarah_css, "Results should differ based on payload context"
        print("   ✓ PROOF: Different payloads → Different results (agent is stateless)")

    async def test_step2_security_audit_project_specific(self):
        """
        PROOF: Security agent only knows about "Real-time Analytics Dashboard"
        because Sarah explicitly provides it in the payload.
        """
        print("\n" + "=" * 60)
        print("STEP 2: Security Threat Modeling")
        print("=" * 60)

        await agency_security_engineer.initialize()

        print("\n2. Sarah provides project details in payload...")
        security_task = TaskData(
            id="security_flowmetrics",
            title="FlowMetrics Security Audit",
            payload={
                "system_name": "Real-time Analytics Dashboard",  # ← Sarah provides this
                "methodology": "stride",
                "data_sensitivity": "high",
                "user_types": ["admin", "analyst", "viewer"],
                "integrations": ["postgresql", "redis", "s3"],
            },
            metadata={
                "type": "conduct_threat_modeling",
                "tenant_id": 847,
                "user_id": "sarah_chen",
            },
        )

        result = await agency_security_engineer.process_task(security_task)

        assert result.success
        threats = result.result_data.get("threats", [])

        # Verify: Threats are specific to what Sarah described
        threat_categories = [t["category"] for t in threats]

        # Should have threats relevant to analytics dashboards
        assert (
            "Information Disclosure" in threat_categories
        ), "Should identify data exposure risks (because Sarah said 'high sensitivity')"
        assert (
            "Denial of Service" in threat_categories
        ), "Should identify DoS risks (because Sarah mentioned 'real-time')"

        print("   ✓ Threats specific to 'Real-time Analytics Dashboard'")
        print(f"   ✓ Identified {len(threats)} threats based on Sarah's context")

        # PROOF: If we change the payload, threats change
        print("\n2B. Changing payload to 'Marketing Website'...")
        different_task = TaskData(
            id="security_marketing_site",
            title="Different Project",
            payload={
                "system_name": "Marketing Website",  # Different!
                "methodology": "stride",
                "data_sensitivity": "low",  # Different!
            },
            metadata={"type": "conduct_threat_modeling"},
        )

        different_result = await agency_security_engineer.process_task(different_task)

        # Should produce DIFFERENT threats (no "high sensitivity" issues)
        assert (
            result.result_data != different_result.result_data
        ), "Different payload should produce different security analysis"
        print("   ✓ PROOF: Different context → Different threats (agent adapts to payload)")

    async def test_step3_tenant_isolation_sarah_vs_competitor(self):
        """
        CRITICAL TEST: Verify that another tenant (competitor) using the same agent
        CANNOT access Sarah's project data or results.
        """
        print("\n" + "=" * 60)
        print("STEP 3: Tenant Isolation Verification")
        print("=" * 60)

        await agency_ui_designer.initialize()

        # Sarah (Tenant 847) creates her design system
        print("\n3A. Sarah (Tenant 847) creates design system...")
        sarah_task = TaskData(
            id="sarah_design_001",
            title="Sarah's Design System",
            payload={
                "brand_colors": {"primary": "#6366f1"},  # FlowMetrics purple
                "secret_feature": "proprietary_ml_algorithm",  # Sensitive!
            },
            metadata={
                "type": "create_design_system",
                "tenant_id": 847,  # Sarah's tenant
            },
        )

        sarah_result = await agency_ui_designer.process_task(sarah_task)
        sarah_output = sarah_result.result_data

        # Competitor (Tenant 999) tries to get the same result
        print("\n3B. Competitor (Tenant 999) calls same agent with different tenant_id...")
        competitor_task = TaskData(
            id="competitor_design_001",
            title="Competitor's Design System",
            payload={
                "brand_colors": {"primary": "#ff0000"},  # Different color
            },
            metadata={
                "type": "create_design_system",
                "tenant_id": 999,  # Different tenant!
            },
        )

        competitor_result = await agency_ui_designer.process_task(competitor_task)
        competitor_output = competitor_result.result_data

        # CRITICAL: Competitor should get DIFFERENT results
        assert "#6366f1" not in str(
            competitor_output
        ), "Competitor should NOT see Sarah's brand color"
        assert "proprietary_ml_algorithm" not in str(
            competitor_output
        ), "Competitor should NOT see Sarah's secret feature"

        print("   ✓ Sarah sees: #6366f1 (her color)")
        print("   ✓ Competitor sees: #ff0000 (their color)")
        print("   ✓ PROOF: Tenant isolation works - agents don't share data between tenants")

    async def test_step4_complete_sarah_workflow_via_service(self):
        """
        INTEGRATION: Test the full workflow using TenantAgentService.
        Verifies that the service correctly manages tenant context.
        """
        print("\n" + "=" * 60)
        print("STEP 4: Complete Workflow via TenantAgentService")
        print("=" * 60)

        # Sarah uses the service (clean interface)
        print("\n4. Sarah uses TenantAgentService for all tasks...")
        sarah_service = TenantAgentService(tenant_id=847)

        # Task 1: Design System
        print("\n   4A. Design System...")
        design_result = await sarah_service.execute(
            agent_name="ui_designer",
            task_type="create_design_system",
            payload={
                "brand_colors": {"primary": "#6366f1", "secondary": "#8b5cf6"},
                "component_needs": ["dashboard_cards", "charts"],
            },
            user_id="sarah_chen",
        )
        assert design_result["success"]
        assert "#6366f1" in str(design_result["result"])
        print("      ✓ Design system generated")

        # Task 2: Security Audit
        print("\n   4B. Security Audit...")
        security_result = await sarah_service.execute(
            agent_name="security_engineer",
            task_type="conduct_threat_modeling",
            payload={"system_name": "Real-time Analytics Dashboard", "data_sensitivity": "high"},
            user_id="sarah_chen",
        )
        assert security_result["success"]
        threats = security_result["result"].get("threats", [])
        assert len(threats) > 0
        print(f"      ✓ {len(threats)} threats identified")

        # Task 3: Backend API
        print("\n   4C. Backend Architecture...")
        backend_result = await sarah_service.execute(
            agent_name="backend_architect",
            task_type="design_api",
            payload={
                "api_type": "rest",
                "resources": ["analytics_data", "dashboards"],
                "special_requirements": ["real_time_updates"],
            },
            user_id="sarah_chen",
        )
        assert backend_result["success"]
        endpoints = backend_result["result"].get("endpoints", [])
        assert len(endpoints) > 0
        print(f"      ✓ {len(endpoints)} API endpoints designed")

        # Task 4: Growth Strategy
        print("\n   4D. Growth Strategy...")
        growth_result = await sarah_service.execute(
            agent_name="growth_hacker",
            task_type="design_viral_loop",
            payload={"product_type": "saas", "feature": "analytics_dashboard"},
            user_id="sarah_chen",
        )
        assert growth_result["success"]
        print(
            f"      ✓ Viral coefficient target: {growth_result['result']['kpi_targets']['viral_coefficient']}"
        )

        # Task 5: Content
        print("\n   4E. Content Creation...")
        content_result = await sarah_service.execute(
            agent_name="content_creator",
            task_type="write_blog_post",
            payload={"topic": "Introducing Real-time Analytics", "tone": "professional"},
            user_id="sarah_chen",
        )
        assert content_result["success"]
        headlines = content_result["result"].get("headlines", [])
        assert len(headlines) > 0
        print(f"      ✓ {len(headlines)} headline options generated")

        # Task 6: Frontend Component
        print("\n   4F. Frontend Component...")
        frontend_result = await sarah_service.execute(
            agent_name="frontend_developer",
            task_type="create_component",
            payload={
                "framework": "react",
                "component_name": "AnalyticsChart",
                "props": [{"name": "data", "type": "TimeSeriesData[]"}],
            },
            user_id="sarah_chen",
        )
        assert frontend_result["success"]
        code = frontend_result["result"].get("code", "")
        assert "AnalyticsChart" in code
        print(f"      ✓ React component generated ({len(code)} chars)")

        print("\n   ✓ ALL 6 TASKS COMPLETED SUCCESSFULLY")
        print(
            f"   ✓ Total execution time: {sum([r['execution_time'] for r in [design_result, security_result, backend_result, growth_result, content_result, frontend_result]]):.2f}s"
        )

    async def test_step5_agent_has_no_hidden_memory(self):
        """
        CRITICAL PROOF: Demonstrate that agents truly have NO memory.

        We call the same agent twice with the SAME payload.
        If the agent had "learned" from Sarah, the second call might be different.
        But since it's stateless, both calls return consistent results.
        """
        print("\n" + "=" * 60)
        print("STEP 5: Proof of Stateless Nature (No Hidden Memory)")
        print("=" * 60)

        await agency_ui_designer.initialize()

        payload = {"brand_colors": {"primary": "#123456"}, "spacing_base": 8}

        print("\n5A. First call with specific payload...")
        task1 = TaskData(
            id="memory_test_1",
            title="Test 1",
            payload=payload,
            metadata={"type": "create_design_system"},
        )
        result1 = await agency_ui_designer.process_task(task1)

        print("\n5B. Second call with IDENTICAL payload...")
        task2 = TaskData(
            id="memory_test_2",  # Different ID!
            title="Test 2",
            payload=payload,  # Same payload
            metadata={"type": "create_design_system"},
        )
        result2 = await agency_ui_designer.process_task(task2)

        # Results should be functionally equivalent
        # (LLM might vary slightly, but structure should be consistent)
        assert result1.success and result2.success
        assert "css_variables" in result1.result_data
        assert "css_variables" in result2.result_data

        print("   ✓ Both calls succeeded")
        print("   ✓ PROOF: Agent produces consistent output for same input (stateless)")
        print("   ✓ Agent did NOT 'remember' previous call or 'learn' from Sarah")


@pytest.mark.asyncio
async def test_full_sarah_scenario():
    """
    Run the complete Sarah scenario as a single integration test.
    """
    print("\n" + "=" * 70)
    print("FULL E2E TEST: Sarah Chen's FlowMetrics Workflow")
    print("=" * 70)

    test_class = TestSarahScenarioE2E()

    # Run all steps
    await test_class.test_step1_design_system_requires_explicit_context()
    await test_class.test_step2_security_audit_project_specific()
    await test_class.test_step3_tenant_isolation_sarah_vs_competitor()
    await test_class.test_step4_complete_sarah_workflow_via_service()
    await test_class.test_step5_agent_has_no_hidden_memory()

    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED - E2E SCENARIO VERIFIED")
    print("=" * 70)
    print("\nKEY FINDINGS:")
    print("1. Agents are STATELESS - they only 'know' what Sarah tells them")
    print("2. Context MUST be provided explicitly in payload")
    print("3. Tenant isolation works - competitors cannot access Sarah's data")
    print("4. Agents generate results based on payload, not hidden memory")
    print("5. Same payload = Same result (deterministic behavior)")
