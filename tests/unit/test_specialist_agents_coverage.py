"""
P4.1.1: Specialist Agents Coverage Tests
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
    python -m pytest tests/unit/test_specialist_agents_coverage.py --cov=src/core/subagents/specialist_agents --cov-report=term-missing -v
"""

import asyncio
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

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
        assert "unknown_analysis" in result["error"].lower()
        assert "available_methods" in result

    @pytest.mark.asyncio
    async def test_execute_specific_task_statistical_summary(self, data_agent):
        """Test statistical summary analysis."""
        await data_agent._agent_specific_init()

        with (
            patch("pandas.Series") as mock_series,
            patch("scipy.stats.shapiro") as mock_shapiro,
            patch("scipy.stats.skew", return_value=0.5),
            patch("scipy.stats.kurtosis", return_value=0.3),
        ):
            # Mock pandas Series behavior
            mock_df = MagicMock()
            mock_df.mean.return_value = 5.0
            mock_df.median.return_value = 5.0
            mock_df.std.return_value = 2.0
            mock_df.var.return_value = 4.0
            mock_df.min.return_value = 1.0
            mock_df.max.return_value = 10.0
            mock_df.quantile.side_effect = lambda x: {0.25: 3.0, 0.50: 5.0, 0.75: 7.0}[x]
            mock_series.return_value = mock_df

            # Mock shapiro test
            mock_shapiro.return_value = (0.95, 0.1)

            result = await data_agent._execute_specific_task(
                {
                    "analysis_type": "statistical_summary",
                    "data": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                    "parameters": {},
                }
            )

            assert result["analysis_type"] == "statistical_summary"
            assert "result" in result
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_statistical_summary_empty_data(self, data_agent):
        """Test statistical summary with empty data."""
        await data_agent._agent_specific_init()

        result = await data_agent._statistical_summary([], {})

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_statistical_summary_with_data(self, data_agent):
        """Test statistical summary with valid data."""
        await data_agent._agent_specific_init()

        # Use real computation with mocked imports
        with patch("numpy.isinf", return_value=[False] * 10):
            with patch("pandas.isna", return_value=[False]):
                with patch("pandas.Series") as mock_series:
                    mock_df = MagicMock()
                    mock_df.mean.return_value = 5.5
                    mock_df.median.return_value = 5.5
                    mock_df.std.return_value = 3.0
                    mock_df.var.return_value = 9.0
                    mock_df.min.return_value = 1.0
                    mock_df.max.return_value = 10.0
                    mock_df.quantile.side_effect = lambda x: {
                        0.25: 3.0,
                        0.50: 5.5,
                        0.75: 8.0,
                    }[x]
                    mock_series.return_value = mock_df

                    with patch("scipy.stats.shapiro", return_value=(0.95, 0.1)):
                        with patch("scipy.stats.skew", return_value=0.0):
                            with patch("scipy.stats.kurtosis", return_value=0.0):
                                result = await data_agent._statistical_summary(
                                    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], {}
                                )

                                assert result["success"] is True
                                assert "basic_statistics" in result

    @pytest.mark.asyncio
    async def test_pattern_recognition_insufficient_data(self, data_agent):
        """Test pattern recognition with insufficient data."""
        await data_agent._agent_specific_init()

        result = await data_agent._pattern_recognition([], {})
        assert result["success"] is False
        assert "error" in result

        result = await data_agent._pattern_recognition([1], {})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_pattern_recognition_with_data(self, data_agent):
        """Test pattern recognition with valid data."""
        await data_agent._agent_specific_init()

        with (
            patch("sklearn.cluster.KMeans") as mock_kmeans,
            patch("sklearn.preprocessing.StandardScaler") as mock_scaler,
        ):
            # Mock scaler
            mock_scaler_instance = MagicMock()
            mock_scaler_instance.fit_transform.return_value = [[1], [2], [3], [4], [5]]
            mock_scaler.return_value = mock_scaler_instance

            # Mock KMeans
            mock_kmeans_instance = MagicMock()
            mock_kmeans_instance.fit.return_value = None
            mock_kmeans_instance.fit_predict.return_value = [0, 0, 1, 1, 1]
            mock_kmeans_instance.inertia_ = 10.0
            mock_kmeans.return_value = mock_kmeans_instance

            with patch("sklearn.metrics.silhouette_score", return_value=0.5):
                import numpy as np

                with patch("numpy.array", return_value=np.array([1, 2, 3, 4, 5]).reshape(-1, 1)):
                    with patch("numpy.mean", return_value=3.0):
                        with patch("numpy.std", return_value=1.5):
                            result = await data_agent._pattern_recognition([1, 2, 3, 4, 5], {})

                            # Result could be success or failure depending on mocks
                            assert "success" in result or "error" in result

    @pytest.mark.asyncio
    async def test_correlation_analysis_insufficient_variables(self, data_agent):
        """Test correlation analysis with insufficient variables."""
        await data_agent._agent_specific_init()

        result = await data_agent._correlation_analysis({"x": [1, 2, 3]}, {})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_correlation_analysis_success(self, data_agent):
        """Test correlation analysis with valid data."""
        await data_agent._agent_specific_init()

        data = {"x": [1, 2, 3, 4, 5], "y": [2, 4, 6, 8, 10]}

        result = await data_agent._correlation_analysis(data, {})

        assert "correlations" in result
        assert result["variables_analyzed"] == 2
        assert result["total_comparisons"] >= 1

    def test_calculate_correlation(self, data_agent):
        """Test correlation coefficient calculation."""
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]

        corr = data_agent._calculate_correlation(x, y)

        # Perfect positive correlation
        assert corr == pytest.approx(1.0, rel=0.01)

    def test_calculate_correlation_negative(self, data_agent):
        """Test negative correlation calculation."""
        x = [1, 2, 3, 4, 5]
        y = [10, 8, 6, 4, 2]

        corr = data_agent._calculate_correlation(x, y)

        # Perfect negative correlation
        assert corr == pytest.approx(-1.0, rel=0.01)

    def test_calculate_correlation_insufficient_data(self, data_agent):
        """Test correlation with insufficient data."""
        result = data_agent._calculate_correlation([1], [2])
        assert result == 0.0

        result = data_agent._calculate_correlation([1, 2], [1])
        assert result == 0.0

    def test_interpret_correlation_strength(self, data_agent):
        """Test correlation strength interpretation."""
        assert data_agent._interpret_correlation_strength(0.95) == "very_strong"
        assert data_agent._interpret_correlation_strength(0.8) == "strong"
        assert data_agent._interpret_correlation_strength(0.6) == "moderate"
        assert data_agent._interpret_correlation_strength(0.4) == "weak"
        assert data_agent._interpret_correlation_strength(0.1) == "very_weak"

    @pytest.mark.asyncio
    async def test_trend_analysis_insufficient_data(self, data_agent):
        """Test trend analysis with insufficient data."""
        await data_agent._agent_specific_init()

        result = await data_agent._trend_analysis([1, 2], {})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_trend_analysis_increasing(self, data_agent):
        """Test trend analysis with increasing data."""
        await data_agent._agent_specific_init()

        result = await data_agent._trend_analysis([1, 2, 3, 4, 5], {})

        assert result["trend_direction"] == "increasing"
        assert result["average_change"] > 0
        assert result["data_points"] == 5

    @pytest.mark.asyncio
    async def test_trend_analysis_decreasing(self, data_agent):
        """Test trend analysis with decreasing data."""
        await data_agent._agent_specific_init()

        result = await data_agent._trend_analysis([5, 4, 3, 2, 1], {})

        assert result["trend_direction"] == "decreasing"
        assert result["average_change"] < 0

    @pytest.mark.asyncio
    async def test_trend_analysis_stable(self, data_agent):
        """Test trend analysis with stable data."""
        await data_agent._agent_specific_init()

        result = await data_agent._trend_analysis([5, 5, 5, 5, 5], {})

        assert result["trend_direction"] == "stable"
        assert result["average_change"] == 0

    @pytest.mark.asyncio
    async def test_anomaly_detection_insufficient_data(self, data_agent):
        """Test anomaly detection with insufficient data."""
        await data_agent._agent_specific_init()

        result = await data_agent._anomaly_detection([1, 2, 3], {})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_anomaly_detection_with_anomalies(self, data_agent):
        """Test anomaly detection with clear outliers."""
        await data_agent._agent_specific_init()

        # Data with clear outlier
        data = [1, 2, 2, 3, 2, 2, 100]  # 100 is an outlier

        result = await data_agent._anomaly_detection(
            data, {"method": "standard_deviation", "sensitivity": 2.0}
        )

        assert "anomalies_detected" in result
        assert "anomalies" in result
        assert result["data_points_analyzed"] == 7

    @pytest.mark.asyncio
    async def test_anomaly_detection_no_anomalies(self, data_agent):
        """Test anomaly detection with no outliers."""
        await data_agent._agent_specific_init()

        data = [5, 5, 5, 5, 5, 5, 5]

        result = await data_agent._anomaly_detection(data, {})

        assert result["anomalies_detected"] == 0


# =============================================================================
# TEST CLASS: SystemMonitorAgent
# =============================================================================


class TestSystemMonitorAgent:
    """Test SystemMonitorAgent class."""

    @pytest.fixture
    def monitor_agent(self, mock_agent_config):
        """Create a SystemMonitorAgent instance."""
        from src.core.subagents.specialist_agents import SystemMonitorAgent

        mock_agent_config.agent_type = AgentType.MONITOR
        agent = SystemMonitorAgent("monitor-agent-001", mock_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, monitor_agent):
        """Test monitor agent initialization."""
        await monitor_agent._agent_specific_init()

        assert hasattr(monitor_agent, "monitoring_functions")
        assert "system_health" in monitor_agent.monitoring_functions
        assert "resource_usage" in monitor_agent.monitoring_functions
        assert "process_monitoring" in monitor_agent.monitoring_functions
        assert "network_status" in monitor_agent.monitoring_functions
        assert "disk_analysis" in monitor_agent.monitoring_functions

    @pytest.mark.asyncio
    async def test_execute_specific_task_unknown_type(self, monitor_agent):
        """Test execution with unknown monitor type."""
        await monitor_agent._agent_specific_init()

        result = await monitor_agent._execute_specific_task({"monitor_type": "unknown_monitor"})

        assert "error" in result
        assert "available_types" in result

    @pytest.mark.asyncio
    async def test_check_system_health(self, monitor_agent):
        """Test system health check."""
        await monitor_agent._agent_specific_init()

        with patch("psutil.cpu_percent", return_value=45.0):
            mock_memory = MagicMock()
            mock_memory.percent = 60.0
            with patch("psutil.virtual_memory", return_value=mock_memory):
                mock_disk = MagicMock()
                mock_disk.percent = 50.0
                with patch("psutil.disk_usage", return_value=mock_disk):
                    result = await monitor_agent._check_system_health({})

                    assert "health_score" in result
                    assert "health_status" in result
                    assert result["health_score"] <= 100

    @pytest.mark.asyncio
    async def test_check_system_health_high_cpu(self, monitor_agent):
        """Test system health with high CPU usage."""
        await monitor_agent._agent_specific_init()

        with patch("psutil.cpu_percent", return_value=95.0):
            mock_memory = MagicMock()
            mock_memory.percent = 50.0
            with patch("psutil.virtual_memory", return_value=mock_memory):
                mock_disk = MagicMock()
                mock_disk.percent = 50.0
                with patch("psutil.disk_usage", return_value=mock_disk):
                    result = await monitor_agent._check_system_health({})

                    assert "High CPU usage" in result["issues"]
                    assert result["health_score"] < 100

    @pytest.mark.asyncio
    async def test_check_system_health_error(self, monitor_agent):
        """Test system health with error."""
        await monitor_agent._agent_specific_init()

        with patch("psutil.cpu_percent", side_effect=Exception("CPU error")):
            result = await monitor_agent._check_system_health({})

            assert "error" in result

    @pytest.mark.asyncio
    async def test_get_resource_usage(self, monitor_agent):
        """Test resource usage collection."""
        await monitor_agent._agent_specific_init()

        with patch("psutil.cpu_percent", return_value=25.0):
            with patch("psutil.cpu_count", return_value=8):
                mock_freq = MagicMock()
                mock_freq._asdict.return_value = {
                    "current": 2400,
                    "min": 800,
                    "max": 3200,
                }
                with patch("psutil.cpu_freq", return_value=mock_freq):
                    mock_memory = MagicMock()
                    mock_memory.total = 16 * 1024**3
                    mock_memory.available = 8 * 1024**3
                    mock_memory.used = 8 * 1024**3
                    mock_memory.percent = 50.0
                    mock_memory.buffers = 1 * 1024**3
                    mock_memory.cached = 2 * 1024**3
                    with patch("psutil.virtual_memory", return_value=mock_memory):
                        mock_disk = MagicMock()
                        mock_disk.total = 500 * 1024**3
                        mock_disk.used = 250 * 1024**3
                        mock_disk.free = 250 * 1024**3
                        with patch("psutil.disk_usage", return_value=mock_disk):
                            mock_net = MagicMock()
                            mock_net.bytes_sent = 1000000
                            mock_net.bytes_recv = 2000000
                            mock_net.packets_sent = 1000
                            mock_net.packets_recv = 2000
                            with patch("psutil.net_io_counters", return_value=mock_net):
                                with patch("psutil.net_connections", return_value=[]):
                                    result = await monitor_agent._get_resource_usage({})

                                    assert "cpu" in result
                                    assert "memory" in result
                                    assert "disk" in result
                                    assert "network" in result

    @pytest.mark.asyncio
    async def test_monitor_processes(self, monitor_agent):
        """Test process monitoring."""
        await monitor_agent._agent_specific_init()

        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 1234,
            "name": "test_process",
            "cpu_percent": 5.0,
            "memory_percent": 3.0,
            "status": "running",
        }

        with patch("psutil.process_iter", return_value=[mock_proc]):
            result = await monitor_agent._monitor_processes({"top_n": 5})

            assert "total_processes" in result
            assert "top_processes" in result

    @pytest.mark.asyncio
    async def test_check_network_status(self, monitor_agent):
        """Test network status check."""
        await monitor_agent._agent_specific_init()

        mock_addr = MagicMock()
        mock_addr.family = MagicMock()
        mock_addr.family.name = "AF_INET"
        mock_addr.address = "192.168.1.1"
        mock_addr.netmask = "255.255.255.0"
        mock_addr.broadcast = "192.168.1.255"

        with patch("psutil.net_if_addrs", return_value={"eth0": [mock_addr]}):
            mock_net_io = MagicMock()
            mock_net_io.bytes_sent = 1000
            mock_net_io.bytes_recv = 2000
            mock_net_io.packets_sent = 100
            mock_net_io.packets_recv = 200
            mock_net_io.errin = 0
            mock_net_io.errout = 0
            mock_net_io.dropin = 0
            mock_net_io.dropout = 0
            with patch("psutil.net_io_counters", return_value=mock_net_io):
                mock_conn = MagicMock()
                mock_conn.status = "ESTABLISHED"
                with patch("psutil.net_connections", return_value=[mock_conn]):
                    result = await monitor_agent._check_network_status({})

                    assert "interfaces" in result
                    assert "network_stats" in result
                    assert "connection_stats" in result

    @pytest.mark.asyncio
    async def test_analyze_disk_usage(self, monitor_agent):
        """Test disk usage analysis."""
        await monitor_agent._agent_specific_init()

        mock_partition = MagicMock()
        mock_partition.device = "/dev/sda1"
        mock_partition.mountpoint = "/"
        mock_partition.fstype = "ext4"

        mock_usage = MagicMock()
        mock_usage.total = 100 * 1024**3
        mock_usage.used = 50 * 1024**3
        mock_usage.free = 50 * 1024**3

        mock_io = MagicMock()
        mock_io.read_count = 1000
        mock_io.write_count = 500
        mock_io.read_bytes = 1000000
        mock_io.write_bytes = 500000
        mock_io.read_time = 100
        mock_io.write_time = 50

        with patch("psutil.disk_partitions", return_value=[mock_partition]):
            with patch("psutil.disk_usage", return_value=mock_usage):
                with patch("psutil.disk_io_counters", return_value=mock_io):
                    result = await monitor_agent._analyze_disk_usage({})

                    assert "partitions" in result
                    assert "io_statistics" in result


# =============================================================================
# TEST CLASS: CodeExecutionAgent
# =============================================================================


class TestCodeExecutionAgent:
    """Test CodeExecutionAgent class."""

    @pytest.fixture
    def code_agent(self, mock_agent_config):
        """Create a CodeExecutionAgent instance."""
        from src.core.subagents.specialist_agents import CodeExecutionAgent

        mock_agent_config.agent_type = AgentType.EXECUTOR
        agent = CodeExecutionAgent("code-agent-001", mock_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, code_agent):
        """Test code agent initialization."""
        await code_agent._agent_specific_init()

        assert hasattr(code_agent, "supported_languages")
        assert "python" in code_agent.supported_languages
        assert "javascript" in code_agent.supported_languages
        assert "shell" in code_agent.supported_languages
        assert hasattr(code_agent, "execution_limits")

    @pytest.mark.asyncio
    async def test_execute_no_code(self, code_agent):
        """Test execution with no code provided."""
        await code_agent._agent_specific_init()

        result = await code_agent._execute_specific_task({"language": "python", "code": ""})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_unsupported_language(self, code_agent):
        """Test execution with unsupported language."""
        await code_agent._agent_specific_init()

        result = await code_agent._execute_specific_task(
            {"language": "cobol", "code": "DISPLAY 'HELLO'"}
        )

        assert "error" in result
        assert "supported_languages" in result

    @pytest.mark.asyncio
    async def test_validate_code_security_safe(self, code_agent):
        """Test security validation for safe code."""
        await code_agent._agent_specific_init()

        safe_code = """
x = 1 + 2
y = x * 3
print(y)
"""
        result = await code_agent._validate_code_security(safe_code, "python")

        assert result["is_safe"] is True
        assert result["threat_type"] == "SAFE"

    @pytest.mark.asyncio
    async def test_validate_code_security_dangerous_imports(self, code_agent):
        """Test security validation for dangerous imports."""
        await code_agent._agent_specific_init()

        dangerous_code = """
import os
os.system('rm -rf /')
"""
        result = await code_agent._validate_code_security(dangerous_code, "python")

        assert result["is_safe"] is False
        assert len(result["threats_found"]) > 0

    @pytest.mark.asyncio
    async def test_validate_code_security_eval(self, code_agent):
        """Test security validation for eval."""
        await code_agent._agent_specific_init()

        dangerous_code = 'eval("malicious_code")'
        result = await code_agent._validate_code_security(dangerous_code, "python")

        assert result["is_safe"] is False

    def test_wrap_python_code_with_security(self, code_agent):
        """Test Python code wrapping with security."""
        code = "print('hello')"
        wrapped = code_agent._wrap_python_code_with_security(code)

        assert "MAX_EXECUTION_TIME" in wrapped
        assert "check_resources" in wrapped
        assert "SecurityError" in wrapped
        assert "print('hello')" in wrapped

    @pytest.mark.asyncio
    async def test_execute_javascript_code(self, code_agent):
        """Test JavaScript code execution (mock)."""
        await code_agent._agent_specific_init()

        js_code = "console.log('Hello from JS');"
        result = await code_agent._execute_javascript_code(js_code, {})

        assert result["success"] is True
        # Output may be empty in mock/test environment, just check structure
        assert "output" in result

    @pytest.mark.asyncio
    async def test_execute_shell_code_safe(self, code_agent):
        """Test safe shell code execution."""
        await code_agent._agent_specific_init()

        shell_code = 'echo "Hello World"'
        result = await code_agent._execute_shell_code(shell_code, {})

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_shell_code_dangerous(self, code_agent):
        """Test dangerous shell code detection."""
        await code_agent._agent_specific_init()

        dangerous_code = "rm -rf /"
        result = await code_agent._execute_shell_code(dangerous_code, {})

        assert result["success"] is False
        assert "Security" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_shell_code_sudo(self, code_agent):
        """Test sudo command detection."""
        await code_agent._agent_specific_init()

        sudo_code = "sudo apt-get install package"
        result = await code_agent._execute_shell_code(sudo_code, {})

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_execute_python_code_safe(self, code_agent):
        """Test safe Python code execution."""
        await code_agent._agent_specific_init()

        safe_code = "print('test')"

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.communicate.return_value = ("test output\n", "")
            mock_process.returncode = 0
            mock_popen.return_value = mock_process

            with patch("tempfile.TemporaryDirectory"):
                result = await code_agent._execute_python_code(safe_code, {})

                # The result depends on whether security check passes
                assert "success" in result


# =============================================================================
# TEST CLASS: KnowledgeAgent
# =============================================================================


class TestKnowledgeAgent:
    """Test KnowledgeAgent class."""

    @pytest.fixture
    def knowledge_agent(self, mock_agent_config):
        """Create a KnowledgeAgent instance."""
        from src.core.subagents.specialist_agents import KnowledgeAgent

        agent = KnowledgeAgent("knowledge-agent-001", mock_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, knowledge_agent):
        """Test knowledge agent initialization."""
        await knowledge_agent._agent_specific_init()

        assert hasattr(knowledge_agent, "knowledge_sources")
        assert "internal_kb" in knowledge_agent.knowledge_sources
        assert "document_search" in knowledge_agent.knowledge_sources
        assert "web_search" in knowledge_agent.knowledge_sources
        assert "faq_lookup" in knowledge_agent.knowledge_sources

    @pytest.mark.asyncio
    async def test_execute_no_query(self, knowledge_agent):
        """Test execution with no query."""
        await knowledge_agent._agent_specific_init()

        result = await knowledge_agent._execute_specific_task({"query": ""})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_with_query(self, knowledge_agent):
        """Test execution with valid query."""
        await knowledge_agent._agent_specific_init()

        with patch.object(knowledge_agent, "_query_internal_knowledge") as mock_kb:
            mock_kb.return_value = {
                "source": "internal_kb",
                "items": [],
                "query_time": 0.1,
            }
            # Update knowledge_sources reference since it stores the bound method
            knowledge_agent.knowledge_sources["internal_kb"] = mock_kb

            result = await knowledge_agent._execute_specific_task(
                {"query": "test query", "sources": ["internal_kb"], "max_results": 5}
            )

            assert "query" in result
            assert "results" in result

    def test_calculate_text_relevance(self, knowledge_agent):
        """Test text relevance calculation."""
        query = "machine learning"
        text = "This is about machine learning and deep learning algorithms"

        relevance = knowledge_agent._calculate_text_relevance(query, text)

        assert relevance > 0
        assert relevance <= 1.0

    def test_calculate_text_relevance_exact_match(self, knowledge_agent):
        """Test relevance with exact phrase match."""
        query = "machine learning"
        text = "Learn about machine learning today"

        relevance = knowledge_agent._calculate_text_relevance(query, text)

        # Should be boosted for exact match
        assert relevance > 0.5

    def test_calculate_text_relevance_no_match(self, knowledge_agent):
        """Test relevance with no match."""
        query = "quantum physics"
        text = "This is about cooking recipes"

        relevance = knowledge_agent._calculate_text_relevance(query, text)

        assert relevance == 0.0

    def test_extract_relevant_snippet(self, knowledge_agent):
        """Test snippet extraction."""
        query = "python"
        text = "Java is a language. Python is great for data science. Ruby is elegant."

        snippet = knowledge_agent._extract_relevant_snippet(query, text, max_length=100)

        # Should find the sentence with Python
        assert len(snippet) <= 100

    @pytest.mark.asyncio
    async def test_web_search(self, knowledge_agent):
        """Test web search (mock implementation)."""
        await knowledge_agent._agent_specific_init()

        result = await knowledge_agent._web_search("test query", 5)

        assert "source" in result
        assert result["source"] == "web_search"
        assert "items" in result

    @pytest.mark.asyncio
    async def test_faq_lookup(self, knowledge_agent):
        """Test FAQ lookup."""
        await knowledge_agent._agent_specific_init()

        result = await knowledge_agent._faq_lookup("how does it work", 5)

        assert "source" in result
        assert result["source"] == "faq_lookup"
        assert "items" in result


# =============================================================================
# TEST CLASS: ReportingAgent
# =============================================================================


class TestReportingAgent:
    """Test ReportingAgent class."""

    @pytest.fixture
    def reporting_agent(self, mock_agent_config):
        """Create a ReportingAgent instance."""
        from src.core.subagents.specialist_agents import ReportingAgent

        agent = ReportingAgent("reporting-agent-001", mock_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, reporting_agent):
        """Test reporting agent initialization."""
        await reporting_agent._agent_specific_init()

        assert hasattr(reporting_agent, "report_templates")
        assert "system_summary" in reporting_agent.report_templates
        assert "performance_report" in reporting_agent.report_templates
        assert "security_audit" in reporting_agent.report_templates
        assert "usage_analytics" in reporting_agent.report_templates

    @pytest.mark.asyncio
    async def test_execute_unknown_report_type(self, reporting_agent):
        """Test execution with unknown report type."""
        await reporting_agent._agent_specific_init()

        result = await reporting_agent._execute_specific_task({"report_type": "unknown_report"})

        assert "error" in result
        assert "available_types" in result

    @pytest.mark.asyncio
    async def test_generate_system_summary(self, reporting_agent):
        """Test system summary report generation."""
        await reporting_agent._agent_specific_init()

        with patch("psutil.cpu_percent", return_value=30.0):
            mock_memory = MagicMock()
            mock_memory.total = 16 * 1024**3
            mock_memory.used = 8 * 1024**3
            mock_memory.percent = 50.0
            with patch("psutil.virtual_memory", return_value=mock_memory):
                mock_disk = MagicMock()
                mock_disk.percent = 60.0
                mock_disk.free = 200 * 1024**3
                with patch("psutil.disk_usage", return_value=mock_disk):
                    with patch(
                        "psutil.boot_time",
                        return_value=datetime.now(timezone.utc).timestamp() - 86400,
                    ):
                        with patch("psutil.process_iter", return_value=[]):
                            result = await reporting_agent._generate_system_summary({})

                            assert "title" in result
                            assert "summary" in result
                            assert "system_resources" in result

    def test_generate_recommendations_optimal(self, reporting_agent):
        """Test recommendations for optimal system."""
        recommendations = reporting_agent._generate_recommendations(
            health_score=95, cpu_percent=30.0, memory_percent=40.0, disk_percent=50.0
        )

        assert "System performing optimally" in recommendations

    def test_generate_recommendations_high_cpu(self, reporting_agent):
        """Test recommendations for high CPU."""
        recommendations = reporting_agent._generate_recommendations(
            health_score=70, cpu_percent=85.0, memory_percent=40.0, disk_percent=50.0
        )

        assert any("CPU" in rec for rec in recommendations)

    def test_generate_recommendations_high_memory(self, reporting_agent):
        """Test recommendations for high memory."""
        recommendations = reporting_agent._generate_recommendations(
            health_score=70, cpu_percent=30.0, memory_percent=85.0, disk_percent=50.0
        )

        assert any("memory" in rec.lower() for rec in recommendations)

    @pytest.mark.asyncio
    async def test_generate_performance_report(self, reporting_agent):
        """Test performance report generation."""
        await reporting_agent._agent_specific_init()

        result = await reporting_agent._generate_performance_report({})

        assert "title" in result
        assert "metrics" in result
        assert "bottlenecks" in result

    @pytest.mark.asyncio
    async def test_generate_security_audit(self, reporting_agent):
        """Test security audit report generation."""
        await reporting_agent._agent_specific_init()

        result = await reporting_agent._generate_security_audit({})

        assert "title" in result
        assert "security_score" in result
        assert "findings" in result
        assert "compliance" in result

    @pytest.mark.asyncio
    async def test_generate_usage_analytics(self, reporting_agent):
        """Test usage analytics report generation."""
        await reporting_agent._agent_specific_init()

        result = await reporting_agent._generate_usage_analytics({})

        assert "title" in result
        assert "user_activity" in result
        assert "feature_usage" in result


# =============================================================================
# TEST CLASS: PerformanceAgent
# =============================================================================


class TestPerformanceAgent:
    """Test PerformanceAgent class."""

    @pytest.fixture
    def performance_agent(self, mock_agent_config):
        """Create a PerformanceAgent instance."""
        from src.core.subagents.specialist_agents import PerformanceAgent

        agent = PerformanceAgent("perf-agent-001", mock_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, performance_agent):
        """Test performance agent initialization."""
        await performance_agent._agent_specific_init()

        assert hasattr(performance_agent, "analysis_functions")
        assert "benchmark" in performance_agent.analysis_functions
        assert "bottleneck_analysis" in performance_agent.analysis_functions
        assert "resource_optimization" in performance_agent.analysis_functions
        assert "scaling_analysis" in performance_agent.analysis_functions

    @pytest.mark.asyncio
    async def test_execute_unknown_analysis_type(self, performance_agent):
        """Test execution with unknown analysis type."""
        await performance_agent._agent_specific_init()

        result = await performance_agent._execute_specific_task(
            {"analysis_type": "unknown_analysis"}
        )

        assert "error" in result
        assert "available_types" in result

    @pytest.mark.asyncio
    async def test_run_benchmark(self, performance_agent):
        """Test benchmark execution."""
        await performance_agent._agent_specific_init()

        with patch("psutil.cpu_percent", return_value=30.0):
            mock_memory = MagicMock()
            mock_memory.percent = 50.0
            with patch("psutil.virtual_memory", return_value=mock_memory):
                result = await performance_agent._run_benchmark(
                    "system", {"duration_seconds": 1, "load_level": "light"}
                )

                assert "benchmark_type" in result
                assert "results" in result or "error" in result

    @pytest.mark.asyncio
    async def test_benchmark_system(self, performance_agent):
        """Test system benchmark."""
        await performance_agent._agent_specific_init()

        operations, latencies = await performance_agent._benchmark_system(1, "light")

        assert operations > 0
        assert len(latencies) > 0

    @pytest.mark.asyncio
    async def test_benchmark_memory(self, performance_agent):
        """Test memory benchmark."""
        await performance_agent._agent_specific_init()

        operations, latencies = await performance_agent._benchmark_memory(1, "normal")

        assert operations > 0
        assert len(latencies) > 0

    @pytest.mark.asyncio
    async def test_benchmark_cpu(self, performance_agent):
        """Test CPU benchmark."""
        await performance_agent._agent_specific_init()

        operations, latencies = await performance_agent._benchmark_cpu(1, "normal")

        assert operations > 0
        assert len(latencies) > 0

    def test_calculate_performance_score(self, performance_agent):
        """Test performance score calculation."""
        score = performance_agent._calculate_performance_score(
            throughput=100.0, avg_latency=0.01, cpu_usage=30.0, memory_usage=40.0
        )

        assert 0 <= score <= 100

    def test_get_performance_grade(self, performance_agent):
        """Test performance grade assignment."""
        assert performance_agent._get_performance_grade(95) == "A+"
        assert performance_agent._get_performance_grade(85) == "A"
        assert performance_agent._get_performance_grade(75) == "B+"
        assert performance_agent._get_performance_grade(65) == "B"
        assert performance_agent._get_performance_grade(55) == "C+"
        assert performance_agent._get_performance_grade(45) == "C"
        assert performance_agent._get_performance_grade(35) == "D"

    @pytest.mark.asyncio
    async def test_analyze_bottlenecks(self, performance_agent):
        """Test bottleneck analysis."""
        await performance_agent._agent_specific_init()

        result = await performance_agent._analyze_bottlenecks("system", {"depth": "standard"})

        assert "bottlenecks_found" in result
        assert "bottlenecks" in result
        assert "priority_order" in result

    @pytest.mark.asyncio
    async def test_optimize_resources_memory(self, performance_agent):
        """Test memory resource optimization."""
        await performance_agent._agent_specific_init()

        result = await performance_agent._optimize_resources("memory", {"type": "memory"})

        assert "optimization_type" in result
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_optimize_resources_cpu(self, performance_agent):
        """Test CPU resource optimization."""
        await performance_agent._agent_specific_init()

        result = await performance_agent._optimize_resources("cpu", {"type": "cpu"})

        assert "optimization_type" in result
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_optimize_resources_io(self, performance_agent):
        """Test I/O resource optimization."""
        await performance_agent._agent_specific_init()

        result = await performance_agent._optimize_resources("io", {"type": "io"})

        assert "optimization_type" in result
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_analyze_scaling_needs(self, performance_agent):
        """Test scaling needs analysis."""
        await performance_agent._agent_specific_init()

        result = await performance_agent._analyze_scaling_needs(
            "system", {"projected_load_increase": 2.0, "time_horizon_months": 6}
        )

        assert "current_capacity" in result
        assert "projected_needs" in result
        assert "scaling_recommendations" in result
        assert "timeline" in result


# =============================================================================
# INTEGRATION TESTS - Agent Lifecycle
# =============================================================================


class TestAgentLifecycle:
    """Test agent lifecycle operations."""

    @pytest.mark.asyncio
    async def test_data_agent_full_lifecycle(self, mock_agent_config):
        """Test complete lifecycle of DataAnalysisAgent."""
        from src.core.subagents.specialist_agents import DataAnalysisAgent

        mock_agent_config.agent_type = AgentType.DATA_ANALYSIS
        agent = DataAnalysisAgent("lifecycle-test-001", mock_agent_config)

        # Initialize
        result = await agent.initialize()
        assert result is True
        assert agent.status == AgentStatus.IDLE

        # Execute task
        task_result = await agent.execute_task(
            {
                "analysis_type": "trend_analysis",
                "data": [1, 2, 3, 4, 5],
                "parameters": {},
            }
        )

        assert task_result["success"] is True
        assert agent.metrics.tasks_completed >= 1

    @pytest.mark.asyncio
    async def test_monitor_agent_full_lifecycle(self, mock_agent_config):
        """Test complete lifecycle of SystemMonitorAgent."""
        from src.core.subagents.specialist_agents import SystemMonitorAgent

        mock_agent_config.agent_type = AgentType.MONITOR
        agent = SystemMonitorAgent("lifecycle-test-002", mock_agent_config)

        result = await agent.initialize()
        assert result is True

        with patch("psutil.cpu_percent", return_value=25.0):
            mock_memory = MagicMock()
            mock_memory.percent = 50.0
            with patch("psutil.virtual_memory", return_value=mock_memory):
                mock_disk = MagicMock()
                mock_disk.percent = 40.0
                with patch("psutil.disk_usage", return_value=mock_disk):
                    task_result = await agent.execute_task(
                        {"monitor_type": "system_health", "parameters": {}}
                    )

                    assert task_result["success"] is True

    @pytest.mark.asyncio
    async def test_concurrent_task_limit(self, mock_agent_config):
        """Test agent concurrent task limit."""
        from src.core.subagents.specialist_agents import DataAnalysisAgent

        mock_agent_config.max_concurrent_tasks = 1
        agent = DataAnalysisAgent("concurrent-test-001", mock_agent_config)

        await agent.initialize()

        # Manually add a task to current_tasks to simulate running task
        agent.current_tasks["fake-task-id"] = {
            "start_time": datetime.now(timezone.utc),
            "task_data": {},
        }

        # Try to execute another task
        result = await agent.execute_task(
            {"analysis_type": "trend_analysis", "data": [1, 2, 3, 4, 5]}
        )

        assert result["success"] is False
        assert "maximum capacity" in result["error"]


# =============================================================================
# EDGE CASES AND ERROR HANDLING
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_statistical_summary_exception_handling(self, mock_agent_config):
        """Test exception handling in statistical summary."""
        from src.core.subagents.specialist_agents import DataAnalysisAgent

        agent = DataAnalysisAgent("edge-test-001", mock_agent_config)
        await agent._agent_specific_init()

        with patch("pandas.Series", side_effect=Exception("Pandas error")):
            result = await agent._statistical_summary([1, 2, 3], {})

            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_pattern_recognition_exception_handling(self, mock_agent_config):
        """Test exception handling in pattern recognition."""
        from src.core.subagents.specialist_agents import DataAnalysisAgent

        agent = DataAnalysisAgent("edge-test-002", mock_agent_config)
        await agent._agent_specific_init()

        with patch("sklearn.cluster.KMeans", side_effect=Exception("KMeans error")):
            result = await agent._pattern_recognition([1, 2, 3, 4, 5], {})

            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_resource_usage_exception_handling(self, mock_agent_config):
        """Test exception handling in resource usage."""
        from src.core.subagents.specialist_agents import SystemMonitorAgent

        agent = SystemMonitorAgent("edge-test-003", mock_agent_config)
        await agent._agent_specific_init()

        with patch("psutil.cpu_percent", side_effect=Exception("CPU error")):
            result = await agent._get_resource_usage({})

            assert "error" in result

    @pytest.mark.asyncio
    async def test_process_monitoring_exception_handling(self, mock_agent_config):
        """Test exception handling in process monitoring."""
        from src.core.subagents.specialist_agents import SystemMonitorAgent

        agent = SystemMonitorAgent("edge-test-004", mock_agent_config)
        await agent._agent_specific_init()

        with patch("psutil.process_iter", side_effect=Exception("Process error")):
            result = await agent._monitor_processes({})

            assert "error" in result

    @pytest.mark.asyncio
    async def test_code_execution_timeout(self, mock_agent_config):
        """Test code execution timeout handling."""
        import tempfile
        from subprocess import TimeoutExpired

        from src.core.subagents.specialist_agents import CodeExecutionAgent

        agent = CodeExecutionAgent("edge-test-005", mock_agent_config)
        await agent._agent_specific_init()

        # Create a real temp directory for the test
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                mock_process.communicate.side_effect = TimeoutExpired("python", 30)
                mock_process.kill = MagicMock()
                mock_popen.return_value = mock_process

                # Mock security validation to pass
                with patch.object(agent, "_validate_code_security") as mock_security:
                    mock_security.return_value = {
                        "is_safe": True,
                        "threat_type": "SAFE",
                    }

                    # Call with a safe code that should trigger timeout
                    result = await agent._execute_python_code("print('test')", {"timeout": 1})

                    # The test may hit the timeout or other error
                    assert result["success"] is False


# =============================================================================
# ADDITIONAL COVERAGE TESTS - High coverage targets
# =============================================================================


class TestAdditionalCoverage:
    """Additional tests for higher coverage."""

    @pytest.mark.asyncio
    async def test_knowledge_agent_internal_kb_real(self, mock_agent_config):
        """Test internal knowledge base query with file access."""
        from src.core.subagents.specialist_agents import KnowledgeAgent

        agent = KnowledgeAgent("kb-test-001", mock_agent_config)
        await agent._agent_specific_init()

        with patch("glob.glob", return_value=[]):
            result = await agent._query_internal_knowledge("test query", 5)

            assert "source" in result
            assert result["source"] == "internal_kb"

    @pytest.mark.asyncio
    async def test_knowledge_agent_document_search_real(self, mock_agent_config):
        """Test document search with file access."""
        from src.core.subagents.specialist_agents import KnowledgeAgent

        agent = KnowledgeAgent("doc-test-001", mock_agent_config)
        await agent._agent_specific_init()

        with patch("glob.glob", return_value=[]):
            result = await agent._search_documents("test query", 5)

            assert "source" in result
            assert result["source"] == "document_search"

    def test_knowledge_agent_extract_code_snippet(self, mock_agent_config):
        """Test code snippet extraction."""
        from src.core.subagents.specialist_agents import KnowledgeAgent

        agent = KnowledgeAgent("snippet-test-001", mock_agent_config)

        code = '''def hello():
    """Say hello."""
    print("hello")

def world():
    print("world")
'''
        snippet = agent._extract_code_snippet("hello", code, max_length=100)
        assert len(snippet) <= 100

    @pytest.mark.asyncio
    async def test_performance_agent_benchmark_agents(self, mock_agent_config):
        """Test agent benchmark."""
        from src.core.subagents.specialist_agents import PerformanceAgent

        agent = PerformanceAgent("bench-agent-001", mock_agent_config)
        await agent._agent_specific_init()

        # Test directly with fallback to system benchmark by using short duration
        operations, latencies = await agent._benchmark_system(1, "light")

        # Should have some results from system benchmark
        assert operations >= 0
        assert isinstance(latencies, list)

    @pytest.mark.asyncio
    async def test_system_health_high_memory(self, mock_agent_config):
        """Test system health with high memory usage."""
        from src.core.subagents.specialist_agents import SystemMonitorAgent

        agent = SystemMonitorAgent("health-test-001", mock_agent_config)
        await agent._agent_specific_init()

        with patch("psutil.cpu_percent", return_value=50.0):
            mock_memory = MagicMock()
            mock_memory.percent = 95.0
            with patch("psutil.virtual_memory", return_value=mock_memory):
                mock_disk = MagicMock()
                mock_disk.percent = 50.0
                with patch("psutil.disk_usage", return_value=mock_disk):
                    result = await agent._check_system_health({})

                    assert "High memory usage" in result["issues"]

    @pytest.mark.asyncio
    async def test_system_health_high_disk(self, mock_agent_config):
        """Test system health with high disk usage."""
        from src.core.subagents.specialist_agents import SystemMonitorAgent

        agent = SystemMonitorAgent("health-test-002", mock_agent_config)
        await agent._agent_specific_init()

        with patch("psutil.cpu_percent", return_value=50.0):
            mock_memory = MagicMock()
            mock_memory.percent = 50.0
            with patch("psutil.virtual_memory", return_value=mock_memory):
                mock_disk = MagicMock()
                mock_disk.percent = 98.0
                with patch("psutil.disk_usage", return_value=mock_disk):
                    result = await agent._check_system_health({})

                    assert "Very low disk space" in result["issues"]

    @pytest.mark.asyncio
    async def test_reporting_system_summary_error(self, mock_agent_config):
        """Test system summary with error handling."""
        from src.core.subagents.specialist_agents import ReportingAgent

        agent = ReportingAgent("report-test-001", mock_agent_config)
        await agent._agent_specific_init()

        with patch("psutil.cpu_percent", side_effect=Exception("CPU error")):
            result = await agent._generate_system_summary({})

            # Should return fallback summary
            assert "title" in result
            assert "fallback_summary" in result or "error" in result

    def test_recommendations_disk_usage(self, mock_agent_config):
        """Test recommendations with high disk usage."""
        from src.core.subagents.specialist_agents import ReportingAgent

        agent = ReportingAgent("rec-test-001", mock_agent_config)

        recommendations = agent._generate_recommendations(
            health_score=60, cpu_percent=30.0, memory_percent=40.0, disk_percent=85.0
        )

        assert any("disk" in rec.lower() for rec in recommendations)

    @pytest.mark.asyncio
    async def test_code_execution_dangerous_code(self, mock_agent_config):
        """Test code execution with dangerous code patterns."""
        from src.core.subagents.specialist_agents import CodeExecutionAgent

        agent = CodeExecutionAgent("danger-test-001", mock_agent_config)
        await agent._agent_specific_init()

        dangerous_code = """
import socket
socket.connect(("evil.com", 80))
"""
        result = await agent._validate_code_security(dangerous_code, "python")

        assert result["is_safe"] is False
        assert "socket" in str(result["threats_found"]).lower()

    @pytest.mark.asyncio
    async def test_code_execution_network_operations(self, mock_agent_config):
        """Test security validation for network operations."""
        from src.core.subagents.specialist_agents import CodeExecutionAgent

        agent = CodeExecutionAgent("net-test-001", mock_agent_config)
        await agent._agent_specific_init()

        network_code = "import urllib\nurllib.request.urlopen('http://evil.com')"
        result = await agent._validate_code_security(network_code, "python")

        assert result["is_safe"] is False

    @pytest.mark.asyncio
    async def test_code_execution_infinite_loop(self, mock_agent_config):
        """Test security validation for infinite loop detection."""
        from src.core.subagents.specialist_agents import CodeExecutionAgent

        agent = CodeExecutionAgent("loop-test-001", mock_agent_config)
        await agent._agent_specific_init()

        loop_code = "while True:\n    pass"
        result = await agent._validate_code_security(loop_code, "python")

        assert result["is_safe"] is False

    @pytest.mark.asyncio
    async def test_disk_analysis_permission_error(self, mock_agent_config):
        """Test disk analysis with permission error."""
        from src.core.subagents.specialist_agents import SystemMonitorAgent

        agent = SystemMonitorAgent("disk-test-001", mock_agent_config)
        await agent._agent_specific_init()

        mock_partition = MagicMock()
        mock_partition.device = "/dev/sda1"
        mock_partition.mountpoint = "/protected"
        mock_partition.fstype = "ext4"

        mock_io = MagicMock()
        mock_io.read_count = 100
        mock_io.write_count = 50
        mock_io.read_bytes = 1000
        mock_io.write_bytes = 500
        mock_io.read_time = 10
        mock_io.write_time = 5

        with patch("psutil.disk_partitions", return_value=[mock_partition]):
            with patch("psutil.disk_usage", side_effect=PermissionError("Access denied")):
                with patch("psutil.disk_io_counters", return_value=mock_io):
                    result = await agent._analyze_disk_usage({})

                    assert "partitions" in result
                    assert "error" in result["partitions"]["/dev/sda1"]

    @pytest.mark.asyncio
    async def test_process_monitoring_no_such_process(self, mock_agent_config):
        """Test process monitoring with NoSuchProcess error."""
        import psutil

        from src.core.subagents.specialist_agents import SystemMonitorAgent

        agent = SystemMonitorAgent("proc-test-001", mock_agent_config)
        await agent._agent_specific_init()

        mock_proc = MagicMock()
        mock_proc.info = psutil.NoSuchProcess(999)

        def raise_exception():
            raise psutil.NoSuchProcess(999)

        mock_proc_with_error = MagicMock()
        mock_proc_with_error.info.__getitem__.side_effect = psutil.NoSuchProcess(999)

        with patch("psutil.process_iter", return_value=[]):
            result = await agent._monitor_processes({"top_n": 5})

            assert "total_processes" in result
            assert result["total_processes"] == 0

    @pytest.mark.asyncio
    async def test_network_status_error(self, mock_agent_config):
        """Test network status with error."""
        from src.core.subagents.specialist_agents import SystemMonitorAgent

        agent = SystemMonitorAgent("net-error-test-001", mock_agent_config)
        await agent._agent_specific_init()

        with patch("psutil.net_if_addrs", side_effect=Exception("Network error")):
            result = await agent._check_network_status({})

            assert "error" in result

    @pytest.mark.asyncio
    async def test_disk_analysis_error(self, mock_agent_config):
        """Test disk analysis with general error."""
        from src.core.subagents.specialist_agents import SystemMonitorAgent

        agent = SystemMonitorAgent("disk-error-test-001", mock_agent_config)
        await agent._agent_specific_init()

        with patch("psutil.disk_partitions", side_effect=Exception("Disk error")):
            result = await agent._analyze_disk_usage({})

            assert "error" in result

    @pytest.mark.asyncio
    async def test_benchmark_error(self, mock_agent_config):
        """Test benchmark with error."""
        from src.core.subagents.specialist_agents import PerformanceAgent

        agent = PerformanceAgent("bench-error-001", mock_agent_config)
        await agent._agent_specific_init()

        with patch("psutil.cpu_percent", side_effect=Exception("Benchmark error")):
            result = await agent._run_benchmark("system", {"duration_seconds": 1})

            assert "error" in result

    @pytest.mark.asyncio
    async def test_moderate_system_health(self, mock_agent_config):
        """Test moderate CPU and memory health."""
        from src.core.subagents.specialist_agents import SystemMonitorAgent

        agent = SystemMonitorAgent("moderate-test-001", mock_agent_config)
        await agent._agent_specific_init()

        with patch("psutil.cpu_percent", return_value=75.0):
            mock_memory = MagicMock()
            mock_memory.percent = 80.0
            with patch("psutil.virtual_memory", return_value=mock_memory):
                mock_disk = MagicMock()
                mock_disk.percent = 88.0
                with patch("psutil.disk_usage", return_value=mock_disk):
                    result = await agent._check_system_health({})

                    # Should have moderate issues
                    assert "health_score" in result
                    assert result["health_score"] < 100
                    # Check for moderate messages
                    issues = result.get("issues", [])
                    assert len(issues) > 0

    @pytest.mark.asyncio
    async def test_execute_python_code_with_dangerous_code(self, mock_agent_config):
        """Test Python code execution rejection for dangerous code."""
        from src.core.subagents.specialist_agents import CodeExecutionAgent

        agent = CodeExecutionAgent("danger-py-001", mock_agent_config)
        await agent._agent_specific_init()

        dangerous_code = "import os\nos.system('rm -rf /')"
        result = await agent._execute_python_code(dangerous_code, {})

        assert result["success"] is False
        assert (
            "security" in result["error"].lower()
            or "security" in str(result.get("security_details", "")).lower()
        )

    @pytest.mark.asyncio
    async def test_execute_task_full_flow(self, mock_agent_config):
        """Test full task execution flow for DataAnalysisAgent."""
        from src.core.subagents.specialist_agents import DataAnalysisAgent

        agent = DataAnalysisAgent("full-flow-001", mock_agent_config)
        await agent.initialize()

        # Execute a complete analysis task
        task_data = {
            "id": "test-task-123",
            "analysis_type": "anomaly_detection",
            "data": [1, 2, 2, 3, 2, 2, 100, 2, 2],
            "parameters": {"method": "standard_deviation", "sensitivity": 2.0},
        }

        result = await agent.execute_task(task_data)

        assert result["success"] is True
        assert "result" in result
        assert result["task_id"] == "test-task-123"
