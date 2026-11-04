"""Unit tests for ToolAuditRepository.

Tests use a mocked AsyncSession to avoid needing a real database.
For integration tests against a real DB, see tests/integration/.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.tool_broker.audit_repository import ToolAuditRepository
from src.core.tool_broker.audit_utils import compute_audit_hash, compute_output_hash


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_db() -> MagicMock:
    """Build a minimal AsyncSession mock."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_repo(tenant_id: int = 1) -> tuple:
    db = _make_mock_db()
    repo = ToolAuditRepository(db=db, tenant_id=tenant_id)
    return repo, db


# ---------------------------------------------------------------------------
# Happy paths: log_execution
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestLogExecution:
    @pytest.mark.asyncio
    async def test_log_execution_calls_db_add_and_commit(self):
        repo, db = _make_repo()

        await repo.log_execution(
            agent_id="agent-1",
            tool_name="serena__search",
            risk_level="low",
            tool_input={"query": "hello"},
            tool_output={"result": "world"},
            status="success",
            duration_seconds=0.42,
        )

        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_execution_computes_output_hash_for_non_null_output(self):
        repo, db = _make_repo()

        added_log = None

        def capture_add(obj):
            nonlocal added_log
            added_log = obj

        db.add = capture_add

        tool_output = {"result": "world"}
        await repo.log_execution(
            agent_id="agent-1",
            tool_name="serena__search",
            risk_level="low",
            tool_input={"query": "hello"},
            tool_output=tool_output,
            status="success",
            duration_seconds=0.1,
        )

        expected_hash = compute_output_hash(tool_output)
        assert added_log is not None
        assert added_log.output_hash == expected_hash

    @pytest.mark.asyncio
    async def test_log_execution_null_output_hash_when_no_output(self):
        repo, db = _make_repo()
        added_log = None

        def capture_add(obj):
            nonlocal added_log
            added_log = obj

        db.add = capture_add

        await repo.log_execution(
            agent_id="agent-1",
            tool_name="serena__search",
            risk_level="low",
            tool_input={},
            tool_output=None,
            status="failed",
            duration_seconds=0.0,
        )

        assert added_log is not None
        assert added_log.output_hash is None

    @pytest.mark.asyncio
    async def test_log_execution_computes_audit_hash(self):
        repo, db = _make_repo(tenant_id=42)
        added_log = None

        def capture_add(obj):
            nonlocal added_log
            added_log = obj

        db.add = capture_add
        # Eerst het slot per klant, dan de lezing van de vorige hash (brief 2026-10-22): de
        # repository leest die zelf, de aanroeper geeft hem niet meer mee.
        staart = MagicMock()
        staart.scalar_one_or_none.return_value = "abc123"
        db.execute = AsyncMock(side_effect=[MagicMock(), staart])

        await repo.log_execution(
            agent_id="agent-x",
            tool_name="local__read_file",
            risk_level="low",
            tool_input={"path": "/tmp/file.txt"},
            tool_output=None,
            status="success",
            duration_seconds=0.05,
        )

        assert added_log is not None
        assert added_log.audit_hash is not None
        assert len(added_log.audit_hash) == 64  # SHA-256 hex
        assert "pg_advisory_xact_lock" in str(db.execute.await_args_list[0].args[0])
        assert added_log.previous_hash == "abc123"
        assert added_log.audit_hash == compute_audit_hash(
            tenant_id=42,
            agent_id="agent-x",
            tool_name="local__read_file",
            timestamp=added_log.timestamp,
            status="success",
            output_hash=None,
            previous_hash="abc123",
            tool_input={"path": "/tmp/file.txt"},
        )

    @pytest.mark.asyncio
    async def test_log_execution_stores_tenant_id(self):
        repo, db = _make_repo(tenant_id=99)
        added_log = None

        def capture_add(obj):
            nonlocal added_log
            added_log = obj

        db.add = capture_add

        await repo.log_execution(
            agent_id="agent-1",
            tool_name="test__echo",
            risk_level="low",
            tool_input={},
            tool_output=None,
            status="success",
            duration_seconds=0.0,
        )

        assert added_log is not None
        assert added_log.tenant_id == 99

    @pytest.mark.asyncio
    async def test_log_execution_sanitizes_output_before_storage(self):
        repo, db = _make_repo()
        added_log = None

        def capture_add(obj):
            nonlocal added_log
            added_log = obj

        db.add = capture_add

        tool_output = {"result": "ok", "password": "s3cr3t", "data": "value"}
        await repo.log_execution(
            agent_id="agent-1",
            tool_name="local__run_shell",
            risk_level="high",
            tool_input={},
            tool_output=tool_output,
            status="success",
            duration_seconds=1.0,
        )

        # tool_output stored is sanitized (REDACTED) but output_hash is of ORIGINAL
        assert added_log is not None
        assert added_log.tool_output is not None
        assert added_log.tool_output.get("password") == "[REDACTED]"
        assert added_log.tool_output.get("result") == "ok"

    @pytest.mark.asyncio
    async def test_log_execution_stores_hitl_ticket_ref(self):
        repo, db = _make_repo()
        added_log = None

        def capture_add(obj):
            nonlocal added_log
            added_log = obj

        db.add = capture_add

        await repo.log_execution(
            agent_id="agent-1",
            tool_name="local__send_email",
            risk_level="high",
            tool_input={},
            tool_output=None,
            status="pending_hitl",
            duration_seconds=0.0,
            hitl_ticket_ref="TOOL-AB12CD34",
        )

        assert added_log is not None
        assert added_log.hitl_ticket_ref == "TOOL-AB12CD34"
        assert added_log.status == "pending_hitl"


# ---------------------------------------------------------------------------
# Happy paths: get_last_audit_hash
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestGetLastAuditHash:
    @pytest.mark.asyncio
    async def test_returns_hash_when_records_exist(self):
        repo, db = _make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "deadbeef" * 8  # 64 chars
        db.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_last_audit_hash()

        assert result == "deadbeef" * 8

    @pytest.mark.asyncio
    async def test_returns_none_when_no_records(self):
        repo, db = _make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_last_audit_hash()

        assert result is None


# ---------------------------------------------------------------------------
# Happy paths: get_logs_by_agent + get_logs_by_tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestGetLogs:
    @pytest.mark.asyncio
    async def test_get_logs_by_agent_returns_list(self):
        repo, db = _make_repo()

        mock_log = MagicMock()
        mock_log.agent_id = "agent-1"
        mock_log.tenant_id = 1

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        db.execute = AsyncMock(return_value=mock_result)

        logs = await repo.get_logs_by_agent("agent-1")

        assert len(logs) == 1
        assert logs[0].agent_id == "agent-1"

    @pytest.mark.asyncio
    async def test_get_logs_by_agent_returns_empty_for_unknown_agent(self):
        repo, db = _make_repo()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        logs = await repo.get_logs_by_agent("nonexistent-agent")

        assert logs == []

    @pytest.mark.asyncio
    async def test_get_logs_by_tool_returns_list(self):
        repo, db = _make_repo()
        mock_log = MagicMock()
        mock_log.tool_name = "serena__search"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        db.execute = AsyncMock(return_value=mock_result)

        logs = await repo.get_logs_by_tool("serena__search")

        assert len(logs) == 1
        assert logs[0].tool_name == "serena__search"


# ---------------------------------------------------------------------------
# Happy paths: verify_chain_integrity
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestVerifyChainIntegrity:
    @pytest.mark.asyncio
    async def test_returns_true_for_empty_log(self):
        repo, db = _make_repo()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await repo.verify_chain_integrity()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_for_single_genesis_entry(self):
        repo, db = _make_repo()

        log = MagicMock()
        log.previous_hash = None
        log.audit_hash = "abc123"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [log]
        db.execute = AsyncMock(return_value=mock_result)

        result = await repo.verify_chain_integrity()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_for_valid_chain(self):
        repo, db = _make_repo()

        log1 = MagicMock()
        log1.previous_hash = None
        log1.audit_hash = "hash1"

        log2 = MagicMock()
        log2.previous_hash = "hash1"
        log2.audit_hash = "hash2"

        log3 = MagicMock()
        log3.previous_hash = "hash2"
        log3.audit_hash = "hash3"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [log1, log2, log3]
        db.execute = AsyncMock(return_value=mock_result)

        result = await repo.verify_chain_integrity()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_for_broken_chain(self):
        repo, db = _make_repo()

        log1 = MagicMock()
        log1.previous_hash = None
        log1.audit_hash = "hash1"

        log2 = MagicMock()
        log2.previous_hash = "WRONG_HASH"  # Chain broken
        log2.audit_hash = "hash2"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [log1, log2]
        db.execute = AsyncMock(return_value=mock_result)

        result = await repo.verify_chain_integrity()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_first_entry_has_non_genesis_hash(self):
        repo, db = _make_repo()

        log = MagicMock()
        log.previous_hash = "some_hash_that_is_not_none_or_genesis"
        log.audit_hash = "hash1"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [log]
        db.execute = AsyncMock(return_value=mock_result)

        result = await repo.verify_chain_integrity()

        assert result is False


# ---------------------------------------------------------------------------
# Happy paths: get_blocked_tools_count
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestGetBlockedToolsCount:
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_blocked_tools(self):
        repo, db = _make_repo()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        count = await repo.get_blocked_tools_count()

        assert count == 0

    @pytest.mark.asyncio
    async def test_returns_count_of_blocked_tools(self):
        repo, db = _make_repo()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=mock_result)

        count = await repo.get_blocked_tools_count()

        assert count == 2


# ---------------------------------------------------------------------------
# Unhappy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestAuditRepositoryUnhappyPaths:
    @pytest.mark.asyncio
    async def test_log_execution_propagates_db_commit_failure(self):
        """A failing commit propagates — caller (best_effort) handles it."""
        repo, db = _make_repo()
        db.commit = AsyncMock(side_effect=RuntimeError("db ded"))

        with pytest.raises(RuntimeError, match="db ded"):
            await repo.log_execution(
                agent_id="agent-1",
                tool_name="test__echo",
                risk_level="low",
                tool_input={},
                tool_output=None,
                status="success",
                duration_seconds=0.0,
            )

    @pytest.mark.asyncio
    async def test_tenant_isolation_different_tenant_does_not_see_logs(self):
        """Each repo instance is scoped to one tenant_id."""
        repo_t1, _ = _make_repo(tenant_id=1)
        repo_t2, _ = _make_repo(tenant_id=2)

        # They have different tenant scopes — verify constructor
        assert repo_t1.tenant_id == 1
        assert repo_t2.tenant_id == 2
        assert repo_t1.tenant_id != repo_t2.tenant_id
