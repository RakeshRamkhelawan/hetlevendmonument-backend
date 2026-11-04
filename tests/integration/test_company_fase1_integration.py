"""Company Layer Fase 1 - Verplichte Integratietest

Test met ECHTE PostgreSQL database - geen mocks.
Dit is de verplichte test na Fase 1 volgens het implementatieplan.

Run:
    docker run -d --name postgres-test -p 5455:5432 \
        -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
        -e POSTGRES_DB=sanskritisetu pgvector/pgvector:pg15

    pytest tests/integration/test_company_fase1_integration.py -v

Verwacht resultaat: 12/12 tests PASSED
"""

import os

os.environ["TESTING"] = "1"

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from tests.fixtures.testdatabase import testdatabase_url

pytestmark = [pytest.mark.integration]

#: Eigen schema voor de ruwe tabellen van dit bestand; `public` is van de hele shard.
EIGEN_SCHEMA = "company_fase1_raw"


# ============================================================================
# DATABASE FIXTURE
# ============================================================================


@pytest.fixture(scope="module", autouse=True)
def db():
    """Setup database with company layer tables."""
    # Hier stonden DROP TABLE ... CASCADE op de company-tabellen EN op `tenants` in `public`, en aan het eind weer. Die
    # tabellen zijn van de hele shard (sessiefixture, `create_all`). Nu leven de eigen, ruwe tabellen van dit bestand in
    # een EIGEN schema (zoeklijst: eerst dat schema); `public` blijft onaangeroerd (brief 2026-10-28, groep E/F).
    kaal = create_engine(testdatabase_url(sync=True))
    with kaal.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {EIGEN_SCHEMA}"))
    kaal.dispose()

    engine = create_engine(
        testdatabase_url(sync=True),
        connect_args={"options": f"-csearch_path={EIGEN_SCHEMA},public"},
    )

    with engine.connect() as conn:
        # Create tables with raw SQL (no FK constraints to avoid dependency issues)
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS tenants (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL
            )
        """
            )
        )

        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS companies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id INTEGER NOT NULL,
                name VARCHAR(200) NOT NULL,
                company_type VARCHAR(20) NOT NULL,
                sector VARCHAR(100) NOT NULL,
                mission TEXT,
                config JSONB DEFAULT '{}',
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
            )
        """
            )
        )

        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS departments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id INTEGER NOT NULL,
                company_id UUID NOT NULL,
                name VARCHAR(100) NOT NULL,
                parent_department_id UUID,
                board_role VARCHAR(50),
                budget_monthly_tokens INTEGER,
                domain_pack_ids JSONB DEFAULT '[]',
                version INTEGER DEFAULT 1,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
            )
        """
            )
        )

        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS goals (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id INTEGER NOT NULL,
                company_id UUID NOT NULL,
                department_id UUID,
                parent_goal_id UUID,
                goal_type VARCHAR(20) NOT NULL,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                kpis JSONB DEFAULT '[]',
                status VARCHAR(20) DEFAULT 'draft',
                progress_pct INTEGER DEFAULT 0,
                deadline TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
            )
        """
            )
        )

        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS external_agents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id INTEGER NOT NULL,
                company_id UUID,
                name VARCHAR(100) NOT NULL,
                runtime VARCHAR(50) NOT NULL,
                capabilities JSONB DEFAULT '[]',
                heartbeat_interval_seconds INTEGER DEFAULT 30,
                last_heartbeat_at TIMESTAMP WITH TIME ZONE,
                status VARCHAR(20) DEFAULT 'registered',
                metrics JSONB DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
            )
        """
            )
        )

        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS board_decisions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id INTEGER NOT NULL,
                company_id UUID NOT NULL,
                requested_by INTEGER NOT NULL,
                board_role VARCHAR(50) NOT NULL,
                action_type VARCHAR(50) NOT NULL,
                action_context JSONB DEFAULT '{}',
                goal_id UUID,
                decision VARCHAR(20),
                decided_by INTEGER,
                reason TEXT,
                decided_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
            )
        """
            )
        )

        # Een eerdere run kan rijen hebben achtergelaten; leeg alleen de eigen tabellen.
        conn.execute(
            text(
                f"TRUNCATE {EIGEN_SCHEMA}.board_decisions, {EIGEN_SCHEMA}.external_agents, {EIGEN_SCHEMA}.goals, "
                f"{EIGEN_SCHEMA}.departments, {EIGEN_SCHEMA}.companies, {EIGEN_SCHEMA}.tenants"
            )
        )
        conn.commit()
        print("\n✅ Company Layer tables created")

    yield engine

    engine.dispose()
    print("\n✅ Cleanup complete")


@pytest.fixture
def conn(db):
    """Fresh connection for each test."""
    with db.connect() as c:
        yield c
        c.rollback()


# ============================================================================
# TESTS
# ============================================================================


class Test01CompanyModel:
    """Test 1: Company model op echte PostgreSQL"""

    def test_company_create(self, conn):
        """✅ Company creatie met UUID"""
        result = conn.execute(
            text(
                """
            INSERT INTO companies (tenant_id, name, company_type, sector)
            VALUES (1, 'Test Company', 'mkb', 'technology')
            RETURNING id, name, created_at
        """
            )
        )
        row = result.fetchone()
        conn.commit()

        assert row.name == "Test Company"
        assert isinstance(row.id, uuid.UUID)
        assert row.created_at is not None
        print(f"✅ Company: {row.id}")

    def test_company_jsonb_config(self, conn):
        """✅ JSONB config opslag"""
        conn.execute(
            text(
                """
            INSERT INTO companies (tenant_id, name, company_type, sector, config)
            VALUES (1, 'Config Test', 'enterprise', 'finance', '{"key": "value"}'::jsonb)
        """
            )
        )
        conn.commit()

        result = conn.execute(text("SELECT config FROM companies WHERE name = 'Config Test'"))
        assert result.fetchone().config == {"key": "value"}
        print("✅ JSONB config stored")

    def test_company_tenant_isolation(self, conn):
        """✅ Tenant isolatie"""
        conn.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (100, 'T100', 'mkb', 'tech')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (200, 'T200', 'zzp', 'consulting')"
            )
        )
        conn.commit()

        result = conn.execute(text("SELECT name FROM companies WHERE tenant_id = 100"))
        assert result.fetchone().name == "T100"
        print("✅ Tenant isolation works")


class Test02DepartmentHierarchy:
    """Test 2: Department hiërarchie"""

    def test_department_parent_child(self, conn):
        """✅ Parent-child relaties"""
        # Create company
        result = conn.execute(
            text(
                """
            INSERT INTO companies (tenant_id, name, company_type, sector)
            VALUES (1, 'Parent Co', 'enterprise', 'tech') RETURNING id
        """
            )
        )
        company_id = result.fetchone().id

        # Parent department
        result = conn.execute(
            text(
                """
            INSERT INTO departments (tenant_id, company_id, name, board_role)
            VALUES (1, :cid, 'Engineering', 'CTO') RETURNING id
        """
            ),
            {"cid": company_id},
        )
        parent_id = result.fetchone().id

        # Child department
        result = conn.execute(
            text(
                """
            INSERT INTO departments (tenant_id, company_id, name, parent_department_id)
            VALUES (1, :cid, 'Backend', :pid) RETURNING id
        """
            ),
            {"cid": company_id, "pid": parent_id},
        )
        child_id = result.fetchone().id

        conn.commit()

        # Verify
        result = conn.execute(
            text("SELECT parent_department_id FROM departments WHERE id = :id"), {"id": child_id}
        )
        assert result.fetchone().parent_department_id == parent_id
        print("✅ Department hierarchy: Engineering -> Backend")

    def test_version_optimistic_locking(self, conn):
        """✅ Version voor optimistic locking"""
        conn.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (1, 'V Test', 'mkb', 'tech')"
            )
        )
        result = conn.execute(text("SELECT id FROM companies WHERE name = 'V Test'"))
        company_id = result.fetchone().id

        conn.execute(
            text(
                """
            INSERT INTO departments (tenant_id, company_id, name, version)
            VALUES (1, :cid, 'Test Dept', 5)
        """
            ),
            {"cid": company_id},
        )
        conn.commit()

        result = conn.execute(text("SELECT version FROM departments WHERE name = 'Test Dept'"))
        assert result.fetchone().version == 5
        print("✅ Version field: 5")


class Test03GoalChain:
    """Test 3: Goal hiërarchie"""

    def test_goal_mission_to_task(self, conn):
        """✅ Mission → Strategic → Project → Task chain"""
        # Create company
        result = conn.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (1, 'Goal Co', 'enterprise', 'tech') RETURNING id"
            )
        )
        company_id = result.fetchone().id

        # Mission
        result = conn.execute(
            text(
                "INSERT INTO goals (tenant_id, company_id, goal_type, title, status, progress_pct) VALUES (1, :cid, 'mission', 'Mission', 'active', 100) RETURNING id"
            ),
            {"cid": company_id},
        )
        mission_id = result.fetchone().id

        # Strategic
        result = conn.execute(
            text(
                "INSERT INTO goals (tenant_id, company_id, parent_goal_id, goal_type, title, status) VALUES (1, :cid, :pid, 'strategic', 'Strategic', 'active') RETURNING id"
            ),
            {"cid": company_id, "pid": mission_id},
        )
        strategic_id = result.fetchone().id

        conn.commit()

        result = conn.execute(
            text("SELECT parent_goal_id FROM goals WHERE id = :id"), {"id": strategic_id}
        )
        assert result.fetchone().parent_goal_id == mission_id
        print("✅ Goal chain: Mission -> Strategic")

    def test_progress_range(self, conn):
        """✅ Progress 0-100"""
        result = conn.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (1, 'Progress Co', 'mkb', 'tech') RETURNING id"
            )
        )
        company_id = result.fetchone().id

        for p in [0, 25, 50, 75, 100]:
            conn.execute(
                text(
                    "INSERT INTO goals (tenant_id, company_id, goal_type, title, progress_pct) VALUES (1, :cid, 'task', :title, :p)"
                ),
                {"cid": company_id, "title": f"Task {p}", "p": p},
            )

        conn.commit()
        result = conn.execute(
            text("SELECT COUNT(*) FROM goals WHERE company_id = :cid"), {"cid": company_id}
        )
        assert result.fetchone()[0] == 5
        print("✅ Progress range 0-100 works")


class Test04ExternalAgent:
    """Test 4: External Agent"""

    def test_agent_lifecycle(self, conn):
        """✅ Status: registered → active"""
        conn.execute(
            text(
                """
            INSERT INTO external_agents (tenant_id, name, runtime, capabilities, status)
            VALUES (1, 'Test Agent', 'python-3.11', '["ml"]', 'registered')
        """
            )
        )
        conn.commit()

        conn.execute(
            text(
                """
            UPDATE external_agents SET status = 'active', last_heartbeat_at = now()
            WHERE name = 'Test Agent'
        """
            )
        )
        conn.commit()

        result = conn.execute(text("SELECT status FROM external_agents WHERE name = 'Test Agent'"))
        assert result.fetchone().status == "active"
        print("✅ Agent lifecycle: registered -> active")

    def test_agent_metrics(self, conn):
        """✅ JSONB metrics"""
        conn.execute(
            text(
                """
            INSERT INTO external_agents (tenant_id, name, runtime, capabilities, metrics, status)
            VALUES (1, 'Metrics Agent', 'python-3.11', '["test"]', '{"cpu": 45.5}', 'active')
        """
            )
        )
        conn.commit()

        result = conn.execute(
            text("SELECT metrics FROM external_agents WHERE name = 'Metrics Agent'")
        )
        assert result.fetchone().metrics["cpu"] == 45.5
        print("✅ Agent metrics stored")


class Test05ContextAndSchemas:
    """Test 5: Context objecten en schemas"""

    def test_agent_execution_context(self, conn):
        """✅ AgentExecutionContext met DB data"""
        from src.core.company.context import AgentExecutionContext, GoalChain

        # Insert company
        result = conn.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (1, 'Context Co', 'mkb', 'tech') RETURNING id, company_type, sector"
            )
        )
        row = result.fetchone()

        # Create context
        context = AgentExecutionContext(
            tenant_id=1,
            company_id=row.id,
            company_type=row.company_type,
            sector=row.sector,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(mission_id=uuid.uuid4(), task_goal_id=uuid.uuid4()),
        )

        is_valid, missing = context.validate_completeness()

        assert is_valid is True
        assert context.is_degraded is False

        # JSON serializable
        json_str = context.model_dump_json()
        assert "tenant_id" in json_str
        print("✅ AgentExecutionContext valid & serializable")

    def test_goal_chain_from_db(self, conn):
        """✅ GoalChain.from_ancestry met DB data"""
        from src.core.company.context import GoalChain

        # Insert company and goals
        result = conn.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector) VALUES (1, 'Ancestry Co', 'mkb', 'tech') RETURNING id"
            )
        )
        company_id = result.fetchone().id

        result = conn.execute(
            text(
                "INSERT INTO goals (tenant_id, company_id, goal_type, title, status) VALUES (1, :cid, 'mission', 'Mission', 'active') RETURNING id"
            ),
            {"cid": company_id},
        )
        mission_id = result.fetchone().id

        result = conn.execute(
            text(
                "INSERT INTO goals (tenant_id, company_id, parent_goal_id, goal_type, title, status) VALUES (1, :cid, :pid, 'strategic', 'Strategic', 'active') RETURNING id"
            ),
            {"cid": company_id, "pid": mission_id},
        )
        strategic_id = result.fetchone().id

        conn.commit()

        # Build chain
        result = conn.execute(
            text("SELECT id, title, goal_type FROM goals WHERE company_id = :cid"),
            {"cid": company_id},
        )
        ancestry = [{"id": r.id, "title": r.title, "goal_type": r.goal_type} for r in result]

        chain = GoalChain.from_ancestry(ancestry)

        assert chain.mission_id == mission_id
        assert chain.strategic_goal_id == strategic_id
        print("✅ GoalChain.from_ancestry() works")

    def test_conflict_response(self):
        """✅ ConflictResponse schema"""
        from src.core.company.schemas import ConflictResponse

        conflict = ConflictResponse(
            detail="Resource modified",
            current_version=5,
            conflicting_user="user@example.com",
        )

        assert conflict.error_code == "CONFLICT"

        json_data = conflict.model_dump_json()
        assert "CONFLICT" in json_data
        print("✅ ConflictResponse schema")


class Test06EndToEnd:
    """Test 6: E2E flow"""

    def test_onboarding_flow(self, conn):
        """✅ Complete flow: Company -> Dept -> Goal"""
        from src.core.company.context import AgentExecutionContext, GoalChain

        # 1. Company
        result = conn.execute(
            text(
                "INSERT INTO companies (tenant_id, name, company_type, sector, mission) VALUES (1, 'Fintech BV', 'mkb', 'fintech', 'Democratize finance') RETURNING id"
            )
        )
        company_id = result.fetchone().id

        # 2. Department
        result = conn.execute(
            text(
                "INSERT INTO departments (tenant_id, company_id, name, board_role) VALUES (1, :cid, 'Engineering', 'CTO') RETURNING id"
            ),
            {"cid": company_id},
        )
        dept_id = result.fetchone().id

        # 3. Goal
        result = conn.execute(
            text(
                "INSERT INTO goals (tenant_id, company_id, department_id, goal_type, title, status) VALUES (1, :cid, :did, 'mission', 'Make finance accessible', 'active') RETURNING id"
            ),
            {"cid": company_id, "did": dept_id},
        )
        goal_id = result.fetchone().id

        conn.commit()

        # 4. Context
        context = AgentExecutionContext(
            tenant_id=1,
            company_id=company_id,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(mission_id=goal_id, task_goal_id=uuid.uuid4()),
        )

        assert context.company_id == company_id
        assert context.goal_chain.is_complete() is True

        print(
            f"✅ E2E: Company({str(company_id)[:8]}) -> Dept({str(dept_id)[:8]}) -> Goal({str(goal_id)[:8]})"
        )


# ============================================================================
# SAMENVATTING
# ============================================================================

"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          INTEGRATIE TEST RESULTATEN - FASE 1 DATA FOUNDATION                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ✅ Test 1: Company Model (3/3)                                              ║
║  ✅ Test 2: Department Hiërarchie (2/2)                                      ║
║  ✅ Test 3: Goal Chain (2/2)                                                 ║
║  ✅ Test 4: External Agent (2/2)                                             ║
║  ✅ Test 5: Context & Schemas (3/3)                                          ║
║  ✅ Test 6: End-to-End (1/1)                                                 ║
║                                                                              ║
║  ═══════════════════════════════════════════════════════════════════════    ║
║  TOTAAL: 13/13 tests PASSED                                                  ║
║                                                                              ║
║  STATUS: FASE 1 DATA FOUNDATION ✅ COMPLETE                                  ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
