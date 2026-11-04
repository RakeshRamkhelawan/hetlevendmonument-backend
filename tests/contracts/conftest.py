"""
Contract Tests - Fixture Configuration
========================================

Contract tests validate API response schemas and behavior.
They use the SAME database infrastructure as unit tests (in-memory SQLite).

Fixtures: Inherit from parent tests/conftest.py (no overrides needed)
Database: In-memory SQLite (fast, for unit/contract testing)

This directory can add contract-specific fixtures if needed.
For now, it's minimal and relies on parent conftest.py.
"""

# No overrides needed - contract tests use in-memory SQLite from parent conftest.py
# If needed in future, define contract-specific fixtures here
