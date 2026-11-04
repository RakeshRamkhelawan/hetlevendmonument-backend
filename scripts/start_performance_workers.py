"""
Start Dramatiq Workers for Performance Testing
===============================================

This script starts Dramatiq workers needed for performance tests.
It configures the environment and validates connections before starting.

Usage:
    python scripts/start_performance_workers.py
    python scripts/start_performance_workers.py --processes 4 --threads 8
    python scripts/start_performance_workers.py --dry-run  # Validate config only

Environment:
    Uses .env.test for configuration (DATABASE_URL, REDIS_URL)
    Requires Redis running on localhost:6379
    Requires PostgreSQL running (for integration tests)
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import NoReturn
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_env_test() -> dict[str, str]:
    """Load environment variables from .env.test file."""
    env_vars: dict[str, str] = {}
    env_test_path = Path(".env.test")

    if not env_test_path.exists():
        logger.warning(".env.test not found, using current environment")
        return env_vars

    with open(env_test_path, encoding="ascii") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

    return env_vars


def validate_redis_connection(redis_url: str) -> bool:
    """Validate Redis connection."""
    try:
        import redis as redis_lib  # type: ignore

        client = redis_lib.from_url(redis_url, socket_connect_timeout=5)
        client.ping()
        logger.info(f"Redis connection OK: {redis_url}")
        return True
    except ImportError:
        logger.error("redis package not installed. Install with: pip install redis")
        return False
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        logger.error("Make sure Redis is running: redis-server or docker-compose up redis")
        return False


def validate_dramatiq_installed() -> bool:
    """Check if Dramatiq is installed."""
    try:
        import dramatiq  # noqa: F401

        logger.info(f"Dramatiq version: {dramatiq.__version__}")
        return True
    except ImportError:
        logger.error("Dramatiq not installed. Install with: pip install dramatiq[redis]")
        return False


def validate_database_url(database_url: str | None) -> bool:
    """Validate DATABASE_URL is set."""
    if not database_url:
        logger.error("DATABASE_URL not set in environment")
        return False

    if "postgresql" not in database_url.lower():
        logger.warning(f"DATABASE_URL is not PostgreSQL: {database_url_zonder_wachtwoord(database_url)}")
        logger.warning("Workers may not function correctly with SQLite")

    logger.info(f"Database URL configured: {database_url_zonder_wachtwoord(database_url)}")
    return True


def setup_environment() -> dict[str, str]:
    """Set up environment variables from .env.test."""
    env_vars = load_env_test()

    # Set environment variables
    for key, value in env_vars.items():
        if key not in os.environ:
            os.environ[key] = value
            logger.debug(f"Set {key}")

    return env_vars


def start_workers(processes: int, threads: int, verbose: bool) -> NoReturn:
    """Start the Dramatiq workers."""
    logger.info("=" * 60)
    logger.info("Starting Dramatiq Workers for Performance Testing")
    logger.info("=" * 60)

    # Validate prerequisites
    if not validate_dramatiq_installed():
        sys.exit(1)

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    database_url = os.environ.get("DATABASE_URL")

    if not validate_redis_connection(redis_url):
        sys.exit(1)

    if not validate_database_url(database_url):
        sys.exit(1)

    logger.info(f"Worker configuration: {processes} processes, {threads} threads")
    logger.info(f"Redis URL: {redis_url}")
    logger.info(f"Log level: {os.environ.get('WORKER_LOG_LEVEL', 'INFO')}")
    logger.info("=" * 60)

    # Build dramatiq command
    cmd = [
        sys.executable,
        "-m",
        "dramatiq",
        "src.workers.workflow_worker",
        "--processes",
        str(processes),
        "--threads",
        str(threads),
    ]

    if verbose:
        cmd.append("--verbose")

    logger.info(f"Command: {' '.join(cmd)}")
    logger.info("Press Ctrl+C to stop the workers\n")

    try:
        # Start dramatiq worker
        subprocess.run(cmd, check=True)  # nosec B603
    except KeyboardInterrupt:
        logger.info("\nWorkers stopped by user")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        logger.error(f"Worker process exited with code {e.returncode}")
        sys.exit(e.returncode)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Start Dramatiq workers for performance testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start workers with default settings (2 processes, 4 threads)
  python scripts/start_performance_workers.py

  # Start with more workers for heavy load tests
  python scripts/start_performance_workers.py --processes 4 --threads 8

  # Validate configuration without starting workers
  python scripts/start_performance_workers.py --dry-run
        """,
    )

    parser.add_argument(
        "--processes",
        "-p",
        type=int,
        default=2,
        help="Number of worker processes (default: 2)",
    )
    parser.add_argument(
        "--threads",
        "-t",
        type=int,
        default=4,
        help="Number of threads per process (default: 4)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Validate configuration without starting workers",
    )

    args = parser.parse_args()

    # Set up environment from .env.test
    setup_environment()

    if args.dry_run:
        logger.info("DRY RUN MODE - Validating configuration only")
        validate_dramatiq_installed()
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        database_url = os.environ.get("DATABASE_URL")
        validate_redis_connection(redis_url)
        validate_database_url(database_url)
        logger.info("Configuration validation complete")
        sys.exit(0)

    # Start workers
    start_workers(args.processes, args.threads, args.verbose)


if __name__ == "__main__":
    main()
