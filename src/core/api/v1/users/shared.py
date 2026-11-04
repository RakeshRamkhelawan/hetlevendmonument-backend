"""
Shared helpers for Users sub-routers (ADR-033).
"""

from collections.abc import Coroutine

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Role, User, user_roles
from src.core.api.v1.users.dependencies import (
    RBACService,
    get_current_user,
    is_platform_superuser,
)


def has_role(user: object, role_name: str) -> bool:
    """Check if user has a specific role.

    De ingelogde gebruiker (UserResponse) heeft rollen als TEKST, een ORM-gebruiker als
    Role-objecten met `.name`. Beide vormen tellen, hoofdletterongevoelig zoals `is_admin`.
    """
    wanted = role_name.strip().lower()
    for role in getattr(user, "roles", None) or []:
        name = role if isinstance(role, str) else getattr(role, "name", None)
        if isinstance(name, str) and name.strip().lower() == wanted:
            return True
    return False


async def eis_dat_gebruiker_uitgeschakeld_mag_worden(
    db: AsyncSession, request: Request, actor_id: int, doel_user_id: int, tenant_id: int
) -> None:
    """403 (Nederlandse tekst) als de doelgebruiker een platformbeheerder is die de aanvrager niet mag wijzigen.

    De regel staat in `RBACService.controleer_uitschakelen`; dit is alleen de vertaling naar HTTP, gedeeld
    door `PUT /users/{id}` (is_active=false), `DELETE /users/{id}` en `POST /gdpr/users/{id}/erase`.
    """
    await _weiger_met_403_en_auditregel(
        db,
        request,
        RBACService(db).controleer_uitschakelen(actor_id, doel_user_id, tenant_id),
        actor_id=actor_id,
        doel_user_id=doel_user_id,
        tenant_id=tenant_id,
        event_type="platform_user_disable_refused",
        description="Platform administrator account disable/delete/erase refused",
    )


async def eis_dat_profiel_gewijzigd_mag_worden(
    db: AsyncSession, request: Request, actor_id: int, doel_user_id: int, tenant_id: int
) -> None:
    """403 (Nederlandse tekst) als de doelgebruiker een platformbeheerder is en de aanvrager de platformrol niet heeft.

    De regel staat in `RBACService.controleer_profiel_wijzigen`; dit is de vertaling naar HTTP voor elke
    route die het e-mailadres of het wachtwoord van een ANDERE gebruiker zet. Aanroepen VOOR de eerste
    `setattr`: zo ligt er geen halve wijziging in de sessie.
    """
    await _weiger_met_403_en_auditregel(
        db,
        request,
        RBACService(db).controleer_profiel_wijzigen(actor_id, doel_user_id, tenant_id),
        actor_id=actor_id,
        doel_user_id=doel_user_id,
        tenant_id=tenant_id,
        event_type="platform_user_profile_change_refused",
        description="Platform administrator e-mail/password change refused",
    )


async def eis_dat_rollen_gewijzigd_mag_worden(
    db: AsyncSession, request: Request, actor_id: int, doel_user_id: int, tenant_id: int
) -> None:
    """403 (Nederlandse tekst) als de doelgebruiker een platformbeheerder is en de aanvrager de platformrol niet heeft.

    Voor een vervangende rollenset (`PUT /users/{id}` met `role_ids`); afnemen via `revoke-role` en de
    bulkroute loopt via `RBACService.revoke_role`, dat dezelfde regel (`controleer_rollen_wijzigen`) toepast.
    """
    await _weiger_met_403_en_auditregel(
        db,
        request,
        RBACService(db).controleer_rollen_wijzigen(actor_id, doel_user_id, tenant_id),
        actor_id=actor_id,
        doel_user_id=doel_user_id,
        tenant_id=tenant_id,
        event_type="platform_user_roles_change_refused",
        description="Platform administrator role change refused",
    )


async def eis_dat_tenant_gewist_mag_worden(
    db: AsyncSession, request: Request, actor_id: int, tenant_id: int
) -> None:
    """403 (Nederlandse tekst) als de tenant een platformbeheerder bevat en de aanvrager de platformrol niet heeft.

    De regel staat in `RBACService.controleer_tenant_wissen` (`POST /gdpr/delete-all`).
    """
    await _weiger_met_403_en_auditregel(
        db,
        request,
        RBACService(db).controleer_tenant_wissen(actor_id, tenant_id),
        actor_id=actor_id,
        doel_user_id=None,
        tenant_id=tenant_id,
        event_type="platform_tenant_wipe_refused",
        description="Tenant-wide erasure refused: tenant contains a platform administrator",
    )


async def _weiger_met_403_en_auditregel(
    db: AsyncSession,
    request: Request,
    controle: Coroutine[object, object, None],
    *,
    actor_id: int,
    doel_user_id: int | None,
    tenant_id: int,
    event_type: str,
    description: str,
) -> None:
    """Draai een platformregel uit de dienst en vertaal een weigering naar 403 plus een auditregel.

    De auditregel noemt het ECHTE verzoek (methode, pad, IP van `request`), niet een vaste tekst.
    """
    try:
        await controle
    except PermissionError as exc:
        # EERST terugdraaien: de aanroeper kan al een wijziging in de sessie hebben gezet, en de commit
        # hieronder zou die vastleggen terwijl de aanvrager een 403 krijgt: een e-mailwijziging van een
        # platformbeheerder is een accountovername via wachtwoordherstel (Gate 2, B1, gemeten 2026-10-18).
        # De profielroutes roepen de controle bovendien VOOR hun eerste `setattr` aan.
        await db.rollback()

        # Auditeren voor je weigert, direct in `audit_logs`: de `governance_bus` schrijft alleen als de
        # handlers in de app-opstart zijn aangesloten (de testapp draait zonder die opstart).
        from src.core.api.v1.admin.dependencies import log_security_event

        await log_security_event(
            event_type=event_type,
            user_id=actor_id,
            tenant_id=tenant_id,
            request_path=request.url.path,
            request_method=request.method,
            ip_address=request.client.host if request.client else "unknown",
            details={"doel_user_id": doel_user_id} if doel_user_id is not None else {},
            description=description,
            threat_level="high",
            db=db,
        )
        # `log_security_event` schrijft met flush; zonder commit draait de 403 hieronder de transactie terug
        # en verdwijnt de auditregel (gemeten 2026-10-18). Er is op dit punt niets anders gewijzigd.
        await db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def can_manage_users(current_user: object, target_tenant_id: int) -> bool:
    """Check if user can manage users in the target tenant."""
    if is_platform_superuser(current_user):
        return True
    if getattr(current_user, "tenant_id", None) != target_tenant_id:
        return False
    return has_role(current_user, "admin") or has_role(current_user, "TenantAdmin")


async def require_user_manager(
    target_tenant_id: int = Query(..., ge=1, description="Tenant ID to create the user in"),
    current_user: User = Depends(get_current_user),
) -> User:
    """Mag deze gebruiker in `target_tenant_id` gebruikers beheren? Als dependency.

    Stond tot 2026-10-08 in `create_user` zelf, dus na de validatie van de body (plan nazorg,
    punt d). De queryparameter wordt hier en in de route gelezen; het is dezelfde waarde.
    """
    if not can_manage_users(current_user, target_tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to create users in this tenant",
        )
    return current_user


async def _get_tenant_scoped_roles(
    db: AsyncSession,
    tenant_id: int,
    role_ids: list[int],
    *,
    actor_id: int | None = None,
    doel_user_id: int | None = None,
) -> list[Role]:
    """Return only roles that belong to the given tenant for safe assignment.

    Een platformrol (`system_admin`) deelt alleen uit wie hem zelf heeft (`RBACService.mag_rol_uitdelen`):
    anders is dit een achterdeur voor wat `assign-role` en uitnodigen al weigeren (Gate 2, 2026-10-16).
    Heeft de DOELgebruiker de rol al, dan is er niets nieuw toegekend en blijft hij staan. `actor_id=None`
    is het systeem.
    """
    # Een lege set vervangt alles; dan moet een platformrol van de doelgebruiker nog steeds blijven staan.
    if not role_ids and (doel_user_id is None or actor_id is None):
        return []

    roles_result = await db.execute(
        select(Role).where(
            Role.id.in_(role_ids),
            Role.tenant_id == tenant_id,
        )
    )
    roles = list(roles_result.scalars().all())

    found_ids = {int(getattr(r, "id")) for r in roles}
    missing_ids = sorted(rid for rid in role_ids if rid not in found_ids)
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"Some roles were not found in the target tenant: {missing_ids}"),
        )

    if actor_id is not None:
        rbac = RBACService(db)
        if doel_user_id is not None:
            # Een vervangende set laat een platformrol staan die de aanvrager niet mag wijzigen: weglaten is
            # ontnemen, en ontnemen volgt dezelfde regel als uitdelen (brief 2026-10-17).
            roles = roles + await rbac.platformrollen_die_blijven(
                actor_id, doel_user_id, tenant_id, {int(getattr(r, "id")) for r in roles}
            )
        al_in_bezit: set[int] = set()
        if doel_user_id is not None:
            al_in_bezit = {
                int(r)
                for r in (
                    await db.execute(
                        select(user_roles.c.role_id).where(user_roles.c.user_id == doel_user_id)
                    )
                ).scalars()
            }
        for rol in roles:
            if int(getattr(rol, "id")) in al_in_bezit:
                continue
            if not await rbac.mag_rol_uitdelen(actor_id, str(rol.name), tenant_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Deze rol kan alleen door een platformbeheerder worden toegekend.",
                )

    return roles
