"""Unit tests for src.core.database.query_analyzer."""

import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text

from src.core.database.query_analyzer import (
    QueryLog,
    QueryAnalyzer,
    setup_query_logging,
    query_analyzer,
)


def test_query_log_dataclass():
    """Validates QueryLog fields."""
    entry = QueryLog(
        query="SELECT * FROM users",
        params={"id": 1},
        duration_ms=12.5,
        timestamp="2026-09-21T23:00:00Z",
        caller="test_module",
        rows_affected=1,
        is_slow=False,
    )
    assert entry.query == "SELECT * FROM users"
    assert entry.duration_ms == 12.5
    assert entry.is_slow is False


def test_query_analyzer_normalize_query():
    """Normalizes whitespace and handles None queries."""
    analyzer = QueryAnalyzer(enable_logging=False)
    assert analyzer._normalize_query("  SELECT   * \n FROM   users  ") == "SELECT * FROM users"
    assert analyzer._normalize_query(None) == ""


def test_query_analyzer_log_query_and_slow_detection(tmp_path, caplog):
    """Detects slow queries when duration exceeds threshold and logs warning."""
    import logging
    log_file = tmp_path / "queries.jsonl"
    analyzer = QueryAnalyzer(slow_query_threshold_ms=50.0, log_file=str(log_file))

    with caplog.at_level(logging.WARNING):
        q1 = analyzer.log_query("SELECT 1", duration_ms=10.0)
        assert q1.is_slow is False
        assert "Slow query" not in caplog.text

        q2 = analyzer.log_query("SELECT count(*) FROM large_table", duration_ms=120.0)
        assert q2.is_slow is True
        assert "Slow query (120.00ms)" in caplog.text

    slow = analyzer.get_slow_queries()
    assert len(slow) == 1
    assert slow[0].query == "SELECT count(*) FROM large_table"

    # Check file output
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_query_analyzer_stats():
    """Calculates query performance statistics."""
    analyzer = QueryAnalyzer(slow_query_threshold_ms=50.0, enable_logging=False)

    # Empty stats
    assert analyzer.get_query_stats() == {"total": 0}

    analyzer.log_query("Q1", duration_ms=10.0)
    analyzer.log_query("Q2", duration_ms=20.0)
    analyzer.log_query("Q3", duration_ms=90.0)

    stats = analyzer.get_query_stats()
    assert stats["total"] == 3
    assert stats["slow_count"] == 1
    assert pytest.approx(stats["slow_percentage"]) == 33.333333333333336
    assert stats["avg_duration_ms"] == 40.0
    assert stats["max_duration_ms"] == 90.0
    assert stats["min_duration_ms"] == 10.0


def test_query_analyzer_detect_n_plus_one():
    """Identifies N+1 candidate queries appearing > 5 times."""
    analyzer = QueryAnalyzer(enable_logging=False)

    for _ in range(6):
        analyzer.log_query("SELECT * FROM profiles WHERE user_id = :id", params={"id": 1})

    analyzer.log_query("SELECT * FROM users", duration_ms=5.0)

    candidates = analyzer.detect_n_plus_one()
    assert len(candidates) == 1
    assert "profiles WHERE user_id" in candidates[0]["query"]
    assert candidates[0]["count"] == 6
    assert "JOIN" in candidates[0]["suggestion"]


def test_query_analyzer_export_analysis(tmp_path):
    """Exports JSON analysis report."""
    analyzer = QueryAnalyzer(enable_logging=False)
    analyzer.log_query("SELECT 1", duration_ms=5.0)

    export_path = tmp_path / "report.json"
    exported = analyzer.export_analysis(str(export_path))
    assert exported == str(export_path)

    with open(export_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "generated_at" in data
    assert data["stats"]["total"] == 1
    assert "slow_queries" in data
    assert "n_plus_one_candidates" in data


def test_query_analyzer_clear():
    """Clears internal queries list."""
    analyzer = QueryAnalyzer(enable_logging=False)
    analyzer.log_query("SELECT 1")
    assert len(analyzer.queries) == 1
    analyzer.clear()
    assert len(analyzer.queries) == 0


def test_setup_query_logging_sync_engine():
    """Validates SQLAlchemy event listeners log queries on actual engine."""
    engine = create_engine("sqlite:///:memory:")
    analyzer = QueryAnalyzer(enable_logging=False)

    setup_query_logging(engine, analyzer)

    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE test (id int)"))
        conn.execute(text("INSERT INTO test VALUES (1)"))
        conn.execute(text("SELECT * FROM test"))

    assert len(analyzer.queries) >= 3
    queries = [q.query for q in analyzer.queries]
    assert any("CREATE TABLE" in q for q in queries)
    assert any("INSERT INTO" in q for q in queries)
    assert any("SELECT * FROM test" in q for q in queries)


def test_global_instance():
    """Validates global query_analyzer singleton."""
    assert isinstance(query_analyzer, QueryAnalyzer)
