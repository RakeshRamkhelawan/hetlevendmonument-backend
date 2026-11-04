"""
Shared Value Objects - DDD Building Blocks
Immutable objects that represent domain concepts
"""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EntityId(BaseModel):
    """Unique identifier for entities"""

    model_config = ConfigDict(frozen=True)

    value: str

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)


class Email(BaseModel):
    """Email address value object"""

    model_config = ConfigDict(frozen=True)

    value: EmailStr

    def __str__(self) -> str:
        return self.value


class Timestamp(BaseModel):
    """Timestamp value object"""

    model_config = ConfigDict(frozen=True)

    value: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return self.value.isoformat()
