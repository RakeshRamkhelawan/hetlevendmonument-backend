"""
Script: reset_test_environment.py
Description: This script performs a nuclear reset of the test environment by:
- Stopping and removing all Docker containers, networks, volumes, and images.
- Clearing Redis cache.
- Reinstalling Python dependencies.

Usage:
    python scripts/reset_test_environment.py

Author: SanskritiSetu.org Dev Team
Date: December 8, 2025
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(command: str) -> None:
    """
    Executes a shell command and streams the output in real-time.

    Args:
        command (str): The shell command to execute.

    Raises:
        RuntimeError: If the command fails.
    """
    process = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    for line in process.stdout:
        print(line, end="")
    for line in process.stderr:
        print(line, end="")
    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"Command failed: {command}")


def stop_and_remove_docker_containers() -> None:
    """
    Stops and removes all Docker containers, networks, volumes, and images.
    """
    print("Stopping and removing all Docker containers, networks, volumes, and images...")
    run_command("docker-compose down --volumes --remove-orphans")
    run_command("docker system prune --all --force --volumes")


def clear_redis_cache(redis_url: str) -> None:
    """
    Clears the Redis cache.

    Args:
        redis_url (str): The Redis connection URL.
    """
    print("Clearing Redis cache...")
    run_command(f"redis-cli -u {redis_url} FLUSHALL")


def reinstall_dependencies() -> None:
    """
    Reinstalls Python dependencies using pip.
    """
    print("Reinstalling Python dependencies...")
    requirements_file = Path("requirements.txt")
    if not requirements_file.exists():
        raise FileNotFoundError("requirements.txt not found in the current directory.")
    run_command(f"{sys.executable} -m pip install --upgrade pip")
    run_command(f"{sys.executable} -m pip install -r requirements.txt")


def main() -> None:
    """
    Main function to reset the test environment.
    """
    try:
        # Environment variables
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

        # Step 1: Stop and remove Docker containers
        stop_and_remove_docker_containers()

        # Step 2: Clear Redis cache
        clear_redis_cache(redis_url)

        # Step 3: Reinstall Python dependencies
        reinstall_dependencies()

        print("\nTest environment reset successfully.")
    except Exception as e:
        print(f"Error during reset: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
