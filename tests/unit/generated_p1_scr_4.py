"""
Script: reset_test_environment.py
Description: Performs a nuclear reset of the test environment by:
- Stopping and removing all Docker containers and volumes.
- Clearing Redis cache.
- Reinstalling Python dependencies.
- Resetting the database.

Usage:
    python scripts/reset_test_environment.py

Author: SanskritiSetu.org
"""

import os
import subprocess
import sys
from typing import List


def run_command(command: List[str]) -> None:
    """
    Run a shell command and print its output in real-time.

    Args:
        command (List[str]): The command to execute as a list of arguments.
    """
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        for line in process.stdout:
            print(line, end="")
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command)
    except subprocess.CalledProcessError as e:
        print(f"Error: Command '{' '.join(e.cmd)}' failed with exit code {e.returncode}")
        sys.exit(e.returncode)


def stop_and_remove_docker_containers() -> None:
    """
    Stops and removes all Docker containers and volumes.
    """
    print("Stopping and removing all Docker containers and volumes...")
    run_command(["docker-compose", "-f", "docker-compose.dev.yml", "down", "-v"])


def clear_redis_cache() -> None:
    """
    Clears the Redis cache.
    """
    print("Clearing Redis cache...")
    redis_url = os.getenv(
        "REDIS_URL", "redis://localhost:6380  # Redis port updated from 6379 to 6380"
    )
    run_command(["redis-cli", "-u", redis_url, "FLUSHALL"])


def reinstall_dependencies() -> None:
    """
    Reinstalls Python dependencies.
    """
    print("Reinstalling Python dependencies...")
    run_command([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])


def reset_database() -> None:
    """
    Resets the database by running migrations.
    """
    print("Resetting the database...")
    run_command(["alembic", "downgrade", "base"])
    run_command(["alembic", "upgrade", "head"])


def main() -> None:
    """
    Main function to perform the nuclear reset of the test environment.
    """
    print("Starting nuclear reset of the test environment...")
    stop_and_remove_docker_containers()
    clear_redis_cache()
    reinstall_dependencies()
    reset_database()
    print("Test environment reset complete.")


if __name__ == "__main__":
    main()
