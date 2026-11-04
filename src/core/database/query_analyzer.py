"""
SD-11.1: Query Analysis Log
Logs and analyzes slow queries.
"""

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


@dataclass
class QueryLog:
    """Logged query information."""

    query: str
    params: dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
    duration_ms: float
    timestamp: str
    caller: str | None = None
    rows_affected: int | None = None
    is_slow: bool = False


class QueryAnalyzer:
    """
    SD-11.1: Logs and analyzes database queries.

    Features:
    - Log slow queries
    - Analyze query patterns
    - Identify N+1 queries
    - Export analytics
    """

    def __init__(
        self,
        slow_query_threshold_ms: float = 100,
        log_file: str | None = None,
        enable_logging: bool = True,
    ) -> None:
        self.slow_threshold = slow_query_threshold_ms
        self.enable_logging = enable_logging
        self.queries: list[QueryLog] = []

        self.log_file: str = log_file or os.getenv("QUERY_LOG_FILE") or "logs/query_analysis.jsonl"

        # Ensure log directory exists
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)

    def log_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        duration_ms: float = 0,
        caller: str | None = None,
        rows_affected: int | None = None,
    ) -> QueryLog:
        """Log a database query."""
        is_slow = duration_ms >= self.slow_threshold

        log_entry = QueryLog(
            query=self._normalize_query(query),
            params=params,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
            caller=caller,
            rows_affected=rows_affected,
            is_slow=is_slow,
        )

        self.queries.append(log_entry)

        if is_slow:
            logger.warning(f"Slow query ({duration_ms:.2f}ms): {query[:100]}...")

        if self.enable_logging:
            self._write_to_file(log_entry)

        return log_entry

    def _normalize_query(self, query: str) -> str:
        """Normalize query for comparison."""
        # Remove extra whitespace
        import re

        if query is None:
            return ""
        query = re.sub(r"\s+", " ", query.strip())
        return query

    def _write_to_file(self, log_entry: QueryLog) -> None:
        """Append log entry to file."""
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(asdict(log_entry)) + "\n")
        except Exception as e:
            logger.error(f"Failed to write query log: {e}")

    def get_slow_queries(self) -> list[QueryLog]:
        """Get all logged slow queries."""
        return [q for q in self.queries if q.is_slow]

    def get_query_stats(self) -> dict[str, int | float]:
        """Get query statistics."""
        if not self.queries:
            return {"total": 0}

        durations = [q.duration_ms for q in self.queries]
        slow_count = len(self.get_slow_queries())

        return {
            "total": len(self.queries),
            "slow_count": slow_count,
            "slow_percentage": (slow_count / len(self.queries)) * 100,
            "avg_duration_ms": sum(durations) / len(durations),
            "max_duration_ms": max(durations),
            "min_duration_ms": min(durations),
        }

    def detect_n_plus_one(self) -> list[dict[str, str | int]]:
        """Detect potential N+1 query patterns."""
        from collections import Counter

        # Count similar queries
        query_counts = Counter(q.query for q in self.queries)

        # Find queries that appear many times
        potential_n_plus_one: list[dict[str, str | int]] = []
        for query, count in query_counts.most_common(10):
            if count > 5:  # Threshold for N+1 detection
                potential_n_plus_one.append(
                    {
                        "query": query[:200],
                        "count": count,
                        "suggestion": "Consider using JOIN or batch fetching",
                    }
                )

        return potential_n_plus_one

    def export_analysis(self, output_file: str | None = None) -> str:
        """Export query analysis to file."""
        output_file = output_file or "logs/query_analysis_report.json"

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": self.get_query_stats(),
            "slow_queries": [asdict(q) for q in self.get_slow_queries()[:20]],
            "n_plus_one_candidates": self.detect_n_plus_one(),
        }

        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Query analysis exported to {output_file}")
        return output_file

    def clear(self) -> None:
        """Clear logged queries."""
        self.queries = []


# SQLAlchemy event listener for query logging
def setup_query_logging(engine: Engine, analyzer: QueryAnalyzer | None = None) -> QueryAnalyzer:
    """Set up SQLAlchemy event listeners for query logging."""
    from sqlalchemy import event

    analyzer = analyzer or QueryAnalyzer()

    @event.listens_for(engine, "before_cursor_execute")
    def before_execute(
        conn: Any, cursor: Any, statement: Any, parameters: Any, context: Any, executemany: Any  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        conn.info["query_start_time"] = time.time()

    @event.listens_for(engine, "after_cursor_execute")
    def after_execute(
        conn: Any, cursor: Any, statement: Any, parameters: Any, context: Any, executemany: Any  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        start_time = conn.info.get("query_start_time")
        if start_time:
            duration_ms = (time.time() - start_time) * 1000
            rowcount: int | None = cursor.rowcount if hasattr(cursor, "rowcount") else None
            analyzer.log_query(
                query=statement,
                params=parameters if isinstance(parameters, dict) else None,
                duration_ms=duration_ms,
                rows_affected=rowcount,
            )

    return analyzer


# Global analyzer instance
query_analyzer = QueryAnalyzer()
