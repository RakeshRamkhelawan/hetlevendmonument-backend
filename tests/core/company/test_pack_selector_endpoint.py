"""Integration tests for POST /api/v1/pack-selector."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

PACK_SELECTOR_URL = "/api/v1/pack-selector"

VALID_PAYLOAD = {
    "company_id": str(uuid.uuid4()),
    "department_id": str(uuid.uuid4()),
    "signals": {
        "sector": "finance",
        "company_type": "mkb",
        "department_name": "Finance",
    },
}


@pytest.fixture
def pack_selector_app():
    """Create a minimal FastAPI app with just the pack selector router."""
    from fastapi import FastAPI

    from src.core.api.v1.company.pack_selector_router import router as pack_selector_router
    from src.core.auth.dependencies import get_current_user

    app = FastAPI()
    app.include_router(pack_selector_router, prefix="/api/v1")

    # Mock authentication
    from types import SimpleNamespace

    async def override_get_current_user():
        return SimpleNamespace(
            id=1,
            sub="1",
            user_id=1,
            tenant_id=1,
            email="test@example.com",
            roles=["user"],
        )

    app.dependency_overrides[get_current_user] = override_get_current_user

    # OP-11 (2026-07-31): deze fixture overschreef alleen get_current_user, niet get_db.
    # Daardoor liep de echte databaselaag mee en faalden deze tests op
    # "Database not initialized. Call initialize_database() first." -- een ontbrekende
    # override, geen productieprobleem. Het endpoint doet eerst een tenant-isolatiecheck
    # (`company.tenant_id != current_user.tenant_id` -> 403), dus de mock-sessie moet een
    # company teruggeven die bij tenant 1 hoort.
    from unittest.mock import AsyncMock

    from src.core.api.v1.company.dependencies import get_db as company_get_db

    async def override_get_db():
        session = AsyncMock()
        session.get = AsyncMock(return_value=SimpleNamespace(id=1, tenant_id=1))
        # session.execute is awaitable, maar het RESULTAAT is synchroon:
        # `db_result.scalars().all()`. Met een kale AsyncMock levert scalars() een
        # coroutine op ('coroutine' object has no attribute 'all').
        db_result = MagicMock()
        db_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=db_result)
        # ExperimentService vraagt de actieve experimenten op; een lege lijst betekent
        # "geen A/B-test actief", het pad dat deze tests willen toetsen.
        yield session

    app.dependency_overrides[company_get_db] = override_get_db

    with patch(
        "src.core.api.v1.company.pack_selector_router.ExperimentService"
    ) as mock_experiment_service:
        mock_experiment_service.return_value.get_active_experiments = AsyncMock(return_value=[])
        yield app


@pytest.mark.asyncio
async def test_pack_selector_returns_scored_list(pack_selector_app):
    """Valid request returns a list of scored pack recommendations."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=pack_selector_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(PACK_SELECTOR_URL, json=VALID_PAYLOAD)

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


@pytest.mark.asyncio
async def test_pack_selector_requires_auth():
    """Unauthenticated requests are rejected with 401."""
    from fastapi import FastAPI, HTTPException
    from httpx import ASGITransport, AsyncClient

    from src.core.api.v1.company.pack_selector_router import router as pack_selector_router
    from src.core.auth.dependencies import get_current_user

    app = FastAPI()
    app.include_router(pack_selector_router, prefix="/api/v1")

    # Override to simulate no authentication
    async def override_no_auth():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = override_no_auth

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(PACK_SELECTOR_URL, json=VALID_PAYLOAD)

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_pack_selector_returns_r2_fields(pack_selector_app):
    """Each result contains R2-required fields: match_reason, confidence, input_signals."""
    from httpx import ASGITransport, AsyncClient

    # OP-11 (2026-07-31): deze mock gaf een PackActivationResult terug, maar
    # PackActivationScorer.score_all_packs levert een PackScore (zie de return-annotatie).
    # Het endpoint leest daarom `r.score`, en dat veld bestaat niet op
    # PackActivationResult -> AttributeError. Niet de productiecode was fout, maar het
    # model in deze mock.
    from src.core.company.pack_activation import PackScore

    mock_result = PackScore(
        pack_id=str(uuid.uuid4()),
        pack_name="Finance Pack",
        # PackScore scheidt het getal (`score`) van het label (`confidence`: EXACT/HIGH/...).
        # Het endpoint mapt `r.score` naar het numerieke confidence-veld van de response.
        score=0.85,
        confidence="HIGH",
        match_reason="sector=finance",
        input_signals=["sector:finance"],
        score_breakdown={"sector_match": 0.9},
        audit_log_id=uuid.uuid4(),
        activated_automatically=True,
    )

    with patch("src.core.api.v1.company.pack_selector_router.PackActivationScorer") as MockScorer:
        MockScorer.return_value.score_all_packs.return_value = [mock_result]

        transport = ASGITransport(app=pack_selector_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(PACK_SELECTOR_URL, json=VALID_PAYLOAD)

    assert resp.status_code == 200
    results = resp.json()
    if results:
        first = results[0]
        assert "match_reason" in first
        assert "confidence" in first
        assert "input_signals" in first
        assert "audit_log_id" in first
