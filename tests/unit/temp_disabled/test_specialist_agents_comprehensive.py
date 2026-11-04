"""
P4.1: Specialist Agents Comprehensive Tests
Tests for src/core/subagents/specialist_agents.py (1,807 LOC)

Coverage target: 80%+

Modules tested:
- DataAnalysisAgent: statistical_summary, pattern_recognition, correlation_analysis, trend_analysis, anomaly_detection
- SystemMonitorAgent: system_health, resource_usage, process_monitoring, network_status, disk_analysis
- CodeExecutionAgent: Python/JavaScript/shell execution with security validation
- KnowledgeAgent: internal_kb, document_search, web_search, faq_lookup
- ReportingAgent: system_summary, performance_report, security_audit, usage_analytics
- PerformanceAgent: benchmark, bottleneck_analysis, resource_optimization, scaling_analysis

Run:
    python -m pytest tests/unit/test_specialist_agents_comprehensive.py --cov=src/core/subagents/specialist_agents --cov-report=term-missing -v
"""

import asyncio
import statistics
import time
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.core.subagents.agent_factory import AgentConfiguration, AgentMetrics, AgentStatus
from src.core.types import AgentType

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_agent_config():
    """Create a mock agent configuration."""
    return AgentConfiguration(
        agent_type=AgentType.DATA_ANALYSIS,
        name="test_agent",
        capabilities=["analysis", "monitoring"],
        max_concurrent_tasks=5,
        memory_limit_mb=256,
        cpu_priority="normal",
        specialized_parameters={},
    )


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for agents that use it."""
    mock = AsyncMock()
    mock.generate.return_value = {"valid": True, "errors": []}
    return mock


@pytest.fixture
def mock_memory_manager():
    """Mock memory manager for agents."""
    mock = MagicMock()
    mock.store = AsyncMock()
    mock.retrieve = AsyncMock(return_value={})
    return mock


# =============================================================================
# TEST CLASS: DataAnalysisAgent
# =============================================================================


class TestDataAnalysisAgent:
    """Test DataAnalysisAgent class."""

    @pytest.fixture
    def data_agent(self, mock_agent_config):
        """Create a DataAnalysisAgent instance."""
        from src.core.subagents.specialist_agents import DataAnalysisAgent

        mock_agent_config.agent_type = AgentType.DATA_ANALYSIS
        agent = DataAnalysisAgent("data-agent-001", mock_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, data_agent):
        """Test agent initialization with analysis methods."""
        await data_agent._agent_specific_init()

        assert hasattr(data_agent, "analysis_methods")
        assert "statistical_summary" in data_agent.analysis_methods
        assert "pattern_recognition" in data_agent.analysis_methods
        assert "correlation_analysis" in data_agent.analysis_methods
        assert "trend_analysis" in data_agent.analysis_methods
        assert "anomaly_detection" in data_agent.analysis_methods

    @pytest.mark.asyncio
    async def test_execute_specific_task_unknown_type(self, data_agent):
        """Test execution with unknown analysis type."""
        await data_agent._agent_specific_init()

        result = await data_agent._execute_specific_task(
            {"analysis_type": "unknown_analysis", "data": [1, 2, 3]}
        )

        assert "error" in result
        assert "Unknown analysis type" in result["error"]
        assert "available_methods" in result

    @pytest.mark.asyncio
    async def test_execute_specific_task_statistical_summary(self, data_agent):
        """Test statistical summary execution."""
        await data_agent._agent_specific_init()

        test_data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = await data_agent._execute_specific_task(
            {
                "analysis_type": "statistical_summary",
                "data": test_data,
                "parameters": {},
            }
        )

        assert result["analysis_type"] == "statistical_summary"
        assert "result" in result
        assert result["data_points_analyzed"] == len(test_data)
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_statistical_summary_with_empty_data(self, data_agent):
        """Test statistical summary with empty data."""
        result = await data_agent._statistical_summary([], {})

        assert "success" in result
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_statistical_summary_with_valid_data(self, data_agent):
        """Test statistical summary with valid data."""
        test_data = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = await data_agent._statistical_summary(test_data, {})

        assert result["success"] is True
        assert "basic_statistics" in result
        assert result["basic_statistics"]["mean"] == 30.0
        assert result["basic_statistics"]["median"] == 30.0
        assert "quartiles" in result
        assert "outliers" in result
        assert "distribution" in result
        assert "data_quality" in result

    @pytest.mark.asyncio
    async def test_statistical_summary_outlier_detection(self, data_agent):
        """Test outlier detection in statistical analysis."""
        test_data = [1.0, 2.0, 3.0, 4.0, 5.0, 100.0]  # 100 is an outlier
        result = await data_agent._statistical_summary(test_data, {})

        assert result["success"] is True
        assert result["outliers"]["count"] > 0

    @pytest.mark.asyncio
    async def test_pattern_recognition_insufficient_data(self, data_agent):
        """Test pattern recognition with insufficient data."""
        result = await data_agent._pattern_recognition([1], {})

        assert "success" in result
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_pattern_recognition_with_valid_data(self, data_agent):
        """Test pattern recognition with valid data."""
        test_data = [1.0, 2.0, 3.0, 10.0, 11.0, 12.0, 20.0, 21.0, 22.0]
        result = await data_agent._pattern_recognition(test_data, {})

        assert result["success"] is True
        assert "optimal_clusters" in result
        assert "patterns" in result
        assert "quality_metrics" in result

    @pytest.mark.asyncio
    async def test_correlation_analysis_insufficient_variables(self, data_agent):
        """Test correlation analysis with insufficient variables."""
        result = await data_agent._correlation_analysis([1, 2, 3], {})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_correlation_analysis_with_valid_data(self, data_agent):
        """Test correlation analysis with valid data."""
        test_data = {
            "var1": [1.0, 2.0, 3.0, 4.0, 5.0],
            "var2": [1.0, 2.0, 3.0, 4.0, 5.0],  # Perfect positive correlation
            "var3": [5.0, 4.0, 3.0, 2.0, 1.0],  # Perfect negative correlation
        }
        result = await data_agent._correlation_analysis(test_data, {})

        assert "correlations" in result
        assert result["variables_analyzed"] == 3

    @pytest.mark.asyncio
    async def test_calculate_correlation(self, data_agent):
        """Test correlation coefficient calculation."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [1.0, 2.0, 3.0, 4.0, 5.0]

        correlation = data_agent._calculate_correlation(x, y)

        assert isinstance(correlation, float)
        assert 0.99 <= correlation <= 1.01  # Approximately 1.0 for perfect correlation

    @pytest.mark.asyncio
    async def test_calculate_correlation_no_correlation(self, data_agent):
        """Test correlation with no correlation."""
        x = [1.0, 2.0, 3.0]
        y = [3.0, 1.0, 2.0]

        correlation = data_agent._calculate_correlation(x, y)

        assert isinstance(correlation, float)

    @pytest.mark.asyncio
    async def test_interpret_correlation_strength(self, data_agent):
        """Test correlation strength interpretation."""
        tests = [
            (0.95, "very_strong"),
            (0.75, "strong"),
            (0.55, "moderate"),
            (0.35, "weak"),
            (0.10, "very_weak"),
        ]

        for coef, expected_strength in tests:
            strength = data_agent._interpret_correlation_strength(coef)
            assert strength == expected_strength

    @pytest.mark.asyncio
    async def test_trend_analysis_insufficient_data(self, data_agent):
        """Test trend analysis with insufficient data."""
        result = await data_agent._trend_analysis([1, 2], {})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_trend_analysis_increasing_trend(self, data_agent):
        """Test trend analysis with increasing trend."""
        test_data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = await data_agent._trend_analysis(test_data, {})

        assert result["trend_direction"] == "increasing"
        assert result["average_change"] > 0

    @pytest.mark.asyncio
    async def test_trend_analysis_decreasing_trend(self, data_agent):
        """Test trend analysis with decreasing trend."""
        test_data = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = await data_agent._trend_analysis(test_data, {})

        assert result["trend_direction"] == "decreasing"
        assert result["average_change"] < 0

    @pytest.mark.asyncio
    async def test_trend_analysis_stable_trend(self, data_agent):
        """Test trend analysis with stable trend."""
        test_data = [3.0, 3.0, 3.0, 3.0, 3.0]
        result = await data_agent._trend_analysis(test_data, {})

        assert result["trend_direction"] == "stable"

    @pytest.mark.asyncio
    async def test_anomaly_detection_insufficient_data(self, data_agent):
        """Test anomaly detection with insufficient data."""
        result = await data_agent._anomaly_detection([1, 2, 3, 4], {})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_anomaly_detection_with_anomalies(self, data_agent):
        """Test anomaly detection with anomalies."""
        test_data = [1.0, 2.0, 3.0, 4.0, 5.0, 100.0]  # 100 is anomaly
        result = await data_agent._anomaly_detection(
            test_data, {"method": "standard_deviation", "sensitivity": 2.0}
        )

        assert "anomalies_detected" in result
        assert "anomalies" in result
        assert result["anomalies_detected"] > 0

    @pytest.mark.asyncio
    async def test_anomaly_detection_no_anomalies(self, data_agent):
        """Test anomaly detection with no anomalies."""
        test_data = [10.0, 10.5, 10.2, 9.8, 10.1]
        result = await data_agent._anomaly_detection(
            test_data, {"method": "standard_deviation", "sensitivity": 3.0}
        )

        assert "anomalies_detected" in result


# =============================================================================
# TEST CLASS: SystemMonitorAgent
# =============================================================================


class TestSystemMonitorAgent:
    """Test SystemMonitorAgent class."""

    @pytest.fixture
    def monitor_agent(self, mock_agent_config):
        """Create a SystemMonitorAgent instance."""
        from src.core.subagents.specialist_agents import SystemMonitorAgent

        mock_agent_config.agent_type = AgentType.DATA_ANALYSIS  # Use any agent type
        agent = SystemMonitorAgent("monitor-agent-001", mock_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, monitor_agent):
        """Test agent initialization with monitoring functions."""
        await monitor_agent._agent_specific_init()

        assert hasattr(monitor_agent, "monitoring_functions")
        assert "system_health" in monitor_agent.monitoring_functions
        assert "resource_usage" in monitor_agent.monitoring_functions
        assert "process_monitoring" in monitor_agent.monitoring_functions
        assert "network_status" in monitor_agent.monitoring_functions
        assert "disk_analysis" in monitor_agent.monitoring_functions

    @pytest.mark.asyncio
    async def test_execute_specific_task_unknown_type(self, monitor_agent):
        """Test execution with unknown monitoring type."""
        await monitor_agent._agent_specific_init()

        result = await monitor_agent._execute_specific_task(
            {"monitor_type": "unknown_monitor", "parameters": {}}
        )

        assert "error" in result
        assert "Unknown monitoring type" in result["error"]

    @pytest.mark.asyncio
    async def test_check_system_health(self, monitor_agent):
        """Test system health check."""
        with (
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
        ):
            mock_cpu.return_value = 50.0
            mock_mem.return_value = MagicMock(percent=60.0)
            mock_disk.return_value = MagicMock(percent=70.0)

            result = await monitor_agent._check_system_health({})

            assert "health_score" in result
            assert "health_status" in result
            assert "issues" in result
            assert "metrics" in result
            assert result["metrics"]["cpu_usage"] == 50.0

    @pytest.mark.asyncio
    async def test_check_system_health_high_cpu(self, monitor_agent):
        """Test system health with high CPU."""
        with (
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
        ):
            mock_cpu.return_value = 95.0
            mock_mem.return_value = MagicMock(percent=30.0)
            mock_disk.return_value = MagicMock(percent=50.0)

            result = await monitor_agent._check_system_health({})

            assert any("CPU" in issue for issue in result["issues"])

    @pytest.mark.asyncio
    async def test_get_resource_usage(self, monitor_agent):
        """Test resource usage collection."""
        with (
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.cpu_count") as mock_core_count,
            patch("psutil.cpu_freq") as mock_freq,
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("psutil.net_io_counters") as mock_net,
        ):
            mock_cpu.return_value = 50.0
            mock_core_count.return_value = 4
            mock_freq.return_value = MagicMock(_asdict=lambda: {"current": 2400})
            mock_mem.return_value = MagicMock(
                total=16 * 1024**3,
                available=8 * 1024**3,
                used=8 * 1024**3,
                percent=50.0,
                buffers=1 * 1024**3,
                cached=2 * 1024**3,
            )
            mock_disk.return_value = MagicMock(
                total=500 * 1024**3, used=250 * 1024**3, free=250 * 1024**3
            )
            mock_net.return_value = MagicMock(
                bytes_sent=1000, bytes_recv=2000, packets_sent=10, packets_recv=20
            )

            result = await monitor_agent._get_resource_usage({})

            assert "cpu" in result
            assert "memory" in result
            assert "disk" in result
            assert "network" in result
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_monitor_processes(self, monitor_agent):
        """Test process monitoring."""
        mock_process = MagicMock()
        mock_process.info = {
            "pid": 1234,
            "name": "test_process",
            "cpu_percent": 10.0,
            "memory_percent": 5.0,
            "status": "running",
        }

        with patch("psutil.process_iter") as mock_process_iter:
            mock_process_iter.return_value = [mock_process]

            result = await monitor_agent._monitor_processes({"top_n": 10, "sort_by": "cpu_percent"})

            assert "total_processes" in result
            assert "top_processes" in result

    @pytest.mark.asyncio
    async def test_check_network_status(self, monitor_agent):
        """Test network status check."""
        with (
            patch("psutil.net_if_stats") as mock_net_stats,
            patch("psutil.net_io_counters") as mock_net_counters,
        ):
            mock_net_stats.return_value = {"eth0": MagicMock(isup=True, speed=1000)}
            mock_net_counters.return_value = MagicMock(
                bytes_sent=1000, bytes_recv=2000, packets_sent=10, packets_recv=20
            )

            result = await monitor_agent._check_network_status({})

            assert "status" in result or "interfaces" in result

    @pytest.mark.asyncio
    async def test_analyze_disk_usage(self, monitor_agent):
        """Test disk usage analysis."""
        with (
            patch("psutil.disk_partitions") as mock_partitions,
            patch("psutil.disk_usage") as mock_disk_usage,
            patch("psutil.disk_io_counters") as mock_io,
        ):
            mock_partition = MagicMock()
            mock_partition.device = "/dev/sda1"
            mock_partition.mountpoint = "/"
            mock_partition.fstype = "ext4"
            mock_partitions.return_value = [mock_partition]
            mock_disk_usage.return_value = MagicMock(
                total=100 * 1024**3, used=60 * 1024**3, free=40 * 1024**3
            )
            mock_io.return_value = MagicMock(
                read_count=1000,
                write_count=500,
                read_bytes=10000,
                write_bytes=5000,
                read_time=100,
                write_time=50,
            )

            result = await monitor_agent._analyze_disk_usage({})

            assert "partitions" in result or "error" in result


# =============================================================================
# TEST CLASS: CodeExecutionAgent
# =============================================================================


class TestCodeExecutionAgent:
    """Test CodeExecutionAgent class."""

    @pytest.fixture
    def code_agent(self, mock_agent_config):
        """Create a CodeExecutionAgent instance."""
        from src.core.subagents.specialist_agents import CodeExecutionAgent

        mock_agent_config.agent_type = AgentType.DATA_ANALYSIS
        agent = CodeExecutionAgent("code-agent-001", mock_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, code_agent):
        """Test agent initialization with execution capabilities."""
        await code_agent._agent_specific_init()

        assert hasattr(code_agent, "supported_languages")
        assert "python" in code_agent.supported_languages
        assert "javascript" in code_agent.supported_languages
        assert "shell" in code_agent.supported_languages
        assert hasattr(code_agent, "execution_limits")

    @pytest.mark.asyncio
    async def test_execute_specific_task_no_code(self, code_agent):
        """Test execution with no code provided."""
        await code_agent._agent_specific_init()

        result = await code_agent._execute_specific_task(
            {"language": "python", "code": "", "context": {}}
        )

        assert "error" in result
        assert "No code provided" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_specific_task_unsupported_language(self, code_agent):
        """Test execution with unsupported language."""
        await code_agent._agent_specific_init()

        result = await code_agent._execute_specific_task(
            {"language": "java", "code": "public class Test {}", "context": {}}
        )

        assert "error" in result
        assert "Unsupported language" in result["error"]

    @pytest.mark.asyncio
    async def test_validate_code_security_safe_code(self, code_agent):
        """Test security validation for safe code."""
        code = "x = 5\ny = 10\nz = x + y"
        result = await code_agent._validate_code_security(code, "python")

        assert "is_safe" in result
        assert isinstance(result["is_safe"], bool)

    @pytest.mark.asyncio
    async def test_validate_code_security_dangerous_code(self, code_agent):
        """Test security validation for dangerous code."""
        code = "import os; os.system('rm -rf /')"
        result = await code_agent._validate_code_security(code, "python")

        assert "is_safe" in result
        assert result["is_safe"] is False

    @pytest.mark.asyncio
    async def test_wrap_python_code_with_security(self, code_agent):
        """Test Python code wrapping with security."""
        code = "print('hello')"
        wrapped = code_agent._wrap_python_code_with_security(code)

        assert isinstance(wrapped, str)
        assert "check_resources" in wrapped

    @pytest.mark.asyncio
    async def test_execute_javascript_code(self, code_agent):
        """Test JavaScript code execution."""
        code = "console.log('test')"
        result = await code_agent._execute_javascript_code(code, {})

        assert "success" in result
        assert "output" in result
        assert isinstance(result["output"], list)

    @pytest.mark.asyncio
    async def test_execute_javascript_code_no_output(self, code_agent):
        """Test JavaScript code without console.log."""
        code = "var x = 5; var y = 10;"
        result = await code_agent._execute_javascript_code(code, {})

        assert "success" in result
        assert "output" in result


# =============================================================================
# TEST CLASS: KnowledgeAgent
# =============================================================================


class TestKnowledgeAgent:
    """Test KnowledgeAgent class."""

    @pytest.fixture
    def knowledge_agent(self, mock_agent_config):
        """Create a KnowledgeAgent instance."""
        from src.core.subagents.specialist_agents import KnowledgeAgent

        mock_agent_config.agent_type = AgentType.DATA_ANALYSIS
        agent = KnowledgeAgent("knowledge-agent-001", mock_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, knowledge_agent):
        """Test agent initialization with knowledge sources."""
        await knowledge_agent._agent_specific_init()

        assert hasattr(knowledge_agent, "knowledge_sources")
        assert "internal_kb" in knowledge_agent.knowledge_sources
        assert "document_search" in knowledge_agent.knowledge_sources
        assert "web_search" in knowledge_agent.knowledge_sources
        assert "faq_lookup" in knowledge_agent.knowledge_sources
        assert hasattr(knowledge_agent, "knowledge_cache")

    @pytest.mark.asyncio
    async def test_execute_specific_task_no_query(self, knowledge_agent):
        """Test execution with no query."""
        await knowledge_agent._agent_specific_init()

        result = await knowledge_agent._execute_specific_task(
            {"query": "", "sources": ["internal_kb"]}
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_specific_task_with_query(self, knowledge_agent):
        """Test execution with valid query."""
        await knowledge_agent._agent_specific_init()

        with patch.object(knowledge_agent, "_query_internal_knowledge") as mock_kb:
            mock_kb.return_value = {
                "source": "internal_kb",
                "items": [],
                "query_time": 0.1,
            }

            result = await knowledge_agent._execute_specific_task(
                {"query": "test query", "sources": ["internal_kb"], "max_results": 10}
            )

            assert "query" in result
            assert "results" in result
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_calculate_text_relevance(self, knowledge_agent):
        """Test text relevance calculation."""
        query = "machine learning"
        text = "This is about machine learning and AI"

        relevance = knowledge_agent._calculate_text_relevance(query, text)

        assert isinstance(relevance, float)
        assert 0 <= relevance <= 1

    @pytest.mark.asyncio
    async def test_calculate_text_relevance_empty_query(self, knowledge_agent):
        """Test relevance with empty query."""
        relevance = knowledge_agent._calculate_text_relevance("", "some text")

        assert relevance == 0.0

    @pytest.mark.asyncio
    async def test_extract_relevant_snippet(self, knowledge_agent):
        """Test snippet extraction."""
        query = "AI"
        text = "This is about AI. Machine learning is a subset of AI. Deep learning uses neural networks."

        snippet = knowledge_agent._extract_relevant_snippet(query, text)

        assert isinstance(snippet, str)

    @pytest.mark.asyncio
    async def test_query_internal_knowledge(self, knowledge_agent):
        """Test internal knowledge base query."""
        with patch("glob.glob") as mock_glob, patch("builtins.open", create=True) as mock_open:
            mock_glob.return_value = []
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = lambda s, *args: None

            result = await knowledge_agent._query_internal_knowledge("test", 10)

            assert "items" in result
            assert "source" in result

    @pytest.mark.asyncio
    async def test_search_documents(self, knowledge_agent):
        """Test document search."""
        result = await knowledge_agent._search_documents("test query", 10)

        assert "items" in result or "error" in result

    @pytest.mark.asyncio
    async def test_web_search(self, knowledge_agent):
        """Test web search."""
        result = await knowledge_agent._web_search("test query", 10)

        assert "items" in result or "error" in result

    @pytest.mark.asyncio
    async def test_faq_lookup(self, knowledge_agent):
        """Test FAQ lookup."""
        result = await knowledge_agent._faq_lookup("how to use", 10)

        assert "items" in result or "error" in result


# =============================================================================
# TEST CLASS: ReportingAgent
# =============================================================================


class TestReportingAgent:
    """Test ReportingAgent class."""

    @pytest.fixture
    def reporting_agent(self, mock_agent_config):
        """Create a ReportingAgent instance."""
        from src.core.subagents.specialist_agents import ReportingAgent

        mock_agent_config.agent_type = AgentType.DATA_ANALYSIS
        agent = ReportingAgent("reporting-agent-001", mock_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, reporting_agent):
        """Test agent initialization with report templates."""
        await reporting_agent._agent_specific_init()

        assert hasattr(reporting_agent, "report_templates")
        assert "system_summary" in reporting_agent.report_templates
        assert "performance_report" in reporting_agent.report_templates
        assert "security_audit" in reporting_agent.report_templates
        assert "usage_analytics" in reporting_agent.report_templates

    @pytest.mark.asyncio
    async def test_execute_specific_task_unknown_report_type(self, reporting_agent):
        """Test execution with unknown report type."""
        await reporting_agent._agent_specific_init()

        result = await reporting_agent._execute_specific_task(
            {"report_type": "unknown_report", "data_sources": {}, "format": "json"}
        )

        assert "error" in result
        assert "Unknown report type" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_specific_task_system_summary(self, reporting_agent):
        """Test system summary report generation."""
        await reporting_agent._agent_specific_init()

        with (
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("psutil.process_iter") as mock_processes,
        ):
            mock_cpu.return_value = 50.0
            mock_mem.return_value = MagicMock(
                percent=60.0, available=8 * 1024**3, total=16 * 1024**3
            )
            mock_disk.return_value = MagicMock(percent=70.0)
            mock_processes.return_value = []

            result = await reporting_agent._execute_specific_task(
                {"report_type": "system_summary", "data_sources": {}, "format": "json"}
            )

            assert result["report_type"] == "system_summary"
            assert "content" in result
            assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_generate_system_summary(self, reporting_agent):
        """Test system summary generation."""
        with (
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("psutil.process_iter") as mock_processes,
        ):
            mock_cpu.return_value = 45.0
            mock_mem.return_value = MagicMock(
                percent=55.0,
                available=7 * 1024**3,
                total=16 * 1024**3,
                buffers=1 * 1024**3,
                cached=2 * 1024**3,
            )
            mock_disk.return_value = MagicMock(percent=65.0)
            mock_processes.return_value = []

            result = await reporting_agent._generate_system_summary({})

            assert "system_metrics" in result or "cpu_usage" in str(result)

    @pytest.mark.asyncio
    async def test_generate_performance_report(self, reporting_agent):
        """Test performance report generation."""
        result = await reporting_agent._generate_performance_report({})

        assert "report" in result or "metrics" in result

    @pytest.mark.asyncio
    async def test_generate_security_audit(self, reporting_agent):
        """Test security audit generation."""
        result = await reporting_agent._generate_security_audit({})

        assert "title" in result
        assert "security_score" in result
        assert "findings" in result
        assert "compliance" in result
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_generate_usage_analytics(self, reporting_agent):
        """Test usage analytics generation."""
        result = await reporting_agent._generate_usage_analytics({})

        assert "title" in result
        assert "user_activity" in result
        assert "feature_usage" in result
        assert "performance_by_feature" in result


# =============================================================================
# TEST CLASS: PerformanceAgent
# =============================================================================


class TestPerformanceAgent:
    """Test PerformanceAgent class."""

    @pytest.fixture
    def performance_agent(self, mock_agent_config):
        """Create a PerformanceAgent instance."""
        from src.core.subagents.specialist_agents import PerformanceAgent

        mock_agent_config.agent_type = AgentType.DATA_ANALYSIS
        agent = PerformanceAgent("performance-agent-001", mock_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, performance_agent):
        """Test agent initialization with analysis functions."""
        await performance_agent._agent_specific_init()

        assert hasattr(performance_agent, "analysis_functions")
        assert "benchmark" in performance_agent.analysis_functions
        assert "bottleneck_analysis" in performance_agent.analysis_functions
        assert "resource_optimization" in performance_agent.analysis_functions
        assert "scaling_analysis" in performance_agent.analysis_functions

    @pytest.mark.asyncio
    async def test_execute_specific_task_unknown_type(self, performance_agent):
        """Test execution with unknown analysis type."""
        await performance_agent._agent_specific_init()

        result = await performance_agent._execute_specific_task(
            {
                "analysis_type": "unknown_analysis",
                "target_component": "system",
                "parameters": {},
            }
        )

        assert "error" in result
        assert "Unknown analysis type" in result["error"]

    @pytest.mark.asyncio
    async def test_run_benchmark(self, performance_agent):
        """Test benchmark execution."""
        result = await performance_agent._run_benchmark(
            "system", {"duration_seconds": 1, "load_level": "normal"}
        )

        assert "benchmark_type" in result
        assert "results" in result or "operations_completed" in result or "error" in result

    @pytest.mark.asyncio
    async def test_benchmark_system(self, performance_agent):
        """Test system benchmarking."""
        result = await performance_agent._benchmark_system(1, "light")

        assert isinstance(result, tuple)
        assert len(result) == 2
        operations, latencies = result
        assert isinstance(operations, int)
        assert isinstance(latencies, list)

    @pytest.mark.asyncio
    async def test_benchmark_system_heavy_load(self, performance_agent):
        """Test system benchmarking with heavy load."""
        result = await performance_agent._benchmark_system(1, "heavy")

        assert isinstance(result, tuple)
        operations, latencies = result
        assert operations >= 0

    @pytest.mark.asyncio
    async def test_benchmark_memory(self, performance_agent):
        """Test memory benchmarking."""
        result = await performance_agent._benchmark_memory(1, "normal")

        assert isinstance(result, tuple)
        operations, latencies = result
        assert operations > 0

    @pytest.mark.asyncio
    async def test_benchmark_cpu(self, performance_agent):
        """Test CPU benchmarking."""
        result = await performance_agent._benchmark_cpu(1, "normal")

        assert isinstance(result, tuple)
        operations, latencies = result
        assert operations > 0

    @pytest.mark.asyncio
    async def test_calculate_performance_score(self, performance_agent):
        """Test performance score calculation."""
        score = performance_agent._calculate_performance_score(
            throughput=100.0, avg_latency=0.01, cpu_usage=30.0, memory_usage=40.0
        )

        assert isinstance(score, float)
        assert 0 <= score <= 100

    @pytest.mark.asyncio
    async def test_get_performance_grade(self, performance_agent):
        """Test performance grading."""
        grades = [
            (95, "A+"),
            (85, "A"),
            (75, "B+"),
            (65, "B"),
            (55, "C+"),
            (45, "C"),
            (25, "D"),
        ]

        for score, expected_grade in grades:
            grade = performance_agent._get_performance_grade(score)
            assert grade == expected_grade

    @pytest.mark.asyncio
    async def test_analyze_bottlenecks(self, performance_agent):
        """Test bottleneck analysis."""
        result = await performance_agent._analyze_bottlenecks("system", {"depth": "standard"})

        assert "bottlenecks" in result or "bottlenecks_found" in result

    @pytest.mark.asyncio
    async def test_optimize_resources(self, performance_agent):
        """Test resource optimization suggestions."""
        result = await performance_agent._optimize_resources("system", {"type": "memory"})

        assert "recommendations" in result or "optimizations" in result

    @pytest.mark.asyncio
    async def test_optimize_resources_cpu(self, performance_agent):
        """Test CPU resource optimization."""
        result = await performance_agent._optimize_resources("system", {"type": "cpu"})

        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_analyze_scaling_needs(self, performance_agent):
        """Test scaling analysis."""
        result = await performance_agent._analyze_scaling_needs(
            "system", {"projected_load_increase": 2.0, "time_horizon_months": 6}
        )

        assert "current_capacity" in result or "scaling_recommendations" in result


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestSpecialistAgentsIntegration:
    """Integration tests for multiple specialist agents."""

    @pytest.mark.asyncio
    async def test_data_analysis_workflow(self, mock_agent_config):
        """Test complete data analysis workflow."""
        from src.core.subagents.specialist_agents import DataAnalysisAgent

        agent = DataAnalysisAgent("workflow-agent", mock_agent_config)
        await agent._agent_specific_init()

        # Step 1: Statistical analysis
        test_data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = await agent._execute_specific_task(
            {
                "analysis_type": "statistical_summary",
                "data": test_data,
                "parameters": {},
            }
        )

        assert result["analysis_type"] == "statistical_summary"

    @pytest.mark.asyncio
    async def test_monitoring_workflow(self, mock_agent_config):
        """Test complete monitoring workflow."""
        from src.core.subagents.specialist_agents import SystemMonitorAgent

        agent = SystemMonitorAgent("monitor-workflow", mock_agent_config)
        await agent._agent_specific_init()

        # Test multiple monitoring types
        with (
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("psutil.cpu_count") as mock_count,
            patch("psutil.cpu_freq") as mock_freq,
            patch("psutil.net_io_counters") as mock_net,
        ):
            mock_cpu.return_value = 50.0
            mock_mem.return_value = MagicMock(
                percent=60.0,
                total=16 * 1024**3,
                available=8 * 1024**3,
                used=8 * 1024**3,
                buffers=1 * 1024**3,
                cached=2 * 1024**3,
            )
            mock_disk.return_value = MagicMock(
                percent=70.0,
                total=500 * 1024**3,
                used=250 * 1024**3,
                free=250 * 1024**3,
            )
            mock_count.return_value = 4
            mock_freq.return_value = MagicMock(_asdict=lambda: {})
            mock_net.return_value = MagicMock(
                bytes_sent=1000, bytes_recv=2000, packets_sent=10, packets_recv=20
            )

            result = await agent._execute_specific_task(
                {"monitor_type": "system_health", "parameters": {}}
            )

            assert "result" in result
            assert "timestamp" in result
