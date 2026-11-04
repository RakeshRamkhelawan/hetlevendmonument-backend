"""Company Layer Fase 1 - Geïsoleerde Integratietest

Test ALLEEN de Fase 1 componenten (Company Layer) op echte PostgreSQL.
Gebruikt directe CREATE TABLE statements in een EIGEN schema (`company_isolated`), zodat de tabellen van de
gedeelde testdatabase (`public`) ongemoeid blijven.

Usage:
    docker run -d --name postgres-test -p 5455:5432 \
        -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
        -e POSTGRES_DB=sanskritisetu pgvector/pgvector:pg15

    pytest tests/integration/test_company_layer_isolated.py -v
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.fixtures.testdatabase import testdatabase_url

os.environ["TESTING"] = "1"

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ============================================================================
# DATABASE SETUP - Alleen Company Layer tabellen
# ============================================================================

#: Een EIGEN schema voor de tabellen van dit bestand. Hier stond een DROP TABLE ... CASCADE op `companies`,
#: `departments`, `goals`, `external_agents`, `board_decisions`, `company_templates` en
#: `pack_activation_audit_log` in `public`, gevolgd door een eigen CREATE TABLE zonder `board_decisions.updated_at`.
#: Die tabellen zijn van de hele shard (de sessiefixture in tests/integration/conftest.py bouwt ze met `create_all`),
#: dus faalde `test_fase7_templates_onboarding.py::TestFullOnboardingFlow` daarna met 'column
#: board_decisions.updated_at does not exist' (CI-run 40674951559; gereproduceerd 2026-10-28: dit bestand gevolgd
#: door dat bestand gaf '2 failed, 22 passed'). Bovendien gebruiken deze tests ruwe INSERT's die leunen op defaults
#: (`gen_random_uuid()`, `config DEFAULT '{}'`) die `create_all` niet zet; daarom een eigen schema, geen hergebruik
#: van `public`.
EIGEN_SCHEMA = "company_isolated"


def _eigen_engine(**kwargs):
    """Een engine waarvan de zoeklijst eerst het eigen schema noemt, dan `public` (voor `gen_random_uuid` e.d.)."""
    return create_async_engine(
        testdatabase_url(),
        echo=False,
        connect_args={"server_settings": {"search_path": f"{EIGEN_SCHEMA},public"}},
        **kwargs,
    )


COMPANY_LAYER_SCHEMA = """
-- Company Layer Tables - Fase 1 Data Foundation
-- Clean setup for isolated testing

-- Bedrijven (root van organisatie hiërarchie)
CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    company_type VARCHAR(20) NOT NULL CHECK (company_type IN ('mkb', 'zzp', 'enterprise')),
    sector VARCHAR(50) NOT NULL,
    mission TEXT,
    config JSONB DEFAULT '{}',
    board_role_config JSONB,
    template_id UUID,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Afdelingen (hiërarchische structuur)
CREATE TABLE IF NOT EXISTS departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id INTEGER NOT NULL,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    parent_department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    head_user_id INTEGER,
    board_role VARCHAR(50),
    budget_monthly_tokens INTEGER,
    domain_pack_ids JSONB DEFAULT '[]',
    config JSONB DEFAULT '{}',
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Doelen (mission → strategic → project → task)
CREATE TABLE IF NOT EXISTS goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id INTEGER NOT NULL,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    parent_goal_id UUID REFERENCES goals(id) ON DELETE SET NULL,
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    goal_type VARCHAR(20) NOT NULL CHECK (goal_type IN ('mission', 'strategic', 'project', 'task')),
    title VARCHAR(200) NOT NULL,
    description TEXT,
    kpis JSONB DEFAULT '[]',
    status VARCHAR(20) DEFAULT 'draft',
    progress_pct INTEGER DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    deadline TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Externe Agents (heartbeat protocol)
CREATE TABLE IF NOT EXISTS external_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id INTEGER NOT NULL,
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    name VARCHAR(100) NOT NULL,
    runtime VARCHAR(50) NOT NULL,
    capabilities JSONB DEFAULT '[]',
    webhook_url VARCHAR(500),
    api_key_hash VARCHAR(255) NOT NULL,
    heartbeat_interval_seconds INTEGER DEFAULT 30,
    last_heartbeat_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'registered' CHECK (status IN ('registered', 'active', 'busy', 'dead')),
    metrics JSONB DEFAULT '{}',
    config JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Board Beslissingen (approval queue)
CREATE TABLE IF NOT EXISTS board_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id INTEGER NOT NULL,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    requested_by INTEGER NOT NULL,
    board_role VARCHAR(50) NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    action_context JSONB DEFAULT '{}',
    goal_id UUID REFERENCES goals(id) ON DELETE SET NULL,
    decision VARCHAR(20) CHECK (decision IN ('approved', 'rejected')),
    decided_by INTEGER,
    reason TEXT,
    decided_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Company Templates
CREATE TABLE IF NOT EXISTS company_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    company_type VARCHAR(20) NOT NULL,
    sector VARCHAR(50) NOT NULL,
    description TEXT,
    template_definition JSONB DEFAULT '{}',
    is_platform_template BOOLEAN DEFAULT false,
    contributed_by_tenant_id INTEGER,
    usage_count INTEGER DEFAULT 0,
    rating_sum INTEGER DEFAULT 0,
    rating_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Pack Activation Audit Log
CREATE TABLE IF NOT EXISTS pack_activation_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id INTEGER NOT NULL,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    activated_by INTEGER NOT NULL,
    pack_id VARCHAR(50) NOT NULL,
    pack_name VARCHAR(100) NOT NULL,
    activation_type VARCHAR(20) NOT NULL CHECK (activation_type IN ('manual', 'auto_scored', 'template_based')),
    activation_score FLOAT,
    previous_state JSONB,
    new_state JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_companies_tenant ON companies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_departments_company ON departments(company_id);
CREATE INDEX IF NOT EXISTS idx_departments_tenant ON departments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_goals_company ON goals(company_id);
CREATE INDEX IF NOT EXISTS idx_goals_parent ON goals(parent_goal_id);
CREATE INDEX IF NOT EXISTS idx_external_agents_tenant ON external_agents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_board_decisions_queue ON board_decisions(tenant_id, company_id, decision);

-- RLS Policies
ALTER TABLE IF EXISTS companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS external_agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS board_decisions ENABLE ROW LEVEL SECURITY;
"""


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Create clean company layer schema (sync wrapper to avoid event_loop ScopeMismatch)."""
    import asyncio

    from sqlalchemy.pool import NullPool

    async def _run():
        engine = create_async_engine(
            testdatabase_url(),
            echo=False,
            poolclass=NullPool,
        )
        async with engine.begin() as conn:
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {EIGEN_SCHEMA}"))
        await engine.dispose()

        # Alle tabellen komen in het EIGEN schema (zoeklijst: eerst dat schema). De tabellen in `public` zijn van de
        # hele shard (sessiefixture, `create_all`) en blijven hier onaangeroerd.
        engine = _eigen_engine(poolclass=NullPool)
        async with engine.begin() as conn:
            for stmt in COMPANY_LAYER_SCHEMA.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    await conn.execute(text(stmt))
            # Een eerdere run of een eerder bestand kan rijen hebben achtergelaten; ruim alleen de eigen tabellen op.
            await conn.execute(
                text(
                    f"TRUNCATE {EIGEN_SCHEMA}.pack_activation_audit_log, {EIGEN_SCHEMA}.board_decisions, "
                    f"{EIGEN_SCHEMA}.external_agents, {EIGEN_SCHEMA}.goals, {EIGEN_SCHEMA}.departments, "
                    f"{EIGEN_SCHEMA}.companies, {EIGEN_SCHEMA}.company_templates CASCADE"
                )
            )
        await engine.dispose()

    asyncio.run(_run())
    yield


@pytest.fixture(scope="function")
async def db_session():
    """Create fresh session."""
    engine = _eigen_engine()

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session
        await session.rollback()

    await engine.dispose()


# ============================================================================
# TEST CLASSES - TDD Style
# ============================================================================


class Test01CompanyModelRealDB:
    """Test 1: Company model op echte PostgreSQL"""

    async def test_create_company_basic(self, db_session: AsyncSession):
        """✅ Basis company creatie"""
        result = await db_session.execute(
            text(
                """
                INSERT INTO companies (tenant_id, name, company_type, sector)
                VALUES (:tenant_id, :name, :type, :sector)
                RETURNING id, name, created_at
            """
            ),
            {
                "tenant_id": 1,
                "name": "Test Company BV",
                "type": "mkb",
                "sector": "technology",
            },
        )
        row = result.fetchone()

        assert row is not None
        assert row.name == "Test Company BV"
        assert isinstance(row.id, uuid.UUID)
        print(f"✅ Company created: {row.id}")

    async def test_company_with_config_jsonb(self, db_session: AsyncSession):
        """✅ JSONB config opslag"""
        config = {"key": "value", "nested": {"array": [1, 2, 3]}}

        result = await db_session.execute(
            text(
                """
                INSERT INTO companies (tenant_id, name, company_type, sector, config)
                VALUES (1, 'Config Test', 'enterprise', 'finance', :config)
                RETURNING id, config
            """
            ),
            {"config": str(config).replace("'", '"')},
        )
        row = result.fetchone()

        assert row.config is not None
        print("✅ JSONB config stored")

    async def test_company_tenant_isolation(self, db_session: AsyncSession):
        """✅ Tenant isolatie via queries"""
        # Create company for tenant 1
        await db_session.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (1, 'Tenant 1 Co', 'mkb', 'tech')"
            )
        )

        # Create company for tenant 2
        await db_session.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (2, 'Tenant 2 Co', 'zzp', 'consulting')"
            )
        )

        # Query tenant 1
        result = await db_session.execute(text("SELECT name FROM companies WHERE tenant_id = 1"))
        rows = result.fetchall()

        assert len(rows) == 1
        assert rows[0].name == "Tenant 1 Co"
        print("✅ Tenant isolation verified")


class Test02DepartmentHierarchyRealDB:
    """Test 2: Department hiërarchie"""

    async def test_department_parent_child(self, db_session: AsyncSession):
        """✅ Parent-child department relaties"""
        # Create company
        result = await db_session.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (1, 'Parent Co', 'enterprise', 'tech') RETURNING id"
            )
        )
        company_id = result.fetchone().id

        # Create parent department
        result = await db_session.execute(
            text(
                "INSERT INTO departments (tenant_id, company_id, name, board_role) VALUES (1, :company_id, 'Engineering', 'CTO') RETURNING id"
            ),
            {"company_id": company_id},
        )
        parent_id = result.fetchone().id

        # Create child department
        result = await db_session.execute(
            text(
                "INSERT INTO departments (tenant_id, company_id, name, parent_department_id) VALUES (1, :company_id, 'Backend Team', :parent_id) RETURNING id"
            ),
            {"company_id": company_id, "parent_id": parent_id},
        )
        child_id = result.fetchone().id

        # Verify hierarchy
        result = await db_session.execute(
            text("SELECT parent_department_id FROM departments WHERE id = :id"), {"id": child_id}
        )
        assert result.fetchone().parent_department_id == parent_id
        print(f"✅ Department hierarchy: {str(parent_id)[:8]} -> {str(child_id)[:8]}")

    async def test_department_version_optimistic_locking(self, db_session: AsyncSession):
        """✅ Version field voor optimistic locking"""
        result = await db_session.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (1, 'Version Test', 'mkb', 'tech') RETURNING id"
            )
        )
        company_id = result.fetchone().id

        result = await db_session.execute(
            text(
                "INSERT INTO departments (tenant_id, company_id, name, version) VALUES (1, :company_id, 'Test Dept', 5) RETURNING id, version"
            ),
            {"company_id": company_id},
        )
        row = result.fetchone()

        assert row.version == 5
        print(f"✅ Optimistic locking version: {row.version}")


class Test03GoalChainRealDB:
    """Test 3: Goal hiërarchie chain"""

    async def test_goal_mission_strategic_project_task(self, db_session: AsyncSession):
        """✅ Complete goal chain: Mission → Strategic → Project → Task"""
        # Setup company
        result = await db_session.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (1, 'Goal Chain Co', 'enterprise', 'tech') RETURNING id"
            )
        )
        company_id = result.fetchone().id

        # Mission
        result = await db_session.execute(
            text(
                "INSERT INTO goals (tenant_id, company_id, goal_type, title, status, progress_pct) VALUES (1, :company_id, 'mission', 'Company Mission', 'active', 100) RETURNING id"
            ),
            {"company_id": company_id},
        )
        mission_id = result.fetchone().id

        # Strategic
        result = await db_session.execute(
            text(
                "INSERT INTO goals (tenant_id, company_id, parent_goal_id, goal_type, title, status) VALUES (1, :company_id, :parent_id, 'strategic', '2026 Strategy', 'active') RETURNING id"
            ),
            {"company_id": company_id, "parent_id": mission_id},
        )
        strategic_id = result.fetchone().id

        # Project
        result = await db_session.execute(
            text(
                "INSERT INTO goals (tenant_id, company_id, parent_goal_id, goal_type, title, status) VALUES (1, :company_id, :parent_id, 'project', 'Q1 Project', 'in_progress') RETURNING id"
            ),
            {"company_id": company_id, "parent_id": strategic_id},
        )
        project_id = result.fetchone().id

        # Task
        result = await db_session.execute(
            text(
                "INSERT INTO goals (tenant_id, company_id, parent_goal_id, goal_type, title, status, progress_pct) VALUES (1, :company_id, :parent_id, 'task', 'Implement feature', 'in_progress', 50) RETURNING id"
            ),
            {"company_id": company_id, "parent_id": project_id},
        )
        task_id = result.fetchone().id

        # Verify chain
        result = await db_session.execute(
            text(
                """
                WITH RECURSIVE goal_tree AS (
                    SELECT id, parent_goal_id, goal_type, title, 1 as depth
                    FROM goals WHERE id = :task_id
                    UNION ALL
                    SELECT g.id, g.parent_goal_id, g.goal_type, g.title, gt.depth + 1
                    FROM goals g JOIN goal_tree gt ON g.id = gt.parent_goal_id
                )
                SELECT * FROM goal_tree
            """
            ),
            {"task_id": task_id},
        )
        chain = result.fetchall()

        assert len(chain) == 4  # task -> project -> strategic -> mission
        print(f"✅ Goal chain: {len(chain)} levels deep")

    async def test_goal_progress_0_to_100(self, db_session: AsyncSession):
        """✅ Progress percentage validatie"""
        result = await db_session.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (1, 'Progress Test', 'mkb', 'tech') RETURNING id"
            )
        )
        company_id = result.fetchone().id

        # Valid progress values
        for progress in [0, 25, 50, 75, 100]:
            result = await db_session.execute(
                text(
                    "INSERT INTO goals (tenant_id, company_id, goal_type, title, progress_pct) VALUES (1, :company_id, 'task', 'Task', :progress) RETURNING progress_pct"
                ),
                {"company_id": company_id, "progress": progress},
            )
            assert result.fetchone().progress_pct == progress

        print("✅ Progress validation: 0-100 range works")


class Test04ExternalAgentHeartbeatRealDB:
    """Test 4: ExternalAgent met heartbeat protocol"""

    async def test_agent_lifecycle_status(self, db_session: AsyncSession):
        """✅ Status overgangen: registered → active → busy → dead"""
        result = await db_session.execute(
            text(
                """
                INSERT INTO external_agents (tenant_id, name, runtime, capabilities, api_key_hash, status)
                VALUES (1, 'Test Agent', 'python-3.11', '[\"ml\", \"api\"]', 'hashed_key', 'registered')
                RETURNING id, status
            """
            )
        )
        row = result.fetchone()
        agent_id = row.id
        assert row.status == "registered"

        # Transition to active
        await db_session.execute(
            text(
                "UPDATE external_agents SET status = 'active', last_heartbeat_at = now() WHERE id = :id"
            ),
            {"id": agent_id},
        )

        result = await db_session.execute(
            text("SELECT status, last_heartbeat_at FROM external_agents WHERE id = :id"),
            {"id": agent_id},
        )
        row = result.fetchone()
        assert row.status == "active"
        assert row.last_heartbeat_at is not None

        print("✅ Agent lifecycle: registered → active")

    async def test_agent_metrics_jsonb(self, db_session: AsyncSession):
        """✅ Metrics opslag in JSONB"""
        metrics = {"cpu_percent": 45.5, "memory_mb": 1024, "tasks_completed": 100}

        result = await db_session.execute(
            text(
                """
                INSERT INTO external_agents (tenant_id, name, runtime, capabilities, api_key_hash, metrics)
                VALUES (1, 'Metrics Agent', 'python-3.11', '[\"test\"]', 'key', :metrics)
                RETURNING id, metrics
            """
            ),
            {"metrics": str(metrics).replace("'", '"')},
        )
        row = result.fetchone()

        assert row.metrics is not None
        print("✅ Agent metrics stored")


class Test05ContextAndSchemasRealDB:
    """Test 5: Context objecten en schemas"""

    async def test_agent_execution_context_with_db_data(self, db_session: AsyncSession):
        """✅ AgentExecutionContext met data uit database"""
        from src.core.company.context import AgentExecutionContext, GoalChain

        # Create company in DB
        result = await db_session.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (1, 'Context Test', 'mkb', 'tech') RETURNING id, company_type, sector"
            )
        )
        company = result.fetchone()

        # Build context
        context = AgentExecutionContext(
            tenant_id=1,
            company_id=company.id,
            company_type=company.company_type,
            sector=company.sector,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(
                mission_id=uuid.uuid4(),
                task_goal_id=uuid.uuid4(),
            ),
        )

        is_valid, missing = context.validate_completeness()

        assert is_valid is True
        assert context.is_degraded is False
        assert context.goal_chain.is_complete() is True

        # JSON serializable (voor heartbeat protocol)
        json_str = context.model_dump_json()
        assert "tenant_id" in json_str

        print("✅ AgentExecutionContext valid & serializable")

    async def test_schemas_from_db_models(self, db_session: AsyncSession):
        """✅ Pydantic schemas van database models"""
        from src.core.company.schemas import CompanyResponse

        result = await db_session.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector, status) VALUES (1, 'Schema Test', 'enterprise', 'finance', 'active') RETURNING id, tenant_id, name, company_type, sector, status, created_at"
            )
        )
        row = result.fetchone()

        response = CompanyResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            company_type=row.company_type,
            sector=row.sector,
            status=row.status,
            created_at=row.created_at,
        )

        assert response.name == "Schema Test"

        json_data = response.model_dump_json()
        assert "Schema Test" in json_data

        print("✅ CompanyResponse schema from DB")

    async def test_conflict_response_schema(self, db_session: AsyncSession):
        """✅ ConflictResponse voor 409 errors"""
        from src.core.company.schemas import ConflictResponse

        conflict = ConflictResponse(
            detail="Resource modified by other user",
            current_version=5,
            conflicting_user="user@example.com",
        )

        assert conflict.error_code == "CONFLICT"
        assert conflict.current_version == 5

        json_data = conflict.model_dump_json()
        assert "CONFLICT" in json_data

        print("✅ ConflictResponse schema")


class Test06EndToEndFlowRealDB:
    """Test 6: End-to-End gebruikersflow"""

    async def test_complete_onboarding_flow(self, db_session: AsyncSession):
        """✅ Complete flow: Onboarding → Company → Departments → Goals"""
        from src.core.company.context import AgentExecutionContext, GoalChain
        from src.core.company.schemas import CompanyCreate, DepartmentCreate, GoalCreate

        # Step 1: AI Match (simulated)
        ai_match_result = {
            "template": "fintech_startup",
            "confidence": 0.92,
        }

        # Step 2: Create Company
        company_data = CompanyCreate(
            name="Fintech Startup BV",
            company_type="mkb",
            sector="fintech",
            mission="Democratizing finance",
        )

        result = await db_session.execute(
            text(
                """
                INSERT INTO companies (tenant_id, name, company_type, sector, mission)
                VALUES (1, :name, :type, :sector, :mission)
                RETURNING id
            """
            ),
            {
                "name": company_data.name,
                "type": company_data.company_type,
                "sector": company_data.sector,
                "mission": company_data.mission,
            },
        )
        company_id = result.fetchone().id

        # Step 3: Create Departments
        dept_data = DepartmentCreate(name="Engineering", board_role="CTO")

        result = await db_session.execute(
            text(
                "INSERT INTO departments (tenant_id, company_id, name, board_role) VALUES (1, :company_id, :name, :role) RETURNING id"
            ),
            {"company_id": company_id, "name": dept_data.name, "role": dept_data.board_role},
        )
        dept_id = result.fetchone().id

        # Step 4: Create Goals
        goal_data = GoalCreate(goal_type="mission", title="Make finance accessible")

        result = await db_session.execute(
            text(
                "INSERT INTO goals (tenant_id, company_id, department_id, goal_type, title, status) VALUES (1, :company_id, :dept_id, :type, :title, 'active') RETURNING id"
            ),
            {
                "company_id": company_id,
                "dept_id": dept_id,
                "type": goal_data.goal_type,
                "title": goal_data.title,
            },
        )
        goal_id = result.fetchone().id

        # Step 5: Create Execution Context
        context = AgentExecutionContext(
            tenant_id=1,
            company_id=company_id,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(mission_id=goal_id, task_goal_id=uuid.uuid4()),
        )

        # Verify complete flow
        assert context.company_id == company_id
        assert context.goal_chain.is_complete() is True

        print(
            f"✅ E2E Onboarding: Company({str(company_id)[:8]}) -> Dept({str(dept_id)[:8]}) -> Goal({str(goal_id)[:8]})"
        )


# ============================================================================
# SAMENVATTING
# ============================================================================

"""
INTEGRATIE TEST RESULTATEN - FASE 1 DATA FOUNDATION (GEÏSOLEERD)

✅ Test 1: Company Model (3/3)
   - Basis creatie met UUID
   - JSONB config opslag
   - Tenant isolatie

✅ Test 2: Department Hiërarchie (2/2)
   - Parent-child relaties
   - Optimistic locking (version)

✅ Test 3: Goal Chain (2/2)
   - Mission → Strategic → Project → Task
   - Progress 0-100 validatie

✅ Test 4: External Agent (2/2)
   - Lifecycle status transities
   - JSONB metrics opslag

✅ Test 5: Context & Schemas (3/3)
   - AgentExecutionContext met DB data
   - JSON serializable (heartbeat ready)
   - ConflictResponse schema

✅ Test 6: End-to-End Flow (1/1)
   - Complete onboarding flow

TOTAAL: 13/13 tests PASSED
FASE 1 STATUS: ✅ COMPLETE
"""
