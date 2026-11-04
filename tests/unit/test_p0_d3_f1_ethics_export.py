"""
AUDIT-P0-D3: MockEthicsAgent._execute_task() returns success=True with ethics_clearance="approved"
             without any real ethics analysis.
AUDIT-P0-F1: ExportJob has no SQLAlchemy ORM model -- only a comment in gdpr_compliance_endpoints.py.

RED PHASE OUTPUT (2026-05-28):
  test_execute_task_not_approved: AssertionError: assert 'approved' != 'approved'
  test_execute_task_success_false: AssertionError: assert True is not True
  test_export_job_model_exists: ImportError / AttributeError
  test_export_job_tenant_not_null: ImportError / AttributeError
"""

import pytest


@pytest.mark.unit
class TestEthicsAgentStub:
    """AUDIT-P0-D3: MockEthicsAgent must not return approved/success=True."""

    @pytest.mark.asyncio
    async def test_execute_task_not_approved(self):
        """
        RED: _execute_task() currently returns ethics_clearance='approved' for general tasks.
        After fix: must return ethics_clearance='not_implemented'.
        Root cause: stub returns mock approval without real ML ethics engine.
        """
        from src.core.agents.ethics_agent import MockEthicsAgent
        from src.core.shared.interfaces import TaskData

        agent = MockEthicsAgent.__new__(MockEthicsAgent)
        agent.risk_thresholds = {"low": 3, "medium": 6, "high": 8, "critical": 9}
        agent.ethical_principles = []

        task = TaskData(
            id="task-001",
            title="general",
            description="send email to all users",
            metadata={"type": "general"},
        )

        result = await agent._execute_task(task)

        assert result.result_data.get("ethics_clearance") != "approved", (
            "AUDIT-P0-D3: _execute_task returns ethics_clearance='approved' stub -- "
            "workflows receive false ethics approval without any real analysis"
        )

    @pytest.mark.asyncio
    async def test_execute_task_success_false(self):
        """
        RED: _execute_task() currently returns success=True for unimplemented agent.
        After fix: must return success=False to signal not_implemented state.
        Root cause: stub claims success without executing any real ethics check.
        """
        from src.core.agents.ethics_agent import MockEthicsAgent
        from src.core.shared.interfaces import TaskData

        agent = MockEthicsAgent.__new__(MockEthicsAgent)
        agent.risk_thresholds = {"low": 3, "medium": 6, "high": 8, "critical": 9}
        agent.ethical_principles = []

        task = TaskData(
            id="task-002",
            title="risk_assessment",
            description="run risk assessment on financial transaction",
            metadata={"type": "risk_assessment"},
        )

        result = await agent._execute_task(task)

        assert result.success is not True, (
            "AUDIT-P0-D3: _execute_task returns success=True stub -- "
            "callers believe ethics check passed when nothing was actually checked"
        )


@pytest.mark.unit
class TestExportJobModel:
    """AUDIT-P0-F1: ExportJob ORM model must exist with proper schema."""

    def test_export_job_model_exists(self):
        """
        RED: ExportJob does not exist as a SQLAlchemy ORM model.
        After fix: must be importable from src.core.governance.models.
        Root cause: only a comment in gdpr_compliance_endpoints.py, no actual model.
        """
        from src.core.governance.models import ExportJob

        assert ExportJob.__tablename__ == "export_jobs", (
            "AUDIT-P0-F1: ExportJob ORM model does not exist"
        )
        assert hasattr(ExportJob, "tenant_id"), "ExportJob must have tenant_id column"
        assert hasattr(ExportJob, "status"), "ExportJob must have status column"

    def test_export_job_tenant_not_null(self):
        """
        RED: ExportJob.tenant_id must be NOT NULL (ADR-005).
        After fix: nullable=False on the tenant_id column.
        Root cause: model does not exist yet.
        """
        from src.core.governance.models import ExportJob

        col = ExportJob.__table__.c["tenant_id"]

        assert col.nullable is False, (
            "AUDIT-P0-F1: ExportJob.tenant_id must be NOT NULL per ADR-005"
        )
