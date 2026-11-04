"""Integration tests for agent department_id migration."""

import pytest
from sqlalchemy import inspect


@pytest.mark.integration
class TestAgentDepartmentMigration:
    """Test that migration correctly adds department_id column."""

    async def test_department_id_column_exists(self, postgres_engine):
        """Migration should add department_id column to agents table."""

        def check_column(conn):
            inspector = inspect(conn)
            columns = [c["name"] for c in inspector.get_columns("agents")]
            return columns

        async with postgres_engine.connect() as conn:
            columns = await conn.run_sync(check_column)

        assert "department_id" in columns

    async def test_foreign_key_constraint_exists(self, postgres_engine):
        """Migration should create fk_agents_department constraint."""

        def check_fk(conn):
            inspector = inspect(conn)
            fks = inspector.get_foreign_keys("agents")
            fk_names = [fk["name"] for fk in fks]
            return fk_names

        async with postgres_engine.connect() as conn:
            fk_names = await conn.run_sync(check_fk)

        # Accept both Alembic naming (fk_agents_department) and SQLAlchemy auto-generated naming
        assert any(
            name in fk_names for name in ["fk_agents_department", "agents_department_id_fkey"]
        )

    async def test_index_exists(self, postgres_engine):
        """Migration should create idx_agents_department index."""

        def check_index(conn):
            inspector = inspect(conn)
            indexes = inspector.get_indexes("agents")
            index_names = [idx["name"] for idx in indexes]
            return index_names

        async with postgres_engine.connect() as conn:
            index_names = await conn.run_sync(check_index)

        # Accept both Alembic naming (idx_agents_department) and SQLAlchemy auto-generated naming
        assert any(
            name in index_names for name in ["idx_agents_department", "ix_agents_department_id"]
        )

    async def test_department_id_is_nullable(self, postgres_engine):
        """department_id should be nullable for existing agents."""

        def check_nullable(conn):
            inspector = inspect(conn)
            columns = {c["name"]: c for c in inspector.get_columns("agents")}
            return columns

        async with postgres_engine.connect() as conn:
            columns = await conn.run_sync(check_nullable)

        assert columns["department_id"]["nullable"] is True

    async def test_foreign_key_references_departments(self, postgres_engine):
        """Foreign key should reference departments.id."""

        def check_fk_ref(conn):
            inspector = inspect(conn)
            fks = inspector.get_foreign_keys("agents")
            dept_fk = next(
                fk
                for fk in fks
                if fk["name"] in ["fk_agents_department", "agents_department_id_fkey"]
            )
            return dept_fk

        async with postgres_engine.connect() as conn:
            dept_fk = await conn.run_sync(check_fk_ref)

        assert dept_fk["referred_table"] == "departments"
        assert dept_fk["referred_columns"] == ["id"]
        assert dept_fk["constrained_columns"] == ["department_id"]
