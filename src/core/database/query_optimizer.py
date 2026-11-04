"""
Database Query Optimizer for Sanskriti Setu
Advanced query optimization, indexing, and performance monitoring
"""

import asyncio
import hashlib
import logging
import os
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

# Setup logging
logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Query type classification"""

    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CREATE = "CREATE"
    DROP = "DROP"
    UNKNOWN = "UNKNOWN"


class OptimizationLevel(Enum):
    """Query optimization levels"""

    DISABLED = "disabled"
    BASIC = "basic"
    AGGRESSIVE = "aggressive"
    EXPERIMENTAL = "experimental"


@dataclass
class QueryMetrics:
    """Query performance metrics"""

    query_hash: str
    sql_text: str
    query_type: QueryType
    execution_count: int
    total_time: float
    average_time: float
    min_time: float
    max_time: float
    last_executed: datetime
    parameters_count: int
    result_count: int | None
    cache_hits: int
    optimization_applied: list[str]

    @property
    def performance_score(self) -> float:
        """Calculate performance score (lower is better)"""
        base_score = self.average_time * 100

        # Penalty for high execution count with poor performance
        if self.execution_count > 100 and self.average_time > 1.0:
            base_score *= 2

        # Bonus for cached queries
        cache_ratio = self.cache_hits / max(self.execution_count, 1)
        base_score *= 1 - cache_ratio * 0.3

        return base_score


class QueryAnalyzer:
    """Advanced SQL query analyzer"""

    def __init__(self) -> None:
        self.slow_query_patterns = [
            (r"SELECT \* FROM", "Avoid SELECT * - specify columns"),
            (r"WHERE.*LIKE.*%.*%", "Leading wildcard LIKE prevents index usage"),
            (r"ORDER BY.*RAND\(\)", "ORDER BY RAND() is inefficient for large tables"),
            (r"WHERE.*!=|<>", "Use positive conditions when possible"),
            (r"SELECT.*\(SELECT.*\)", "Consider JOINs instead of subqueries"),
            (r"WHERE.*OR.*OR", "Multiple ORs can be slow - consider UNION"),
        ]

        self.index_suggestions = {
            "WHERE": "Consider adding index on WHERE clause columns",
            "ORDER BY": "Consider adding index on ORDER BY columns",
            "GROUP BY": "Consider adding index on GROUP BY columns",
            "JOIN": "Consider adding index on JOIN columns",
        }

    def analyze_query(
        self, sql: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze SQL query for optimization opportunities"""
        analysis: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "query_type": self._classify_query(sql),
            "issues": [],
            "suggestions": [],
            "complexity_score": self._calculate_complexity(sql),
            "estimated_cost": self._estimate_cost(sql),
        }

        # Check for common anti-patterns
        for pattern, suggestion in self.slow_query_patterns:
            if re.search(pattern, sql, re.IGNORECASE):
                analysis["issues"].append(
                    {
                        "type": "anti_pattern",
                        "description": suggestion,
                        "pattern": pattern,
                    }
                )

        # Suggest indexes
        index_suggestions = self._suggest_indexes(sql)
        analysis["suggestions"].extend(index_suggestions)

        return analysis

    def _classify_query(self, sql: str) -> QueryType:
        """Classify query type"""
        sql_upper = sql.strip().upper()
        for query_type in QueryType:
            if sql_upper.startswith(query_type.value):
                return query_type
        return QueryType.UNKNOWN

    def _calculate_complexity(self, sql: str) -> int:
        """Calculate query complexity score"""
        score = 0

        # Count joins
        join_count = len(re.findall(r"\bJOIN\b", sql, re.IGNORECASE))
        score += join_count * 10

        # Count subqueries
        subquery_count = len(re.findall(r"\(SELECT", sql, re.IGNORECASE))
        score += subquery_count * 15

        # Count aggregations
        agg_count = len(re.findall(r"\b(COUNT|SUM|AVG|MAX|MIN|GROUP BY)\b", sql, re.IGNORECASE))
        score += agg_count * 5

        # Count conditions
        condition_count = len(re.findall(r"\b(WHERE|AND|OR)\b", sql, re.IGNORECASE))
        score += condition_count * 2

        return score

    def _estimate_cost(self, sql: str) -> str:
        """Estimate query execution cost"""
        complexity = self._calculate_complexity(sql)

        if complexity < 20:
            return "LOW"
        elif complexity < 50:
            return "MEDIUM"
        elif complexity < 100:
            return "HIGH"
        else:
            return "VERY_HIGH"

    def _suggest_indexes(self, sql: str) -> list[dict[str, str | list[str]]]:
        """Suggest database indexes based on query"""
        suggestions: list[dict[str, str | list[str]]] = []
        # Extract table and column information
        tables = re.findall(r"FROM\s+(\w+)", sql, re.IGNORECASE)
        where_columns = re.findall(r"WHERE\s+.*?(\w+)\s*[=<>]", sql, re.IGNORECASE)
        order_columns = re.findall(r"ORDER BY\s+(\w+)", sql, re.IGNORECASE)
        re.findall(r"GROUP BY\s+(\w+)", sql, re.IGNORECASE)

        for table in tables:
            if where_columns:
                suggestions.append(
                    {
                        "type": "index",
                        "table": table,
                        "columns": where_columns[:3],  # Limit to 3 columns
                        "reason": "WHERE clause optimization",
                    }
                )

            if order_columns:
                suggestions.append(
                    {
                        "type": "index",
                        "table": table,
                        "columns": order_columns,
                        "reason": "ORDER BY optimization",
                    }
                )

        return suggestions


class QueryCache:
    """Intelligent query result cache"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300) -> None:
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.access_times: dict[str, datetime] = {}
        self.hit_count = 0
        self.miss_count = 0

    def _generate_key(
        self, sql: str, params: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Generate cache key for query"""
        key_data = sql + str(sorted((params or {}).items()))
        return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()

    def _is_cacheable(self, sql: str) -> bool:
        """Check if query should be cached"""
        # Don't cache mutations
        if re.match(r"^\s*(INSERT|UPDATE|DELETE|CREATE|DROP)", sql, re.IGNORECASE):
            return False

        # Don't cache queries with time-sensitive functions
        time_functions = ["NOW()", "CURRENT_TIMESTAMP", "RAND()", "RANDOM()"]
        if any(func in sql.upper() for func in time_functions):
            return False

        return True

    def get(
        self, sql: str, params: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Get cached query result"""
        if not self._is_cacheable(sql):
            return None

        cache_key = self._generate_key(sql, params)

        if cache_key in self.cache:
            # Check TTL
            if cache_key in self.access_times:
                age = (datetime.now(timezone.utc) - self.access_times[cache_key]).total_seconds()
                if age > self.default_ttl:
                    self.invalidate(cache_key)
                    self.miss_count += 1
                    return None

            self.access_times[cache_key] = datetime.now(timezone.utc)
            self.hit_count += 1
            return self.cache[cache_key]

        self.miss_count += 1
        return None

    def set(
        self,
        sql: str,
        result: Any,  # TODO(TYPE): replace Any with concrete type
        params: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        ttl: int | None = None,
    ) -> None:
        """Cache query result"""
        if not self._is_cacheable(sql):
            return

        cache_key = self._generate_key(sql, params)

        # Evict oldest if at capacity
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
            self.invalidate(oldest_key)

        self.cache[cache_key] = result
        self.access_times[cache_key] = datetime.now(timezone.utc)

    def invalidate(self, cache_key: str | None = None) -> None:
        """Invalidate cache entry or all cache"""
        if cache_key:
            self.cache.pop(cache_key, None)
            self.access_times.pop(cache_key, None)
        else:
            self.cache.clear()
            self.access_times.clear()

    def get_stats(self) -> dict[str, int | float]:
        """Get cache statistics"""
        total_requests = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total_requests * 100) if total_requests > 0 else 0

        return {
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "total_requests": total_requests,
            "hit_rate": round(hit_rate, 2),
            "cached_queries": len(self.cache),
            "max_size": self.max_size,
        }


class QueryMonitor:
    """Query performance monitoring"""

    def __init__(self) -> None:
        self.metrics: dict[str, QueryMetrics] = {}
        self.slow_query_threshold = 1.0  # seconds
        self.recent_queries: deque[dict[str, Any]] = deque(  # TODO(TYPE): replace Any with concrete type
            maxlen=100
        )  # TODO(TYPE): replace Any with concrete type
        self.analyzer = QueryAnalyzer()

    def record_query(
        self,
        sql: str,
        execution_time: float,
        params: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        result_count: int | None = None,
        cache_hit: bool = False,
    ) -> None:
        """Record query execution metrics"""
        query_hash = hashlib.md5(sql.encode(), usedforsecurity=False).hexdigest()

        if query_hash not in self.metrics:
            self.metrics[query_hash] = QueryMetrics(
                query_hash=query_hash,
                sql_text=sql,
                query_type=self.analyzer._classify_query(sql),
                execution_count=0,
                total_time=0.0,
                average_time=0.0,
                min_time=float("inf"),
                max_time=0.0,
                last_executed=datetime.now(timezone.utc),
                parameters_count=len(params) if params else 0,
                result_count=result_count,
                cache_hits=0,
                optimization_applied=[],
            )

        metrics = self.metrics[query_hash]
        metrics.execution_count += 1
        metrics.total_time += execution_time
        metrics.average_time = metrics.total_time / metrics.execution_count
        metrics.min_time = min(metrics.min_time, execution_time)
        metrics.max_time = max(metrics.max_time, execution_time)
        metrics.last_executed = datetime.now(timezone.utc)

        if cache_hit:
            metrics.cache_hits += 1

        if result_count is not None:
            metrics.result_count = result_count

        # Record recent query
        self.recent_queries.append(
            {
                "sql": sql,
                "execution_time": execution_time,
                "timestamp": datetime.now(timezone.utc),
                "cache_hit": cache_hit,
            }
        )

        # Log slow queries
        if execution_time > self.slow_query_threshold:
            logger.warning(f"Slow query detected: {execution_time:.2f}s - {sql[:100]}...")

    def get_slow_queries(
        self, limit: int = 10
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get slowest queries"""
        sorted_metrics = sorted(
            self.metrics.values(), key=lambda m: m.performance_score, reverse=True
        )

        return [
            {
                "sql": m.sql_text,
                "average_time": m.average_time,
                "execution_count": m.execution_count,
                "performance_score": m.performance_score,
                "analysis": self.analyzer.analyze_query(m.sql_text),
            }
            for m in sorted_metrics[:limit]
        ]

    def get_query_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive query statistics"""
        if not self.metrics:
            return {"error": "No query data available"}

        total_queries = sum(m.execution_count for m in self.metrics.values())
        total_time = sum(m.total_time for m in self.metrics.values())
        avg_time = total_time / total_queries if total_queries > 0 else 0

        slow_queries = len(
            [m for m in self.metrics.values() if m.average_time > self.slow_query_threshold]
        )

        query_types: dict[str, int] = defaultdict(int)
        for metrics in self.metrics.values():
            query_types[metrics.query_type.value] += metrics.execution_count

        return {
            "total_unique_queries": len(self.metrics),
            "total_executions": total_queries,
            "average_execution_time": round(avg_time, 4),
            "slow_queries_count": slow_queries,
            "query_types": dict(query_types),
            "recent_queries": len(self.recent_queries),
        }


class DatabaseOptimizer:
    """Main database optimization system"""

    def __init__(self, optimization_level: OptimizationLevel = OptimizationLevel.BASIC) -> None:
        self.optimization_level = optimization_level
        self.query_cache = QueryCache()
        self.query_monitor = QueryMonitor()
        self.analyzer = QueryAnalyzer()
        self.connection_pool_size = 20
        self.max_overflow = 10

        logger.info(f"Database optimizer initialized with level: {optimization_level.value}")

    def configure_engine(self, database_url: str) -> Engine:
        """Configure optimized database engine"""
        engine_kwargs = {
            "poolclass": QueuePool,
            "pool_size": self.connection_pool_size,
            "max_overflow": self.max_overflow,
            "pool_pre_ping": True,
            "pool_recycle": 3600,  # Recycle connections every hour
            "echo": False,  # Set to True for SQL logging
        }

        if database_url.startswith("postgresql"):
            engine_kwargs.update(
                {
                    "connect_args": {
                        "server_settings": {
                            "jit": "off",  # Disable JIT for consistent performance
                            "shared_preload_libraries": "pg_stat_statements",
                        }
                    }
                }
            )

        engine = create_engine(database_url, **engine_kwargs)

        # Add query monitoring event listeners
        @event.listens_for(engine, "before_cursor_execute")
        def before_cursor_execute(
            conn: Any,  # TODO(TYPE): replace Any with concrete type
            cursor: Any,  # TODO(TYPE): replace Any with concrete type
            statement: Any,  # TODO(TYPE): replace Any with concrete type
            parameters: Any,  # TODO(TYPE): replace Any with concrete type
            context: Any,  # TODO(TYPE): replace Any with concrete type
            executemany: Any,  # TODO(TYPE): replace Any with concrete type
        ) -> None:
            context._query_start_time = time.time()

        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(
            conn: Any,  # TODO(TYPE): replace Any with concrete type
            cursor: Any,  # TODO(TYPE): replace Any with concrete type
            statement: Any,  # TODO(TYPE): replace Any with concrete type
            parameters: Any,  # TODO(TYPE): replace Any with concrete type
            context: Any,  # TODO(TYPE): replace Any with concrete type
            executemany: Any,  # TODO(TYPE): replace Any with concrete type
        ) -> None:
            if hasattr(context, "_query_start_time"):
                execution_time = time.time() - context._query_start_time
                self.query_monitor.record_query(
                    statement,
                    execution_time,
                    parameters if isinstance(parameters, dict) else {},
                )

        return engine

    async def optimize_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[str, dict[str, list[str]]]:
        """Apply query optimizations"""
        if self.optimization_level == OptimizationLevel.DISABLED:
            return sql, params or {}

        optimized_sql = sql
        optimization_log: list[str] = []
        if self.optimization_level in [
            OptimizationLevel.BASIC,
            OptimizationLevel.AGGRESSIVE,
        ]:
            # Basic optimizations
            if re.search(r"SELECT \* FROM", sql, re.IGNORECASE):
                # This would require knowledge of table schema in real implementation
                optimization_log.append("Recommend replacing SELECT * with specific columns")

            # Remove redundant conditions
            optimized_sql = re.sub(r"\s+", " ", optimized_sql.strip())

        if self.optimization_level == OptimizationLevel.AGGRESSIVE:
            # Aggressive optimizations
            # Add LIMIT if missing for potentially large result sets
            if (
                "SELECT" in sql.upper()
                and "LIMIT" not in sql.upper()
                and "COUNT" not in sql.upper()
            ):
                if not params or "limit" not in params:
                    optimization_log.append("Consider adding LIMIT for large result sets")

        return optimized_sql, {"optimizations": optimization_log}  # dict[str, list[str]]

    async def execute_with_cache(
        self, sql: str, params: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Execute query with intelligent caching"""
        # Check cache first
        cached_result = self.query_cache.get(sql, params)
        if cached_result is not None:
            self.query_monitor.record_query(
                sql, 0.001, params, cache_hit=True
            )  # Very fast cache hit
            return cached_result

        # Execute query (this would be actual database execution in real implementation)
        start_time = time.time()

        # Mock execution for demonstration
        await asyncio.sleep(0.1)  # Simulate query execution
        result = {"mock_result": "query_executed", "params": params}

        execution_time = time.time() - start_time

        # Cache result
        self.query_cache.set(sql, result, params)

        # Record metrics
        self.query_monitor.record_query(
            sql, execution_time, params, len(result) if isinstance(result, list) else 1
        )

        return result

    def suggest_indexes(
        self, table_name: str | None = None
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Suggest database indexes based on query patterns"""
        suggestions: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        for metrics in self.query_monitor.metrics.values():
            if (
                metrics.execution_count > 10 and metrics.average_time > 0.5
            ):  # Frequently executed slow queries
                analysis = self.analyzer.analyze_query(metrics.sql_text)
                for suggestion in analysis.get("suggestions", []):
                    if suggestion["type"] == "index":
                        if table_name is None or suggestion.get("table") == table_name:
                            suggestions.append(
                                {
                                    **suggestion,
                                    "query_frequency": metrics.execution_count,
                                    "avg_time": metrics.average_time,
                                    "priority": min(metrics.performance_score / 10, 10),
                                }
                            )

        # Sort by priority
        return sorted(suggestions, key=lambda x: x.get("priority", 0), reverse=True)

    def get_optimization_report(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate comprehensive optimization report"""
        query_stats = self.query_monitor.get_query_stats()
        cache_stats = self.query_cache.get_stats()
        slow_queries = self.query_monitor.get_slow_queries(5)
        index_suggestions = self.suggest_indexes()

        return {
            "optimization_level": self.optimization_level.value,
            "query_performance": query_stats,
            "cache_performance": cache_stats,
            "slow_queries": slow_queries,
            "index_suggestions": index_suggestions[:10],  # Top 10 suggestions
            "recommendations": self._generate_recommendations(query_stats, cache_stats),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _generate_recommendations(
        self,
        query_stats: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        cache_stats: dict[str, int | float],
    ) -> list[str]:
        """Generate optimization recommendations"""
        recommendations: list[str] = []
        if cache_stats.get("hit_rate", 0) < 50:
            recommendations.append(
                "Consider increasing cache size or TTL - low cache hit rate detected"
            )

        if (
            query_stats.get("slow_queries_count", 0)
            > query_stats.get("total_unique_queries", 1) * 0.1
        ):
            recommendations.append(
                "High number of slow queries - review and optimize frequent queries"
            )

        if query_stats.get("average_execution_time", 0) > 0.5:
            recommendations.append("Average query time is high - consider adding indexes")

        if len(recommendations) == 0:
            recommendations.append("Database performance is optimal")

        return recommendations


# Global database optimizer
database_optimizer = DatabaseOptimizer(
    OptimizationLevel(os.getenv("DB_OPTIMIZATION_LEVEL", "basic"))
)


# Convenience functions
async def optimize_and_execute(
    sql: str, params: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Optimize and execute query"""
    optimized_sql, opt_info = await database_optimizer.optimize_query(sql, params)
    return await database_optimizer.execute_with_cache(optimized_sql, params)


def get_query_stats() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get query performance statistics"""
    return database_optimizer.query_monitor.get_query_stats()


def get_optimization_report() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get comprehensive optimization report"""
    return database_optimizer.get_optimization_report()


def suggest_database_indexes(
    table_name: str | None = None,
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Get index suggestions"""
    return database_optimizer.suggest_indexes(table_name)
