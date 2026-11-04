from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.database.database import Base
from src.core.learning.models import LearningExperience  # noqa: F401
from src.core.learning.persistence_models import AdaptationRuleModel  # noqa: F401
from src.core.learning.persistence_models import LearningInsightModel  # noqa: F401
from src.core.learning.persistence_models import LearningPatternModel  # noqa: F401
from src.core.shared.config import reload_settings


@pytest.fixture
def phase2_learning_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()
    yield monkeypatch
    monkeypatch.delenv("FEATURE_LEARNING_ENABLED", raising=False)
    reload_settings()


@pytest_asyncio.fixture
async def phase2_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    await engine.dispose()
