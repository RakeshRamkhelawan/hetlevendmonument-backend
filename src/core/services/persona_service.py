"""
Persona Service - Manages AI personas and user preferences.
"""

from typing import Any, Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.persona_models import (
    DEFAULT_PERSONAS,
    Persona,
    PersonaCategory,
    UserPersonaPreference,
)


class PersonaService:
    """Service for managing AI personas."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all_personas(
        self, tenant_id: int, limit: int | None = None, offset: int | None = None
    ) -> list[Persona]:
        """Get all active personas for a tenant."""
        stmt = (
            select(Persona)
            .where(and_(Persona.tenant_id == tenant_id, Persona.is_active == True))  # noqa: E712
            .order_by(Persona.is_system.desc(), Persona.name)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_persona_by_id(self, persona_id: int, tenant_id: int) -> Persona | None:
        """Get a specific persona by ID."""
        result = await self.db.execute(
            select(Persona).where(and_(Persona.id == persona_id, Persona.tenant_id == tenant_id))
        )
        return result.scalar_one_or_none()

    async def get_user_active_persona(self, user_id: int, tenant_id: int) -> Persona | None:
        """Get the currently active persona for a user."""
        result = await self.db.execute(
            select(Persona)
            .join(
                UserPersonaPreference,
                and_(
                    UserPersonaPreference.persona_id == Persona.id,
                    UserPersonaPreference.tenant_id == Persona.tenant_id,
                ),
            )
            .where(
                and_(
                    UserPersonaPreference.user_id == user_id,
                    UserPersonaPreference.tenant_id == tenant_id,
                    Persona.tenant_id == tenant_id,
                )
            )
        )
        persona = result.scalar_one_or_none()

        if not persona:
            # Return default persona if no preference set
            result = await self.db.execute(
                select(Persona).where(
                    and_(Persona.tenant_id == tenant_id, Persona.is_default == True)  # noqa: E712
                )
            )
            persona = result.scalar_one_or_none()

        return persona

    async def set_user_persona(self, user_id: int, persona_id: int, tenant_id: int) -> bool:
        """Set the active persona for a user."""
        # Verify persona exists and belongs to tenant
        persona = await self.get_persona_by_id(persona_id, tenant_id)
        if not persona:
            return False

        # Check if preference already exists
        result = await self.db.execute(
            select(UserPersonaPreference).where(
                and_(
                    UserPersonaPreference.user_id == user_id,
                    UserPersonaPreference.tenant_id == tenant_id,
                )
            )
        )
        preference = result.scalar_one_or_none()

        if preference:
            preference.persona_id = persona_id
        else:
            preference = UserPersonaPreference(
                user_id=user_id,
                tenant_id=tenant_id,
                persona_id=persona_id,
            )
            self.db.add(preference)

        await self.db.commit()
        return True

    async def create_persona(
        self,
        tenant_id: int,
        name: str,
        system_prompt: str,
        description: str | None = None,
        category: PersonaCategory = PersonaCategory.CUSTOM,
        avatar_url: str | None = None,
        temperature: str = "0.7",
        verbosity: str = "balanced",
        tone: str = "professional",
    ) -> Persona:
        """Create a new custom persona."""
        persona = Persona(
            tenant_id=tenant_id,
            name=name,
            description=description,
            system_prompt=system_prompt,
            category=category,
            avatar_url=avatar_url,
            temperature=temperature,
            verbosity=verbosity,
            tone=tone,
            is_system=False,
            is_active=True,
        )
        self.db.add(persona)
        await self.db.commit()
        await self.db.refresh(persona)
        return persona

    async def update_persona(
        self, persona_id: int, tenant_id: int, **updates: Any  # TODO(TYPE): replace Any with concrete type
    ) -> Persona | None:
        """Update a persona (only custom personas can be fully updated)."""
        persona = await self.get_persona_by_id(persona_id, tenant_id)
        if not persona:
            return None

        # System personas can only have limited updates
        if persona.is_system:
            allowed_fields = {"is_active", "is_default"}
            updates = {k: v for k, v in updates.items() if k in allowed_fields}

        for key, value in updates.items():
            if hasattr(persona, key):
                setattr(persona, key, value)

        await self.db.commit()
        await self.db.refresh(persona)
        return persona

    async def delete_persona(self, persona_id: int, tenant_id: int) -> bool:
        """Delete a custom persona (system personas cannot be deleted)."""
        persona = await self.get_persona_by_id(persona_id, tenant_id)
        if not persona or persona.is_system:
            return False

        # Remove user preferences for this persona
        await self.db.execute(
            delete(UserPersonaPreference).where(UserPersonaPreference.persona_id == persona_id)
        )

        await self.db.delete(persona)
        await self.db.commit()
        return True

    async def seed_default_personas(self, tenant_id: int) -> list[Persona]:
        """Seed default system personas for a new tenant."""
        created: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for persona_data in DEFAULT_PERSONAS:
            # Check if already exists
            result = await self.db.execute(
                select(Persona).where(
                    and_(
                        Persona.tenant_id == tenant_id,
                        Persona.name == persona_data["name"],
                        Persona.is_system == True,  # noqa: E712
                    )
                )
            )
            existing = result.scalar_one_or_none()

            if not existing:
                persona = Persona(
                    tenant_id=tenant_id,
                    **persona_data,
                    is_default=(persona_data["name"] == "Technical Expert"),
                )
                self.db.add(persona)
                created.append(persona)

        if created:
            await self.db.commit()
            for p in created:
                await self.db.refresh(p)

        return created

    async def get_system_prompt_for_user(self, user_id: int, tenant_id: int) -> str:
        """Get the complete system prompt based on user's active persona."""
        persona = await self.get_user_active_persona(user_id, tenant_id)

        if persona:
            return persona.system_prompt

        # Fallback default prompt
        return """You are a helpful AI assistant. Provide accurate, helpful responses
while maintaining a professional and friendly tone."""
