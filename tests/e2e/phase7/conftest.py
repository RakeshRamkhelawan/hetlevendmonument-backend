from __future__ import annotations

import os
import re
from pathlib import Path
from typing import AsyncGenerator

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import JSON, Boolean, Column, Integer, String, Table, delete, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.database.database import Base, db_manager
from src.core.governance.models import AuditLog
from src.core.learning.gdpr_service import LearningGDPRService
from src.core.learning.learning_repository import LearningRepository
from src.core.learning.models import LearningExperience
from src.core.learning.persistence_models import (
    AdaptationRuleModel,
    LearningInsightModel,
    LearningPatternModel,
)
from src.core.learning.services.adaptation_service import AdaptationService
from src.core.learning.services.insight_service import InsightService
from src.core.learning.services.observation_service import ObservationService
from src.core.learning.services.pattern_service import PatternService
from src.core.shared.config import reload_settings

if "tenants" not in Base.metadata.tables:
    Table(
        "tenants",
        Base.metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(255), nullable=False, unique=True),
        Column("slug", String(100), nullable=False, unique=True),
        Column("is_active", Boolean, nullable=False, default=True),
        Column("max_users", Integer, nullable=False, default=10),
        Column("max_agents", Integer, nullable=False, default=50),
        Column("max_storage_gb", Integer, nullable=False, default=5),
        Column("subscription_tier", String(50), nullable=True),
        Column("subscription_status", String(50), nullable=True),
        Column("settings", JSON, nullable=True),
        Column("metadata", JSON, nullable=True),
        extend_existing=True,
    )

if "users" not in Base.metadata.tables:
    Table(
        "users",
        Base.metadata,
        Column("id", Integer, primary_key=True),
        extend_existing=True,
    )

NO_MOCK_PATTERNS = (
    r"(^|\n)\s*from\s+unittest\.mock\s+import\s+",
    r"(^|\n)\s*import\s+unittest\.mock",
    r"(^|\n)\s*from\s+mock\s+import\s+",
    r"(^|\n)\s*import\s+mock\b",
    r"\bMagicMock\b",
    r"\bAsyncMock\b",
    r"\bMock\(",
)

PHASE7_MARKERS = (
    "e2e: End-to-end tests (full stack)",
    "integration: Tests requiring database/external services",
    "no_mocks: Integration tests that avoid mocks and exercise real components",
    "slow: Slow tests (skip with -m 'not slow')",
)


def pytest_configure(config: pytest.Config) -> None:
    for marker in PHASE7_MARKERS:
        config.addinivalue_line("markers", marker)


def _phase7_enabled() -> bool:
    return os.getenv("RUN_E2E_TESTS") == "true"


@pytest.fixture(autouse=True)
def phase7_no_mock_enforcement(request: pytest.FixtureRequest) -> None:
    test_path = Path(str(request.node.fspath))
    source = test_path.read_text(encoding="utf-8")
    for pattern in NO_MOCK_PATTERNS:
        if re.search(pattern, source, flags=re.MULTILINE):
            pytest.fail(f"Phase 7 no-mock policy violation in {test_path.name}: {pattern}")


@pytest.fixture(autouse=True)
def phase7_requires_enabled_env() -> None:
    if not _phase7_enabled():
        pytest.skip("Phase 7 E2E tests disabled. Set RUN_E2E_TESTS=true.")


@pytest.fixture(scope="session")
def phase7_database_url() -> str:
    # GEEN terugval (ADR-036 OP-243). Hier stond een default naar poort 55433 met
    # inloggegevens test_user/test_password -- een server die in dit project nergens
    # anders voorkomt. Zo'n default faalt niet met "je hebt niets ingesteld" maar met een
    # verbindingsfout naar een adres dat niemand herkent, en dat is de slechtste van de
    # drie werelden. Deze e2e-omgeving is bewust een ANDERE dan de integratietestdatabase,
    # dus hij krijgt zijn eigen expliciete opgave.
    url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL is niet gezet. De phase7-e2e-tests draaien tegen een eigen "
            "omgeving en die wordt NIET geraden (ADR-036 OP-243). Zet hem expliciet, "
            'bijvoorbeeld: export TEST_DATABASE_URL="postgresql+asyncpg://user:pw@host:port/db"'
        )
    return url


@pytest.fixture(scope="session")
def phase7_rabbitmq_url() -> str:
    return os.getenv(
        "TEST_RABBITMQ_URL",
        "amqp://test_user:test_password@127.0.0.1:5673/",
    )


@pytest_asyncio.fixture
async def phase7_engine(phase7_database_url: str):
    os.environ["TESTING"] = "1"
    os.environ["FEATURE_LEARNING_ENABLED"] = "true"
    reload_settings()

    engine = create_async_engine(phase7_database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    bind=sync_conn,
                    tables=[
                        Base.metadata.tables["tenants"],
                        Base.metadata.tables["users"],
                        LearningExperience.__table__,
                        LearningPatternModel.__table__,
                        AdaptationRuleModel.__table__,
                        LearningInsightModel.__table__,
                        AuditLog.__table__,
                    ],
                )
            )
        db_manager.set_engine(engine)
    except (OSError, SQLAlchemyError, asyncpg.PostgresError) as exc:
        await engine.dispose()
        os.environ.pop("FEATURE_LEARNING_ENABLED", None)
        os.environ.pop("TESTING", None)
        reload_settings()
        pytest.skip(f"Phase 7 requires a live test database: {exc}")

    try:
        yield engine
    finally:
        await engine.dispose()
        os.environ.pop("FEATURE_LEARNING_ENABLED", None)
        os.environ.pop("TESTING", None)
        reload_settings()


@pytest_asyncio.fixture
async def phase7_session_factory(
    phase7_engine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    yield async_sessionmaker(phase7_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def phase7_tenant_id() -> int:
    return 700001


@pytest_asyncio.fixture
async def phase7_secondary_tenant_id() -> int:
    return 700002


async def _create_tenant(session: AsyncSession, tenant_id: int) -> None:
    existing = await session.execute(
        text("SELECT 1 FROM tenants WHERE id = :tenant_id"),
        {"tenant_id": tenant_id},
    )
    if existing.scalar_one_or_none() is not None:
        return

    await session.execute(
        text(
            """
            INSERT INTO tenants (
                id,
                name,
                slug,
                is_active,
                max_users,
                max_agents,
                max_storage_gb,
                subscription_tier,
                subscription_status,
                settings,
                metadata
            ) VALUES (
                :id,
                :name,
                :slug,
                :is_active,
                :max_users,
                :max_agents,
                :max_storage_gb,
                :subscription_tier,
                :subscription_status,
                CAST(:settings AS JSON),
                CAST(:metadata AS JSON)
            )
            """
        ),
        {
            "id": tenant_id,
            "name": f"Phase7 Tenant {tenant_id}",
            "slug": f"phase7-tenant-{tenant_id}",
            "is_active": True,
            "max_users": 10,
            "max_agents": 50,
            "max_storage_gb": 5,
            "subscription_tier": "free",
            "subscription_status": "active",
            "settings": "{}",
            "metadata": "{}",
        },
    )
    await session.commit()


@pytest_asyncio.fixture
async def phase7_session(
    phase7_session_factory: async_sessionmaker[AsyncSession],
    phase7_tenant_id: int,
    phase7_secondary_tenant_id: int,
) -> AsyncGenerator[AsyncSession, None]:
    async with phase7_session_factory() as session:
        await _create_tenant(session, phase7_tenant_id)
        await session.execute(
            text(
                """
                INSERT INTO users (id, tenant_id, email, hashed_password, is_active)
                VALUES (:id, :tenant_id, :email, :hashed_password, :is_active)
                ON CONFLICT (id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    email = EXCLUDED.email,
                    hashed_password = EXCLUDED.hashed_password,
                    is_active = EXCLUDED.is_active
                """
            ),
            {
                "id": 1,
                "tenant_id": phase7_tenant_id,
                "email": "phase7-user@sanskritisetu.test",
                "hashed_password": "phase7-not-used",
                "is_active": True,
            },
        )
        await session.commit()
        yield session

        tenant_ids = (phase7_tenant_id, phase7_secondary_tenant_id)

        await session.execute(delete(AuditLog).where(AuditLog.tenant_id.in_(tenant_ids)))
        await session.execute(
            delete(LearningExperience).where(LearningExperience.tenant_id.in_(tenant_ids))
        )
        await session.execute(
            delete(LearningPatternModel).where(
                LearningPatternModel.tenant_id.in_([str(tenant_id) for tenant_id in tenant_ids])
            )
        )
        await session.execute(
            delete(AdaptationRuleModel).where(
                AdaptationRuleModel.tenant_id.in_([str(tenant_id) for tenant_id in tenant_ids])
            )
        )
        await session.execute(
            delete(LearningInsightModel).where(
                LearningInsightModel.tenant_id.in_([str(tenant_id) for tenant_id in tenant_ids])
            )
        )
        await session.execute(
            text("DELETE FROM tenants WHERE id = ANY(:tenant_ids)"),
            {"tenant_ids": list(tenant_ids)},
        )
        await session.execute(text("DELETE FROM users WHERE id = 1"))
        await session.commit()


@pytest_asyncio.fixture
async def phase7_create_tenant(phase7_session: AsyncSession):
    async def factory(tenant_id: int) -> None:
        await _create_tenant(phase7_session, tenant_id)

    return factory


@pytest_asyncio.fixture
async def phase7_learning_stack(
    phase7_session: AsyncSession,
    phase7_session_factory: async_sessionmaker[AsyncSession],
    phase7_tenant_id: int,
):
    return _build_learning_stack(
        session_factory=phase7_session_factory,
        tenant_id=phase7_tenant_id,
        gdpr_session=phase7_session,
    )


@pytest_asyncio.fixture
async def phase7_stack_factory(
    phase7_session: AsyncSession,
    phase7_session_factory: async_sessionmaker[AsyncSession],
):
    async def factory(tenant_id: int):
        await _create_tenant(phase7_session, tenant_id)
        return _build_learning_stack(
            session_factory=phase7_session_factory,
            tenant_id=tenant_id,
            gdpr_session=phase7_session,
        )

    return factory


def _build_learning_stack(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: int,
    gdpr_session: AsyncSession,
):
    repository = LearningRepository(session_factory)
    observation_service = ObservationService(
        tenant_id=tenant_id,
        repository=repository,
        observation_threshold=20,
        rate_limit_max=1000,
    )
    pattern_service = PatternService(tenant_id=tenant_id, repository=repository)
    adaptation_service = AdaptationService(tenant_id=tenant_id, repository=repository)
    insight_service = InsightService(tenant_id=tenant_id, repository=repository)
    gdpr_service = LearningGDPRService(gdpr_session)
    return {
        "repository": repository,
        "observation_service": observation_service,
        "pattern_service": pattern_service,
        "adaptation_service": adaptation_service,
        "insight_service": insight_service,
        "gdpr_service": gdpr_service,
    }
