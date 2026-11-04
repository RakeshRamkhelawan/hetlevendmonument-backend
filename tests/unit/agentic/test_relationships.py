"""
Cross-Domain Relationship Tests - TDD Phase

Tests that agentic models can correctly access related Tenant/User objects
through unidirectional relationships.

Run: pytest tests/unit/agentic/test_relationships.py -v
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class TestFeatureRelationships:
    """Tests for Feature model relationships."""

    @pytest.mark.asyncio
    async def test_feature_tenant_access(self, db_session: AsyncSession, isolated_tenant):
        """Feature moet tenant object kunnen benaderen via relationship."""
        from src.domains.agentic.models import Feature

        feature = Feature(
            id="rel_test_feature",
            name="Relationship Test",
            description="Testing tenant relationship",
            category="test",
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(feature)
        await db_session.commit()
        stmt = select(Feature).options(selectinload(Feature.tenant)).where(Feature.id == feature.id)
        result = await db_session.execute(stmt)
        feature = result.scalar_one()

        # Access via relationship
        assert feature.tenant is not None
        assert feature.tenant.id == isolated_tenant["tenant_id"]

    @pytest.mark.asyncio
    async def test_feature_without_tenant_id_is_rejected(self, db_session: AsyncSession):
        """DATA-001/DB-AUDIT-001 (AUDIT-ARCH-2026-07-02 Groep 4): tenant_id is NOT
        NULL -- there is no such thing as a tenant-less "platform feature" anymore."""
        from sqlalchemy.exc import IntegrityError

        from src.domains.agentic.models import Feature

        feature = Feature(
            id="platform_feature",
            name="Platform Feature",
            description="No tenant",
            category="platform",
            tenant_id=None,
        )
        db_session.add(feature)

        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestUserPersonaRelationships:
    """Tests for UserPersona model relationships."""

    @pytest.mark.asyncio
    async def test_user_persona_user_access(self, db_session: AsyncSession, isolated_tenant):
        """UserPersona moet user object kunnen benaderen."""
        from src.core.models.rbac_models import User
        from src.domains.agentic.models import UserPersona

        # Create user first
        user = User(
            email="persona_test@example.com",
            hashed_password="hashed",
            tenant_id=isolated_tenant["tenant_id"],
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Create persona
        persona = UserPersona(
            user_id=user.id,
            tenant_id=isolated_tenant["tenant_id"],
            persona_type="explorer",
            preferences={"theme": "dark"},
        )
        db_session.add(persona)
        await db_session.commit()
        stmt = (
            select(UserPersona)
            .options(selectinload(UserPersona.user), selectinload(UserPersona.tenant))
            .where(UserPersona.user_id == user.id)
        )
        result = await db_session.execute(stmt)
        persona = result.scalar_one()

        # Access via relationships
        assert persona.user is not None
        assert persona.user.id == user.id
        assert persona.tenant is not None

    @pytest.mark.asyncio
    async def test_user_persona_tenant_access(self, db_session: AsyncSession, isolated_tenant):
        """UserPersona moet tenant object kunnen benaderen."""
        from src.core.models.rbac_models import User
        from src.domains.agentic.models import UserPersona

        user = User(
            email="tenant_access@example.com",
            hashed_password="hashed",
            tenant_id=isolated_tenant["tenant_id"],
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        persona = UserPersona(
            user_id=user.id,
            tenant_id=isolated_tenant["tenant_id"],
            persona_type="builder",
        )
        db_session.add(persona)
        await db_session.commit()
        stmt = (
            select(UserPersona)
            .options(selectinload(UserPersona.tenant))
            .where(UserPersona.user_id == user.id)
        )
        result = await db_session.execute(stmt)
        persona = result.scalar_one()

        assert persona.tenant is not None
        assert persona.tenant.id == isolated_tenant["tenant_id"]


class TestAgentSessionRelationships:
    """Tests for AgentSession model relationships."""

    @pytest.mark.asyncio
    async def test_session_user_access(self, db_session: AsyncSession, isolated_tenant):
        """AgentSession moet user kunnen benaderen."""
        from src.core.models.rbac_models import User
        from src.domains.agentic.models import AgentSession

        user = User(
            email="session_test@example.com",
            hashed_password="hashed",
            tenant_id=isolated_tenant["tenant_id"],
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        session = AgentSession(
            id=uuid.uuid4().hex,
            user_id=user.id,
            tenant_id=isolated_tenant["tenant_id"],
            session_type="chat",
        )
        db_session.add(session)
        await db_session.commit()
        stmt = (
            select(AgentSession)
            .options(selectinload(AgentSession.user))
            .where(AgentSession.id == session.id)
        )
        result = await db_session.execute(stmt)
        session = result.scalar_one()

        assert session.user is not None
        assert session.user.id == user.id

    @pytest.mark.asyncio
    async def test_session_messages_bidirectional(self, db_session: AsyncSession, isolated_tenant):
        """AgentSession en SessionMessage moeten bidirectioneel werken."""
        from src.core.models.rbac_models import User
        from src.domains.agentic.models import AgentSession, SessionMessage

        user = User(
            email="messages_test@example.com",
            hashed_password="hashed",
            tenant_id=isolated_tenant["tenant_id"],
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        session = AgentSession(
            id=uuid.uuid4().hex,
            user_id=user.id,
            tenant_id=isolated_tenant["tenant_id"],
            session_type="chat",
        )
        db_session.add(session)
        await db_session.commit()

        message = SessionMessage(
            session_id=session.id,
            role="user",
            content="Hello agent!",
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(message)
        await db_session.commit()

        # Refresh session to load messages
        # In async, we must use selectinload or explicit join for relationships
        stmt = (
            select(AgentSession)
            .options(selectinload(AgentSession.messages))
            .where(AgentSession.id == session.id)
        )
        result = await db_session.execute(stmt)
        session = result.scalar_one()

        # Bidirectional access within domain
        assert len(session.messages) == 1
        assert session.messages[0].content == "Hello agent!"

        # Access session from message
        stmt = (
            select(SessionMessage)
            .options(selectinload(SessionMessage.session))
            .where(SessionMessage.id == message.id)
        )
        result = await db_session.execute(stmt)
        message = result.scalar_one()

        assert message.session is not None
        assert message.session.id == session.id


class TestEagerLoading:
    """Tests for eager loading performance optimization."""

    @pytest.mark.asyncio
    async def test_feature_eager_load_tenant(self, db_session: AsyncSession, isolated_tenant):
        """Eager loading moet N+1 queries voorkomen."""
        from src.domains.agentic.models import Feature

        # Create multiple features
        for i in range(3):
            feature = Feature(
                id=f"eager_test_{i}",
                name=f"Eager Test {i}",
                description="Testing eager loading",
                category="test",
                tenant_id=isolated_tenant["tenant_id"],
            )
            db_session.add(feature)
        await db_session.commit()

        # Eager load tenant with features
        stmt = (
            select(Feature)
            .options(selectinload(Feature.tenant))
            .where(
                Feature.tenant_id == isolated_tenant["tenant_id"],
                Feature.id.like("eager_test_%"),
            )
        )
        result = await db_session.execute(stmt)
        features = result.scalars().all()

        assert len(features) == 3
        # Tenant should be loaded without additional query
        for f in features:
            assert f.tenant is not None
