"""Personas dependencies -- schemas."""

from pydantic import BaseModel, ConfigDict, Field

from src.core.models.persona_models import PersonaCategory


class PersonaBase(BaseModel):
    """Base persona schema."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    category: PersonaCategory = PersonaCategory.CUSTOM
    system_prompt: str = Field(..., min_length=10)
    avatar_url: str | None = None
    temperature: str = "0.7"
    verbosity: str = "balanced"
    tone: str = "professional"


class PersonaCreate(PersonaBase):
    """Schema for creating a persona."""

    pass


class PersonaUpdate(BaseModel):
    """Schema for updating a persona."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    system_prompt: str | None = Field(None, min_length=10)
    avatar_url: str | None = None
    temperature: str | None = None
    verbosity: str | None = None
    tone: str | None = None
    is_active: bool | None = None
    is_default: bool | None = None


class PersonaResponse(BaseModel):
    """Persona response schema."""

    id: int
    name: str
    description: str | None
    category: PersonaCategory
    avatar_url: str | None
    temperature: str
    verbosity: str
    tone: str
    is_active: bool
    is_default: bool
    is_system: bool

    model_config = ConfigDict(from_attributes=True)


class PersonaDetailResponse(PersonaResponse):
    """Full persona response including system prompt."""

    system_prompt: str


class SetPersonaRequest(BaseModel):
    """Request to set user's active persona."""

    persona_id: int


class ActivePersonaResponse(BaseModel):
    """Response for user's active persona."""

    persona: PersonaResponse | None
    system_prompt: str


from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import get_db as get_db  # noqa: E402, F401
from src.core.services.persona_service import PersonaService as PersonaService  # noqa: E402, F401


async def get_persona_service(db: AsyncSession = Depends(get_db)) -> PersonaService:
    return PersonaService(db)
