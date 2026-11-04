"""
Tests for Blue-Green Deployment Controller

Tests cover:
- Deployment execution
- Health check logic
- Traffic switching
- Rollback procedures
- History tracking
"""

import asyncio
import json

# Import from deployment module (adjust path as needed)
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "deployment" / "blue_green"))

from deploy import (
    BlueGreenDeployer,
    DeploymentConfig,
    DeploymentEnvironment,
    DeploymentHistory,
    DeploymentRecord,
    DeploymentStatus,
    HealthCheckConfig,
)

# ==================== FIXTURES ====================


@pytest.fixture
def temp_history_dir(tmp_path: Path) -> Path:
    """Create temporary history directory"""
    history_dir = tmp_path / "deployment" / "history"
    history_dir.mkdir(parents=True)
    return history_dir


@pytest.fixture
def deployment_config() -> DeploymentConfig:
    """Create test deployment config"""
    return DeploymentConfig(
        project_name="test-project",
        docker_registry="test-registry",
        image_name="test-image",
        replicas=2,
        health_check=HealthCheckConfig(
            endpoint="/health",
            timeout=5,
            retries=2,
            interval=1,
            success_threshold=1,
        ),
        deployment_timeout=30,
        rollback_on_failure=True,
    )


@pytest.fixture
def deployer(deployment_config: DeploymentConfig, temp_history_dir: Path) -> BlueGreenDeployer:
    """Create test deployer instance"""
    return BlueGreenDeployer(
        config=deployment_config,
        history_dir=temp_history_dir,
    )


# ==================== DEPLOYMENT CONFIG TESTS ====================


class TestDeploymentConfig:
    """Tests for DeploymentConfig"""

    def test_default_config(self):
        """Test default configuration values"""
        config = DeploymentConfig()

        assert config.project_name == "sanskritisetu"
        assert config.replicas == 3
        assert config.blue_port == 8001
        assert config.green_port == 8002
        assert config.nginx_port == 80
        assert config.rollback_on_failure is True

    def test_custom_config(self):
        """Test custom configuration"""
        config = DeploymentConfig(
            project_name="custom",
            replicas=5,
            blue_port=9001,
            green_port=9002,
        )

        assert config.project_name == "custom"
        assert config.replicas == 5
        assert config.blue_port == 9001
        assert config.green_port == 9002


class TestHealthCheckConfig:
    """Tests for HealthCheckConfig"""

    def test_default_health_config(self):
        """Test default health check configuration"""
        config = HealthCheckConfig()

        assert config.endpoint == "/health"
        assert config.timeout == 30
        assert config.retries == 3
        assert config.interval == 10
        assert config.success_threshold == 2

    def test_custom_health_config(self):
        """Test custom health check configuration"""
        config = HealthCheckConfig(
            endpoint="/api/health",
            timeout=60,
            retries=5,
        )

        assert config.endpoint == "/api/health"
        assert config.timeout == 60
        assert config.retries == 5


# ==================== DEPLOYMENT ENVIRONMENT TESTS ====================


class TestDeploymentEnvironment:
    """Tests for DeploymentEnvironment enum"""

    def test_blue_environment(self):
        """Test blue environment value"""
        assert DeploymentEnvironment.BLUE.value == "blue"

    def test_green_environment(self):
        """Test green environment value"""
        assert DeploymentEnvironment.GREEN.value == "green"

    def test_environment_from_string(self):
        """Test creating environment from string"""
        assert DeploymentEnvironment("blue") == DeploymentEnvironment.BLUE
        assert DeploymentEnvironment("green") == DeploymentEnvironment.GREEN


class TestDeploymentStatus:
    """Tests for DeploymentStatus enum"""

    def test_all_statuses(self):
        """Test all deployment statuses exist"""
        assert DeploymentStatus.PENDING.value == "pending"
        assert DeploymentStatus.DEPLOYING.value == "deploying"
        assert DeploymentStatus.HEALTH_CHECK.value == "health_check"
        assert DeploymentStatus.SWITCHING_TRAFFIC.value == "switching_traffic"
        assert DeploymentStatus.COMPLETED.value == "completed"
        assert DeploymentStatus.FAILED.value == "failed"
        assert DeploymentStatus.ROLLED_BACK.value == "rolled_back"


# ==================== DEPLOYMENT RECORD TESTS ====================


class TestDeploymentRecord:
    """Tests for DeploymentRecord"""

    def test_record_creation(self):
        """Test creating deployment record"""
        now = datetime.now(timezone.utc)
        record = DeploymentRecord(
            id="deploy-123",
            version="1.0.0",
            environment=DeploymentEnvironment.BLUE,
            status=DeploymentStatus.PENDING,
            started_at=now,
        )

        assert record.id == "deploy-123"
        assert record.version == "1.0.0"
        assert record.environment == DeploymentEnvironment.BLUE
        assert record.status == DeploymentStatus.PENDING
        assert record.started_at == now
        assert record.completed_at is None
        assert record.error_message is None

    def test_record_to_dict(self):
        """Test converting record to dictionary"""
        now = datetime.now(timezone.utc)
        record = DeploymentRecord(
            id="deploy-123",
            version="1.0.0",
            environment=DeploymentEnvironment.BLUE,
            status=DeploymentStatus.COMPLETED,
            started_at=now,
            completed_at=now,
        )

        result = record.to_dict()

        assert result["id"] == "deploy-123"
        assert result["version"] == "1.0.0"
        assert result["environment"] == "blue"
        assert result["status"] == "completed"
        assert result["started_at"] == now.isoformat()
        assert result["completed_at"] == now.isoformat()


# ==================== DEPLOYMENT HISTORY TESTS ====================


class TestDeploymentHistory:
    """Tests for DeploymentHistory"""

    def test_empty_history(self, temp_history_dir: Path):
        """Test empty history returns None"""
        history = DeploymentHistory(temp_history_dir / "test.json")

        assert history.get_latest() is None
        assert history.get_active_environment() == DeploymentEnvironment.BLUE

    def test_add_record(self, temp_history_dir: Path):
        """Test adding deployment record"""
        history = DeploymentHistory(temp_history_dir / "test.json")

        record = DeploymentRecord(
            id="deploy-123",
            version="1.0.0",
            environment=DeploymentEnvironment.BLUE,
            status=DeploymentStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
        )
        history.add(record)

        latest = history.get_latest()
        assert latest is not None
        assert latest["id"] == "deploy-123"
        assert latest["version"] == "1.0.0"

    def test_update_latest(self, temp_history_dir: Path):
        """Test updating latest record"""
        history = DeploymentHistory(temp_history_dir / "test.json")

        record = DeploymentRecord(
            id="deploy-123",
            version="1.0.0",
            environment=DeploymentEnvironment.BLUE,
            status=DeploymentStatus.PENDING,
            started_at=datetime.now(timezone.utc),
        )
        history.add(record)
        history.update_latest(status=DeploymentStatus.COMPLETED.value)

        latest = history.get_latest()
        assert latest["status"] == "completed"

    def test_get_active_environment(self, temp_history_dir: Path):
        """Test getting active environment"""
        history = DeploymentHistory(temp_history_dir / "test.json")

        # Add blue deployment
        record1 = DeploymentRecord(
            id="deploy-1",
            version="1.0.0",
            environment=DeploymentEnvironment.BLUE,
            status=DeploymentStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
        )
        history.add(record1)

        assert history.get_active_environment() == DeploymentEnvironment.BLUE

        # Add green deployment
        record2 = DeploymentRecord(
            id="deploy-2",
            version="1.1.0",
            environment=DeploymentEnvironment.GREEN,
            status=DeploymentStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
        )
        history.add(record2)

        assert history.get_active_environment() == DeploymentEnvironment.GREEN

    def test_get_previous_successful(self, temp_history_dir: Path):
        """Test getting previous successful deployment"""
        history = DeploymentHistory(temp_history_dir / "test.json")

        # Add first successful deployment
        record1 = DeploymentRecord(
            id="deploy-1",
            version="1.0.0",
            environment=DeploymentEnvironment.BLUE,
            status=DeploymentStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
        )
        history.add(record1)

        # Add failed deployment
        record2 = DeploymentRecord(
            id="deploy-2",
            version="1.1.0",
            environment=DeploymentEnvironment.GREEN,
            status=DeploymentStatus.FAILED,
            started_at=datetime.now(timezone.utc),
        )
        history.add(record2)

        previous = history.get_previous_successful()
        assert previous is not None
        assert previous["id"] == "deploy-1"
        assert previous["version"] == "1.0.0"

    def test_persistence(self, temp_history_dir: Path):
        """Test history persistence across instances"""
        history_file = temp_history_dir / "persist.json"

        # Create and add record
        history1 = DeploymentHistory(history_file)
        record = DeploymentRecord(
            id="deploy-123",
            version="1.0.0",
            environment=DeploymentEnvironment.BLUE,
            status=DeploymentStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
        )
        history1.add(record)

        # Load in new instance
        history2 = DeploymentHistory(history_file)
        latest = history2.get_latest()

        assert latest is not None
        assert latest["id"] == "deploy-123"


# ==================== BLUE-GREEN DEPLOYER TESTS ====================


class TestBlueGreenDeployer:
    """Tests for BlueGreenDeployer"""

    def test_generate_deployment_id(self, deployer: BlueGreenDeployer):
        """Test deployment ID generation"""
        id1 = deployer._generate_deployment_id()
        id2 = deployer._generate_deployment_id()

        assert id1.startswith("deploy-")
        assert len(id1) == 21  # deploy- + 14 digit timestamp
        # IDs may be the same if generated in same second

    def test_get_target_environment_default(self, deployer: BlueGreenDeployer):
        """Test target environment when no history (default to green)"""
        target = deployer._get_target_environment()

        # Default active is blue, so target should be green
        assert target == DeploymentEnvironment.GREEN

    def test_get_target_environment_alternates(
        self,
        deployer: BlueGreenDeployer,
        temp_history_dir: Path,
    ):
        """Test target environment alternates"""
        # Add blue deployment to history
        record = DeploymentRecord(
            id="deploy-1",
            version="1.0.0",
            environment=DeploymentEnvironment.BLUE,
            status=DeploymentStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
        )
        deployer.history.add(record)

        target = deployer._get_target_environment()
        assert target == DeploymentEnvironment.GREEN

        # Add green deployment
        record2 = DeploymentRecord(
            id="deploy-2",
            version="1.1.0",
            environment=DeploymentEnvironment.GREEN,
            status=DeploymentStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
        )
        deployer.history.add(record2)

        target = deployer._get_target_environment()
        assert target == DeploymentEnvironment.BLUE

    def test_get_environment_port(self, deployer: BlueGreenDeployer):
        """Test environment port mapping"""
        blue_port = deployer._get_environment_port(DeploymentEnvironment.BLUE)
        green_port = deployer._get_environment_port(DeploymentEnvironment.GREEN)

        assert blue_port == deployer.config.blue_port
        assert green_port == deployer.config.green_port

    def test_get_status_empty(self, deployer: BlueGreenDeployer):
        """Test status with no deployments"""
        status = deployer.get_status()

        assert status["active_environment"] == "blue"
        assert status["latest_deployment"] is None
        assert "config" in status

    def test_get_status_with_deployment(self, deployer: BlueGreenDeployer):
        """Test status with deployment"""
        record = DeploymentRecord(
            id="deploy-123",
            version="1.0.0",
            environment=DeploymentEnvironment.GREEN,
            status=DeploymentStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
        )
        deployer.history.add(record)

        status = deployer.get_status()

        assert status["active_environment"] == "green"
        assert status["latest_deployment"]["id"] == "deploy-123"

    def test_generate_nginx_config(self, deployer: BlueGreenDeployer):
        """Test nginx config generation"""
        config = deployer._generate_nginx_config(DeploymentEnvironment.BLUE)

        assert "upstream backend" in config
        assert "backend-blue-1" in config
        assert "Active environment: blue" in config

    def test_generate_nginx_config_green(self, deployer: BlueGreenDeployer):
        """Test nginx config for green environment"""
        config = deployer._generate_nginx_config(DeploymentEnvironment.GREEN)

        assert "backend-green-1" in config
        assert "Active environment: green" in config


# ==================== ASYNC DEPLOYMENT TESTS ====================


class TestAsyncDeployment:
    """Tests for async deployment operations"""

    @pytest.mark.asyncio
    async def test_deploy_success(self, deployer: BlueGreenDeployer):
        """Test successful deployment flow"""
        async with deployer:
            # Mock all external operations
            deployer._deploy_to_environment = AsyncMock()
            deployer._run_health_checks = AsyncMock(return_value=True)
            deployer._switch_traffic = AsyncMock()

            record = await deployer.deploy("1.0.0")

            assert record.status == DeploymentStatus.COMPLETED
            assert record.version == "1.0.0"
            assert record.error_message is None

            deployer._deploy_to_environment.assert_called_once()
            deployer._run_health_checks.assert_called_once()
            deployer._switch_traffic.assert_called_once()

    @pytest.mark.asyncio
    async def test_deploy_health_check_failure(self, deployer: BlueGreenDeployer):
        """Test deployment fails on health check"""
        deployer.config.rollback_on_failure = False

        async with deployer:
            deployer._deploy_to_environment = AsyncMock()
            deployer._run_health_checks = AsyncMock(return_value=False)
            deployer._switch_traffic = AsyncMock()

            record = await deployer.deploy("1.0.0")

            assert record.status == DeploymentStatus.FAILED
            assert "Health checks failed" in record.error_message
            deployer._switch_traffic.assert_not_called()

    @pytest.mark.asyncio
    async def test_deploy_with_auto_rollback(
        self,
        deployer: BlueGreenDeployer,
        temp_history_dir: Path,
    ):
        """Test automatic rollback on failure"""
        # Add previous successful deployment
        prev_record = DeploymentRecord(
            id="deploy-prev",
            version="0.9.0",
            environment=DeploymentEnvironment.BLUE,
            status=DeploymentStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
        )
        deployer.history.add(prev_record)

        deployer.config.rollback_on_failure = True

        async with deployer:
            deployer._deploy_to_environment = AsyncMock()
            deployer._run_health_checks = AsyncMock(return_value=False)
            deployer._switch_traffic = AsyncMock()

            record = await deployer.deploy("1.0.0")

            assert record.status == DeploymentStatus.FAILED
            # Rollback should have been called
            assert deployer._switch_traffic.call_count == 1

    @pytest.mark.asyncio
    async def test_rollback_success(
        self,
        deployer: BlueGreenDeployer,
        temp_history_dir: Path,
    ):
        """Test manual rollback"""
        # Add previous successful deployment
        prev_record = DeploymentRecord(
            id="deploy-prev",
            version="0.9.0",
            environment=DeploymentEnvironment.BLUE,
            status=DeploymentStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
        )
        deployer.history.add(prev_record)

        # Add current failed deployment
        curr_record = DeploymentRecord(
            id="deploy-curr",
            version="1.0.0",
            environment=DeploymentEnvironment.GREEN,
            status=DeploymentStatus.FAILED,
            started_at=datetime.now(timezone.utc),
        )
        deployer.history.add(curr_record)

        async with deployer:
            deployer._switch_traffic = AsyncMock()

            rollback_record = await deployer.rollback()

            assert rollback_record is not None
            assert rollback_record.status == DeploymentStatus.ROLLED_BACK
            assert rollback_record.version == "0.9.0"
            assert rollback_record.rollback_from == "deploy-curr"

    @pytest.mark.asyncio
    async def test_rollback_no_previous(self, deployer: BlueGreenDeployer):
        """Test rollback when no previous deployment"""
        async with deployer:
            deployer._switch_traffic = AsyncMock()

            rollback_record = await deployer.rollback()

            assert rollback_record is None
            deployer._switch_traffic.assert_not_called()


# ==================== INTEGRATION-LIKE TESTS ====================


class TestDeploymentIntegration:
    """Integration-style tests for deployment workflow"""

    @pytest.mark.asyncio
    async def test_full_deployment_cycle(
        self,
        deployment_config: DeploymentConfig,
        temp_history_dir: Path,
    ):
        """Test complete deployment cycle: deploy -> deploy -> rollback"""
        deployer = BlueGreenDeployer(
            config=deployment_config,
            history_dir=temp_history_dir,
        )

        async with deployer:
            # Mock external operations
            deployer._deploy_to_environment = AsyncMock()
            deployer._run_health_checks = AsyncMock(return_value=True)
            deployer._switch_traffic = AsyncMock()

            # First deployment (blue -> green)
            record1 = await deployer.deploy("1.0.0")
            assert record1.status == DeploymentStatus.COMPLETED
            assert record1.environment == DeploymentEnvironment.GREEN

            # Second deployment (green -> blue)
            record2 = await deployer.deploy("1.1.0")
            assert record2.status == DeploymentStatus.COMPLETED
            assert record2.environment == DeploymentEnvironment.BLUE

            # Rollback (blue -> green)
            rollback_record = await deployer.rollback()
            assert rollback_record is not None
            assert rollback_record.status == DeploymentStatus.ROLLED_BACK
            assert rollback_record.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_deployment_status_tracking(
        self,
        deployment_config: DeploymentConfig,
        temp_history_dir: Path,
    ):
        """Test that deployment status is properly tracked"""
        deployer = BlueGreenDeployer(
            config=deployment_config,
            history_dir=temp_history_dir,
        )

        status_progression = []

        original_update = deployer.history.update_latest

        def track_status(**kwargs: Any) -> None:
            if "status" in kwargs:
                status_progression.append(kwargs["status"])
            original_update(**kwargs)

        deployer.history.update_latest = track_status

        async with deployer:
            deployer._deploy_to_environment = AsyncMock()
            deployer._run_health_checks = AsyncMock(return_value=True)
            deployer._switch_traffic = AsyncMock()

            await deployer.deploy("1.0.0")

        expected = [
            "deploying",
            "health_check",
            "switching_traffic",
            "completed",
        ]
        assert status_progression == expected


# ==================== EDGE CASE TESTS ====================


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_deploy_exception_handling(self, deployer: BlueGreenDeployer):
        """Test deployment handles exceptions gracefully"""
        deployer.config.rollback_on_failure = False

        async with deployer:
            deployer._deploy_to_environment = AsyncMock(side_effect=Exception("Docker error"))

            record = await deployer.deploy("1.0.0")

            assert record.status == DeploymentStatus.FAILED
            assert "Docker error" in record.error_message

    def test_history_corrupted_file(self, temp_history_dir: Path):
        """Test history handles corrupted JSON file"""
        history_file = temp_history_dir / "corrupted.json"
        history_file.write_text("not valid json {{{")

        history = DeploymentHistory(history_file)

        # Should initialize with empty history
        assert history.get_latest() is None

    def test_history_empty_file(self, temp_history_dir: Path):
        """Test history handles empty file"""
        history_file = temp_history_dir / "empty.json"
        history_file.touch()

        history = DeploymentHistory(history_file)

        assert history.get_latest() is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
