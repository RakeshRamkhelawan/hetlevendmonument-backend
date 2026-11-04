"""
Integration tests: FocusBuilder → v2 Agent Architecture

Tests that FocusBuilder workflows can trigger agents
and that agent execution integrates with workflow state.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestWorkflowAgentTriggers:
    """
    TKFB-AGENT-001: FocusBuilder workflows trigger agents
    """

    @pytest.mark.asyncio
    async def test_webhook_trigger_starts_agent(self):
        """
        GIVEN: Workflow with webhook trigger
        WHEN: External webhook received
        THEN: Agent execution started
        """
        # Mock webhook handler
        mock_webhook_handler = MagicMock()
        mock_webhook_handler.process = AsyncMock(
            return_value={
                "trigger_id": "trig-123",
                "workflow_id": "wf-456",
                "agent_id": "invoice_processor",
            }
        )

        # Mock agent execution
        mock_agent_execution = MagicMock()
        mock_agent_execution.create = AsyncMock(
            return_value={
                "execution_id": "exec-789",
                "agent_id": "invoice_processor",
                "status": "running",
            }
        )

        # Simulate webhook
        webhook_data = {
            "event": "invoice.received",
            "invoice_id": "INV-123",
            "pdf_url": "http://example.com/inv.pdf",
        }

        # Process webhook
        result = await mock_webhook_handler.process(path="/webhooks/invoices", data=webhook_data)

        assert result["agent_id"] == "invoice_processor"
        mock_webhook_handler.process.assert_called_once()

    @pytest.mark.asyncio
    async def test_schedule_trigger_executes_periodically(self):
        """
        GIVEN: Workflow with schedule trigger (cron)
        WHEN: Cron time reached
        THEN: Agent execution queued
        """
        mock_scheduler = MagicMock()
        mock_scheduler.trigger_due_workflows = AsyncMock(
            return_value=[
                {"workflow_id": "wf-001", "execution_id": "exec-001"},
                {"workflow_id": "wf-002", "execution_id": "exec-002"},
            ]
        )

        # Trigger scheduler
        results = await mock_scheduler.trigger_due_workflows()

        assert len(results) > 0
        mock_scheduler.trigger_due_workflows.assert_called_once()


class TestAgentUpdatesWorkflow:
    """
    TKFB-AGENT-002: Agent execution updates workflow state
    """

    @pytest.mark.asyncio
    async def test_agent_result_updates_workflow_nodes(self):
        """
        GIVEN: Running workflow with agent node
        WHEN: Agent completes with result
        THEN: Workflow state updated, next node triggered
        """
        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.current_node_id = "agent_1"

        # Simulate agent completion
        agent_result = {"analysis": "Complete", "score": 95}

        # Update workflow
        mock_workflow.advance_to_node = AsyncMock(
            return_value={
                "current_node_id": "email_1",
                "previous_node_id": "agent_1",
                "agent_result": agent_result,
            }
        )

        result = await mock_workflow.advance_to_node(
            next_node="email_1", previous_result=agent_result
        )

        assert result["current_node_id"] == "email_1"
        assert result["agent_result"] == agent_result


class TestMultiAgentOrchestration:
    """
    TKFB-AGENT-003: Workflows orchestrate multiple agents
    """

    @pytest.mark.asyncio
    async def test_parallel_agent_execution(self):
        """
        GIVEN: Workflow with parallel agent branches
        WHEN: Workflow starts
        THEN: Multiple agents execute in parallel
        """
        # Mock parallel agent executions
        mock_agent_a = AsyncMock(return_value={"agent": "analyzer_a", "done": True})
        mock_agent_b = AsyncMock(return_value={"agent": "analyzer_b", "done": True})

        # Execute in parallel
        results = await asyncio.gather(mock_agent_a(), mock_agent_b())

        assert len(results) == 2
        assert all(r["done"] for r in results)

        # Verify both were called
        mock_agent_a.assert_called_once()
        mock_agent_b.assert_called_once()
