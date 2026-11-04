#!/usr/bin/env python3
"""
P1.SCR.4: Reset Test Environment Script
Purpose: Clean and reinitialize test environment for fresh test runs
Features:
  - Stop and remove Docker containers
  - Clean Python cache and test artifacts
  - Reset database and Redis
  - Validate environment readiness
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

# ANSI Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


class TestEnvironmentReset:
    """Reset and validate test environment"""

    def __init__(self):
        self.workspace_root = Path(__file__).parent
        self.results = {
            "success": [],
            "warnings": [],
            "errors": [],
        }
        self.start_time = datetime.now(timezone.utc)

    def log_success(self, msg: str):
        print(f"{GREEN}[✓]{RESET} {msg}")
        self.results["success"].append(msg)

    def log_warning(self, msg: str):
        print(f"{YELLOW}[!]{RESET} {msg}")
        self.results["warnings"].append(msg)

    def log_error(self, msg: str):
        print(f"{RED}[✗]{RESET} {msg}")
        self.results["errors"].append(msg)

    def log_info(self, msg: str):
        print(f"{BLUE}[i]{RESET} {msg}")

    def run_command(self, cmd: str, description: str = "", cwd=None) -> Tuple[bool, str]:
        """Run shell command and return success status and output"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=cwd or self.workspace_root,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            self.log_error(f"{description}: Command timeout")
            return False, "Timeout"
        except Exception as e:
            self.log_error(f"{description}: {str(e)}")
            return False, str(e)

    def cleanup_python_cache(self) -> bool:
        """Clean Python cache directories and files"""
        self.log_info("Cleaning Python cache files...")
        cache_dirs = [
            "__pycache__",
            ".pytest_cache",
            "*.egg-info",
            ".tox",
            ".coverage",
            "htmlcov",
        ]

        for pattern in cache_dirs:
            for path in self.workspace_root.rglob(pattern):
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                        self.log_success(
                            f"Removed directory: {path.relative_to(self.workspace_root)}"
                        )
                    elif path.is_file():
                        path.unlink()
                        self.log_success(f"Removed file: {path.relative_to(self.workspace_root)}")
                except Exception as e:
                    self.log_warning(f"Could not remove {path}: {str(e)}")

        return True

    def cleanup_test_artifacts(self) -> bool:
        """Clean test artifacts and temporary files"""
        self.log_info("Cleaning test artifacts...")
        artifacts = [
            ".coverage",
            "coverage.xml",
            "htmlcov",
            "dist",
            "build",
            ".mypy_cache",
            "*.pyc",
        ]

        for pattern in artifacts:
            for path in self.workspace_root.glob(pattern):
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                        self.log_success(f"Removed artifact directory: {path.name}")
                    else:
                        path.unlink()
                        self.log_success(f"Removed artifact file: {path.name}")
                except Exception as e:
                    self.log_warning(f"Could not remove {path}: {str(e)}")

        return True

    def stop_docker_containers(self) -> bool:
        """Stop all Docker containers gracefully"""
        self.log_info("Stopping Docker containers...")

        # List of docker-compose files to stop
        compose_files = [
            "docker-compose.dev.yml",
            "docker-compose.test.yml",
            "docker-compose.test.prod.yml",
            "docker-compose.test.optimized.yml",
        ]

        for compose_file in compose_files:
            compose_path = self.workspace_root / compose_file
            if compose_path.exists():
                self.log_info(f"Stopping containers from {compose_file}...")
                success, output = self.run_command(
                    f"docker-compose -f {compose_file} down -v --remove-orphans",
                    f"Stop containers ({compose_file})",
                )
                if success:
                    self.log_success(f"Stopped containers from {compose_file}")
                else:
                    self.log_warning(f"Could not stop containers from {compose_file}")
            else:
                self.log_warning(f"Docker compose file not found: {compose_file}")

        return True

    def remove_docker_volumes(self) -> bool:
        """Remove Docker volumes to ensure clean state"""
        self.log_info("Cleaning Docker volumes...")
        success, output = self.run_command(
            "docker volume prune -f",
            "Remove unused Docker volumes",
        )
        if success:
            self.log_success("Docker volumes pruned")
        else:
            self.log_warning("Could not prune Docker volumes")

        return True

    def validate_docker(self) -> bool:
        """Validate Docker is running and accessible"""
        self.log_info("Validating Docker installation...")
        success, output = self.run_command("docker --version", "Docker version check")
        if success:
            self.log_success(f"Docker ready: {output.strip()}")
            return True
        else:
            self.log_error("Docker is not running or not installed")
            return False

    def validate_python(self) -> bool:
        """Validate Python environment"""
        self.log_info("Validating Python environment...")
        success, output = self.run_command("python --version", "Python version check")
        if success:
            self.log_success(f"Python ready: {output.strip()}")
            return True
        else:
            self.log_error("Python not found in PATH")
            return False

    def validate_pip_packages(self) -> bool:
        """Check required pip packages are installed"""
        self.log_info("Validating pip packages...")
        required_packages = ["pytest", "sqlalchemy", "fastapi", "httpx"]

        for package in required_packages:
            success, _ = self.run_command(
                f"python -c 'import {package}'",
                f"Check {package}",
            )
            if success:
                self.log_success(f"Package '{package}' is installed")
            else:
                self.log_warning(f"Package '{package}' is not installed")

        return True

    def cleanup_db_connections(self) -> bool:
        """Close any lingering database connections"""
        self.log_info("Cleaning database connections...")
        # This is mainly handled by Docker cleanup, but we log it
        self.log_success("Database connection cleanup handled by Docker shutdown")
        return True

    def reset_mlflow(self) -> bool:
        """Reset MLflow runs (local artifact store)"""
        self.log_info("Resetting MLflow artifacts...")
        mlruns_path = self.workspace_root / "mlruns"
        if mlruns_path.exists():
            try:
                shutil.rmtree(mlruns_path)
                self.log_success("MLflow artifacts directory cleared")
            except Exception as e:
                self.log_warning(f"Could not clear MLflow: {str(e)}")
        return True

    def create_reset_summary(self) -> str:
        """Create a summary of reset operations"""
        elapsed = datetime.now(timezone.utc) - self.start_time
        summary = f"""
{BLUE}═══════════════════════════════════════════════════════════════
            TEST ENVIRONMENT RESET SUMMARY
            Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}
            Duration: {elapsed.total_seconds():.2f}s
═══════════════════════════════════════════════════════════════{RESET}

{GREEN}✓ SUCCESSFUL OPERATIONS ({len(self.results['success'])}){RESET}
{chr(10).join(f'  • {item}' for item in self.results['success'])}

{YELLOW}! WARNINGS ({len(self.results['warnings'])}){RESET}
{chr(10).join(f'  • {item}' for item in self.results['warnings']) if self.results['warnings'] else '  (none)'}

{RED}✗ ERRORS ({len(self.results['errors'])}){RESET}
{chr(10).join(f'  • {item}' for item in self.results['errors']) if self.results['errors'] else '  (none)'}

{BLUE}═══════════════════════════════════════════════════════════════{RESET}

{BLUE}Next Steps:{RESET}
1. Run: docker-compose -f docker-compose.dev.yml up -d
2. Wait for services: python scripts/wait_for_services.py
3. Run tests: python -m pytest tests/unit/ -v --tb=short
"""
        return summary

    def run_all_resets(self) -> bool:
        """Execute all reset operations in sequence"""
        print(f"\n{BLUE}{'='*70}")
        print("       P1.SCR.4: TEST ENVIRONMENT RESET")
        print(f"{'='*70}{RESET}\n")

        steps = [
            ("Python Cache Cleanup", self.cleanup_python_cache),
            ("Test Artifacts Cleanup", self.cleanup_test_artifacts),
            ("Docker Validation", self.validate_docker),
            ("Docker Container Shutdown", self.stop_docker_containers),
            ("Docker Volume Cleanup", self.remove_docker_volumes),
            ("Python Validation", self.validate_python),
            ("Pip Packages Validation", self.validate_pip_packages),
            ("Database Connection Cleanup", self.cleanup_db_connections),
            ("MLflow Reset", self.reset_mlflow),
        ]

        failed_steps = []
        for step_name, step_func in steps:
            self.log_info(f"Executing: {step_name}...")
            try:
                if not step_func():
                    failed_steps.append(step_name)
            except Exception as e:
                self.log_error(f"{step_name} failed with exception: {str(e)}")
                failed_steps.append(step_name)

        # Print summary
        summary = self.create_reset_summary()
        print(summary)

        # Save summary to file
        summary_file = self.workspace_root / "RESET_SUMMARY.log"
        try:
            with open(summary_file, "w") as f:
                f.write(summary)
            self.log_success("Summary saved to RESET_SUMMARY.log")
        except Exception as e:
            self.log_warning(f"Could not save summary: {str(e)}")

        return len(failed_steps) == 0


def main():
    """Main entry point"""
    reset = TestEnvironmentReset()
    success = reset.run_all_resets()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
