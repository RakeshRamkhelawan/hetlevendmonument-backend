"""
Pydantic schemas for User CRUD operations.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.core.shared.wachtwoordregels import controleer_gekozen_wachtwoord


class UserBase(BaseModel):
    """Base User schema with common fields."""

    email: EmailStr = Field(..., description="User email address")
    is_active: bool = Field(default=True, description="Whether the user is active")


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str | None = Field(
        default=None,
        min_length=8,
        description="Leeg laten: de medewerker krijgt een e-mail met een eenmalige link en kiest zelf een wachtwoord",
    )
    role_ids: list[int] = Field(default_factory=list, description="Role IDs to assign")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str | None) -> str | None:
        """Ensure password meets complexity requirements (een bron: `shared/wachtwoordregels.py`)."""
        if v is None:
            return v
        return controleer_gekozen_wachtwoord(v)


class UserUpdate(BaseModel):
    """Schema for updating an existing user."""

    email: EmailStr | None = None
    is_active: bool | None = None
    role_ids: list[int] | None = None


class UserPasswordUpdate(BaseModel):
    """Schema for updating user password."""

    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Ensure password meets complexity requirements (een bron: `shared/wachtwoordregels.py`)."""
        return controleer_gekozen_wachtwoord(v)


class UserRole(BaseModel):
    """User role information."""

    id: int
    name: str

    class Config:
        from_attributes = True


class UserResponse(UserBase):
    """Schema for user response."""

    id: int
    tenant_id: int
    email: str = Field(..., description="User email address")
    roles: list[UserRole] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None
    last_login: datetime | None = None
    #: Alleen gezet bij aanmaken ZONDER wachtwoord: is de uitnodigingsmail verstuurd? `False` betekent dat
    #: de gebruiker wel bestaat maar de mail niet is aangekomen (de beheerder moet dat zien).
    invitation_email_sent: bool | None = None

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """Schema for list of users with pagination."""

    data: list[UserResponse]
    total: int
    page: int
    per_page: int


class UserProfileUpdate(BaseModel):
    """Schema for updating user profile (self-service)."""

    email: EmailStr | None = None
