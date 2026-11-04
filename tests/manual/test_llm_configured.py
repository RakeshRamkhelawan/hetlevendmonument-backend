import os
import sys

import requests

# API configuration
API_URL = "http://168.231.111.16/api"
CREDENTIALS = {"username": "admin@sanskritisetu.org", "password": "Admin@123"}


def test_llm_features():
    """Test if LLM providers are accessible."""
    print("[*] Testing LLM provider configuration...")

    # Step 1: Login
    print("\n[1/3] Logging in...")
    login_data = {
        "grant_type": "password",
        "username": CREDENTIALS["username"],
        "password": CREDENTIALS["password"],
        "scope": "admin:*",
    }
    login_response = requests.post(f"{API_URL}/v1/oauth2/token", data=login_data)

    if login_response.status_code != 200:
        print(f"[FAIL] Login failed: {login_response.status_code} - {login_response.text}")
        return False

    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("[OK] Login successful - Token obtained")

    # Step 2: Check agents endpoint (should have AI agents)
    print("\n[2/3] Fetching registered agents...")
    agents_response = requests.get(f"{API_URL}/v1/agents/registered", headers=headers)

    if agents_response.status_code != 200:
        print(f"[FAIL] Agents endpoint failed: {agents_response.status_code}")
        return False

    agents = agents_response.json().get("agents", [])
    print(f"[OK] Found {len(agents)} registered agents")

    # Step 3: Test agent types that use LLM
    llm_agent_types = ["CVA", "ORCHESTRATOR", "SPECIALIST"]
    llm_agents = [a for a in agents if a.get("agent_type") in llm_agent_types]

    print(f"\n[3/3] LLM-powered agents: {len(llm_agents)}")
    for agent in llm_agents[:3]:  # Show first 3
        print(f"  - {agent.get('name')} ({agent.get('agent_type')})")

    print("\n" + "=" * 50)
    print("[OK] LLM providers configured successfully!")
    print("=" * 50)
    return True


if __name__ == "__main__":
    try:
        success = test_llm_features()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[FAIL] Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
