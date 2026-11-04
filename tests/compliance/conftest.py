"""
Compliance test fixtures — reuse integration test infrastructure.

Loads the full integration conftest so that postgres_session,
authenticated_client and other DB-backed fixtures are available
in tests/compliance/ without duplication.

Note: pytest_plugins moved to top-level tests/conftest.py for pytest 8+ compatibility.
"""
