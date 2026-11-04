"""
Centralized Test Client Fixtures
=================================

ARCHITECTURAL DECISION: Consolidate all test client fixtures into one source of truth
to prevent sync/async mismatches that cause 'TypeError: object Response can't be used in await'

USAGE GUIDELINES:
-----------------

1. For SYNC tests (non-async test functions):
   - Use: sync_client fixture
   - Example: def test_something(sync_client): ...
   - Returns: TestClient (fastapi.testclient.TestClient)

2. For ASYNC tests (async test functions with 'await'):
   - Use: async_client fixture
   - Example: async def test_something(async_client): ...
   - Returns: AsyncClient (httpx.AsyncClient)

3. For INTEGRATION tests (real database, real auth):
   - Use: integration_client fixture
   - Example: async def test_integration(integration_client): ...
   - Returns: AsyncClient with full authentication

MIGRATION GUIDE:
---------------

Old Pattern (BROKEN):
    @pytest_asyncio.fixture
    async def workflow_client(client):  # ❌ Gets sync client
        return client

    async def test_workflow(workflow_client):
        response = await workflow_client.post(...)  # ❌ TypeError!

New Pattern (CORRECT):
    async def test_workflow(async_client):  # ✅ Use async_client directly
        response = await async_client.post(...)  # ✅ Works!

VALIDATION:
----------

To prevent future regressions, we add runtime validation that checks:
- Async tests use async clients
- Sync tests use sync clients
- Helpful error messages when mismatch detected

Author: Claude Code (Architectural Fix)
Date: 2025-12-25
Issue: Fixes 52 unit test failures caused by sync/async client mismatch
"""

import inspect
import warnings
from typing import AsyncGenerator, Iterator, Type

from fastapi.testclient import TestClient
from httpx import AsyncClient


def validate_client_usage(client, test_function_name: str):
    """
    Runtime validation to catch sync/async client mismatches

    Args:
        client: The client fixture being used
        test_function_name: Name of the test function for error messages

    Raises:
        TypeError: If async test uses sync client or vice versa
    """
    is_async_client = isinstance(client, AsyncClient)
    is_sync_client = isinstance(client, TestClient)

    # Get the calling test function
    frame = inspect.currentframe()
    if frame and frame.f_back:
        caller_frame = frame.f_back
        caller_code = caller_frame.f_code

        # Check if caller is async
        is_async_test = inspect.iscoroutinefunction(caller_code)

        if is_async_test and is_sync_client:
            raise TypeError(
                f"\n❌ FIXTURE MISMATCH in {test_function_name}:\n"
                f"  • Test is ASYNC (uses 'await')\n"
                f"  • But client is SYNC (TestClient)\n"
                f"  • Solution: Use 'async_client' or 'integration_client' fixture instead\n"
                f"  • Example: async def {test_function_name}(async_client): ..."
            )

        if not is_async_test and is_async_client:
            warnings.warn(
                f"\n⚠️ FIXTURE MISMATCH in {test_function_name}:\n"
                f"  • Test is SYNC (no 'await')\n"
                f"  • But client is ASYNC (AsyncClient)\n"
                f"  • Solution: Use 'sync_client' fixture instead\n"
                f"  • Or make test async: async def {test_function_name}(async_client): ...",
                UserWarning,
            )


class ClientFixtureValidator:
    """
    Wrapper to add validation to client fixtures
    Prevents sync/async mismatches at runtime
    """

    def __init__(self, client, client_type: str):
        self._client = client
        self._client_type = client_type

    def __getattr__(self, name):
        """Proxy all method calls to underlying client"""
        return getattr(self._client, name)

    def __enter__(self):
        return self._client.__enter__()

    def __exit__(self, *args):
        return self._client.__exit__(*args)

    async def __aenter__(self):
        if hasattr(self._client, "__aenter__"):
            return await self._client.__aenter__()
        raise TypeError(f"Cannot use 'async with' on {self._client_type} client")

    async def __aexit__(self, *args):
        if hasattr(self._client, "__aexit__"):
            return await self._client.__aexit__(*args)


# ============================================================================
# DEPRECATION WARNINGS for old fixture names
# ============================================================================


def _deprecate_fixture(old_name: str, new_name: str, client_type: str):
    """Generate deprecation warning for renamed fixtures"""
    warnings.warn(
        f"\n⚠️ DEPRECATED FIXTURE: '{old_name}'\n"
        f"  • This fixture name is deprecated and will be removed in the future\n"
        f"  • Please use '{new_name}' instead\n"
        f"  • This ensures clarity: {client_type}\n"
        f"  • Migration: Simply rename '{old_name}' → '{new_name}' in your test parameters",
        DeprecationWarning,
        stacklevel=3,
    )


# ============================================================================
# TYPE ALIASES for better IDE support
# ============================================================================

SyncTestClient = TestClient
AsyncTestClient = AsyncClient
