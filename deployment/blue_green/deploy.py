"""
Blue-Green Deployment Controller for SanskritiSetu.org

This module implements zero-downtime blue-green deployment strategy
with automatic rollback capabilities.

Features:
- Zero-downtime deployments
- Automatic health checks
- Traffic switching via nginx/kubernetes
- Rollback on failure
- Deployment history tracking

Usage:
    python deploy.py deploy --version 1.2.3
    python deploy.py rollback
    python deploy.py status
"""

import asyncio
import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DeploymentEnvironment(Enum):
    """Active deployment environment"""
    BLUE = "blue"
    GREEN = "green"


class DeploymentStatus(Enum):
    """Deployment status states"""
    PENDING = "pending"
    DEPLOYING = "deploying"
    HEALTH_CHECK = "health_check"
    SWITCHING_TRAFFIC = "switching_traffic"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class HealthCheckConfig:
    """Health check configuration"""
    endpoint: str = "/health"
    timeout: int = 30
    retries: int = 3
    interval: int = 10
    success_threshold: int = 2


@dataclass
class DeploymentConfig:
    """Deployment configuration"""
    project_name: str = "sanskritisetu"
    docker_registry: str = "ghcr.io/rakeshramkhelawan"
    image_name: str = "sanskritisetu-backend"
    replicas: int = 3
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    deployment_timeout: int = 300  # 5 minutes
    rollback_on_failure: bool = True

    # Port mapping
    blue_port: int = 8001
    green_port: int = 8002
    nginx_port: int = 80


@dataclass
class DeploymentRecord:
    """Record of a deployment"""
    id: str
    version: str
    environment: DeploymentEnvironment
    status: DeploymentStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    rollback_from: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "environment": self.environment.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "rollback_from": self.rollback_from,
        }


class DeploymentHistory:
    """Manages deployment history"""

    def __init__(self, history_file: Path):
        self.history_file = history_file
        self._history: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """Load history from file"""
        if self.history_file.exists():
            try:
                with open(self.history_file) as f:
                    self._history = json.load(f)
            except json.JSONDecodeError:
                self._history = []
        else:
            self._history = []

    def _save(self) -> None:
        """Save history to file"""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, "w") as f:
            json.dump(self._history, f, indent=2)

    def add(self, record: DeploymentRecord) -> None:
        """Add deployment record"""
        self._history.append(record.to_dict())
        self._save()

    def update_latest(self, **updates: Any) -> None:
        """Update the latest deployment record"""
        if self._history:
            self._history[-1].update(updates)
            if "completed_at" in updates and updates["completed_at"]:
                self._history[-1]["completed_at"] = updates["completed_at"].isoformat()
            self._save()

    def get_latest(self) -> Optional[dict[str, Any]]:
        """Get the latest deployment"""
        return self._history[-1] if self._history else None

    def get_active_environment(self) -> DeploymentEnvironment:
        """Get the currently active environment"""
        latest = self.get_latest()
        if latest and latest.get("status") == DeploymentStatus.COMPLETED.value:
            return DeploymentEnvironment(latest["environment"])
        return DeploymentEnvironment.BLUE  # Default to blue

    def get_previous_successful(self) -> Optional[dict[str, Any]]:
        """Get the previous successful deployment"""
        for record in reversed(self._history[:-1]):
            if record.get("status") == DeploymentStatus.COMPLETED.value:
                return record
        return None


class BlueGreenDeployer:
    """
    Blue-Green Deployment Controller

    Implements zero-downtime deployment strategy:
    1. Deploy new version to inactive environment
    2. Run health checks on new deployment
    3. Switch traffic from active to new environment
    4. Keep old environment as rollback target
    """

    def __init__(
        self,
        config: Optional[DeploymentConfig] = None,
        history_dir: Optional[Path] = None,
    ):
        self.config = config or DeploymentConfig()
        history_dir = history_dir or Path("deployment/history")
        self.history = DeploymentHistory(history_dir / "deployments.json")
        self._http_client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "BlueGreenDeployer":
        self._http_client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._http_client:
            await self._http_client.aclose()

    def _generate_deployment_id(self) -> str:
        """Generate unique deployment ID"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"deploy-{timestamp}"

    def _get_target_environment(self) -> DeploymentEnvironment:
        """Get the target environment (opposite of current active)"""
        active = self.history.get_active_environment()
        return DeploymentEnvironment.GREEN if active == DeploymentEnvironment.BLUE else DeploymentEnvironment.BLUE

    def _get_environment_port(self, env: DeploymentEnvironment) -> int:
        """Get port for environment"""
        return self.config.blue_port if env == DeploymentEnvironment.BLUE else self.config.green_port

    async def deploy(self, version: str) -> DeploymentRecord:
        """
        Execute blue-green deployment

        Args:
            version: Version tag to deploy

        Returns:
            DeploymentRecord with deployment status
        """
        deployment_id = self._generate_deployment_id()
        target_env = self._get_target_environment()

        record = DeploymentRecord(
            id=deployment_id,
            version=version,
            environment=target_env,
            status=DeploymentStatus.PENDING,
            started_at=datetime.now(timezone.utc),
        )
        self.history.add(record)

        logger.info(f"[DEPLOY] Starting deployment {deployment_id}")
        logger.info(f"[DEPLOY] Version: {version}")
        logger.info(f"[DEPLOY] Target environment: {target_env.value}")

        try:
            # Step 1: Deploy to target environment
            record.status = DeploymentStatus.DEPLOYING
            self.history.update_latest(status=DeploymentStatus.DEPLOYING.value)
            await self._deploy_to_environment(target_env, version)

            # Step 2: Run health checks
            record.status = DeploymentStatus.HEALTH_CHECK
            self.history.update_latest(status=DeploymentStatus.HEALTH_CHECK.value)
            health_ok = await self._run_health_checks(target_env)

            if not health_ok:
                raise Exception("Health checks failed")

            # Step 3: Switch traffic
            record.status = DeploymentStatus.SWITCHING_TRAFFIC
            self.history.update_latest(status=DeploymentStatus.SWITCHING_TRAFFIC.value)
            await self._switch_traffic(target_env)

            # Step 4: Mark complete
            record.status = DeploymentStatus.COMPLETED
            record.completed_at = datetime.now(timezone.utc)
            self.history.update_latest(
                status=DeploymentStatus.COMPLETED.value,
                completed_at=record.completed_at,
            )

            logger.info(f"[OK] Deployment {deployment_id} completed successfully")
            return record

        except Exception as e:
            logger.error(f"[FAIL] Deployment failed: {e}")
            record.status = DeploymentStatus.FAILED
            record.error_message = str(e)
            record.completed_at = datetime.now(timezone.utc)
            self.history.update_latest(
                status=DeploymentStatus.FAILED.value,
                error_message=str(e),
                completed_at=record.completed_at,
            )

            if self.config.rollback_on_failure:
                logger.info("[ROLLBACK] Initiating automatic rollback...")
                await self.rollback()

            return record

    async def _deploy_to_environment(
        self,
        env: DeploymentEnvironment,
        version: str,
    ) -> None:
        """Deploy new version to target environment"""
        logger.info(f"[DEPLOY] Deploying version {version} to {env.value} environment")

        image = f"{self.config.docker_registry}/{self.config.image_name}:{version}"
        port = self._get_environment_port(env)

        # Docker Compose deployment
        compose_file = f"docker-compose.{env.value}.yml"

        # Pull new image
        logger.info(f"[DEPLOY] Pulling image: {image}")
        await self._run_command(["docker", "pull", image])

        # Stop existing containers in target environment
        logger.info(f"[DEPLOY] Stopping existing {env.value} containers")
        await self._run_command([
            "docker-compose",
            "-f", compose_file,
            "-p", f"{self.config.project_name}-{env.value}",
            "down",
        ])

        # Start new containers
        logger.info(f"[DEPLOY] Starting new {env.value} containers")
        await self._run_command([
            "docker-compose",
            "-f", compose_file,
            "-p", f"{self.config.project_name}-{env.value}",
            "up", "-d",
            "--scale", f"backend={self.config.replicas}",
        ])

        # Wait for containers to be ready
        await asyncio.sleep(10)

    async def _run_health_checks(self, env: DeploymentEnvironment) -> bool:
        """
        Run health checks on target environment

        Returns:
            True if all health checks pass
        """
        logger.info(f"[HEALTH] Running health checks on {env.value} environment")

        port = self._get_environment_port(env)
        health_url = f"http://localhost:{port}{self.config.health_check.endpoint}"

        success_count = 0

        for attempt in range(self.config.health_check.retries):
            try:
                logger.info(f"[HEALTH] Check {attempt + 1}/{self.config.health_check.retries}")

                if self._http_client:
                    response = await self._http_client.get(
                        health_url,
                        timeout=self.config.health_check.timeout,
                    )

                    if response.status_code == 200:
                        success_count += 1
                        logger.info(f"[OK] Health check passed ({success_count}/{self.config.health_check.success_threshold})")

                        if success_count >= self.config.health_check.success_threshold:
                            logger.info("[OK] All health checks passed")
                            return True
                    else:
                        logger.warning(f"[WARN] Health check returned {response.status_code}")
                        success_count = 0

            except Exception as e:
                logger.warning(f"[WARN] Health check failed: {e}")
                success_count = 0

            await asyncio.sleep(self.config.health_check.interval)

        logger.error("[FAIL] Health checks did not pass")
        return False

    async def _switch_traffic(self, target_env: DeploymentEnvironment) -> None:
        """Switch traffic to target environment via nginx"""
        logger.info(f"[TRAFFIC] Switching traffic to {target_env.value} environment")

        # Update nginx configuration
        nginx_config = self._generate_nginx_config(target_env)
        config_path = Path("nginx/nginx.active.conf")
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            f.write(nginx_config)

        # Reload nginx
        logger.info("[TRAFFIC] Reloading nginx configuration")
        await self._run_command([
            "docker-compose",
            "-f", "docker-compose.production.yml",
            "exec", "-T", "nginx",
            "nginx", "-s", "reload",
        ])

        logger.info(f"[OK] Traffic now routing to {target_env.value}")

    def _generate_nginx_config(self, active_env: DeploymentEnvironment) -> str:
        """Generate nginx upstream configuration for active environment"""
        port = self._get_environment_port(active_env)

        return f"""# Auto-generated nginx upstream configuration
# Active environment: {active_env.value}
# Generated: {datetime.now(timezone.utc).isoformat()}

upstream backend {{
    least_conn;

    # {active_env.value.upper()} environment backends
    server backend-{active_env.value}-1:{port} weight=1;
    server backend-{active_env.value}-2:{port} weight=1;
    server backend-{active_env.value}-3:{port} weight=1;

    keepalive 32;
}}

server {{
    listen 80;
    listen 443 ssl http2;

    server_name sanskritisetu.org *.sanskritisetu.org;

    # SSL configuration
    ssl_certificate /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Health check endpoint
    location /health {{
        proxy_pass http://backend/health;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }}

    # API endpoints
    location /api/ {{
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";

        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Buffering
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }}

    # WebSocket support
    location /ws/ {{
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }}

    # Frontend static files
    location / {{
        root /var/www/html;
        try_files $uri $uri/ /index.html;
    }}
}}
"""

    async def rollback(self) -> Optional[DeploymentRecord]:
        """
        Rollback to previous successful deployment

        Returns:
            DeploymentRecord if rollback successful, None otherwise
        """
        previous = self.history.get_previous_successful()

        if not previous:
            logger.error("[ROLLBACK] No previous successful deployment found")
            return None

        logger.info(f"[ROLLBACK] Rolling back to version {previous['version']}")
        logger.info(f"[ROLLBACK] Target environment: {previous['environment']}")

        # Switch traffic back to previous environment
        target_env = DeploymentEnvironment(previous["environment"])
        await self._switch_traffic(target_env)

        # Record rollback
        rollback_record = DeploymentRecord(
            id=self._generate_deployment_id(),
            version=previous["version"],
            environment=target_env,
            status=DeploymentStatus.ROLLED_BACK,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            rollback_from=self.history.get_latest()["id"] if self.history.get_latest() else None,
        )
        self.history.add(rollback_record)

        logger.info(f"[OK] Rollback completed to version {previous['version']}")
        return rollback_record

    def get_status(self) -> dict[str, Any]:
        """Get current deployment status"""
        latest = self.history.get_latest()
        active_env = self.history.get_active_environment()

        return {
            "active_environment": active_env.value,
            "latest_deployment": latest,
            "config": {
                "project_name": self.config.project_name,
                "replicas": self.config.replicas,
                "blue_port": self.config.blue_port,
                "green_port": self.config.green_port,
            }
        }

    async def _run_command(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        """Run shell command"""
        logger.debug(f"[CMD] Running: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise Exception(f"Command failed: {error_msg}")

        return subprocess.CompletedProcess(
            cmd, process.returncode,
            stdout.decode(), stderr.decode()
        )


# CLI Interface
async def main() -> None:
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Blue-Green Deployment Controller")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Deploy command
    deploy_parser = subparsers.add_parser("deploy", help="Deploy new version")
    deploy_parser.add_argument("--version", "-v", required=True, help="Version to deploy")
    deploy_parser.add_argument("--no-rollback", action="store_true", help="Disable auto-rollback")

    # Rollback command
    subparsers.add_parser("rollback", help="Rollback to previous version")

    # Status command
    subparsers.add_parser("status", help="Show deployment status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = DeploymentConfig(
        rollback_on_failure=not getattr(args, "no_rollback", False)
    )

    async with BlueGreenDeployer(config=config) as deployer:
        if args.command == "deploy":
            record = await deployer.deploy(args.version)
            if record.status == DeploymentStatus.FAILED:
                sys.exit(1)

        elif args.command == "rollback":
            record = await deployer.rollback()
            if not record:
                sys.exit(1)

        elif args.command == "status":
            status = deployer.get_status()
            print(json.dumps(status, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
