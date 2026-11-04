import pytest

# Skip entire module - requires real LLM and database
pytestmark = pytest.mark.skip(reason="Requires real LLM API and running database - run manually")

import asyncio
import time

from prometheus_client import REGISTRY

from src.core.database.database import db_manager
from src.core.models.rbac_models import Tenant
from src.core.services.llm.service import LLMService


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_semantic_cache_zero_mock():
    """
    Zero-Mock Integration Test: Proves cache works with real LLM and DB.
    Uses a forced output to guarantee textual match.
    """
    await db_manager.initialize()

    # 1. Create a real test tenant
    async with db_manager.get_session() as db:
        tenant = Tenant(name="E2E Cache Test", slug="e2e-cache-test", is_active=True)
        db.add(tenant)
        await db.flush()
        tenant_id = tenant.id
        await db.commit()

    try:
        service = LLMService(enable_cache=True)
        # Forced prompt for deterministic-like behavior
        prompt = "Antwoord met alleen het getal 42."
        messages = [{"role": "user", "content": prompt}]

        # --- CALL 1: REAL LLM ---
        start_time = time.time()
        res1, usage1 = await service.generate(messages, tenant_id=tenant_id, return_usage=True)
        duration1 = time.time() - start_time

        assert "42" in res1
        assert usage1["total_tokens"] > 0
        print(f"\n[Call 1] Real LLM took {duration1:.2f}s, Tokens: {usage1['total_tokens']}")

        # Wait for cache persistence
        await asyncio.sleep(2)

        # --- CALL 2: CACHE HIT ---
        start_time = time.time()
        res2, usage2 = await service.generate(messages, tenant_id=tenant_id, return_usage=True)
        duration2 = time.time() - start_time

        assert res2 == res1
        assert usage2["total_tokens"] == 0
        assert usage2["model"] == "cache"
        print(f"[Call 2] Cache Hit took {duration2:.4f}s, Tokens: 0")

        # --- VALIDATE SUCCESS ---
        # 1. Verification via latency and token usage (The most reliable proof)
        assert res2 == res1
        assert usage2["total_tokens"] == 0
        assert usage2["model"] == "cache"
        assert duration2 < duration1 / 10  # Must be significantly faster

        print(
            f"✅ Integratietest geslaagd: Latency reductie van {duration1:.2f}s naar {duration2:.4f}s."
        )
        print("✅ Tokens bespaard: 100% op tweede call.")

    finally:
        # Cleanup
        async with db_manager.get_session() as db:
            from sqlalchemy import delete

            await db.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await db.commit()
