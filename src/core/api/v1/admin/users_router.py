"""Admin users sub-router: POST /create_user, POST /assign_role/{user_id}, GET /users."""

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import auth_service
from src.core.auth.api_deps import UserResponse, UserCreate
from src.core.models.rbac_models import Role, User

from .dependencies import (
    _current_user_value,
    _resolve_tenant_id,
    get_db,
    log_security_event,
    RBACService,
    require_admin_role,
    stuur_uitnodiging,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


class AdminUserCreateRequest(BaseModel):
    """Schema for privileged user creation."""

    username: str | None = None
    email: EmailStr
    #: Leeg laten: de medewerker wordt UITGENODIGD (e-mail met een eenmalige link, hij kiest zelf een
    #: wachtwoord). Een opgegeven wachtwoord blijft werken (de beheerder geeft het dan zelf door).
    password: str | None = None
    role: str = "admin"


class AssignRoleRequest(BaseModel):
    """Schema for assigning tenant-scoped roles."""

    role: str


@router.post("/create_user", status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: AdminUserCreateRequest,
    request: Request,
    current_user: UserResponse = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Create tenant-scoped administrative users with full audit logging."""
    tenant_id = _resolve_tenant_id(current_user)
    creator_id = _current_user_value(current_user, "id")

    gevraagde_rol = payload.role or "admin"

    # ADR-036 OP-184, tweede pad. `payload.role` is een VRIJ tekstveld uit de body
    # (regel 35). Een beheerder mag een rol kiezen, maar geen rol VERZINNEN: tot
    # 2026-09-11 ging die tekenreeks ongevalideerd naar create_user, en het primitief
    # daar maakte er een rol van (OP-185). Nu eerst resolveren tegen de bestaande rollen
    # van deze tenant, en anders weigeren met een melding die de waarheid vertelt -- het
    # oude pad gaf via create_user None terug, waarvan dit endpoint 409 "User already
    # exists" maakte, en dat zet de beheerder op het verkeerde spoor.
    # Eerst de standaardrollen zaaien, DAARNA controleren. Gemeten door de Gate-2-reviewer
    # op 2026-09-11: in de eerste versie stond deze controle voor de aanroep van
    # ensure_default_roles (die stond pas na create_user), waardoor een verse tenant zonder
    # rollen nooit zijn eerste beheerder kon krijgen -- de HTTPException viel voordat er
    # ook maar iets was gezaaid. Fail-secure werd daarmee fail-dead. Zaaien is geen
    # versoepeling van OP-185: het maakt uitsluitend de vaste standaardlijst aan.
    rbac = RBACService(db)
    await rbac.ensure_default_roles(tenant_id)

    # Een platformrol (system_admin) deelt alleen uit wie hem zelf heeft. De rij kan in de tenant van
    # het platform bestaan, en "de rol bestaat" is geen toestemming (gemeten 2026-10-16: een gewone
    # beheerder kon er een gebruiker mee uitnodigen). Eerst weigeren, voor er iets wordt aangemaakt.
    if not await rbac.mag_rol_uitdelen(creator_id, gevraagde_rol, tenant_id):
        await log_security_event(
            event_type="ADMIN_USER_CREATE_REFUSED",
            user_id=creator_id,
            tenant_id=tenant_id,
            request_path="/api/v1/admin/create_user",
            request_method="POST",
            ip_address=request.client.host if request.client else "unknown",
            details={"reason": "platform_role_requested", "requested_role": gevraagde_rol},
            description=f"Admin user creation refused: platform role '{gevraagde_rol}' requested",
            threat_level="high",
            db=db,
        )
        # `log_security_event` schrijft met flush; zonder commit draait de 403 hieronder de transactie terug
        # en verdwijnt de auditregel (gemeten 2026-10-18). Er is op dit punt niets anders gewijzigd.
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Deze rol kan alleen door een platformbeheerder worden toegekend.",
        )

    rol_bestaat = await db.execute(
        select(Role).where(Role.name == gevraagde_rol).where(Role.tenant_id == tenant_id)
    )
    if rol_bestaat.scalar_one_or_none() is None:
        # Auditeren voor je weigert. Gemeten door de Gate-2-securityreviewer op
        # 2026-09-11: deze tak gooide een 400 zonder enig beveiligingsevent, terwijl het
        # registratiepad dat wel doet. Een gekaapt beheerdersaccount dat rolnamen aftast
        # (system_admin, tenantadmin, ...) liet daardoor geen spoor achter.
        await log_security_event(
            event_type="ADMIN_USER_CREATE_REFUSED",
            user_id=creator_id,
            tenant_id=tenant_id,
            request_path="/api/v1/admin/create_user",
            request_method="POST",
            ip_address=request.client.host if request.client else "unknown",
            details={
                "reason": "unknown_role_requested",
                "requested_role": gevraagde_rol,
                "email": payload.email,
            },
            description=(
                f"Admin user creation refused: role '{gevraagde_rol}' does not exist in "
                f"tenant {tenant_id}"
            ),
            threat_level="medium",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Rol '{gevraagde_rol}' bestaat niet in deze tenant. Maak de rol eerst aan "
                "met de rollenbeheerfunctie; het aanmaken van een gebruiker maakt geen "
                "rollen aan."
            ),
        )

    # Zonder wachtwoord: een willekeurig, onbekend startwachtwoord (hoofdletter, kleine letter en cijfer,
    # zodat het aan de regels voldoet). Zonder de eenmalige link kan niemand inloggen.
    uitnodigen = payload.password is None
    wachtwoord = payload.password if payload.password is not None else secrets.token_urlsafe(24) + "Aa1"
    user_data = UserCreate(
        email=payload.email,
        password=wachtwoord,
        role_name=gevraagde_rol,
    )

    client_ip = request.client.host if request.client else "unknown"
    created_user = await auth_service.create_user(
        db,
        user_data,
        client_ip=client_ip,
        tenant_id=tenant_id,
        request_path="/api/v1/admin/users",
    )

    if created_user is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists for this tenant",
        )

    await rbac.assign_role(created_user.id, gevraagde_rol, tenant_id, assigned_by=creator_id)

    await log_security_event(
        event_type="admin_user_created",
        user_id=creator_id,
        tenant_id=tenant_id,
        request_path="/api/admin/create_user",
        request_method="POST",
        ip_address=client_ip,
        details={
            "created_user": created_user.email,
            "role": payload.role or "admin",
            "invited": uitnodigen,
        },
        threat_level="low",
        db=db,
    )

    # Pas NA het vastleggen van de gebruiker: een mislukte mail breekt het aanmaken niet af maar is
    # niet stil (log ERROR, en de beheerder ziet `invitation_email_sent: false`).
    uitnodiging_verstuurd = (
        await stuur_uitnodiging(created_user.email, created_user.id) if uitnodigen else None
    )

    return {
        "id": created_user.id,
        "email": created_user.email,
        "role": payload.role or "admin",
        "status": "created",
        "tenant_id": tenant_id,
        "invitation_email_sent": uitnodiging_verstuurd,
    }


@router.post("/assign_role/{user_id}")
async def assign_role_to_user(
    user_id: int,
    payload: AssignRoleRequest,
    current_user: UserResponse = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Assign an RBAC role to an existing user within the same tenant."""
    tenant_id = _resolve_tenant_id(current_user)
    creator_id = _current_user_value(current_user, "id")

    result = await db.execute(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found in tenant")

    rbac = RBACService(db)
    await rbac.ensure_default_roles(tenant_id)
    try:
        assigned = await rbac.assign_role(user_id, payload.role, tenant_id, assigned_by=creator_id)
    except PermissionError as exc:
        # Een platformrol deelt alleen uit wie hem zelf heeft (RBACService.mag_rol_uitdelen).
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Geen toegang.") from exc

    if not assigned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Role assignment failed"
        )

    await log_security_event(
        event_type="admin_role_assigned",
        user_id=creator_id,
        tenant_id=tenant_id,
        request_path=f"/api/admin/assign_role/{user_id}",
        request_method="POST",
        ip_address="internal",
        details={"target_user": target_user.email, "role": payload.role},
        threat_level="low",
        db=db,
    )

    return {"user_id": user_id, "role": payload.role, "status": "assigned"}


@router.get("/users")
async def list_users(
    current_user: UserResponse = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List users endpoint -- real database queries with tenant filter."""
    try:
        logger.info("User %s listing all users (skip=%s, limit=%s)", current_user.id, skip, limit)

        tenant_id = _resolve_tenant_id(current_user)

        from src.core.models.rbac_models import user_roles

        query = (
            select(
                User.id,
                User.email,
                User.is_active,
                User.created_at,
                User.last_login,
                User.tenant_id,
                Role.name.label("role_name"),
            )
            .join(user_roles, User.id == user_roles.c.user_id)
            .join(Role, user_roles.c.role_id == Role.id)
            .where(User.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        rows = result.all()

        users: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for row in rows:
            users.append(
                {
                    "id": row.id,
                    "email": row.email,
                    "role": row.role_name,
                    "is_active": row.is_active,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "last_login": row.last_login.isoformat() if row.last_login else None,
                }
            )

        total_count_result = await db.execute(
            select(func.count(User.id)).where(User.tenant_id == tenant_id)
        )
        total_count = total_count_result.scalar_one()

        return {
            "message": "User list access granted",
            "users": users,
            "pagination": {
                "total": total_count,
                "skip": skip,
                "limit": limit,
                "returned": len(users),
            },
        }
    except Exception as e:
        logger.error("List users error: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e
