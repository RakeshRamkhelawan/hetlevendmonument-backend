# orphan:exempt reason: sub-router samengesteld door auth/router.py (ADR-033 Laag 1)
"""Registration endpoints."""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.auth.schemas import UserResponse
from src.core.auth import auth_service
from src.core.auth.auth_service import (
    DEFAULT_ROLE_NAME,
    RegistrationRequest,
    UserCreate,
)
from src.core.auth import registratie_omgeving
from src.core.middleware.tenant_context import (
    require_tenant_id,  # noqa: F401  (bestaande unit-tests patchen deze naam; hij wordt BEWUST niet aangeroepen)
)
from .auth_config import auth_limiter
from .dependencies import adopt_tenant, get_db, RBACService  # noqa: F401  (patch-doel van bestaande unit-tests)

router = APIRouter(tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    description="Register a new user (Public Endpoint)",
)
@auth_limiter.limit("3/minute")
async def register_user(
    user_data: RegistrationRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Register a new user safely bypassing tenant filters for creation.
    """
    client_ip = request.client.host if request.client else "unknown"

    # Een publieke registratie heeft GEEN tenant en leest er ook geen uit het verzoek:
    # niet uit `require_tenant_id()` (op dit pad leeg, of een achtergebleven waarde van een
    # vorig verzoek), niet uit een header, query of body. De tenant ontstaat verderop uit de
    # NIEUWE rij die deze registratie zelf aanmaakt.
    #
    # In single_tenant is de deur alleen open op een lege installatie (besluit Rakesh
    # 2026-10-04): de eerste registratie maakt de ene tenant en de eerste beheerder, daarna
    # voegen beheerders gebruikers toe. De modus wordt PER AANVRAAG gelezen.
    if registratie_omgeving.is_single_tenant() and (
        await registratie_omgeving.installatie_heeft_al_een_omgeving(db)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is closed",
        )

    # GEEN omzeiling meer bij de bestaanscontrole (ADR-036 OP-154 stap 2b).
    #
    # Hier stond `with TenantFilterBypass():`. Die regel maakte de controle PLATFORMBREED,
    # terwijl de klantcontext op dit punt al vaststaat: `require_tenant_id()` hierboven
    # werpt een fout als hij niet gezet is, dus we zijn er voorbij.
    #
    # Waarom dat weg moet. Na de omschakeling naar `sanskritisetu_app` doet
    # `TenantFilterBypass` alleen nog de ORM-hook uit; PostgreSQL trekt zich daar niets van
    # aan en schermt met de policy op `users` af op de klant die in `app.current_tenant`
    # staat. De applicatielaag en de database zouden dan tegengesteld werken, en de
    # database wint. Het resultaat is een controle PER KLANT.
    #
    # Dat is ook de JUISTE uitkomst: `users.email` is alleen uniek per klant
    # (`rbac_models.py:348`, `idx_user_tenant_email`), er is geen globale unieke index.
    # Een platformbrede controle weigerde dus registraties die de database gewoon toestaat,
    # en gaf tegelijk weg of een adres ergens in het platform bestaat -- precies de
    # gebruikersenumeratie over een klantgrens die het commentaar hieronder beschrijft en
    # die bij OP-235c al half is teruggedrongen door de melding neutraal te maken.
    #
    # De registerrij van OP-154 voorspelde iets anders voor deze plek: "valt die controle
    # stil, dan SLAAGT elke registratie". Nagemeten klopt dat niet -- de controle valt niet
    # stil, hij wordt klantgebonden, en dat is wat de unieke index ook afdwingt.
    existing_user = await auth_service.get_user_by_email(db, email=user_data.email)
    if existing_user:
        # GEEN bestaansinformatie meer in het antwoord (ADR-036 OP-235c). Hier stond
        # "user with this email already exists". Die melding gaf weg of een adres al in
        # gebruik was, en zolang de controle onder `TenantFilterBypass` liep gold dat
        # zelfs platformbreed: een aanmelder kon vaststellen of een adres ergens in het
        # PLATFORM bestond, ook in een andere klant. Die omzeiling is bij OP-154 stap 2b
        # weggehaald (zie de toelichting hierboven), dus de controle is nu klantgebonden.
        # De neutrale melding blijft: binnen een klant is bestaansinformatie nog steeds
        # bestaansinformatie.
        #
        # Dit project houdt die lijn al aan voor wachtwoordherstel
        # (`test_forgot_password_never_reveals_user_existence`). Twee routes in
        # dezelfde applicatie die tegengesteld omgaan met bestaansinformatie is geen
        # ontwerpkeuze maar een inconsistentie.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed",
        )

    # De rolnaam wordt hier SERVER-SIDE gezet en komt nooit uit de request-body.
    # ADR-036 OP-184: dit endpoint bond tot 2026-09-11 het interne `UserCreate`, dat
    # een veld `role_name` heeft, dus een willekeurige aanmelder kon zijn eigen rol
    # meesturen. Hetzelfde patroon gebruikt users_list_router.py:64 al.
    #
    # De eerste gebruiker van een NIEUWE omgeving is de beheerder ervan: er is niemand
    # anders om de omgeving in te richten. Dat geldt alleen voor de tenant die hieronder
    # wordt aangemaakt; deze route kan niemand in een bestaande tenant plaatsen.
    intern = UserCreate(
        email=user_data.email,
        password=user_data.password,
        role_name=registratie_omgeving.EERSTE_GEBRUIKER_ROL,
    )

    # De dubbelcontrole is hierboven al gepasseerd, pas nu ontstaat de tenant.
    tenant_id = await registratie_omgeving.maak_omgeving(db)
    try:
        # De tenant wordt aangenomen zodra hij vaststaat (OP-154): `users` en `roles`
        # hebben een afschermingsregel, `tenants` niet. Het zaaien van de standaardrollen
        # is dezelfde zaaier als bij een beheerder die een tenant aanmaakt
        # (`ensure_default_roles`); `create_user` maakt sinds OP-185 zelf geen rollen aan.
        async with adopt_tenant(db, tenant_id):
            await registratie_omgeving.zaai_rollen(db, tenant_id)
            user = await auth_service.create_user(
                db,
                intern,
                client_ip=client_ip,
                tenant_id=tenant_id,
                request_path="/api/v1/auth/register",
                event_type="REGISTRATION_FAILED",
            )
    except Exception:
        await registratie_omgeving.ruim_mislukte_omgeving_op(db, tenant_id)
        raise

    if not user:
        await registratie_omgeving.ruim_mislukte_omgeving_op(db, tenant_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Registration failed."
        )

    return cast(UserResponse, user)
