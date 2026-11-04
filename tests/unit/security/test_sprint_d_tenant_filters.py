"""
Sprint D: Repository/service methods missing tenant_id filter.

Source-scan tests — no DB, no fixtures needed.
Each test reads the source file and verifies that the method either:
  - contains an explicit tenant_id WHERE filter, OR
  - passes tenant_id through to a helper that does the filtering.

RED phase: all tests fail against current implementation.
GREEN phase: tests pass after fixes are applied.
"""

import re
from pathlib import Path

SRC = Path(__file__).parents[3] / "src"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def _extract_method(source: str, method_name: str) -> str:
    """Return the body of the first def <method_name> found (stops at next same-level def/class)."""
    lines = source.splitlines()
    inside = False
    body_lines: list[str] = []
    base_indent: int | None = None

    for line in lines:
        if not inside:
            stripped = line.lstrip()
            if re.match(rf"async def {method_name}\b|def {method_name}\b", stripped):
                inside = True
                base_indent = len(line) - len(line.lstrip())
                body_lines.append(line)
            continue

        current_indent = len(line) - len(line.lstrip()) if line.strip() else 9999
        if (
            line.strip()
            and base_indent is not None
            and current_indent <= base_indent
            and body_lines
        ):
            if re.match(r"(async )?def |class ", line.lstrip()):
                break
        body_lines.append(line)

    return "\n".join(body_lines)


def _has(text: str, *patterns: str) -> bool:
    return all(re.search(p, text) for p in patterns)


# ===========================================================================
# 1. AgentRegistry.get_agent_by_id — DB fallback must filter on tenant_id
# ===========================================================================


class TestGetAgentByIdTenantFilter:
    _F = "core/agents/agent_registry.py"

    def _body(self) -> str:
        return _extract_method(_read(self._F), "get_agent_by_id")

    def test_db_fallback_filters_on_tenant_id(self) -> None:
        """DB query must include a tenant_id condition to prevent cross-tenant agent access."""
        body = self._body()
        has_tenant_filter = _has(body, r"tenant_id")
        assert has_tenant_filter, (
            f"{self._F}: get_agent_by_id() DB fallback must filter by tenant_id. "
            "Without it, any tenant can retrieve another tenant's agent."
        )

    def test_tenant_id_in_where_clause(self) -> None:
        """tenant_id must appear in a .where() or equivalent condition, not just a comment."""
        body = self._body()
        # Check that tenant_id appears as a WHERE filter (not just a log/comment)
        has_where = bool(
            re.search(r"\.where\(.*tenant_id", body, re.DOTALL)
            or re.search(r"tenant_id\s*==", body)
            or re.search(r'"tenant_id"\s*:', body)  # dict filter
        )
        assert has_where, (
            f"{self._F}: get_agent_by_id() must use tenant_id in a WHERE condition, "
            "not just reference it in a comment or log."
        )


# ===========================================================================
# 2. WorkflowEngine.get_execution_status — must propagate tenant isolation
# ===========================================================================


class TestGetExecutionStatusTenantIsolation:
    _F = "core/workflow/engine.py"

    def _body(self) -> str:
        return _extract_method(_read(self._F), "get_execution_status")

    def test_accepts_tenant_id_parameter(self) -> None:
        """get_execution_status must accept a tenant_id parameter for isolation."""
        body = self._body()
        has_param = _has(body, r"tenant_id")
        assert has_param, (
            f"{self._F}: get_execution_status() must accept tenant_id so it can "
            "pass it through to _get_execution() for cross-tenant protection."
        )

    def test_passes_tenant_id_to_get_execution(self) -> None:
        """Must pass tenant_id through to _get_execution(), which enforces it."""
        body = self._body()
        # _get_execution is called — it must receive tenant_id
        has_call = bool(
            re.search(r"_get_execution\(.*tenant_id", body, re.DOTALL)
            or re.search(r"_get_execution\([^)]*tenant_id", body)
        )
        assert has_call, (
            f"{self._F}: get_execution_status() must pass tenant_id to _get_execution(). "
            "_get_execution() already supports the tenant filter — it just needs to be used."
        )


# ===========================================================================
# 3. WorkflowEngine.cancel_execution — must propagate tenant isolation
# ===========================================================================


class TestCancelExecutionTenantIsolation:
    _F = "core/workflow/engine.py"

    def _body(self) -> str:
        return _extract_method(_read(self._F), "cancel_execution")

    def test_accepts_tenant_id_parameter(self) -> None:
        """cancel_execution must accept a tenant_id parameter."""
        body = self._body()
        has_param = _has(body, r"tenant_id")
        assert has_param, (
            f"{self._F}: cancel_execution() has a TODO for tenant isolation. "
            "It must accept and forward tenant_id to _get_execution()."
        )

    def test_passes_tenant_id_to_get_execution(self) -> None:
        """Must pass tenant_id to _get_execution() to prevent cross-tenant cancellation."""
        body = self._body()
        has_call = bool(
            re.search(r"_get_execution\(.*tenant_id", body, re.DOTALL)
            or re.search(r"_get_execution\([^)]*tenant_id", body)
        )
        assert has_call, (
            f"{self._F}: cancel_execution() must pass tenant_id to _get_execution(). "
            "Without this, any authenticated user can cancel another tenant's execution."
        )


# ===========================================================================
# 4. WorkflowEngine API caller — cancel_execution endpoint must pass tenant_id
# ===========================================================================


class TestCancelExecutionApiTenantIsolation:
    """Wees tot 2026-08-27 naar `core/workflow/api.py`, bevestigd dode code (ADR-036
    OP-158 D2b) en verwijderd. `core/api/v1/workflow/workflow_execution_cancel_router.py`
    is de ECHTE, gemounte endpoint -- structureel anders (een directe DB-WHERE-clause
    i.p.v. een `engine.cancel_execution(tenant_id=...)`-delegatie), dus de oude regex
    (`cancel_execution\\(.*tenant_id`) is hier niet zinvol; deze toetst rechtstreeks op
    de WHERE-clause.
    """

    _F = "core/api/v1/workflow/workflow_execution_cancel_router.py"

    def _body(self) -> str:
        return _extract_method(_read(self._F), "cancel_execution")

    def test_the_query_filters_by_tenant_id(self) -> None:
        """De query die de execution ophaalt MOET op tenant_id filteren, anders kan een
        aanvrager een execution van een andere tenant annuleren via een geraden ID.
        """
        body = self._body()
        assert re.search(r"WorkflowExecution\.tenant_id\s*==\s*tenant_id", body), (
            f"{self._F}: cancel_execution mist een tenant_id-filter op de WorkflowExecution-"
            "query. Zonder die WHERE-clause kan elke tenant elke execution annuleren."
        )


# ===========================================================================
# 5. ConversationPersistenceService.get_user_conversations — must filter by tenant
# ===========================================================================


class TestGetUserConversationsTenantFilter:
    _F = "core/services/conversation_persistence.py"

    def _body(self) -> str:
        return _extract_method(_read(self._F), "get_user_conversations")

    def test_method_accepts_tenant_id(self) -> None:
        """get_user_conversations must accept a tenant_id parameter."""
        body = self._body()
        has_param = _has(body, r"tenant_id")
        assert has_param, (
            f"{self._F}: get_user_conversations() filters only by user_id. "
            "It must also accept and filter by tenant_id to prevent cross-tenant conversation leaks."
        )

    def test_sql_filters_on_tenant_id(self) -> None:
        """SQL query must include tenant_id in the WHERE clause."""
        body = self._body()
        # SQL text should reference tenant_id as a filter
        has_sql_filter = bool(
            re.search(r"tenant_id\s*=\s*:tenant_id", body)
            or re.search(r"AND tenant_id", body, re.IGNORECASE)
            or re.search(r"WHERE.*tenant_id", body, re.DOTALL | re.IGNORECASE)
        )
        assert has_sql_filter, (
            f"{self._F}: get_user_conversations() SQL must filter by tenant_id. "
            "Current query only filters by user_id — user_id alone does not guarantee tenant isolation."
        )


# ===========================================================================
# 6. ConversationPersistenceService table DDL — conversations table needs tenant_id
# ===========================================================================


class TestConversationsTableHasTenantId:
    _F = "core/services/conversation_persistence.py"

    def test_conversations_table_ddl_includes_tenant_id(self) -> None:
        """The CREATE TABLE for conversations must include a tenant_id column."""
        src = _read(self._F)
        # Locate the start of the CREATE TABLE conversations statement.
        # We cannot use a simple capturing group because column types like VARCHAR(36)
        # contain unbalanced ')' that would stop a non-greedy match too early.
        start = re.search(
            r"CREATE TABLE IF NOT EXISTS conversations\s*\(",
            src,
            re.IGNORECASE,
        )
        assert start, f"{self._F}: Could not locate CREATE TABLE conversations DDL"
        # Scan forward from the opening '(' counting depth to find the matching ')'.
        pos = start.end() - 1  # position of the opening '('
        depth = 0
        end_pos = pos
        for i, ch in enumerate(src[pos:], start=pos):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end_pos = i
                    break
        ddl_body = src[pos : end_pos + 1]
        has_tenant = bool(re.search(r"tenant_id", ddl_body, re.IGNORECASE))
        assert has_tenant, (
            f"{self._F}: conversations table DDL is missing tenant_id column. "
            "Without it, conversations are not tenant-scoped at the DB level."
        )


# ===========================================================================
# 7. ConversationPersistenceService.get_conversation_history — must filter by tenant
# ===========================================================================


class TestGetConversationHistoryTenantFilter:
    _F = "core/services/conversation_persistence.py"

    def _body(self) -> str:
        return _extract_method(_read(self._F), "get_conversation_history")

    def test_accepts_tenant_id_parameter(self) -> None:
        """get_conversation_history must accept a tenant_id parameter."""
        body = self._body()
        assert re.search(r"tenant_id", body), (
            f"{self._F}: get_conversation_history() fetches messages by conversation_id "
            "alone -- an attacker who guesses a UUID can read another tenant's conversation. "
            "Add a tenant_id parameter and verify ownership in the SQL WHERE clause."
        )

    def test_sql_verifies_conversation_tenant(self) -> None:
        """SQL must check tenant_id so only the owning tenant can read a conversation."""
        body = self._body()
        has_filter = bool(
            re.search(r"tenant_id\s*=\s*:tenant_id", body)
            or re.search(r"AND.*tenant_id", body, re.IGNORECASE | re.DOTALL)
            or re.search(r"WHERE.*tenant_id", body, re.IGNORECASE | re.DOTALL)
        )
        assert has_filter, (
            f"{self._F}: get_conversation_history() SQL must filter by tenant_id. "
            "Querying only by conversation_id allows cross-tenant conversation access."
        )


# ===========================================================================
# 8. ConversationPersistenceService.get_conversation_analytics — must filter by tenant
# ===========================================================================


class TestGetConversationAnalyticsTenantFilter:
    _F = "core/services/conversation_persistence.py"

    def _body(self) -> str:
        return _extract_method(_read(self._F), "get_conversation_analytics")

    def test_accepts_tenant_id_parameter(self) -> None:
        """get_conversation_analytics must accept a tenant_id parameter."""
        body = self._body()
        assert re.search(r"tenant_id", body), (
            f"{self._F}: get_conversation_analytics() has no tenant_id parameter. "
            "Without it, analytics aggregate data across ALL tenants -- a data leak."
        )

    def test_sql_filters_analytics_by_tenant(self) -> None:
        """The SQL base_query must include a tenant_id condition."""
        body = self._body()
        has_filter = bool(
            re.search(r"tenant_id\s*=\s*:tenant_id", body)
            or re.search(r"AND.*tenant_id", body, re.IGNORECASE | re.DOTALL)
            or re.search(r"WHERE.*tenant_id", body, re.IGNORECASE | re.DOTALL)
        )
        assert has_filter, (
            f"{self._F}: get_conversation_analytics() SQL must filter by tenant_id. "
            "Current base_query filters by cutoff_date only -- cross-tenant analytics leak."
        )


# ===========================================================================
# 9. ConversationPersistenceService.cleanup_old_conversations — must be tenant-scoped
# ===========================================================================


class TestCleanupOldConversationsTenantFilter:
    _F = "core/services/conversation_persistence.py"

    def _body(self) -> str:
        return _extract_method(_read(self._F), "cleanup_old_conversations")

    def test_cleanup_accepts_tenant_id(self) -> None:
        """cleanup_old_conversations must accept a tenant_id parameter."""
        body = self._body()
        assert re.search(r"tenant_id", body), (
            f"{self._F}: cleanup_old_conversations() deletes conversations by date alone "
            "with no tenant scope -- it would delete OTHER tenants' conversations. "
            "Add a tenant_id parameter and filter all queries with it."
        )

    def test_cleanup_sql_filters_by_tenant(self) -> None:
        """SELECT and DELETE statements must include a tenant_id condition."""
        body = self._body()
        has_filter = bool(
            re.search(r"tenant_id\s*=\s*:tenant_id", body)
            or re.search(r"AND.*tenant_id", body, re.IGNORECASE | re.DOTALL)
            or re.search(r"WHERE.*tenant_id", body, re.IGNORECASE | re.DOTALL)
        )
        assert has_filter, (
            f"{self._F}: cleanup_old_conversations() SQL must filter by tenant_id. "
            "Without this, the cleanup job silently deletes conversations from all tenants."
        )


# ===========================================================================
# 10. TrainingService.fetch_experiences — must filter by tenant_id
# ===========================================================================


class TestFetchExperiencesTenantFilter:
    _F = "core/services/training_service.py"

    def _body(self) -> str:
        return _extract_method(_read(self._F), "fetch_experiences")

    def test_accepts_tenant_id_parameter(self) -> None:
        """fetch_experiences must accept a tenant_id parameter."""
        body = self._body()
        assert re.search(r"tenant_id", body), (
            f"{self._F}: fetch_experiences() queries LearningExperience without tenant_id. "
            "This trains the model on cross-tenant data -- a privacy and isolation violation."
        )

    def test_query_filters_by_tenant(self) -> None:
        """SQLAlchemy query must include a tenant_id WHERE condition."""
        body = self._body()
        has_filter = bool(
            re.search(r"\.tenant_id\s*==\s*tenant_id", body)
            or re.search(r"LearningExperience\.tenant_id", body)
        )
        assert has_filter, (
            f"{self._F}: fetch_experiences() WHERE clause must filter LearningExperience.tenant_id. "
            "Without it, training mixes data from different tenants."
        )


# ===========================================================================
# 11. TrainingService.get_experience_count — must filter by tenant_id
# ===========================================================================


class TestGetExperienceCountTenantFilter:
    _F = "core/services/training_service.py"

    def _body(self) -> str:
        return _extract_method(_read(self._F), "get_experience_count")

    def test_accepts_tenant_id_parameter(self) -> None:
        """get_experience_count must accept a tenant_id parameter."""
        body = self._body()
        assert re.search(r"tenant_id", body), (
            f"{self._F}: get_experience_count() counts experiences from all tenants. "
            "Add tenant_id parameter and filter the count query by it."
        )

    def test_count_query_filters_by_tenant(self) -> None:
        """COUNT query must include LearningExperience.tenant_id in the WHERE clause."""
        body = self._body()
        has_filter = bool(
            re.search(r"\.tenant_id\s*==\s*tenant_id", body)
            or re.search(r"LearningExperience\.tenant_id", body)
        )
        assert has_filter, (
            f"{self._F}: get_experience_count() must filter by LearningExperience.tenant_id. "
            "Cross-tenant counts leak metadata about other tenants' activity."
        )


# ===========================================================================
# 12. DriftDetector -- __init__ must accept tenant_id; all queries must filter
# ===========================================================================


class TestDriftDetectorTenantIsolation:
    _F = "core/monitoring/drift_detection.py"

    def _src(self) -> str:
        return _read(self._F)

    def test_init_accepts_tenant_id(self) -> None:
        """DriftDetector.__init__ must accept a tenant_id parameter."""
        body = _extract_method(self._src(), "__init__")
        assert re.search(r"tenant_id", body), (
            f"{self._F}: DriftDetector.__init__ has no tenant_id parameter. "
            "Without it, all four detect methods query LearningExperience across all tenants."
        )

    def test_establish_baseline_filters_by_tenant(self) -> None:
        """establish_baseline() must call _reader.get_experiences with tenant_id=self.tenant_id."""
        body = _extract_method(self._src(), "establish_baseline")
        has_reader = bool(re.search(r"self\._reader\.get_experiences", body))
        has_tenant = bool(re.search(r"tenant_id\s*=\s*self\.tenant_id", body))
        assert has_reader and has_tenant, (
            f"{self._F}: establish_baseline() must call self._reader.get_experiences("
            "tenant_id=self.tenant_id). Cross-tenant baseline contaminates drift detection."
        )

    def test_detect_distribution_drift_filters_by_tenant(self) -> None:
        """detect_distribution_drift() must call _reader.get_experiences with tenant_id=self.tenant_id."""
        body = _extract_method(self._src(), "detect_distribution_drift")
        has_reader = bool(re.search(r"self\._reader\.get_experiences", body))
        has_tenant = bool(re.search(r"tenant_id\s*=\s*self\.tenant_id", body))
        assert has_reader and has_tenant, (
            f"{self._F}: detect_distribution_drift() must call self._reader.get_experiences("
            "tenant_id=self.tenant_id). Cross-tenant window data invalidates drift tests."
        )

    def test_detect_concept_drift_filters_by_tenant(self) -> None:
        """detect_concept_drift() must call _reader.get_experiences with tenant_id=self.tenant_id."""
        body = _extract_method(self._src(), "detect_concept_drift")
        has_reader = bool(re.search(r"self\._reader\.get_experiences", body))
        has_tenant = bool(re.search(r"tenant_id\s*=\s*self\.tenant_id", body))
        assert has_reader and has_tenant, (
            f"{self._F}: detect_concept_drift() must call self._reader.get_experiences("
            "tenant_id=self.tenant_id)."
        )

    def test_detect_feature_drift_filters_by_tenant(self) -> None:
        """detect_feature_drift() must call _reader.get_experiences with tenant_id=self.tenant_id."""
        body = _extract_method(self._src(), "detect_feature_drift")
        has_reader = bool(re.search(r"self\._reader\.get_experiences", body))
        has_tenant = bool(re.search(r"tenant_id\s*=\s*self\.tenant_id", body))
        assert has_reader and has_tenant, (
            f"{self._F}: detect_feature_drift() must call self._reader.get_experiences("
            "tenant_id=self.tenant_id)."
        )
