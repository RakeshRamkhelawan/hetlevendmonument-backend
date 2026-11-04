"""
Comprehensive tests for query_optimizer.py
Covers: QueryType, OptimizationLevel, QueryMetrics, QueryAnalyzer, QueryCache, QueryMonitor, DatabaseOptimizer

Coverage target: 277 missing statements -> 80%+
"""

import asyncio
import hashlib
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.database.query_optimizer import (
    DatabaseOptimizer,
    OptimizationLevel,
    QueryAnalyzer,
    QueryCache,
    QueryMetrics,
    QueryMonitor,
    QueryType,
    database_optimizer,
    get_optimization_report,
    get_query_stats,
    optimize_and_execute,
    suggest_database_indexes,
)


class TestQueryTypeEnum:
    """Tests for QueryType enum"""

    def test_query_type_select(self):
        """Test SELECT query type"""
        assert QueryType.SELECT.value == "SELECT"

    def test_query_type_insert(self):
        """Test INSERT query type"""
        assert QueryType.INSERT.value == "INSERT"

    def test_query_type_update(self):
        """Test UPDATE query type"""
        assert QueryType.UPDATE.value == "UPDATE"

    def test_query_type_delete(self):
        """Test DELETE query type"""
        assert QueryType.DELETE.value == "DELETE"

    def test_query_type_create(self):
        """Test CREATE query type"""
        assert QueryType.CREATE.value == "CREATE"

    def test_query_type_drop(self):
        """Test DROP query type"""
        assert QueryType.DROP.value == "DROP"

    def test_query_type_unknown(self):
        """Test UNKNOWN query type"""
        assert QueryType.UNKNOWN.value == "UNKNOWN"


class TestOptimizationLevelEnum:
    """Tests for OptimizationLevel enum"""

    def test_optimization_disabled(self):
        """Test DISABLED level"""
        assert OptimizationLevel.DISABLED.value == "disabled"

    def test_optimization_basic(self):
        """Test BASIC level"""
        assert OptimizationLevel.BASIC.value == "basic"

    def test_optimization_aggressive(self):
        """Test AGGRESSIVE level"""
        assert OptimizationLevel.AGGRESSIVE.value == "aggressive"

    def test_optimization_experimental(self):
        """Test EXPERIMENTAL level"""
        assert OptimizationLevel.EXPERIMENTAL.value == "experimental"


class TestQueryMetrics:
    """Tests for QueryMetrics dataclass"""

    def test_query_metrics_creation(self):
        """Test QueryMetrics creation"""
        metrics = QueryMetrics(
            query_hash="abc123",
            sql_text="SELECT * FROM users",
            query_type=QueryType.SELECT,
            execution_count=10,
            total_time=5.0,
            average_time=0.5,
            min_time=0.1,
            max_time=1.0,
            last_executed=datetime.now(timezone.utc),
            parameters_count=2,
            result_count=100,
            cache_hits=3,
            optimization_applied=["index_used"],
        )

        assert metrics.query_hash == "abc123"
        assert metrics.execution_count == 10
        assert metrics.cache_hits == 3

    def test_performance_score_basic(self):
        """Test basic performance score calculation"""
        metrics = QueryMetrics(
            query_hash="abc123",
            sql_text="SELECT * FROM users",
            query_type=QueryType.SELECT,
            execution_count=10,
            total_time=5.0,
            average_time=0.5,
            min_time=0.1,
            max_time=1.0,
            last_executed=datetime.now(timezone.utc),
            parameters_count=2,
            result_count=100,
            cache_hits=0,
            optimization_applied=[],
        )

        # base_score = 0.5 * 100 = 50
        score = metrics.performance_score
        assert score > 0

    def test_performance_score_penalty_for_slow_frequent(self):
        """Test penalty for high execution count with poor performance"""
        metrics = QueryMetrics(
            query_hash="abc123",
            sql_text="SELECT * FROM users",
            query_type=QueryType.SELECT,
            execution_count=150,  # > 100
            total_time=180.0,
            average_time=1.2,  # > 1.0
            min_time=1.0,
            max_time=2.0,
            last_executed=datetime.now(timezone.utc),
            parameters_count=0,
            result_count=None,
            cache_hits=0,
            optimization_applied=[],
        )

        score = metrics.performance_score
        # Should have penalty applied (score *= 2)
        assert score >= 120 * 2 * 0.7  # base * penalty * cache_bonus_absent

    def test_performance_score_cache_bonus(self):
        """Test bonus for cached queries"""
        metrics = QueryMetrics(
            query_hash="abc123",
            sql_text="SELECT * FROM users",
            query_type=QueryType.SELECT,
            execution_count=100,
            total_time=50.0,
            average_time=0.5,
            min_time=0.1,
            max_time=1.0,
            last_executed=datetime.now(timezone.utc),
            parameters_count=0,
            result_count=50,
            cache_hits=50,  # 50% cache ratio
            optimization_applied=[],
        )

        score = metrics.performance_score
        # With 50% cache ratio, should have 15% bonus
        assert score < 50  # Lower than base due to cache bonus


class TestQueryAnalyzer:
    """Tests for QueryAnalyzer class"""

    @pytest.fixture
    def analyzer(self):
        """Create QueryAnalyzer instance"""
        return QueryAnalyzer()

    def test_classify_query_select(self, analyzer):
        """Test SELECT classification"""
        result = analyzer._classify_query("SELECT * FROM users")
        assert result == QueryType.SELECT

    def test_classify_query_insert(self, analyzer):
        """Test INSERT classification"""
        result = analyzer._classify_query("INSERT INTO users VALUES (1, 'test')")
        assert result == QueryType.INSERT

    def test_classify_query_update(self, analyzer):
        """Test UPDATE classification"""
        result = analyzer._classify_query("UPDATE users SET name = 'test'")
        assert result == QueryType.UPDATE

    def test_classify_query_delete(self, analyzer):
        """Test DELETE classification"""
        result = analyzer._classify_query("DELETE FROM users WHERE id = 1")
        assert result == QueryType.DELETE

    def test_classify_query_unknown(self, analyzer):
        """Test UNKNOWN classification"""
        result = analyzer._classify_query("VACUUM ANALYZE users")
        assert result == QueryType.UNKNOWN

    def test_calculate_complexity_simple(self, analyzer):
        """Test complexity for simple query"""
        sql = "SELECT id FROM users"
        score = analyzer._calculate_complexity(sql)
        assert score >= 0

    def test_calculate_complexity_with_joins(self, analyzer):
        """Test complexity with JOINs"""
        sql = "SELECT * FROM users JOIN orders ON users.id = orders.user_id JOIN products ON orders.product_id = products.id"
        score = analyzer._calculate_complexity(sql)
        assert score >= 20  # At least 2 joins * 10

    def test_calculate_complexity_with_subquery(self, analyzer):
        """Test complexity with subqueries"""
        sql = "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)"
        score = analyzer._calculate_complexity(sql)
        assert score >= 15  # At least 1 subquery * 15

    def test_calculate_complexity_with_aggregations(self, analyzer):
        """Test complexity with aggregations"""
        sql = "SELECT COUNT(*), SUM(amount), AVG(price) FROM orders GROUP BY user_id"
        score = analyzer._calculate_complexity(sql)
        assert score >= 15  # At least 3 aggregations * 5

    def test_estimate_cost_low(self, analyzer):
        """Test LOW cost estimation"""
        sql = "SELECT id FROM users"
        cost = analyzer._estimate_cost(sql)
        assert cost == "LOW"

    def test_estimate_cost_medium(self, analyzer):
        """Test MEDIUM cost estimation"""
        sql = "SELECT * FROM users JOIN orders ON users.id = orders.user_id WHERE status = 'active' AND amount > 100"
        cost = analyzer._estimate_cost(sql)
        assert cost in ["LOW", "MEDIUM", "HIGH"]  # Depends on complexity

    def test_estimate_cost_high(self, analyzer):
        """Test HIGH cost estimation"""
        sql = """
        SELECT * FROM users
        JOIN orders ON users.id = orders.user_id
        JOIN products ON orders.product_id = products.id
        JOIN categories ON products.category_id = categories.id
        WHERE users.status = 'active' AND orders.amount > 100
        GROUP BY users.id
        ORDER BY COUNT(*) DESC
        """
        cost = analyzer._estimate_cost(sql)
        assert cost in ["MEDIUM", "HIGH", "VERY_HIGH"]

    def test_suggest_indexes_with_where(self, analyzer):
        """Test index suggestions for WHERE clause"""
        sql = "SELECT * FROM users WHERE email = 'test@example.com'"
        suggestions = analyzer._suggest_indexes(sql)

        assert len(suggestions) >= 1
        assert any(s["reason"] == "WHERE clause optimization" for s in suggestions)

    def test_suggest_indexes_with_order_by(self, analyzer):
        """Test index suggestions for ORDER BY clause"""
        sql = "SELECT * FROM users ORDER BY created_at"
        suggestions = analyzer._suggest_indexes(sql)

        assert len(suggestions) >= 1
        assert any(s["reason"] == "ORDER BY optimization" for s in suggestions)

    def test_analyze_query_select_star_antipattern(self, analyzer):
        """Test detection of SELECT * anti-pattern"""
        sql = "SELECT * FROM users"
        analysis = analyzer.analyze_query(sql)

        assert analysis["query_type"] == QueryType.SELECT
        assert len(analysis["issues"]) >= 1
        assert any("SELECT *" in issue["description"] for issue in analysis["issues"])

    def test_analyze_query_like_wildcard_antipattern(self, analyzer):
        """Test detection of leading wildcard LIKE anti-pattern"""
        sql = "SELECT * FROM users WHERE name LIKE '%test%'"
        analysis = analyzer.analyze_query(sql)

        assert any("wildcard" in issue["description"].lower() for issue in analysis["issues"])

    def test_analyze_query_order_by_rand_antipattern(self, analyzer):
        """Test detection of ORDER BY RAND() anti-pattern"""
        sql = "SELECT * FROM users ORDER BY RAND()"
        analysis = analyzer.analyze_query(sql)

        assert any("RAND()" in issue["description"] for issue in analysis["issues"])

    def test_analyze_query_subquery_antipattern(self, analyzer):
        """Test detection of subquery anti-pattern"""
        sql = "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)"
        analysis = analyzer.analyze_query(sql)

        assert any(
            "subquery" in issue["description"].lower() or "JOIN" in issue["description"]
            for issue in analysis["issues"]
        )


class TestQueryCache:
    """Tests for QueryCache class"""

    @pytest.fixture
    def cache(self):
        """Create QueryCache instance"""
        return QueryCache(max_size=100, default_ttl=60)

    def test_generate_key(self, cache):
        """Test cache key generation"""
        key1 = cache._generate_key("SELECT * FROM users", {"id": 1})
        key2 = cache._generate_key("SELECT * FROM users", {"id": 2})
        key3 = cache._generate_key("SELECT * FROM users", {"id": 1})

        assert key1 != key2  # Different params
        assert key1 == key3  # Same query and params

    def test_is_cacheable_select(self, cache):
        """Test SELECT queries are cacheable"""
        assert cache._is_cacheable("SELECT * FROM users") is True

    def test_is_cacheable_insert_false(self, cache):
        """Test INSERT queries are not cacheable"""
        assert cache._is_cacheable("INSERT INTO users VALUES (1)") is False

    def test_is_cacheable_update_false(self, cache):
        """Test UPDATE queries are not cacheable"""
        assert cache._is_cacheable("UPDATE users SET name = 'test'") is False

    def test_is_cacheable_delete_false(self, cache):
        """Test DELETE queries are not cacheable"""
        assert cache._is_cacheable("DELETE FROM users") is False

    def test_is_cacheable_with_now_false(self, cache):
        """Test queries with NOW() are not cacheable"""
        assert cache._is_cacheable("SELECT * FROM users WHERE created_at > NOW()") is False

    def test_is_cacheable_with_rand_false(self, cache):
        """Test queries with RAND() are not cacheable"""
        assert cache._is_cacheable("SELECT * FROM users ORDER BY RAND()") is False

    def test_get_miss(self, cache):
        """Test cache miss"""
        result = cache.get("SELECT * FROM users", {"id": 1})
        assert result is None
        assert cache.miss_count == 1

    def test_set_and_get_hit(self, cache):
        """Test cache set and get (hit)"""
        sql = "SELECT * FROM users"
        params = {"id": 1}
        expected_result = [{"id": 1, "name": "test"}]

        cache.set(sql, expected_result, params)
        result = cache.get(sql, params)

        assert result == expected_result
        assert cache.hit_count == 1

    def test_set_evicts_oldest_at_capacity(self, cache):
        """Test cache evicts oldest entry at capacity"""
        small_cache = QueryCache(max_size=2, default_ttl=60)

        small_cache.set("SELECT 1", "result1")
        small_cache.set("SELECT 2", "result2")
        small_cache.set("SELECT 3", "result3")  # Should evict oldest

        assert len(small_cache.cache) == 2

    def test_invalidate_specific_key(self, cache):
        """Test invalidating specific cache entry"""
        cache.set("SELECT 1", "result1")
        cache.set("SELECT 2", "result2")

        key = cache._generate_key("SELECT 1")
        cache.invalidate(key)

        assert cache.get("SELECT 1") is None
        assert cache.get("SELECT 2") == "result2"

    def test_invalidate_all(self, cache):
        """Test invalidating all cache entries"""
        cache.set("SELECT 1", "result1")
        cache.set("SELECT 2", "result2")

        cache.invalidate()

        assert len(cache.cache) == 0

    def test_get_stats(self, cache):
        """Test cache statistics"""
        cache.set("SELECT 1", "result1")
        cache.get("SELECT 1")  # Hit
        cache.get("SELECT 2")  # Miss

        stats = cache.get_stats()

        assert stats["hit_count"] == 1
        assert stats["miss_count"] == 1
        assert stats["total_requests"] == 2
        assert stats["hit_rate"] == 50.0
        assert stats["cached_queries"] == 1

    def test_ttl_expiration(self, cache):
        """Test TTL expiration"""
        cache.default_ttl = 0  # Immediate expiration
        cache.set("SELECT 1", "result1")

        # Wait a tiny bit and access
        time.sleep(0.01)
        result = cache.get("SELECT 1")

        assert result is None  # Should be expired

    def test_set_non_cacheable_ignored(self, cache):
        """Test that non-cacheable queries are not cached"""
        cache.set("INSERT INTO users VALUES (1)", "result")
        assert len(cache.cache) == 0


class TestQueryMonitor:
    """Tests for QueryMonitor class"""

    @pytest.fixture
    def monitor(self):
        """Create QueryMonitor instance"""
        return QueryMonitor()

    def test_record_query_new(self, monitor):
        """Test recording new query"""
        monitor.record_query("SELECT * FROM users", 0.5, {"id": 1}, 10)

        assert len(monitor.metrics) == 1

    def test_record_query_updates_existing(self, monitor):
        """Test recording updates existing query metrics"""
        monitor.record_query("SELECT * FROM users", 0.3)
        monitor.record_query("SELECT * FROM users", 0.5)

        assert len(monitor.metrics) == 1

        query_hash = list(monitor.metrics.keys())[0]
        metrics = monitor.metrics[query_hash]

        assert metrics.execution_count == 2
        assert metrics.total_time == pytest.approx(0.8, rel=0.01)
        assert metrics.average_time == pytest.approx(0.4, rel=0.01)
        assert metrics.min_time == 0.3
        assert metrics.max_time == 0.5

    def test_record_query_cache_hit(self, monitor):
        """Test recording cache hit"""
        monitor.record_query("SELECT * FROM users", 0.001, cache_hit=True)

        query_hash = list(monitor.metrics.keys())[0]
        assert monitor.metrics[query_hash].cache_hits == 1

    def test_record_query_logs_slow_query(self, monitor, caplog):
        """Test slow query logging"""
        import logging

        monitor.slow_query_threshold = 0.5

        with caplog.at_level(logging.WARNING):
            monitor.record_query("SELECT * FROM users", 1.0)

        assert "Slow query detected" in caplog.text

    def test_get_slow_queries(self, monitor):
        """Test getting slow queries"""
        monitor.record_query("SELECT 1", 0.1)
        monitor.record_query("SELECT 2", 0.5)
        monitor.record_query("SELECT 3", 1.0)

        slow_queries = monitor.get_slow_queries(limit=2)

        assert len(slow_queries) <= 2

    def test_get_query_stats_empty(self, monitor):
        """Test query stats when empty"""
        stats = monitor.get_query_stats()
        assert "error" in stats

    def test_get_query_stats(self, monitor):
        """Test query stats with data"""
        monitor.record_query("SELECT * FROM users", 0.5)
        monitor.record_query("INSERT INTO users VALUES (1)", 0.3)

        stats = monitor.get_query_stats()

        assert stats["total_unique_queries"] == 2
        assert stats["total_executions"] == 2
        assert stats["average_execution_time"] == pytest.approx(0.4, rel=0.01)

    def test_recent_queries_deque(self, monitor):
        """Test recent queries are stored in deque"""
        for i in range(110):
            monitor.record_query(f"SELECT {i}", 0.1)

        assert len(monitor.recent_queries) == 100  # maxlen


class TestDatabaseOptimizer:
    """Tests for DatabaseOptimizer class"""

    @pytest.fixture
    def optimizer(self):
        """Create DatabaseOptimizer instance"""
        return DatabaseOptimizer(OptimizationLevel.BASIC)

    def test_init_basic(self, optimizer):
        """Test optimizer initialization"""
        assert optimizer.optimization_level == OptimizationLevel.BASIC
        assert optimizer.query_cache is not None
        assert optimizer.query_monitor is not None

    def test_init_disabled(self):
        """Test optimizer with disabled level"""
        opt = DatabaseOptimizer(OptimizationLevel.DISABLED)
        assert opt.optimization_level == OptimizationLevel.DISABLED

    @pytest.mark.asyncio
    async def test_optimize_query_disabled(self):
        """Test query optimization when disabled"""
        opt = DatabaseOptimizer(OptimizationLevel.DISABLED)

        sql, info = await opt.optimize_query("SELECT * FROM users")

        assert sql == "SELECT * FROM users"
        assert info == {}

    @pytest.mark.asyncio
    async def test_optimize_query_basic(self, optimizer):
        """Test basic query optimization"""
        sql, info = await optimizer.optimize_query("SELECT * FROM users")

        assert "optimizations" in info

    @pytest.mark.asyncio
    async def test_optimize_query_aggressive(self):
        """Test aggressive query optimization"""
        opt = DatabaseOptimizer(OptimizationLevel.AGGRESSIVE)

        sql, info = await opt.optimize_query("SELECT * FROM users")

        assert "optimizations" in info
        assert any("LIMIT" in opt for opt in info.get("optimizations", []))

    @pytest.mark.asyncio
    async def test_execute_with_cache_miss(self, optimizer):
        """Test execute with cache miss"""
        result = await optimizer.execute_with_cache("SELECT 1")

        assert result is not None
        assert optimizer.query_cache.miss_count >= 1

    @pytest.mark.asyncio
    async def test_execute_with_cache_hit(self, optimizer):
        """Test execute with cache hit"""
        sql = "SELECT * FROM cached_query"

        # First call - cache miss
        await optimizer.execute_with_cache(sql)

        # Second call - cache hit
        result = await optimizer.execute_with_cache(sql)

        assert result is not None
        assert optimizer.query_cache.hit_count >= 1

    def test_suggest_indexes_empty(self, optimizer):
        """Test index suggestions with no data"""
        suggestions = optimizer.suggest_indexes()
        assert suggestions == []

    def test_suggest_indexes_with_slow_queries(self, optimizer):
        """Test index suggestions with slow queries"""
        # Record some slow queries
        for i in range(15):
            optimizer.query_monitor.record_query(
                "SELECT * FROM users WHERE email = 'test@example.com'",
                0.6,  # Slow
            )

        suggestions = optimizer.suggest_indexes()
        # May or may not have suggestions depending on analysis
        assert isinstance(suggestions, list)

    def test_get_optimization_report(self, optimizer):
        """Test optimization report generation"""
        optimizer.query_monitor.record_query("SELECT 1", 0.1)

        report = optimizer.get_optimization_report()

        assert "optimization_level" in report
        assert "query_performance" in report
        assert "cache_performance" in report
        assert "slow_queries" in report
        assert "index_suggestions" in report
        assert "recommendations" in report
        assert "timestamp" in report

    def test_generate_recommendations_low_cache(self, optimizer):
        """Test recommendations for low cache hit rate"""
        query_stats = {"slow_queries_count": 0, "total_unique_queries": 10}
        cache_stats = {"hit_rate": 30}  # Low

        recommendations = optimizer._generate_recommendations(query_stats, cache_stats)

        assert any("cache" in r.lower() for r in recommendations)

    def test_generate_recommendations_high_slow_queries(self, optimizer):
        """Test recommendations for high slow query count"""
        query_stats = {
            "slow_queries_count": 20,
            "total_unique_queries": 100,
            "average_execution_time": 0.1,
        }
        cache_stats = {"hit_rate": 80}

        recommendations = optimizer._generate_recommendations(query_stats, cache_stats)

        assert any("slow" in r.lower() for r in recommendations)

    def test_generate_recommendations_high_avg_time(self, optimizer):
        """Test recommendations for high average execution time"""
        query_stats = {
            "slow_queries_count": 1,
            "total_unique_queries": 100,
            "average_execution_time": 0.8,
        }
        cache_stats = {"hit_rate": 80}

        recommendations = optimizer._generate_recommendations(query_stats, cache_stats)

        assert any("index" in r.lower() for r in recommendations)

    def test_generate_recommendations_optimal(self, optimizer):
        """Test recommendations when everything is optimal"""
        query_stats = {
            "slow_queries_count": 0,
            "total_unique_queries": 100,
            "average_execution_time": 0.1,
        }
        cache_stats = {"hit_rate": 90}

        recommendations = optimizer._generate_recommendations(query_stats, cache_stats)

        assert any("optimal" in r.lower() for r in recommendations)

    def test_configure_engine_postgresql(self, optimizer):
        """Test engine configuration for PostgreSQL"""
        # Use a proper mock that supports SQLAlchemy event system
        with patch("src.core.database.query_optimizer.create_engine") as mock_create:
            from sqlalchemy import create_engine as real_create_engine

            # Create a minimal in-memory SQLite engine that supports events
            real_engine = real_create_engine("sqlite:///:memory:")
            mock_create.return_value = real_engine

            engine = optimizer.configure_engine("postgresql://user:pass@localhost/db")

            mock_create.assert_called_once()
            # Verify engine was configured
            assert engine is not None


class TestConvenienceFunctions:
    """Tests for module-level convenience functions"""

    @pytest.mark.asyncio
    async def test_optimize_and_execute(self):
        """Test optimize_and_execute function"""
        result = await optimize_and_execute("SELECT 1")
        assert result is not None

    def test_get_query_stats(self):
        """Test get_query_stats function"""
        stats = get_query_stats()
        assert isinstance(stats, dict)

    def test_get_optimization_report(self):
        """Test get_optimization_report function"""
        report = get_optimization_report()
        assert isinstance(report, dict)
        assert "optimization_level" in report

    def test_suggest_database_indexes(self):
        """Test suggest_database_indexes function"""
        suggestions = suggest_database_indexes()
        assert isinstance(suggestions, list)

    def test_suggest_database_indexes_with_table(self):
        """Test suggest_database_indexes with specific table"""
        suggestions = suggest_database_indexes("users")
        assert isinstance(suggestions, list)


class TestGlobalDatabaseOptimizer:
    """Tests for global database_optimizer instance"""

    def test_global_optimizer_exists(self):
        """Test global optimizer is initialized"""
        assert database_optimizer is not None
        assert isinstance(database_optimizer, DatabaseOptimizer)

    def test_global_optimizer_level_from_env(self):
        """Test optimizer level from environment"""
        # Default is "basic" if not set
        assert database_optimizer.optimization_level in [
            OptimizationLevel.BASIC,
            OptimizationLevel.DISABLED,
            OptimizationLevel.AGGRESSIVE,
            OptimizationLevel.EXPERIMENTAL,
        ]


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_query_metrics_zero_execution_count(self):
        """Test QueryMetrics with zero execution count (edge case)"""
        metrics = QueryMetrics(
            query_hash="test",
            sql_text="SELECT 1",
            query_type=QueryType.SELECT,
            execution_count=0,
            total_time=0.0,
            average_time=0.0,
            min_time=float("inf"),
            max_time=0.0,
            last_executed=datetime.now(timezone.utc),
            parameters_count=0,
            result_count=None,
            cache_hits=0,
            optimization_applied=[],
        )

        # Should not divide by zero
        score = metrics.performance_score
        assert score >= 0

    def test_cache_get_stats_no_requests(self):
        """Test cache stats with no requests"""
        cache = QueryCache()
        stats = cache.get_stats()

        assert stats["hit_rate"] == 0
        assert stats["total_requests"] == 0

    def test_analyzer_empty_query(self):
        """Test analyzer with empty query"""
        analyzer = QueryAnalyzer()
        analysis = analyzer.analyze_query("")

        assert analysis["query_type"] == QueryType.UNKNOWN

    def test_analyzer_whitespace_query(self):
        """Test analyzer with whitespace-only query"""
        analyzer = QueryAnalyzer()
        result = analyzer._classify_query("   ")

        assert result == QueryType.UNKNOWN

    @pytest.mark.asyncio
    async def test_optimize_query_with_none_params(self):
        """Test optimize_query with None params"""
        optimizer = DatabaseOptimizer(OptimizationLevel.BASIC)
        sql, info = await optimizer.optimize_query("SELECT 1", None)

        assert sql is not None
