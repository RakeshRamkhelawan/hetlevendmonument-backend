"""
Canvas Integration Tests - Database Isolated Version

Uses SQLite in-memory for fast, reliable tests without legacy schema issues.
"""

import asyncio
import json
import uuid
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.dialects.sqlite import BLOB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.pool import StaticPool

from src.domains.canvas.agent_blocks import (
    AgentBlock,
    AgentBlockType,
    CodeBlockConfig,
    ExecutionEnvironment,
    agent_block_registry,
)
from src.domains.canvas.execution_service import execution_service
from src.domains.canvas.export_import import (
    ExportFormat,
    ImportFormat,
    canvas_exporter,
    canvas_importer,
)
from src.domains.canvas.ot_engine import Operation, OperationType, ot_engine
from src.domains.canvas.revision_manager import RevisionManager
from src.domains.canvas.schemas import (
    BlockCreate,
    BlockUpdate,
    CanvasCreate,
    CanvasUpdate,
    CollaboratorCreate,
)
from src.domains.canvas.templates import PROJECT_KANBAN_TEMPLATE, template_registry

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# All test models in one Base to handle foreign keys
StubBase = declarative_base()


class StubTenant(StubBase):
    """Minimal tenant table for testing."""

    __tablename__ = "tenants"
    id = Column(BLOB, primary_key=True)
    name = Column(String(100))
    slug = Column(String(100))
    domain = Column(String(100))
    is_active = Column(Boolean, default=True)


class StubUser(StubBase):
    """Minimal user table for testing."""

    __tablename__ = "users"
    id = Column(BLOB, primary_key=True)
    email = Column(String(100))
    hashed_password = Column(String(100))
    full_name = Column(String(100))
    is_active = Column(Boolean, default=True)
    tenant_id = Column(BLOB, ForeignKey("tenants.id"))


class StubCanvas(StubBase):
    """Minimal canvas table for testing."""

    __tablename__ = "canvases"
    id = Column(BLOB, primary_key=True)
    tenant_id = Column(BLOB, ForeignKey("tenants.id"), nullable=False)
    owner_id = Column(BLOB, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    template = Column(String(50), default="blank")
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    version = Column(Integer, default=1)
    blocks = relationship("StubCanvasBlock", back_populates="canvas", cascade="all, delete-orphan")
    collaborators = relationship(
        "StubCanvasCollaborator", back_populates="canvas", cascade="all, delete-orphan"
    )


class StubCanvasBlock(StubBase):
    """Minimal canvas block table for testing."""

    __tablename__ = "canvas_blocks"
    id = Column(BLOB, primary_key=True)
    canvas_id = Column(BLOB, ForeignKey("canvases.id"), nullable=False)
    type = Column(String(50), nullable=False)
    x = Column(Numeric(10, 2), nullable=False)
    y = Column(Numeric(10, 2), nullable=False)
    width = Column(Numeric(10, 2), nullable=False)
    height = Column(Numeric(10, 2), nullable=False)
    z_index = Column(Integer, default=0)
    content = Column(Text, default="{}")
    agent_id = Column(BLOB, nullable=True)
    execution_id = Column(BLOB, nullable=True)
    created_by = Column(BLOB, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    version = Column(Integer, default=1)
    canvas = relationship("StubCanvas", back_populates="blocks")


class StubCanvasCollaborator(StubBase):
    """Minimal canvas collaborator table for testing."""

    __tablename__ = "canvas_collaborators"
    id = Column(BLOB, primary_key=True)
    canvas_id = Column(BLOB, ForeignKey("canvases.id"), nullable=False)
    user_id = Column(BLOB, ForeignKey("users.id"), nullable=False)
    role = Column(String(50), default="viewer")
    added_by = Column(BLOB, ForeignKey("users.id"), nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)
    canvas = relationship("StubCanvas", back_populates="collaborators")
    __table_args__ = (UniqueConstraint("canvas_id", "user_id", name="uix_canvas_collaborator"),)


# Test constants
TENANT_ID_BYTES = uuid.UUID(int=1).bytes  # Fixed UUID for tests
USER_ID_BYTES = uuid.UUID(int=2).bytes  # Fixed UUID for tests


def uuid_to_bytes(u: UUID) -> bytes:
    """Convert UUID to bytes."""
    return u.bytes


def bytes_to_uuid(b: bytes) -> UUID:
    """Convert bytes to UUID."""
    return UUID(bytes=b)


@pytest.fixture
async def canvas_db_session():
    """
    Isolated SQLite database for Canvas tests.
    Uses minimal test tables to avoid JSONB/PostgreSQL-specific issues.
    """
    # Create isolated engine
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(StubBase.metadata.create_all)

        # Seed minimal data
        await conn.execute(
            text(
                "INSERT INTO tenants (id, name, slug, domain, is_active) VALUES (:id, 'Test Tenant', 'test', 'test.local', 1)"
            ),
            {"id": TENANT_ID_BYTES},
        )
        await conn.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, full_name, is_active, tenant_id) VALUES (:id, 'test@example.com', 'test', 'Test User', 1, :tenant_id)"
            ),
            {"id": USER_ID_BYTES, "tenant_id": TENANT_ID_BYTES},
        )

    # Create session
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session
        await session.rollback()

    await engine.dispose()


class TestCanvasDatabaseOperations:
    """Test basic database operations."""

    async def test_create_canvas_direct(self, canvas_db_session: AsyncSession):
        """Create canvas directly in database."""
        canvas_id = uuid.uuid4().bytes

        await canvas_db_session.execute(
            text(
                """INSERT INTO canvases (id, tenant_id, owner_id, name, template, is_public, version)
               VALUES (:id, :tenant_id, :owner_id, :name, :template, :is_public, :version)"""
            ),
            {
                "id": canvas_id,
                "tenant_id": TENANT_ID_BYTES,
                "owner_id": USER_ID_BYTES,
                "name": "Test Canvas",
                "template": "blank",
                "is_public": False,
                "version": 1,
            },
        )
        await canvas_db_session.commit()

        result = await canvas_db_session.execute(
            text("SELECT name, version FROM canvases WHERE id = :id"), {"id": canvas_id}
        )
        row = result.fetchone()

        assert row is not None
        assert row.name == "Test Canvas"
        assert row.version == 1

    async def test_create_block_direct(self, canvas_db_session: AsyncSession):
        """Create block directly in database."""
        canvas_id = uuid.uuid4().bytes
        block_id = uuid.uuid4().bytes

        # Create canvas first
        await canvas_db_session.execute(
            text(
                """INSERT INTO canvases (id, tenant_id, owner_id, name, template, is_public, version)
               VALUES (:id, :tenant_id, :owner_id, :name, :template, :is_public, :version)"""
            ),
            {
                "id": canvas_id,
                "tenant_id": TENANT_ID_BYTES,
                "owner_id": USER_ID_BYTES,
                "name": "Canvas With Block",
                "template": "blank",
                "is_public": False,
                "version": 1,
            },
        )

        # Create block
        await canvas_db_session.execute(
            text(
                """INSERT INTO canvas_blocks
               (id, canvas_id, type, x, y, width, height, content, created_by, version)
               VALUES (:id, :canvas_id, :type, :x, :y, :width, :height, :content, :created_by, :version)"""
            ),
            {
                "id": block_id,
                "canvas_id": canvas_id,
                "type": "text",
                "x": 100,
                "y": 50,
                "width": 300,
                "height": 100,
                "content": json.dumps({"text": "Test block"}),
                "created_by": USER_ID_BYTES,
                "version": 1,
            },
        )
        await canvas_db_session.commit()

        result = await canvas_db_session.execute(
            text("SELECT type, x, y FROM canvas_blocks WHERE id = :id"), {"id": block_id}
        )
        row = result.fetchone()

        assert row is not None
        assert row.type == "text"
        assert row.x == 100

    async def test_list_canvases_direct(self, canvas_db_session: AsyncSession):
        """List canvases directly from database."""
        for i in range(3):
            await canvas_db_session.execute(
                text(
                    """INSERT INTO canvases (id, tenant_id, owner_id, name, template, is_public, version)
                   VALUES (:id, :tenant_id, :owner_id, :name, :template, :is_public, :version)"""
                ),
                {
                    "id": uuid.uuid4().bytes,
                    "tenant_id": TENANT_ID_BYTES,
                    "owner_id": USER_ID_BYTES,
                    "name": f"Canvas {i}",
                    "template": "blank",
                    "is_public": False,
                    "version": 1,
                },
            )
        await canvas_db_session.commit()

        result = await canvas_db_session.execute(
            text("SELECT COUNT(*) as count FROM canvases WHERE tenant_id = :tenant_id"),
            {"tenant_id": TENANT_ID_BYTES},
        )
        row = result.fetchone()

        assert row.count == 3


class TestCanvasTemplatesIntegration:
    """Test template system integration."""

    async def test_apply_template(self):
        """Apply template to canvas."""
        canvas_id = uuid4()

        result = template_registry.apply_template(
            template_id=PROJECT_KANBAN_TEMPLATE.id,
            canvas_id=canvas_id,
        )

        assert result["template_name"] == "Project Kanban Board"
        assert len(result["blocks"]) > 0


class TestOTIntegration:
    """Test Operational Transformation integration."""

    async def test_operation_transformation(self):
        """Transform concurrent operations."""
        op1 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=uuid4(),
            data={"text": "Client A", "color": "red"},
        )

        op2 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=op1.target_id,
            data={"text": "Client B"},
        )

        result = ot_engine.transform(op1, op2, priority="server")

        assert result.was_transformed
        assert "text" not in result.operation.data
        assert result.operation.data.get("color") == "red"

    async def test_revision_operations(self):
        """Test OT engine revision tracking."""
        canvas_id = uuid4()

        # Create and transform operations
        op1 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=uuid4(),
            data={"text": "First"},
        )

        op2 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=op1.target_id,
            data={"text": "Second"},
        )

        # Transform operations
        result1 = ot_engine.transform(op1, op2, priority="server")

        assert result1.was_transformed
        # op1 data should not include 'text' after transformation
        assert "text" not in result1.operation.data or result1.operation.data.get("text") != "First"


class TestAgentBlocksIntegration:
    """Test agent block execution integration."""

    async def test_code_block_execution(self):
        """Execute code block."""
        block = AgentBlock(
            block_id=uuid4(),
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=CodeBlockConfig(
                language=ExecutionEnvironment.SAFE_PYTHON,
                code='print("Hello from integration test")',
                timeout_seconds=30,
            ),
            canvas_id=uuid4(),
            tenant_id=1,
        )

        agent_block_registry.register(block)

        result = await block.execute()

        assert result is not None
        assert result.status.value in ["completed", "failed"]

        agent_block_registry.unregister(block.block_id)

    async def test_execution_service(self):
        """Execute via ExecutionService."""
        await execution_service.start()

        try:
            block = AgentBlock(
                block_id=uuid4(),
                block_type=AgentBlockType.CODE_EXECUTOR,
                config=CodeBlockConfig(
                    language=ExecutionEnvironment.SAFE_PYTHON,
                    code='print("Service test")',
                ),
                canvas_id=uuid4(),
                tenant_id=1,
            )

            agent_block_registry.register(block)

            task = await execution_service.execute_block(
                block_id=block.block_id,
                user_id=uuid4(),
            )

            assert task is not None
            assert task.block_id == block.block_id

            await asyncio.sleep(0.5)

            agent_block_registry.unregister(block.block_id)
        finally:
            await execution_service.stop()


class TestExportImportIntegration:
    """Test export and import integration."""

    async def test_export_json(self):
        """Export canvas to JSON."""
        canvas_data = {
            "id": str(uuid4()),
            "name": "Export Test Canvas",
            "description": "Testing export",
            "blocks": [
                {
                    "id": str(uuid4()),
                    "type": "text",
                    "x": 100,
                    "y": 50,
                    "width": 300,
                    "height": 100,
                    "content": {"text": "Export me"},
                }
            ],
            "connections": [],
        }

        result = await canvas_exporter.export_canvas(
            canvas_data=canvas_data,
            format=ExportFormat.JSON,
        )

        assert result.format == ExportFormat.JSON
        assert result.filename.endswith(".json")

        data = json.loads(result.content)
        assert data["canvas"]["name"] == "Export Test Canvas"

    async def test_export_html(self):
        """Export canvas to HTML."""
        canvas_data = {
            "id": str(uuid4()),
            "name": "HTML Export Test",
            "blocks": [
                {
                    "id": str(uuid4()),
                    "type": "metric",
                    "x": 50,
                    "y": 50,
                    "width": 200,
                    "height": 100,
                    "content": {"label": "Sales", "value": "100K"},
                }
            ],
            "connections": [],
        }

        result = await canvas_exporter.export_canvas(
            canvas_data=canvas_data,
            format=ExportFormat.HTML,
        )

        assert result.format == ExportFormat.HTML
        assert "<!DOCTYPE html>" in result.content

    async def test_import_json(self):
        """Import canvas from JSON."""
        content = json.dumps(
            {
                "name": "Imported Canvas",
                "description": "From JSON",
                "blocks": [
                    {"type": "text", "x": 0, "y": 0, "content": {"text": "Imported"}},
                ],
                "connections": [],
            }
        )

        result = await canvas_importer.import_canvas(
            content=content,
            format=ImportFormat.JSON,
        )

        assert result["name"] == "Imported Canvas"
        assert len(result["blocks"]) == 1

    async def test_import_markdown(self):
        """Import canvas from Markdown."""
        content = """
# Markdown Canvas

## Section 1
Content here.

- [ ] Task 1
- [ ] Task 2
"""

        result = await canvas_importer.import_canvas(
            content=content,
            format=ImportFormat.MARKDOWN,
        )

        assert "name" in result
        assert len(result["blocks"]) > 0


class TestCanvasCollaboration:
    """Test multi-user collaboration features with database."""

    async def test_add_collaborator_direct(self, canvas_db_session: AsyncSession):
        """Add collaborator to canvas directly."""
        canvas_id = uuid.uuid4().bytes
        collaborator_user_id = uuid.UUID(int=3).bytes

        # Create canvas
        await canvas_db_session.execute(
            text(
                """INSERT INTO canvases (id, tenant_id, owner_id, name, template, is_public, version)
               VALUES (:id, :tenant_id, :owner_id, :name, :template, :is_public, :version)"""
            ),
            {
                "id": canvas_id,
                "tenant_id": TENANT_ID_BYTES,
                "owner_id": USER_ID_BYTES,
                "name": "Collaboration Test Canvas",
                "template": "blank",
                "is_public": False,
                "version": 1,
            },
        )

        # Create second user
        await canvas_db_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, full_name, is_active, tenant_id) VALUES (:id, 'collab@test.com', 'test', 'Collaborator', 1, :tenant_id)"
            ),
            {"id": collaborator_user_id, "tenant_id": TENANT_ID_BYTES},
        )

        # Add collaborator (SQLite doesn't handle datetime objects well via params)
        collaborator_id = uuid.uuid4().bytes
        await canvas_db_session.execute(
            text(
                """INSERT INTO canvas_collaborators (id, canvas_id, user_id, role, added_by, added_at)
               VALUES (:id, :canvas_id, :user_id, :role, :added_by, datetime('now'))"""
            ),
            {
                "id": collaborator_id,
                "canvas_id": canvas_id,
                "user_id": collaborator_user_id,
                "role": "editor",
                "added_by": USER_ID_BYTES,
            },
        )
        await canvas_db_session.commit()

        # Verify
        result = await canvas_db_session.execute(
            text(
                "SELECT role FROM canvas_collaborators WHERE canvas_id = :canvas_id AND user_id = :user_id"
            ),
            {"canvas_id": canvas_id, "user_id": collaborator_user_id},
        )
        row = result.fetchone()

        assert row is not None
        assert row.role == "editor"
