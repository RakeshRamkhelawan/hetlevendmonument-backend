"""
NEO Audit Fix: Tenant Isolation Tests
Tests voor Sprint 1 — P0: tenant_id op 5 modellen + IDOR fix

RED Phase: Tests schrijven EERST (TDD discipline)
"""

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversations.models import Conversation, ConversationMessage
from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id
from src.core.procedures.models import AIQualityEvent, ProcedureExecution
from src.core.workflow.models import (
    C7ExecutionEvent,
    C7ExecutionTask,
    C7Workflow,
    C7WorkflowExecution,
)
from src.domains.tagging.models import EntityTag, Tag

# ============================================================
# TestConversationMessageTenantIsolation
# ============================================================


class TestConversationMessageTenantIsolation:
    """ConversationMessage model MUST have tenant_id column."""

    async def test_model_has_tenant_id_column(self, db_session: AsyncSession):
        """HAPPY: Het model heeft een tenant_id kolom."""
        mapper = inspect(ConversationMessage)
        column_names = [c.key for c in mapper.column_attrs]
        assert (
            "tenant_id" in column_names
        ), "ConversationMessage MOET een tenant_id kolom hebben voor tenant-isolatie"

    async def test_tenant_id_is_not_nullable(self, db_session: AsyncSession):
        """HAPPY: tenant_id is verplicht (nullable=False)."""
        table = ConversationMessage.__table__
        col = table.c.tenant_id
        assert col.nullable is False, "tenant_id MOET nullable=False zijn"

    async def test_tenant_id_has_foreign_key(self, db_session: AsyncSession):
        """HAPPY: tenant_id is een FK naar tenants.id."""
        table = ConversationMessage.__table__
        col = table.c.tenant_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "tenants.id" in fk_targets, "tenant_id MOET FK naar tenants(id) zijn"

    async def test_tenant_id_is_indexed(self, db_session: AsyncSession):
        """HAPPY: tenant_id heeft een index voor query performance."""
        table = ConversationMessage.__table__
        indexed_columns = set()
        for idx in table.indexes:
            for col in idx.columns:
                indexed_columns.add(col.name)
        assert "tenant_id" in indexed_columns, "tenant_id MOET geïndexeerd zijn"

    @pytest.mark.multi_tenant
    async def test_create_message_with_tenant_id(self, db_session, test_tenant):
        """HAPPY: Een bericht aanmaken met tenant_id werkt correct."""
        # Eerst een conversation aanmaken
        conv = Conversation(
            title="Test conv",
            tenant_id=test_tenant["id"],
            user_id=1,
        )
        db_session.add(conv)
        await db_session.flush()

        msg = ConversationMessage(
            conversation_id=conv.id,
            tenant_id=test_tenant["id"],
            role="user",
            content="Hello world",
        )
        db_session.add(msg)
        await db_session.flush()

        set_tenant_id(test_tenant["id"])
        result = await db_session.execute(select(ConversationMessage).where(ConversationMessage.id == msg.id))
        clear_tenant_context()
        saved = result.scalar_one()
        assert saved.tenant_id == test_tenant["id"]
        assert saved.content == "Hello world"

    @pytest.mark.multi_tenant
    async def test_cross_tenant_query_returns_empty(self, db_session, cross_tenant_setup):
        """UNHAPPY: Query met verkeerde tenant_id retourneert geen resultaten."""
        t1 = cross_tenant_setup["tenant1"]
        t2 = cross_tenant_setup["tenant2"]

        # Create conversation en message voor tenant 1
        conv = Conversation(title="T1 conv", tenant_id=t1["id"], user_id=1)
        db_session.add(conv)
        await db_session.flush()

        msg = ConversationMessage(
            conversation_id=conv.id,
            tenant_id=t1["id"],
            role="user",
            content="Secret message",
        )
        db_session.add(msg)
        await db_session.flush()

        # Query als tenant 2 — moet leeg zijn
        result = await db_session.execute(
            select(ConversationMessage).where(ConversationMessage.tenant_id == t2["id"])
        )
        messages = result.scalars().all()
        assert len(messages) == 0, "Tenant 2 mag GEEN berichten van Tenant 1 zien"

    async def test_create_message_without_tenant_id_fails(self, db_session, test_tenant):
        """UNHAPPY: Bericht zonder tenant_id moet falen (nullable=False)."""
        conv = Conversation(title="Test", tenant_id=test_tenant["id"], user_id=1)
        db_session.add(conv)
        await db_session.flush()

        msg = ConversationMessage(
            conversation_id=conv.id,
            # tenant_id NIET gezet — moet falen
            role="user",
            content="Should fail",
        )
        db_session.add(msg)
        with pytest.raises(Exception):  # IntegrityError of SQLAlchemy validation
            await db_session.flush()


# ============================================================
# TestEntityTagTenantIsolation
# ============================================================


class TestEntityTagTenantIsolation:
    """EntityTag model MUST have tenant_id column."""

    async def test_model_has_tenant_id_column(self, db_session):
        """HAPPY: EntityTag model heeft tenant_id kolom."""
        mapper = inspect(EntityTag)
        column_names = [c.key for c in mapper.column_attrs]
        assert "tenant_id" in column_names

    async def test_tenant_id_is_not_nullable(self, db_session):
        """HAPPY: tenant_id is NOT NULL."""
        table = EntityTag.__table__
        assert table.c.tenant_id.nullable is False

    async def test_tenant_id_has_foreign_key(self, db_session):
        """HAPPY: tenant_id FK naar tenants(id)."""
        table = EntityTag.__table__
        col = table.c.tenant_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "tenants.id" in fk_targets

    @pytest.mark.multi_tenant
    async def test_create_entity_tag_with_tenant_id(self, db_session, test_tenant):
        """HAPPY: EntityTag aan te maken met tenant_id."""
        from datetime import datetime, timezone

        tag = Tag(
            tenant_id=test_tenant["id"],
            name="test-tag",
            created_at=datetime.now(timezone.utc),  # Explicit for SQLite
        )
        db_session.add(tag)
        await db_session.flush()

        et = EntityTag(
            tag_id=tag.id,
            tenant_id=test_tenant["id"],
            entity_type="workflow",
            entity_id=1,
            created_at=datetime.now(timezone.utc),  # Explicit for SQLite
        )
        db_session.add(et)
        await db_session.flush()
        assert et.tenant_id == test_tenant["id"]

    @pytest.mark.multi_tenant
    async def test_cross_tenant_tag_invisible(self, db_session, cross_tenant_setup):
        """UNHAPPY: Tags van tenant 1 onzichtbaar voor tenant 2."""
        from datetime import datetime, timezone

        t1, t2 = cross_tenant_setup["tenant1"], cross_tenant_setup["tenant2"]

        tag = Tag(
            tenant_id=t1["id"],
            name="private-tag",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(tag)
        await db_session.flush()

        et = EntityTag(
            tag_id=tag.id,
            tenant_id=t1["id"],
            entity_type="doc",
            entity_id=1,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(et)
        await db_session.flush()

        result = await db_session.execute(select(EntityTag).where(EntityTag.tenant_id == t2["id"]))
        assert len(result.scalars().all()) == 0


# ============================================================
# TestC7ExecutionTaskTenantIsolation
# ============================================================


class TestC7ExecutionTaskTenantIsolation:
    """C7ExecutionTask MUST have tenant_id column."""

    async def test_model_has_tenant_id_column(self, db_session):
        """HAPPY: Model heeft tenant_id."""
        mapper = inspect(C7ExecutionTask)
        column_names = [c.key for c in mapper.column_attrs]
        assert "tenant_id" in column_names

    async def test_tenant_id_not_nullable(self, db_session):
        """HAPPY: tenant_id is NOT NULL."""
        table = C7ExecutionTask.__table__
        assert table.c.tenant_id.nullable is False

    async def test_tenant_id_has_foreign_key(self, db_session):
        """HAPPY: tenant_id FK naar tenants."""
        table = C7ExecutionTask.__table__
        col = table.c.tenant_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "tenants.id" in fk_targets

    @pytest.mark.multi_tenant
    async def test_create_execution_task_with_tenant_id(self, db_session, test_tenant):
        """HAPPY: C7ExecutionTask maken met tenant_id."""
        import uuid
        from datetime import datetime, timezone

        # Maak eerst workflow (composite PK: id=String, version=Integer)
        workflow = C7Workflow(
            id=str(uuid.uuid4()),  # Required for composite PK
            tenant_id=test_tenant["id"],
            name="test-workflow",
            description="Test",
            workflow_type="MANUAL",
            trigger_type="MANUAL",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(workflow)
        await db_session.flush()

        # Maak execution (id + execution_id are both String PKs/UUIDs)
        execution = C7WorkflowExecution(
            id=str(uuid.uuid4()),  # Required String PK
            execution_id=str(uuid.uuid4()),  # Required unique UUID for idempotency
            workflow_id=workflow.id,
            tenant_id=test_tenant["id"],
            status="PENDING",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(execution)
        await db_session.flush()

        # Maak task
        task = C7ExecutionTask(
            id=str(uuid.uuid4()),  # Required String(50) PK
            execution_id=execution.id,
            tenant_id=test_tenant["id"],
            task_ref="step-1",  # Required: task reference from workflow spec
            task_type="AGENT",  # Required: agent type or task category
            status="PENDING",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(task)
        await db_session.flush()

        assert task.tenant_id == test_tenant["id"]


# ============================================================
# TestC7ExecutionEventTenantIsolation
# ============================================================


class TestC7ExecutionEventTenantIsolation:
    """C7ExecutionEvent MUST have tenant_id column."""

    async def test_model_has_tenant_id_column(self, db_session):
        """HAPPY: Model heeft tenant_id."""
        mapper = inspect(C7ExecutionEvent)
        column_names = [c.key for c in mapper.column_attrs]
        assert "tenant_id" in column_names

    async def test_tenant_id_not_nullable(self, db_session):
        """HAPPY: tenant_id is NOT NULL."""
        table = C7ExecutionEvent.__table__
        assert table.c.tenant_id.nullable is False

    async def test_tenant_id_has_foreign_key(self, db_session):
        """HAPPY: tenant_id FK naar tenants."""
        table = C7ExecutionEvent.__table__
        col = table.c.tenant_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "tenants.id" in fk_targets


# ============================================================
# TestAIQualityEventTenantIsolation
# ============================================================


class TestAIQualityEventTenantIsolation:
    """AIQualityEvent MUST have tenant_id column."""

    async def test_model_has_tenant_id_column(self, db_session):
        """HAPPY: Model heeft tenant_id."""
        mapper = inspect(AIQualityEvent)
        column_names = [c.key for c in mapper.column_attrs]
        assert "tenant_id" in column_names

    async def test_tenant_id_not_nullable(self, db_session):
        """HAPPY: tenant_id is NOT NULL."""
        table = AIQualityEvent.__table__
        assert table.c.tenant_id.nullable is False

    async def test_tenant_id_has_foreign_key(self, db_session):
        """HAPPY: tenant_id FK naar tenants."""
        table = AIQualityEvent.__table__
        col = table.c.tenant_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "tenants.id" in fk_targets

    @pytest.mark.multi_tenant
    async def test_create_quality_event_with_tenant_id(self, db_session, test_tenant):
        """HAPPY: AIQualityEvent maken met tenant_id."""
        import uuid
        from datetime import datetime, timezone

        # Maak procedure execution (uses UUID PKs, procedure_id is required)
        proc_exec = ProcedureExecution(
            tenant_id=test_tenant["id"],
            procedure_id=uuid.uuid4(),  # Required FK (dummy UUID for test)
            status="RUNNING",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(proc_exec)
        await db_session.flush()

        # Maak quality event (severity is required)
        event = AIQualityEvent(
            execution_id=proc_exec.id,
            tenant_id=test_tenant["id"],
            event_type="QUALITY_CHECK",
            severity="info",  # Required: info|warning|error|critical
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(event)
        await db_session.flush()

        assert event.tenant_id == test_tenant["id"]
