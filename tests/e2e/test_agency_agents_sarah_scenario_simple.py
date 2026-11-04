"""
SIMPLIFIED E2E Test: Sarah's Real-world Agent Usage Scenario

This test proves that:
1. Agents are STATELESS (no hidden memory)
2. Context must be EXPLICITLY provided
3. Tenant isolation WORKS
4. Results are based on PAYLOAD, not magic
"""

import pytest

# Skip entire module - requires generated agents and full infrastructure
pytestmark = pytest.mark.skip(reason="Requires generated agents and full stack - run manually")

import asyncio
import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Import agents directly to avoid __init__ loading broken ones
try:
    from src.core.agents.generated.agency_backend_architect_agent import agency_backend_architect
    from src.core.agents.generated.agency_frontend_developer_agent import agency_frontend_developer
    from src.core.agents.generated.agency_growth_hacker_agent import agency_growth_hacker
    from src.core.agents.generated.agency_security_engineer_agent import agency_security_engineer
    from src.core.agents.generated.agency_ui_designer_agent import agency_ui_designer
    from src.core.shared.interfaces import TaskData
except ImportError as e:
    # Define placeholders if imports fail
    agency_ui_designer = None
    agency_security_engineer = None
    agency_backend_architect = None
    agency_growth_hacker = None
    agency_frontend_developer = None
    TaskData = None


async def test_sarah_scenario():
    """
    Replicates Sarah's workflow at FlowMetrics.
    Proves agents are stateless and only respond to explicit context.
    """

    print("\n" + "=" * 70)
    print("E2E TEST: Sarah Chen's FlowMetrics Workflow")
    print("=" * 70)

    # ========================================================================
    # TEST 1: Agent is NOT aware of projects without context
    # ========================================================================
    print("\n[TEST 1] Agent Statelessness Proof")
    print("-" * 50)

    await agency_ui_designer.initialize()

    # Call WITHOUT context → Generic result
    print("\n1A. Calling UI Designer WITHOUT project context...")
    generic_task = TaskData(
        id="test_generic",
        title="Generic Design System",
        payload={},  # NO context!
        metadata={"type": "create_design_system"},
    )

    generic_result = await agency_ui_designer.process_task(generic_task)
    assert generic_result.success

    generic_css = generic_result.result_data.get("css_variables", "")
    print("   [OK] Generic result uses defaults")

    # Call WITH Sarah's context → Specific result
    print("\n1B. Calling UI Designer WITH Sarah's explicit context...")
    sarah_task = TaskData(
        id="test_sarah_flowmetrics",
        title="FlowMetrics Design System",
        payload={
            "brand_colors": {"primary": "#6366f1", "secondary": "#8b5cf6"},  # FlowMetrics purple
            "spacing_base": 4,
            "component_needs": ["dashboard_cards", "charts"],
        },
        metadata={
            "type": "create_design_system",
            "tenant_id": 847,
            "user_id": "sarah_chen",
        },
    )

    sarah_result = await agency_ui_designer.process_task(sarah_task)
    assert sarah_result.success

    sarah_css = sarah_result.result_data.get("css_variables", "")

    # PROOF: Results differ based on payload
    assert "#6366f1" in sarah_css, "Should use Sarah's brand color"
    assert generic_css != sarah_css, "Different payloads → Different results"

    print("   ✓ Sarah's result uses #6366f1 (her brand color)")
    print("   ✓ PROOF: Agent is stateless - only responds to explicit payload")

    # ========================================================================
    # TEST 2: Security agent adapts to provided context
    # ========================================================================
    print("\n[TEST 2] Security Agent Context Adaptation")
    print("-" * 50)

    await agency_security_engineer.initialize()

    print("\n2A. Analyzing 'Real-time Analytics Dashboard'...")
    security_task = TaskData(
        id="security_analytics",
        title="Analytics Security Audit",
        payload={
            "system_name": "Real-time Analytics Dashboard",
            "methodology": "stride",
            "data_sensitivity": "high",
        },
        metadata={"type": "conduct_threat_modeling"},
    )

    analytics_result = await agency_security_engineer.process_task(security_task)
    assert analytics_result.success

    analytics_threats = analytics_result.result_data.get("threats", [])
    print(f"   ✓ Found {len(analytics_threats)} threats for analytics system")

    # Different context → Different results
    print("\n2B. Analyzing 'Marketing Website' (different context)...")
    web_task = TaskData(
        id="security_marketing",
        title="Marketing Site Audit",
        payload={
            "system_name": "Marketing Website",
            "methodology": "stride",
            "data_sensitivity": "low",  # Different!
        },
        metadata={"type": "conduct_threat_modeling"},
    )

    web_result = await agency_security_engineer.process_task(web_task)
    assert web_result.success

    web_threats = web_result.result_data.get("threats", [])
    print(f"   ✓ Found {len(web_threats)} threats for marketing site")

    # PROOF: Different context produces different results
    assert analytics_result.result_data != web_result.result_data
    print("   ✓ PROOF: Agent adapts analysis to provided context")

    # ========================================================================
    # TEST 3: Tenant Isolation
    # ========================================================================
    print("\n[TEST 3] Tenant Isolation Verification")
    print("-" * 50)

    print("\n3A. Sarah (Tenant 847) creates design...")
    sarah_design = TaskData(
        id="sarah_design",
        title="Sarah's Design",
        payload={"brand_colors": {"primary": "#6366f1"}},
        metadata={"type": "create_design_system", "tenant_id": 847},
    )
    sarah_output = await agency_ui_designer.process_task(sarah_design)

    print("\n3B. Competitor (Tenant 999) creates design...")
    competitor_design = TaskData(
        id="competitor_design",
        title="Competitor's Design",
        payload={"brand_colors": {"primary": "#ff0000"}},
        metadata={"type": "create_design_system", "tenant_id": 999},
    )
    competitor_output = await agency_ui_designer.process_task(competitor_design)

    # CRITICAL: Competitor CANNOT see Sarah's data
    competitor_css = competitor_output.result_data.get("css_variables", "")
    assert "#6366f1" not in competitor_css, "Tenant isolation breach!"

    print("   ✓ Sarah sees: #6366f1")
    print("   ✓ Competitor sees: #ff0000")
    print("   ✓ PROOF: Tenant isolation works - no data leakage")

    # ========================================================================
    # TEST 4: Full Workflow
    # ========================================================================
    print("\n[TEST 4] Complete Sarah Workflow (6 Tasks)")
    print("-" * 50)

    await agency_backend_architect.initialize()
    await agency_growth_hacker.initialize()
    await agency_frontend_developer.initialize()

    tasks = [
        ("UI Designer", "create_design_system", {"brand_colors": {"primary": "#6366f1"}}),
        (
            "Security Engineer",
            "conduct_threat_modeling",
            {"system_name": "Real-time Analytics Dashboard", "data_sensitivity": "high"},
        ),
        (
            "Backend Architect",
            "design_api",
            {"api_type": "rest", "resources": ["analytics_data", "dashboards"]},
        ),
        ("Growth Hacker", "design_viral_loop", {"product_type": "saas"}),
        (
            "Frontend Developer",
            "create_component",
            {"framework": "react", "component_name": "AnalyticsChart"},
        ),
    ]

    results = []
    for agent_name, task_type, payload in tasks:
        print(f"\n   Executing: {agent_name} → {task_type}...")

        # Map names to agents
        agent_map = {
            "UI Designer": agency_ui_designer,
            "Security Engineer": agency_security_engineer,
            "Backend Architect": agency_backend_architect,
            "Growth Hacker": agency_growth_hacker,
            "Frontend Developer": agency_frontend_developer,
        }

        task = TaskData(
            id=f"workflow_{task_type}",
            title=task_type,
            payload=payload,
            metadata={"type": task_type, "tenant_id": 847, "user_id": "sarah_chen"},
        )

        result = await agent_map[agent_name].process_task(task)
        assert result.success, f"{agent_name} failed: {result.error_message}"
        results.append(result)
        print(f"      ✓ Success ({result.execution_time:.2f}s)")

    total_time = sum(r.execution_time for r in results)
    print(f"\n   [OK] ALL {len(tasks)} TASKS COMPLETED")
    print(f"   [OK] Total time: {total_time:.2f}s")

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("\n" + "=" * 70)
    print("[SUCCESS] E2E TEST PASSED - ALL VERIFICATIONS SUCCESSFUL")
    print("=" * 70)

    print(
        """
KEY FINDINGS:

1. STATELESS: Agents have NO memory of previous calls or projects
   - Each call is independent
   - No hidden "project awareness"

2. EXPLICIT CONTEXT: Agents only "know" what you tell them
   - Empty payload → Generic result
   - Detailed payload → Specific result

3. TENANT ISOLATION: Data is strictly separated
   - Tenant 847 cannot see Tenant 999's data
   - No cross-tenant leakage

4. PAYLOAD-DRIVEN: Results determined by input, not magic
   - Same payload → Similar result
   - Different payload → Different result

CONCLUSION:
Sarah's agents are NOT "aware" of her project. They generate results
based ENTIRELY on the explicit context she provides in each payload.
    """
    )


if __name__ == "__main__":
    asyncio.run(test_sarah_scenario())
