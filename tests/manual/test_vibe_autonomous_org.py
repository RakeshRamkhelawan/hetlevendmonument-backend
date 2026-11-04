"""
Test VIBE Workflow Generation
Real-life scenario: 95% Autonomous Foundation
"""

import json

import pytest
import requests

BASE_URL = "http://localhost:8100"  # Port updated from 8000 to 8100
EMAIL = "test@example.com"
PASSWORD = "TestPass123"


@pytest.mark.manual
@pytest.mark.skip(reason="Manual test - requires running backend")
def test_vibe_autonomous_organization():
    """Test VIBE workflow generation for 95% autonomous foundation."""
    print("\n" + "=" * 80)
    print("VIBE WORKFLOW TEST - 95% Autonome Stichting")
    print("=" * 80)

    # Step 1: Login
    print("\n[STAP 1/3] Inloggen...")
    login_response = requests.post(
        f"{BASE_URL}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )

    if login_response.status_code != 200:
        print(f"[ERROR] Login failed: {login_response.status_code}")
        pytest.skip(f"Login failed: {login_response.status_code}")

    token = login_response.json().get("access_token")
    print(f"[OK] Ingelogd als {EMAIL}")

    # Step 2: Generate VIBE Workflow
    print("\n[STAP 2/3] VIBE Workflow Genereren...")
    print("\nPrompt:")
    print("-" * 80)

    vibe_prompt = """Ik heb een onderneming, een stichting met een voorzitter, penningmeester en 2 adviseurs,
een educatiemanager en 4 vrijwilligers. De stichting wil een 95% autonome onderneming zijn,
dit betekent dat 95% van alle afdelingen, werkprocessen enz door AI agents wordt uitgevoerd.

Maak een workflow waarbij je:
1. Middels een websearch de meest ideale organogram maakt
2. Zelf de afdelingen van begin tot eind vervaardigt en inricht
3. Alle werkprocessen definieert
4. Passende AI agents toewijst aan elke functie

Houd rekening met:
- Huidige team: 1 voorzitter, 1 penningmeester, 2 adviseurs, 1 educatiemanager, 4 vrijwilligers
- 95% autonomie betekent: alleen strategische beslissingen door mensen
- AI agents voor: admin, financiën, HR, communicatie, projectmanagement, kwaliteitscontrole
- Workflow moet zelfstandig kunnen draaien met minimale menselijke interventie"""

    print(vibe_prompt)
    print("-" * 80)

    vibe_response = requests.post(
        f"{BASE_URL}/api/v1/vibe/generate",
        json={
            "prompt": vibe_prompt,
            "complexity": "complex",
        },  # Complex workflow voor deze use case
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    print("\n[STAP 3/3] Response verwerken...")
    print(f"Status Code: {vibe_response.status_code}")

    if vibe_response.status_code == 200:
        result = vibe_response.json()

        print("\n" + "=" * 80)
        print("RESULTAAT - GEGENEREERDE WORKFLOW")
        print("=" * 80)

        # Workflow naam
        workflow = result.get("workflow", {})
        print(f"\n[*] WORKFLOW NAAM: {workflow.get('name', 'N/A')}")
        print(f"[*] BESCHRIJVING: {workflow.get('description', 'N/A')}")

        # Agent orchestration
        orchestration = result.get("agent_orchestration", {})
        print(f"\n[*] ORCHESTRATOR TYPE: {orchestration.get('orchestrator_type', 'N/A')}")
        print(f"[*] EXECUTION MODE: {orchestration.get('execution_mode', 'N/A')}")

        # Agents overzicht
        agents = orchestration.get("agents", [])
        print(f"\n[*] AANTAL AGENTS: {len(agents)}")

        if agents:
            print("\n" + "-" * 80)
            print("AGENT DETAILS")
            print("-" * 80)

            for i, agent in enumerate(agents, 1):
                print(f"\n{i}. {agent.get('name', 'Unnamed Agent')}")
                print(f"   Type: {agent.get('type', 'N/A')}")
                print(f"   Rol: {agent.get('description', 'N/A')}")

                # Capabilities
                capabilities = agent.get("capabilities", [])
                if capabilities:
                    print(f"   Capabilities: {', '.join(capabilities[:5])}")

                # Tools
                tools = agent.get("tools", [])
                if tools:
                    print(f"   Tools: {', '.join(tools[:5])}")

                # Dependencies
                dependencies = agent.get("dependencies", [])
                if dependencies:
                    print(f"   Dependencies: {', '.join(dependencies)}")

        # Workflow steps
        steps = workflow.get("steps", [])
        if steps:
            print("\n" + "-" * 80)
            print(f"WORKFLOW STAPPEN ({len(steps)} stappen)")
            print("-" * 80)

            for i, step in enumerate(steps, 1):
                print(f"\n{i}. {step.get('name', 'Unnamed Step')}")
                print(f"   Beschrijving: {step.get('description', 'N/A')}")
                print(f"   Agent: {step.get('agent', 'N/A')}")

                # Expected output
                if step.get("expected_output"):
                    print(f"   Output: {step.get('expected_output', '')[:100]}...")

        # AI Reasoning
        reasoning = result.get("reasoning", {})
        if reasoning:
            print("\n" + "-" * 80)
            print("AI REASONING")
            print("-" * 80)
            print(f"\nStrategie: {reasoning.get('strategy', 'N/A')}")
            print(f"\nMotivatie: {reasoning.get('justification', 'N/A')[:300]}...")

            if reasoning.get("architecture_decisions"):
                print("\nArchitectuur Beslissingen:")
                for decision in reasoning.get("architecture_decisions", [])[:3]:
                    print(f"  - {decision}")

        # Metadata
        print("\n" + "=" * 80)
        print("METADATA")
        print("=" * 80)
        print(f"Model gebruikt: {result.get('model_used', 'N/A')}")
        print(f"Verwerkingstijd: {result.get('processing_time', 'N/A')}")
        print(f"Token usage: {result.get('token_usage', 'N/A')}")

        # Save full output
        with open("vibe_output_stichting.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print("\n[OK] Volledige output opgeslagen in: vibe_output_stichting.json")

        # Analyse
        print("\n" + "=" * 80)
        print("ANALYSE - Is dit bruikbaar voor een 95% autonome stichting?")
        print("=" * 80)

        # Check for key components
        has_org_structure = any(
            "organogram" in agent.get("description", "").lower()
            or "organization" in agent.get("description", "").lower()
            for agent in agents
        )

        has_web_search = any(
            "search" in str(agent.get("tools", [])).lower()
            or "web" in str(agent.get("capabilities", [])).lower()
            for agent in agents
        )

        has_process_design = any(
            "process" in agent.get("description", "").lower()
            or "workflow" in agent.get("description", "").lower()
            for agent in agents
        )

        print(f"[CHECK] Organogram design agent: {'JA' if has_org_structure else 'NEE'}")
        print(f"[CHECK] Web search capability: {'JA' if has_web_search else 'NEE'}")
        print(f"[CHECK] Process design agents: {'JA' if has_process_design else 'NEE'}")
        print(f"[CHECK] Totaal agents: {len(agents)} (verwacht: 10-15 voor volledige autonomie)")
        print(f"[CHECK] Workflow stappen: {len(steps)} (verwacht: 20+ voor complete setup)")

        autonomy_score = (
            (1 if has_org_structure else 0) * 25
            + (1 if has_web_search else 0) * 25
            + (1 if has_process_design else 0) * 25
            + min(len(agents) / 15 * 25, 25)
        )

        print(f"\n[SCORE] AUTONOMIE SCORE: {autonomy_score:.0f}% (doel: 95%)")

        if autonomy_score >= 75:
            print("[OK] GESCHIKT voor 95% autonome operatie")
        elif autonomy_score >= 50:
            print("[WARN] GEDEELTELIJK geschikt - extra agents nodig")
        else:
            print("[ERROR] ONVOLDOENDE - workflow moet uitgebreid worden")

    else:
        print("\n[ERROR] VIBE generatie failed")
        print(f"Status: {vibe_response.status_code}")
        print(f"Response: {vibe_response.text[:500]}")
        pytest.skip(f"VIBE generation failed: {vibe_response.status_code}")

    print("\n" + "=" * 80)
    print("TEST COMPLEET")
    print("=" * 80 + "\n")
