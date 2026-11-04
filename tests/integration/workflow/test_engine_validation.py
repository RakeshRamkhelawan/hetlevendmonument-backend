from unittest.mock import MagicMock

import pytest

from src.core.workflow.engine import ProductionWorkflowEngine
from src.core.workflow.interfaces import IAgentRuntime, ILLMProvider, IToolBroker


@pytest.mark.asyncio
async def test_engine_rejects_disconnected_subgraph(postgres_session):
    """
    Integration test to verify that ProductionWorkflowEngine uses
    validate_topology and rejects disconnected subgraphs.
    """
    # 1. Setup Mock Dependencies
    mock_llm = MagicMock(spec=ILLMProvider)
    mock_tools = MagicMock(spec=IToolBroker)
    mock_agent = MagicMock(spec=IAgentRuntime)

    # 2. Initialize Engine with real DB session
    engine = ProductionWorkflowEngine(
        llm_provider=mock_llm,
        tool_broker=mock_tools,
        agent_runtime=mock_agent,
        db_session=postgres_session,
    )

    # 3. Define Disconnected Workflow Spec
    # Two separate chains: node_1->node_2 and node_3->node_4
    workflow_id = "test-disconnected-workflow"
    spec = {
        "tasks": {
            "node_1": {"type": "start"},
            "node_2": {"type": "action"},
            "node_3": {"type": "start"},
            "node_4": {"type": "end"},
        },
        "dependencies": {"node_2": ["node_1"], "node_4": ["node_3"]},
    }

    # 4. Assert Validation Error
    # The engine should call validate_topology which raises WorkflowValidationError.
    # The engine catches this and raises ValueError with the message.
    with pytest.raises(ValueError, match="Invalid workflow DAG: Disconnected subgraph detected"):
        await engine.create_workflow(workflow_id=workflow_id, spec_json=spec, tenant_id="default")
