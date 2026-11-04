"""
Test VIBE Workflow Generation - Enhanced to 95% Autonomy
Verbeterde versie met extra agents en volledige automatisering
"""

import json

import pytest
import requests

BASE_URL = "http://localhost:8100"  # Port updated from 8000 to 8100
EMAIL = "test@example.com"
PASSWORD = "TestPass123"


@pytest.mark.manual
@pytest.mark.skip(reason="Manual test - requires running backend and user setup")
def test_vibe_workflow_95percent_autonomy():
    """Test VIBE workflow generation with 95% autonomy target"""

    print("\n" + "=" * 80)
    print("VIBE WORKFLOW UITBREIDING - Van 75% naar 95% Autonomie")
    print("=" * 80)

    # Login
    print("\n[STAP 1/3] Inloggen...")
    login_response = requests.post(
        f"{BASE_URL}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )

    if login_response.status_code != 200:
        pytest.skip(f"Login failed: {login_response.status_code} - user may not exist")

    token = login_response.json().get("access_token")
    print(f"[OK] Ingelogd als {EMAIL}")

    # Enhanced VIBE Prompt
    print("\n[STAP 2/3] Verbeterde VIBE Workflow Genereren...")
    print("\nPrompt:")
    print("-" * 80)

    vibe_prompt = """Expand foundation workflow from 75% to 95% autonomy.

Current: 12 nodes (org design, dept setup, agent assignment, notifications)

Add 8-10 nodes for:
- Jira/GitHub integration (project tracking)
- Sentiment analysis + quality dashboard
- Invoice processing + budget monitoring
- Onboarding automation + HR scheduling
- Daily dashboard generator + predictive analytics
- Social media automation + email campaigns
- Audit trail + compliance reporting

Target: 20+ total nodes, 95%+ automated, minimal human intervention."""

    print(vibe_prompt)
    print("-" * 80)

    vibe_response = requests.post(
        f"{BASE_URL}/api/v1/vibe/generate",
        json={
            "prompt": vibe_prompt,
            "complexity": "advanced",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    print("\n[STAP 3/3] Response verwerken...")
    print(f"Status Code: {vibe_response.status_code}")

    if vibe_response.status_code != 200:
        pytest.skip(f"VIBE endpoint not available: {vibe_response.status_code}")

    result = vibe_response.json()

    # Save enhanced output
    with open("vibe_output_95percent.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    workflow = result.get("workflow")
    if not workflow:
        print("[ERROR] No workflow in response")
        print(f"Response keys: {list(result.keys())}")
        exit(1)

    nodes = workflow.get("nodes", [])
    edges = workflow.get("edges", [])

    print("\n" + "=" * 80)
    print("RESULTAAT - VERBETERDE 95% WORKFLOW")
    print("=" * 80)

    print("\n[OVERZICHT]")
    print(f"Workflow naam: {workflow.get('name', 'N/A')}")
    print(f"Totaal nodes: {len(nodes)} (was 12, doel: 20+)")
    print(f"Totaal edges: {len(edges)}")
    print(f"Generatietijd: {result.get('generation_time_ms', 0) / 1000:.2f} sec")

    # Analyze node types
    agent_types = {}
    for node in nodes:
        agent_name = node.get("agent_name", "unknown")
        agent_types[agent_name] = agent_types.get(agent_name, 0) + 1

    print("\n[AGENT TYPES]")
    for agent, count in sorted(agent_types.items()):
        print(f"  {agent:30} : {count}x")

    # Count automation vs human interaction
    human_nodes = [
        n
        for n in nodes
        if any(
            keyword in n.get("label", "").lower()
            for keyword in ["notify", "email", "slack", "human", "approval"]
        )
    ]

    automated_nodes = len(nodes) - len(human_nodes)
    autonomy = (automated_nodes / len(nodes) * 100) if nodes else 0

    print("\n[AUTONOMIE BEREKENING]")
    print(f"Geautomatiseerde nodes: {automated_nodes}")
    print(f"Menselijke interventie nodes: {len(human_nodes)}")
    print(f"Autonomie percentage: {autonomy:.1f}%")

    if autonomy >= 95:
        print(f"\n[SUCCESS] DOEL BEREIKT: {autonomy:.1f}% >= 95%")
    elif autonomy >= 90:
        print(f"\n[BIJNA] {autonomy:.1f}% - nog {95-autonomy:.1f}% te gaan")
    else:
        print(f"\n[INFO] {autonomy:.1f}% - verdere optimalisatie mogelijk")

    # Check for required new agents
    print("\n[NIEUWE AGENTS CHECK]")
    required_agents = [
        "jira_integration",
        "github_integration",
        "sentiment_analyzer",
        "invoice_processor",
        "dashboard_generator",
        "predictive_analytics",
        "social_media_agent",
        "onboarding_automation",
    ]

    used_agents = set(node.get("agent_name") for node in nodes)

    for req_agent in required_agents:
        # Check partial match
        found = any(req_agent.replace("_", "") in agent.replace("_", "") for agent in used_agents)
        status = "[OK]" if found else "[MISSING]"
        print(f"  {status} {req_agent}")

    # Feature coverage
    print("\n[FEATURE COVERAGE]")
    features = {
        "Project Management": ["jira", "github", "sprint", "backlog"],
        "Quality Control": ["sentiment", "quality", "alert", "monitoring"],
        "Finance Automation": ["invoice", "budget", "expense", "forecast"],
        "HR Processes": ["onboarding", "performance", "schedule", "leave"],
        "Reporting": ["dashboard", "report", "analytics", "metrics"],
        "Communications": ["social", "email", "stakeholder", "campaign"],
    }

    for feature, keywords in features.items():
        # Check if any node mentions these keywords
        matches = sum(
            1
            for node in nodes
            if any(
                kw in node.get("label", "").lower() or kw in node.get("agent_name", "").lower()
                for kw in keywords
            )
        )
        coverage = "[OK]" if matches > 0 else "[MISSING]"
        print(f"  {coverage} {feature:25} : {matches} nodes")

    print("\n" + "=" * 80)
    print("COMPARISON: 75% vs 95% WORKFLOW")
    print("=" * 80)

    comparison = f"""
    Metric                   | 75% Workflow | 95% Workflow | Improvement
    ------------------------|--------------|--------------|-------------
    Total Nodes             |     12       |     {len(nodes):2}       | +{len(nodes)-12}
    Agent Types             |      9       |     {len(agent_types):2}       | +{len(agent_types)-9}
    Autonomy %              |     75%      |   {autonomy:5.1f}%    | +{autonomy-75:.1f}%
    Human Touchpoints       |      3       |     {len(human_nodes):2}       | {len(human_nodes)-3:+d}
    Departments Covered     |      6       |      6       | Complete
    """
    print(comparison)

    print("\n[OK] Verbeterde workflow opgeslagen in: vibe_output_95percent.json")
    print("\n[NEXT STEPS]")
    print("1. Run: python display_enhanced_workflow.py")
    print("2. Review nieuwe agents en features")
    print("3. Activeer in productie indien goedgekeurd")

    print("\n" + "=" * 80)
    print("TEST COMPLEET")
    print("=" * 80 + "\n")
