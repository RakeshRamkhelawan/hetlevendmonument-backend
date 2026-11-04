from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.core.shared.wachtwoordregels import controleer_gekozen_wachtwoord

# ==========================================
# User Models (from auth_endpoints.py)
# ==========================================


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None


class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool = True
    tenant_id: int
    roles: list[str] = []
    role_id: int | None = None
    scopes: list[str] = []

    #: Is deze gebruiker beheerder BINNEN zijn tenant? Het EXPLICIETE antwoord van de
    #: backend op een vraag die de frontend tot 2026-09-18 zelf probeerde af te leiden
    #: (ADR-036 OP-193).
    #:
    #: **Waarom dit veld bestaat.** `AdminRoute` controleerde `hasAllScopes(['tenant:admin'])`.
    #: Die scope geeft geen enkele backendplek uit -- hij bestaat alleen als
    #: `Permission.TENANT_ADMIN` in `services/rbac_service.py:64`, en dat is een PERMISSIE in
    #: het RBAC-model, geen scope in het token. Gemeten met een Vitest-test over de echte
    #: store: een beheerder met de vier scopes die `_get_user_scopes` hem werkelijk geeft
    #: landde op `/forbidden`, op alle zeven beheerdersroutes in `App.tsx`.
    #:
    #: **En een andere scope controleren was OOK fout geweest.** Een beheerder krijgt
    #: `users:read users:write workflows:read workflows:write` en niets dat zegt DAT hij
    #: beheerder is. Dat is geen omissie maar ADR-036 OP-186: de loper op rolnaam is er
    #: bewust uitgehaald en het oordeel valt server-side. De frontend KAN beheerderschap dus
    #: niet uit de tokenscopes afleiden, en moet het gevraagd krijgen.
    #:
    #: **LET OP bij verplaatsen -- de valkuil die dit veld bijna hol maakte.** Het volstaat
    #: NIET om dit veld hier te declareren. `get_current_user` geeft de GELIJKNAMIGE klasse
    #: uit `src/core/auth/auth_service.py:133` terug, en FastAPI perst die via
    #: `from_attributes` door dit responsemodel. Een bronobject zonder `is_admin`-attribuut
    #: levert dan stilzwijgend de default op -- `false` voor IEDEREEN, ook voor een echte
    #: beheerder, en een test die alleen kijkt of het veld bestaat gaat daar groen doorheen.
    #: `get_me` in `router_login.py` vult dit daarom EXPLICIET.
    #:
    #: **En bereken hem uit het juiste bronobject.** `is_admin()` heeft twee helften:
    #: rolnamen, en de superuser-bypass via `getattr(user, "is_superuser", False)`. Deze
    #: klasse heeft GEEN `is_superuser`; `auth_service.UserResponse` wel. Bereken je de vlag
    #: uit deze klasse, dan krijgt een platform-superuser zonder beheerdersrolnaam
    #: `is_admin=false` terwijl de backend hem wel binnenlaat -- dezelfde soort divergentie
    #: tussen frontend en backend als de storing die dit veld oplost, alleen nieuw aangelegd.
    is_admin: bool = False

    #: De RBAC-rechten van deze gebruiker in zijn tenant, als `resource:action`
    #: (bijvoorbeeld `receivables:write`, of `*:*` voor de beheerder). Alleen `get_me` vult
    #: dit; elders is het leeg. UI-AANWIJZING, GEEN AUTORISATIE: de backend controleert per
    #: route zelf (rolmodel debiteuren, plan-van-aanpak-nazorg deel II punt 1).
    permissions: list[str] = []

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Token Models (from oauth2_endpoints.py)
# ==========================================


class TokenResponse(BaseModel):
    """Standard Token Response"""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str
    scope: str
    # Include the authenticated user so the frontend can hydrate auth state
    # without an extra round-trip to /me.
    user: UserResponse | None = None


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token"""

    grant_type: str = "refresh_token"
    # Optioneel: de browser stuurt het refresh-token als httpOnly-cookie en laat dit veld weg.
    # Verplicht maken gaf een 422 voordat de cookie-terugval in de route kon draaien (gemeten
    # 2026-10-05, tests/unit/api/auth/test_refresh_without_cookie_is_401.py).
    refresh_token: str | None = None


class RefreshTokenResponse(BaseModel):
    """Response for refreshed token"""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class RevokeTokenRequest(BaseModel):
    token: str


class RevokeTokenResponse(BaseModel):
    revoked: bool


class LogoutRequest(BaseModel):
    """Optionele body van `POST /auth/logout`.

    Een browser stuurt niets mee: het refresh-token zit in de cookie. Een API-client zonder cookies
    geeft het hier mee, zodat uitloggen ook dat token intrekt.
    """

    refresh_token: str | None = None


class TokenValidationResponse(BaseModel):
    active: bool
    scope: str = ""
    client_id: str = "frontend-app"
    username: str = ""
    token_type: str = "Bearer"
    exp: int = 0


class TokenVerifyRequest(BaseModel):
    """Request to verify a token for sync-server authentication"""
    token: str


class TokenVerifyResponse(BaseModel):
    """Response for sync-server token verification
    
    Contains minimal information needed for sync-server authentication:
    - valid: Whether the token is valid
    - tenantId: The tenant ID for document isolation
    - userId: The user ID for access control
    """
    valid: bool
    tenantId: str
    userId: str


# ==========================================
# Request/Response Models
# ==========================================


class LoginRequest(BaseModel):
    """
    Unified Login Request
    Supports both 'username' (OAuth2) and 'email' keys
    """

    username: str | None = None
    email: str | None = None
    password: str


class ChangePasswordRequest(BaseModel):
    """Request to change password for authenticated user"""

    current_password: str
    new_password: str = Field(
        min_length=8, description="New password must be at least 8 characters"
    )

    @field_validator("new_password")
    @classmethod
    def _regels_voor_een_gekozen_wachtwoord(cls, v: str) -> str:
        return controleer_gekozen_wachtwoord(v)


class ForgotPasswordRequest(BaseModel):
    """Request to initiate password reset flow"""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Request to reset password with reset token"""

    token: str
    new_password: str = Field(
        min_length=8, description="New password must be at least 8 characters"
    )

    @field_validator("new_password")
    @classmethod
    def _regels_voor_een_gekozen_wachtwoord(cls, v: str) -> str:
        return controleer_gekozen_wachtwoord(v)


class RegisterRequest(BaseModel):
    """Request to register a new user"""

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None


class PasswordResetRequest(BaseModel):
    """Request to initiate password reset"""

    email: EmailStr


class ErrorResponse(BaseModel):
    error: str
    error_description: str = ""
