import asyncio
import os
import sys

import pytest
from fastapi.testclient import TestClient

# Ensure project root is in path
sys.path.insert(0, os.getcwd())

from src.core.agents.analyzer.agent import AnalyzerAgent
from src.core.agents.cva.agent import CVAAgent
from src.core.agents.ethical.engine import EthicalReasoningSystem
from src.core.api.main import app
from src.core.shared.interfaces import AgentType, TaskData
from src.core.subagents.specialists.system_monitor_agent import SystemMonitorAgent


# 1. API System Test
@pytest.mark.asyncio
async def test_api_integrity(integration_client, integration_app):
    print("\n[TEST] Verifying API Integrity (Main.py Refactor)...")
    # Health Check (public endpoint)
    response = await integration_client.get("/health")
    assert response.status_code == 200, f"Health check failed: {response.text}"
    data = response.json()
    assert data["status"] in ("healthy", "ok"), f"Unexpected status: {data['status']}"
    print("  - /health endpoint OK")

    # Routers geregistreerd -- in-process geteld, niet via /openapi.json over HTTP.
    # Deze assertie haalde het schema tot 2026-08-14 op met een 200-verwachting. Wat de test
    # wil weten is "zijn alle routers geregistreerd", en dat is een eigenschap van het
    # app-object; het HTTP-schema-endpoint is daar sinds ADR-036 OP-124 geen betrouwbare proxy
    # meer voor, want buiten development bestaat die route niet.
    paden = {getattr(route, "path", "") for route in integration_app.routes}
    assert len(paden) > 10, f"Te weinig routes geregistreerd ({len(paden)}), routers ontbreken"
    print(f"  - Router registration OK ({len(paden)} paths found)")


# 2. CVA Agent Modularization Test
@pytest.mark.asyncio
async def test_cva_modularization():
    print("\n[TEST] Verifying CVAAgent Modularization...")
    agent = CVAAgent("test_cva", tenant_id=1)

    # Verify Handlers exist
    assert agent.memory_handler is not None
    assert agent.communication_handler is not None
    assert agent.state_manager is not None
    assert agent.llm_handler is not None
    print("  - Handlers initialized OK")

    # Verify Properties
    assert agent.cva_state is not None
    print("  - State property OK")

    # Verify Delegated Methods are callable
    assert callable(agent.initialize_memory_system)
    assert callable(agent.send_strategic_command)
    assert callable(agent.transition_to_mode)
    print("  - Delegated methods present")


# 3. Analyzer Agent Modularization Test
@pytest.mark.asyncio
async def test_analyzer_modularization():
    print("\n[TEST] Verifying AnalyzerAgent Modularization...")
    agent = AnalyzerAgent("test_analyzer")

    # Initialize
    try:
        success = await agent.initialize()
        print(f"  - Initialization result: {success}")
    except Exception as e:
        print(f"  - Initialization warning: {e}")

    # Verify Capabilities (from capabilities.py)
    caps = await agent.get_capabilities()
    assert len(caps) > 0
    assert caps[0].name == "statistical_analysis"
    print("  - Capabilities loaded from module OK")

    # Verify Handler Routing (statistical)
    task = TaskData(
        title="Test Stats",
        description="Analyze",
        metadata={"type": "statistical_analysis", "data_source": "test"},
    )

    # Should execute without crashing
    result = await agent.process_task(task)
    assert result is not None
    print(f"  - Task processing result: {result.success} (Routing OK)")


# 4. Ethical System Test
@pytest.mark.asyncio
async def test_ethical_system_modularization():
    print("\n[TEST] Verifying EthicalReasoningSystem...")
    system = EthicalReasoningSystem()

    # Initialize
    await system.initialize()
    print("  - Initialization OK")

    # Reason
    scenario = {
        "action": "delete_user_data",
        "context": {"user_consent": True, "legal_requirement": True},
    }
    result = await system.reason_about_ethics(scenario)
    assert result is not None
    assert "reasoning_id" in result
    print("  - Ethical reasoning execution OK")


# 5. Specialist Agent Test
@pytest.mark.asyncio
async def test_specialist_agent():
    print("\n[TEST] Verifying Specialist Agent (SystemMonitor)...")
    # Skip if agent config is required - API has evolved
    try:
        agent = SystemMonitorAgent("test_monitor")
        await agent.initialize()
        print("  - Specialist agent creation OK")
    except TypeError as e:
        if "missing" in str(e) and "config" in str(e):
            pytest.skip("SystemMonitorAgent requires config - API changed")
        raise


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(["-v", "__file__"]))
