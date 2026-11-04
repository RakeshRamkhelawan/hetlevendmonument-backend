"""Docentenomgeving (BE-EP-055, ADR-029).

Openbaar (hCaptcha + rate limit):
- POST /docent/aanvraag                          een docentaccount aanvragen

Ingelogde portalgebruiker:
- GET  /docent/ik                                rol en status van de eigen aanvraag

Docent (rol teacher, curator of admin, altijd van DEZE tenant):
- GET  /docent/lesmateriaal                      alle werkbladen en handleidingen
- GET  /docent/lesmateriaal/{id}                 een werkblad of handleiding
- GET  /docent/lesmateriaal/{id}/pdf             printbare PDF
- GET  /docent/klassen                           eigen klassen
- POST /docent/klassen                           klas met klascode (code staat ALLEEN in dit antwoord)
- POST /docent/klassen/{id}/nieuwe-code          nieuwe code voor de klas (oude werkt niet meer)
- POST /docent/klassen/{id}/intrekken            klascode uitzetten
- PUT  /docent/klassen/{id}/lessen               welke werkbladen de klas ziet
- GET  /docent/klassen/{id}/antwoorden           antwoorden van leerlingen
- PUT  /docent/antwoorden/{id}/feedback          feedback op een antwoord

Leerling (klassessie, zie require_edu_session):
- GET  /edu/antwoorden/{content_id}              eigen antwoorden + feedback
- PUT  /edu/antwoorden/{content_id}              antwoorden opslaan

Beheerder (rol admin):
- GET  /admin/docenten/aanvragen                 aanvragen
- POST /admin/docenten/aanvragen/{id}/goedkeuren rol teacher + welkomstmail met inloglink
- POST /admin/docenten/aanvragen/{id}/afwijzen   afwijzen + mail
- GET  /admin/docenten                           docenten
- POST /admin/docenten/{user_id}/intrekken       docentrol weg, klascodes uit

Een docent ziet en wijzigt alleen EIGEN klassen: een klas van een ander geeft 404 (geen
informatie over wat er bestaat). Privacy van leerlingen: zie
src/core/services/foundation_leerlingantwoorden.py.
"""

from __future__ import annotations

import hashlib
import html
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, Response, status
from loguru import logger
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    best_effort,
    utc_now,
    EduSessionContext,
    brevo_email_service,
    get_db,
    hash_edu_code,
    portal_public_write_limit,
    public_tenant_scope,
    require_admin,
    require_edu_session,
    require_portal_user,
)
from src.core.api.v1.foundation.edu import generate_edu_code
from src.core.shared.config import get_settings
from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    EducationalAccess,
    EducationalRole,
    FoundationClassLesson,
    FoundationContent,
    FoundationPortalSettings,
    FoundationStudentAnswer,
    FoundationTeacherApplication,
    MagicLinkToken,
    PortalRole,
    PortalUser,
    StudyCollection,
    Visibility,
)
from src.core.security.hcaptcha import require_hcaptcha
from src.core.api.v1.foundation.dependencies import (
    OngeldigAntwoord,
    hash_leerlingtoken,
    klas_van_toegang,
    maak_les_pdf,
    schoon_antwoorden,
    schoon_naam,
    toegestane_les_ids,
    verwijder_verlopen_antwoorden,
)

router = APIRouter(tags=["foundation-docent"])


def to_utc(moment: datetime) -> datetime:
    """Naive tijden uit de database als UTC lezen (zelfde als src.core.shared.datetime_utils.to_utc)."""
    return (
        moment.replace(tzinfo=timezone.utc)
        if moment.tzinfo is None
        else moment.astimezone(timezone.utc)
    )


#: Rollen die de docentenomgeving mogen gebruiken.
DOCENT_ROLLEN = (PortalRole.TEACHER, PortalRole.CURATOR, PortalRole.ADMIN)
#: Rollen die bij goedkeuring NIET naar teacher terug mogen (nooit een rol verlagen).
_HOGERE_ROLLEN = (PortalRole.CURATOR, PortalRole.ADMIN)
NIVEAUS = ("groep-7-8", "onderbouw-vo")
#: Een welkomstlink is langer geldig dan een gewone inloglink (15 min): een docent leest de mail
#: niet altijd meteen.
_WELKOMSTLINK_GELDIG = timedelta(hours=48)
#: Bovengrens per klas en werkblad, tegen volschrijven van de tabel.
MAX_ANTWOORDEN_PER_LES = 200

_NIET_GEVONDEN = "Niet gevonden"


# ============================================================================
# Schema's
# ============================================================================


class DocentAanvraagRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    school: str = Field(..., min_length=2, max_length=200)
    function: str | None = Field(None, max_length=200)
    motivation: str | None = Field(None, max_length=2000)
    hcaptcha_token: str | None = None


class DocentAanvraagResponse(BaseModel):
    message: str


class DocentIkResponse(BaseModel):
    email: str
    display_name: str | None = None
    role: str
    is_docent: bool
    aanvraag_status: str | None = None


class LesmateriaalItem(BaseModel):
    id: int
    title: str
    type: str
    target_age_group: str | None = None
    description: str | None = None
    lesnummer: int | None = None


class LesmateriaalDetail(LesmateriaalItem):
    body: str | None = None
    metadata: dict[str, object] | None = None


class KlasAanmaakRequest(BaseModel):
    naam: str = Field(..., min_length=1, max_length=100)
    niveau: Literal["groep-7-8", "onderbouw-vo"]
    geldig_dagen: int = Field(28, ge=1, le=180)
    les_ids: list[int] | None = Field(None, max_length=50)


class NieuweCodeRequest(BaseModel):
    geldig_dagen: int = Field(28, ge=1, le=180)


class LessenRequest(BaseModel):
    les_ids: list[int] = Field(default_factory=list, max_length=50)


class KlasItem(BaseModel):
    id: int
    naam: str
    niveau: str | None = None
    actief: bool
    verloopt_op: datetime | None = None
    les_ids: list[int] = Field(default_factory=list)
    aantal_antwoorden: int = 0
    aangemaakt_op: datetime | None = None


class KlasMetCode(KlasItem):
    code: str


class AntwoordItem(BaseModel):
    id: int
    les_id: int
    leerling: str
    antwoorden: dict[str, str]
    feedback: str | None = None
    feedback_op: datetime | None = None
    bijgewerkt_op: datetime | None = None
    verwijderd_na: datetime | None = None


class FeedbackRequest(BaseModel):
    feedback: str = Field("", max_length=2000)


class LeerlingAntwoordRequest(BaseModel):
    naam: str = Field(..., max_length=80)
    antwoorden: dict[str, str] = Field(default_factory=dict)


class LeerlingAntwoordResponse(BaseModel):
    naam: str | None = None
    antwoorden: dict[str, str] = Field(default_factory=dict)
    feedback: str | None = None
    bijgewerkt_op: datetime | None = None
    verwijderd_na: datetime | None = None


class AanvraagItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    school: str
    function: str | None = None
    motivation: str | None = None
    status: str
    created_at: datetime | None = None
    decided_at: datetime | None = None


class AfwijsRequest(BaseModel):
    reden: str | None = Field(None, max_length=1000)


class DocentItem(BaseModel):
    id: int
    email: str
    display_name: str | None = None
    aantal_klassen: int = 0


# ============================================================================
# Hulpfuncties
# ============================================================================


async def require_docent(user: PortalUser = Depends(require_portal_user)) -> PortalUser:
    """Docent, curator of beheerder."""
    if user.role not in DOCENT_ROLLEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Docentaccount vereist")
    return user


def _eigen_tenant(user: PortalUser, tenant_id: int) -> None:
    if user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User does not belong to this tenant"
        )


def _rol(user: PortalUser) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


async def _eigen_klas(
    sessie: AsyncSession, tenant_id: int, user: PortalUser, klas_id: int
) -> StudyCollection:
    """Een klas van DEZE docent, anders 404 (ook als de klas van een ander is)."""
    resultaat = await sessie.execute(
        select(StudyCollection).where(
            StudyCollection.id == klas_id,
            StudyCollection.tenant_id == tenant_id,
            StudyCollection.owner_portal_user_id == user.id,
        )
    )
    klas = resultaat.scalar_one_or_none()
    if klas is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NIET_GEVONDEN)
    return klas


async def _toegang(sessie: AsyncSession, tenant_id: int, toegang_id: int) -> EducationalAccess:
    resultaat = await sessie.execute(
        select(EducationalAccess).where(
            EducationalAccess.id == toegang_id,
            EducationalAccess.tenant_id == tenant_id,
        )
    )
    toegang = resultaat.scalar_one_or_none()
    if toegang is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NIET_GEVONDEN)
    return toegang


def _werkbladen_query(tenant_id: int) -> Select[tuple[FoundationContent]]:
    return select(FoundationContent).where(
        FoundationContent.tenant_id == tenant_id,
        FoundationContent.type == ContentType.EDUCATIONAL_WORKBOOK,
        FoundationContent.visibility == Visibility.EDU,
        FoundationContent.status == ContentStatus.APPROVED,
    )


async def _geldige_les_ids(sessie: AsyncSession, tenant_id: int, les_ids: list[int]) -> list[int]:
    """Alleen goedgekeurde werkbladen van deze tenant; een onbekend id is een 422."""
    gevraagd = sorted(set(les_ids))
    if not gevraagd:
        return []
    resultaat = await sessie.execute(
        _werkbladen_query(tenant_id)
        .with_only_columns(FoundationContent.id)
        .where(FoundationContent.id.in_(gevraagd))
    )
    gevonden = {int(i) for i in resultaat.scalars().all()}
    onbekend = set(gevraagd) - gevonden
    if onbekend:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Onbekend werkblad: {', '.join(str(i) for i in sorted(onbekend))}",
        )
    return gevraagd


async def _zet_lessen(
    sessie: AsyncSession, tenant_id: int, klas: StudyCollection, les_ids: list[int]
) -> None:
    bestaand = await sessie.execute(
        select(FoundationClassLesson).where(
            FoundationClassLesson.tenant_id == tenant_id,
            FoundationClassLesson.study_collection_id == klas.id,
        )
    )
    huidig = {int(r.content_id): r for r in bestaand.scalars().all()}
    gewenst = set(les_ids)
    for content_id, rij in huidig.items():
        if content_id not in gewenst:
            await sessie.delete(rij)
    for content_id in sorted(gewenst - set(huidig)):
        sessie.add(
            FoundationClassLesson(
                tenant_id=tenant_id, study_collection_id=klas.id, content_id=content_id
            )
        )


async def _klas_item(sessie: AsyncSession, tenant_id: int, klas: StudyCollection) -> KlasItem:
    toegang = await _toegang(sessie, tenant_id, klas.educational_access_id)
    lessen = await sessie.execute(
        select(FoundationClassLesson.content_id).where(
            FoundationClassLesson.tenant_id == tenant_id,
            FoundationClassLesson.study_collection_id == klas.id,
        )
    )
    aantal = await sessie.execute(
        select(func.count())
        .select_from(FoundationStudentAnswer)
        .where(
            FoundationStudentAnswer.tenant_id == tenant_id,
            FoundationStudentAnswer.study_collection_id == klas.id,
        )
    )
    verloopt = to_utc(toegang.expires_at) if toegang.expires_at else None
    return KlasItem(
        id=klas.id,
        naam=klas.name,
        niveau=klas.target_age_group,
        actief=bool(toegang.is_active) and (verloopt is None or verloopt > utc_now()),
        verloopt_op=toegang.expires_at,
        les_ids=sorted(int(i) for i in lessen.scalars().all()),
        aantal_antwoorden=int(aantal.scalar() or 0),
        aangemaakt_op=klas.created_at,
    )


async def _nieuwe_code(sessie: AsyncSession) -> tuple[str, str]:
    for _ in range(5):
        code = generate_edu_code(8)
        code_hash = hash_edu_code(code)
        bezet = await sessie.execute(
            select(EducationalAccess.id).where(EducationalAccess.code_hash == code_hash)
        )
        if bezet.scalar_one_or_none() is None:
            return code, code_hash
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Geen unieke klascode gevonden"
    )


def _lesmateriaal_item(c: FoundationContent) -> LesmateriaalItem:
    meta = c.metadata_ or {}
    return LesmateriaalItem(
        id=c.id,
        title=c.title_nl,
        type=c.type.value if hasattr(c.type, "value") else str(c.type),
        target_age_group=c.target_age_group,
        description=c.description_nl,
        lesnummer=meta.get("lesnummer") if isinstance(meta.get("lesnummer"), int) else None,
    )


async def _contactadres(sessie: AsyncSession, tenant_id: int) -> str | None:
    res = await sessie.execute(
        select(FoundationPortalSettings.contact_email).where(
            FoundationPortalSettings.tenant_id == tenant_id
        )
    )
    return res.scalar_one_or_none()


def _portal_url() -> str:
    return get_settings().foundation_portal_base_url.rstrip("/")


async def _mail(
    to: str, onderwerp: str, alineas: list[str], tags: list[str], reply_to: str | None = None
) -> None:
    """Een eenvoudige mail (HTML + tekst); fouten worden gelogd en niet doorgegeven."""
    html_body = "".join(f"<p>{html.escape(a)}</p>" for a in alineas)
    inhoud = (
        '<!DOCTYPE html><html lang="nl"><head><meta charset="utf-8"></head>'
        '<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; '
        f'margin: 0 auto; padding: 24px;">{html_body}</body></html>'
    )
    async with best_effort("docent_mail"):
        await brevo_email_service.send_transactional_email(
            to_email=to,
            subject=onderwerp,
            html_content=inhoud,
            text_content="\n\n".join(alineas),
            tags=tags,
            reply_to=reply_to,
        )


# ============================================================================
# Openbaar: aanvraag
# ============================================================================


@router.post(
    "/docent/aanvraag", response_model=DocentAanvraagResponse, status_code=status.HTTP_202_ACCEPTED
)
@portal_public_write_limit
async def vraag_docentaccount_aan(
    tenantSlug: str,
    request: Request,
    data: DocentAanvraagRequest = Body(...),
    session: AsyncSession = Depends(get_db),
) -> DocentAanvraagResponse:
    """Een docent vraagt een account aan. Altijd hetzelfde antwoord (geen informatie over
    bestaande accounts); een tweede openstaande aanvraag met hetzelfde adres wordt niet bewaard."""
    client_ip = request.client.host if request.client else None
    await require_hcaptcha(data.hcaptcha_token, remote_ip=client_ip)
    email = str(data.email).strip().lower()
    async with public_tenant_scope(tenantSlug, session) as tenant:
        bestaand = await session.execute(
            select(FoundationTeacherApplication.id).where(
                FoundationTeacherApplication.tenant_id == tenant.id,
                FoundationTeacherApplication.email == email,
                FoundationTeacherApplication.status == "pending",
            )
        )
        nieuw = bestaand.scalars().first() is None
        if nieuw:
            session.add(
                FoundationTeacherApplication(
                    tenant_id=tenant.id,
                    email=email,
                    name=data.name.strip(),
                    school=data.school.strip(),
                    function=(data.function or "").strip() or None,
                    motivation=(data.motivation or "").strip() or None,
                    status="pending",
                )
            )
        beheer = await _contactadres(session, tenant.id)
        naam = getattr(tenant, "name", None) or "Het Levend Monument"
        await session.commit()
    if nieuw:
        await _mail(
            email,
            f"Uw aanvraag voor een docentaccount - {naam}",
            [
                f"Beste {data.name.strip()},",
                f"Dank voor uw aanvraag voor een docentaccount bij {naam}. Wij bekijken die zo snel mogelijk.",
                "Na goedkeuring ontvangt u een e-mail met een link om in te loggen.",
            ],
            ["portal-docent", "aanvraag"],
        )
        if beheer:
            await _mail(
                beheer,
                f"Nieuwe aanvraag docentaccount: {data.name.strip()} ({data.school.strip()})",
                [
                    f"Naam: {data.name.strip()}",
                    f"E-mail: {email}",
                    f"School: {data.school.strip()}",
                    f"Functie: {(data.function or '-').strip()}",
                    f"Toelichting: {(data.motivation or '-').strip()}",
                    f"Goedkeuren of afwijzen: {_portal_url()}/beheer (tab Docenten).",
                ],
                ["portal-docent", "aanvraag-beheer"],
                reply_to=email,
            )
    return DocentAanvraagResponse(message="Dank u wel. Uw aanvraag is ontvangen.")


@router.get("/docent/ik", response_model=DocentIkResponse)
async def wie_ben_ik(
    tenantSlug: str,
    user: PortalUser = Depends(require_portal_user),
    session: AsyncSession = Depends(get_db),
) -> DocentIkResponse:
    """Rol van de ingelogde gebruiker en de status van een eventuele aanvraag."""
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        res = await session.execute(
            select(FoundationTeacherApplication.status)
            .where(
                FoundationTeacherApplication.tenant_id == tenant.id,
                FoundationTeacherApplication.email == user.email.lower(),
            )
            .order_by(FoundationTeacherApplication.created_at.desc())
            .limit(1)
        )
        aanvraag = res.scalars().first()
    return DocentIkResponse(
        email=user.email,
        display_name=user.display_name,
        role=_rol(user),
        is_docent=user.role in DOCENT_ROLLEN,
        aanvraag_status=aanvraag,
    )


# ============================================================================
# Docent: lesmateriaal
# ============================================================================


@router.get("/docent/lesmateriaal", response_model=list[LesmateriaalItem])
async def lesmateriaal(
    tenantSlug: str,
    user: PortalUser = Depends(require_docent),
    session: AsyncSession = Depends(get_db),
) -> list[LesmateriaalItem]:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        res = await session.execute(
            select(FoundationContent)
            .where(
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.status == ContentStatus.APPROVED,
                FoundationContent.type.in_(
                    [ContentType.EDUCATIONAL_WORKBOOK, ContentType.TEACHER_GUIDE]
                ),
            )
            .order_by(FoundationContent.target_age_group, FoundationContent.title_nl)
        )
        return [_lesmateriaal_item(c) for c in res.scalars().all()]


async def _les_van_tenant(
    sessie: AsyncSession, tenant_id: int, content_id: int
) -> FoundationContent:
    res = await sessie.execute(
        select(FoundationContent).where(
            FoundationContent.id == content_id,
            FoundationContent.tenant_id == tenant_id,
            FoundationContent.status == ContentStatus.APPROVED,
            FoundationContent.type.in_(
                [ContentType.EDUCATIONAL_WORKBOOK, ContentType.TEACHER_GUIDE]
            ),
        )
    )
    les = res.scalar_one_or_none()
    if les is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NIET_GEVONDEN)
    return les


@router.get("/docent/lesmateriaal/{content_id}", response_model=LesmateriaalDetail)
async def lesmateriaal_detail(
    tenantSlug: str,
    content_id: int,
    user: PortalUser = Depends(require_docent),
    session: AsyncSession = Depends(get_db),
) -> LesmateriaalDetail:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        les = await _les_van_tenant(session, tenant.id, content_id)
        basis = _lesmateriaal_item(les)
        return LesmateriaalDetail(
            **basis.model_dump(), body=les.body_nl, metadata=les.metadata_ or {}
        )


@router.get("/docent/lesmateriaal/{content_id}/pdf")
async def lesmateriaal_pdf(
    tenantSlug: str,
    content_id: int,
    user: PortalUser = Depends(require_docent),
    session: AsyncSession = Depends(get_db),
) -> Response:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        les = await _les_van_tenant(session, tenant.id, content_id)
        meta = les.metadata_ or {}
        pdf = maak_les_pdf(
            les.title_nl,
            les.body_nl or "",
            werkblad=les.type == ContentType.EDUCATIONAL_WORKBOOK,
            bronnen=meta.get("bronnen") if isinstance(meta.get("bronnen"), list) else None,
            afzender=getattr(tenant, "name", None) or "Het Levend Monument",
        )
    bestandsnaam = (
        "".join(ch if ch.isalnum() else "-" for ch in les.title_nl.lower()).strip("-")[:80] or "les"
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{bestandsnaam}.pdf"'},
    )


# ============================================================================
# Docent: klassen
# ============================================================================


@router.get("/docent/klassen", response_model=list[KlasItem])
async def mijn_klassen(
    tenantSlug: str,
    user: PortalUser = Depends(require_docent),
    session: AsyncSession = Depends(get_db),
) -> list[KlasItem]:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        res = await session.execute(
            select(StudyCollection)
            .where(
                StudyCollection.tenant_id == tenant.id,
                StudyCollection.owner_portal_user_id == user.id,
            )
            .order_by(StudyCollection.created_at.desc())
        )
        return [await _klas_item(session, tenant.id, k) for k in res.scalars().all()]


@router.post("/docent/klassen", response_model=KlasMetCode, status_code=status.HTTP_201_CREATED)
async def maak_klas(
    tenantSlug: str,
    data: KlasAanmaakRequest,
    user: PortalUser = Depends(require_docent),
    session: AsyncSession = Depends(get_db),
) -> KlasMetCode:
    """Een klas met een klascode. Zonder les_ids staan alle werkbladen van het niveau open."""
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        if data.les_ids is None:
            res = await session.execute(
                _werkbladen_query(tenant.id)
                .with_only_columns(FoundationContent.id)
                .where(FoundationContent.target_age_group == data.niveau)
            )
            les_ids = sorted(int(i) for i in res.scalars().all())
        else:
            les_ids = await _geldige_les_ids(session, tenant.id, data.les_ids)
        code, code_hash = await _nieuwe_code(session)
        nu = utc_now()
        toegang = EducationalAccess(
            tenant_id=tenant.id,
            code_hash=code_hash,
            email=user.email,
            role=EducationalRole.STUDENT,
            is_active=True,
            expires_at=nu + timedelta(days=data.geldig_dagen),
            created_at=nu,
        )
        session.add(toegang)
        await session.flush()
        klas = StudyCollection(
            tenant_id=tenant.id,
            educational_access_id=toegang.id,
            name=data.naam.strip(),
            description=f"Klas van {user.email}",
            owner_portal_user_id=user.id,
            target_age_group=data.niveau,
            created_at=nu,
        )
        session.add(klas)
        await session.flush()
        await _zet_lessen(session, tenant.id, klas, les_ids)
        await session.flush()
        item = await _klas_item(session, tenant.id, klas)
        await session.commit()
    return KlasMetCode(**item.model_dump(), code=code)


@router.post("/docent/klassen/{klas_id}/nieuwe-code", response_model=KlasMetCode)
async def nieuwe_klascode(
    tenantSlug: str,
    klas_id: int,
    data: NieuweCodeRequest | None = None,
    user: PortalUser = Depends(require_docent),
    session: AsyncSession = Depends(get_db),
) -> KlasMetCode:
    """Nieuwe code voor dezelfde klas: lessen en antwoorden blijven, de oude code werkt niet meer."""
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        klas = await _eigen_klas(session, tenant.id, user, klas_id)
        toegang = await _toegang(session, tenant.id, klas.educational_access_id)
        code, code_hash = await _nieuwe_code(session)
        dagen = (data or NieuweCodeRequest()).geldig_dagen
        toegang.code_hash = code_hash
        toegang.is_active = True
        toegang.expires_at = utc_now() + timedelta(days=dagen)
        await session.flush()
        item = await _klas_item(session, tenant.id, klas)
        await session.commit()
    return KlasMetCode(**item.model_dump(), code=code)


@router.post("/docent/klassen/{klas_id}/intrekken", response_model=KlasItem)
async def trek_klascode_in(
    tenantSlug: str,
    klas_id: int,
    user: PortalUser = Depends(require_docent),
    session: AsyncSession = Depends(get_db),
) -> KlasItem:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        klas = await _eigen_klas(session, tenant.id, user, klas_id)
        toegang = await _toegang(session, tenant.id, klas.educational_access_id)
        toegang.is_active = False
        await session.flush()
        item = await _klas_item(session, tenant.id, klas)
        await session.commit()
    return item


@router.put("/docent/klassen/{klas_id}/lessen", response_model=KlasItem)
async def zet_klaslessen(
    tenantSlug: str,
    klas_id: int,
    data: LessenRequest,
    user: PortalUser = Depends(require_docent),
    session: AsyncSession = Depends(get_db),
) -> KlasItem:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        klas = await _eigen_klas(session, tenant.id, user, klas_id)
        les_ids = await _geldige_les_ids(session, tenant.id, data.les_ids)
        await _zet_lessen(session, tenant.id, klas, les_ids)
        await session.flush()
        item = await _klas_item(session, tenant.id, klas)
        await session.commit()
    return item


def _antwoord_item(a: FoundationStudentAnswer) -> AntwoordItem:
    aangemaakt = to_utc(a.created_at) if a.created_at else None
    return AntwoordItem(
        id=a.id,
        les_id=a.content_id,
        leerling=a.student_name,
        antwoorden={str(k): str(v) for k, v in (a.answers or {}).items()},
        feedback=a.teacher_feedback,
        feedback_op=a.feedback_at,
        bijgewerkt_op=a.updated_at,
        verwijderd_na=(aangemaakt + timedelta(weeks=8)) if aangemaakt else None,
    )


@router.get("/docent/klassen/{klas_id}/antwoorden", response_model=list[AntwoordItem])
async def klasantwoorden(
    tenantSlug: str,
    klas_id: int,
    les_id: int | None = None,
    user: PortalUser = Depends(require_docent),
    session: AsyncSession = Depends(get_db),
) -> list[AntwoordItem]:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        klas = await _eigen_klas(session, tenant.id, user, klas_id)
        await verwijder_verlopen_antwoorden(session, utc_now(), tenant.id)
        stmt = select(FoundationStudentAnswer).where(
            FoundationStudentAnswer.tenant_id == tenant.id,
            FoundationStudentAnswer.study_collection_id == klas.id,
        )
        if les_id is not None:
            stmt = stmt.where(FoundationStudentAnswer.content_id == les_id)
        res = await session.execute(
            stmt.order_by(FoundationStudentAnswer.content_id, FoundationStudentAnswer.student_name)
        )
        items = [_antwoord_item(a) for a in res.scalars().all()]
        await session.commit()
    return items


@router.put("/docent/antwoorden/{antwoord_id}/feedback", response_model=AntwoordItem)
async def geef_feedback(
    tenantSlug: str,
    antwoord_id: int,
    data: FeedbackRequest,
    user: PortalUser = Depends(require_docent),
    session: AsyncSession = Depends(get_db),
) -> AntwoordItem:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        res = await session.execute(
            select(FoundationStudentAnswer).where(
                FoundationStudentAnswer.id == antwoord_id,
                FoundationStudentAnswer.tenant_id == tenant.id,
            )
        )
        antwoord = res.scalar_one_or_none()
        if antwoord is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NIET_GEVONDEN)
        # Eigenaarscontrole via de klas: feedback op een antwoord uit een andere klas is een 404.
        await _eigen_klas(session, tenant.id, user, antwoord.study_collection_id)
        tekst = data.feedback.strip()
        antwoord.teacher_feedback = tekst or None
        antwoord.feedback_at = utc_now() if tekst else None
        await session.flush()
        item = _antwoord_item(antwoord)
        await session.commit()
    return item


# ============================================================================
# Leerling: antwoorden (klassessie)
# ============================================================================


async def _werkblad_voor_klas(
    sessie: AsyncSession, ctx: EduSessionContext, content_id: int
) -> FoundationContent:
    toegestaan = await toegestane_les_ids(sessie, ctx.tenant.id, ctx.access.id)
    if toegestaan is not None and content_id not in toegestaan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NIET_GEVONDEN)
    res = await sessie.execute(
        _werkbladen_query(ctx.tenant.id).where(FoundationContent.id == content_id)
    )
    werkblad = res.scalar_one_or_none()
    if werkblad is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NIET_GEVONDEN)
    return werkblad


def _leerlingtoken(token: str | None) -> str:
    if not token or not (16 <= len(token) <= 100):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Leerlingtoken ontbreekt"
        )
    return hash_leerlingtoken(token)


async def _eigen_antwoord(
    sessie: AsyncSession, tenant_id: int, klas_id: int, content_id: int, token_hash: str
) -> FoundationStudentAnswer | None:
    res = await sessie.execute(
        select(FoundationStudentAnswer).where(
            FoundationStudentAnswer.tenant_id == tenant_id,
            FoundationStudentAnswer.study_collection_id == klas_id,
            FoundationStudentAnswer.content_id == content_id,
            FoundationStudentAnswer.client_token_hash == token_hash,
        )
    )
    return res.scalar_one_or_none()


def _leerling_response(a: FoundationStudentAnswer | None) -> LeerlingAntwoordResponse:
    if a is None:
        return LeerlingAntwoordResponse()
    item = _antwoord_item(a)
    return LeerlingAntwoordResponse(
        naam=item.leerling,
        antwoorden=item.antwoorden,
        feedback=item.feedback,
        bijgewerkt_op=item.bijgewerkt_op,
        verwijderd_na=item.verwijderd_na,
    )


@router.get("/edu/antwoorden/{content_id}", response_model=LeerlingAntwoordResponse)
async def mijn_antwoorden(
    tenantSlug: str,
    content_id: int,
    x_leerling_token: str | None = Header(None),
    ctx: EduSessionContext = Depends(require_edu_session),
    session: AsyncSession = Depends(get_db),
) -> LeerlingAntwoordResponse:
    token_hash = _leerlingtoken(x_leerling_token)
    async with public_tenant_scope(tenantSlug, session) as tenant:
        await _werkblad_voor_klas(session, ctx, content_id)
        klas = await klas_van_toegang(session, tenant.id, ctx.access.id)
        if klas is None:
            return LeerlingAntwoordResponse()
        await verwijder_verlopen_antwoorden(session, utc_now(), tenant.id)
        antwoord = await _eigen_antwoord(session, tenant.id, klas.id, content_id, token_hash)
        uit = _leerling_response(antwoord)
        await session.commit()
    return uit


@router.put("/edu/antwoorden/{content_id}", response_model=LeerlingAntwoordResponse)
async def sla_antwoorden_op(
    tenantSlug: str,
    content_id: int,
    data: LeerlingAntwoordRequest,
    x_leerling_token: str | None = Header(None),
    ctx: EduSessionContext = Depends(require_edu_session),
    session: AsyncSession = Depends(get_db),
) -> LeerlingAntwoordResponse:
    """Antwoorden van een leerling opslaan of bijwerken (alleen met een leerlingcode)."""
    if ctx.access.role != EducationalRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Alleen leerlingen slaan antwoorden op"
        )
    token_hash = _leerlingtoken(x_leerling_token)
    async with public_tenant_scope(tenantSlug, session) as tenant:
        werkblad = await _werkblad_voor_klas(session, ctx, content_id)
        klas = await klas_van_toegang(session, tenant.id, ctx.access.id)
        if klas is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NIET_GEVONDEN)
        vragen = (werkblad.metadata_ or {}).get("vragen") or []
        try:
            naam = schoon_naam(data.naam)
            antwoorden = schoon_antwoorden(
                data.antwoorden, vragen if isinstance(vragen, list) else []
            )
        except OngeldigAntwoord as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
        await verwijder_verlopen_antwoorden(session, utc_now(), tenant.id)
        antwoord = await _eigen_antwoord(session, tenant.id, klas.id, content_id, token_hash)
        nu = utc_now()
        if antwoord is None:
            aantal = await session.execute(
                select(func.count())
                .select_from(FoundationStudentAnswer)
                .where(
                    FoundationStudentAnswer.tenant_id == tenant.id,
                    FoundationStudentAnswer.study_collection_id == klas.id,
                    FoundationStudentAnswer.content_id == content_id,
                )
            )
            if int(aantal.scalar() or 0) >= MAX_ANTWOORDEN_PER_LES:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Deze les heeft het maximale aantal inzendingen",
                )
            antwoord = FoundationStudentAnswer(
                tenant_id=tenant.id,
                study_collection_id=klas.id,
                content_id=content_id,
                student_name=naam,
                client_token_hash=token_hash,
                answers=antwoorden,
                created_at=nu,
                updated_at=nu,
            )
            session.add(antwoord)
        else:
            antwoord.student_name = naam
            antwoord.answers = antwoorden
            antwoord.updated_at = nu
        await session.flush()
        uit = _leerling_response(antwoord)
        await session.commit()
    return uit


# ============================================================================
# Beheer: aanvragen en docenten
# ============================================================================


@router.get("/admin/docenten/aanvragen", response_model=list[AanvraagItem])
async def docentaanvragen(
    tenantSlug: str,
    status_filter: Literal["pending", "approved", "rejected", "alle"] = "pending",
    user: PortalUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> list[AanvraagItem]:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        stmt = select(FoundationTeacherApplication).where(
            FoundationTeacherApplication.tenant_id == tenant.id
        )
        if status_filter != "alle":
            stmt = stmt.where(FoundationTeacherApplication.status == status_filter)
        res = await session.execute(stmt.order_by(FoundationTeacherApplication.created_at.desc()))
        return [AanvraagItem.model_validate(a) for a in res.scalars().all()]


async def _aanvraag(
    sessie: AsyncSession, tenant_id: int, aanvraag_id: int
) -> FoundationTeacherApplication:
    res = await sessie.execute(
        select(FoundationTeacherApplication).where(
            FoundationTeacherApplication.id == aanvraag_id,
            FoundationTeacherApplication.tenant_id == tenant_id,
        )
    )
    aanvraag = res.scalar_one_or_none()
    if aanvraag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NIET_GEVONDEN)
    if aanvraag.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Deze aanvraag is al afgehandeld"
        )
    return aanvraag


@router.post("/admin/docenten/aanvragen/{aanvraag_id}/goedkeuren", response_model=AanvraagItem)
async def keur_aanvraag_goed(
    tenantSlug: str,
    aanvraag_id: int,
    user: PortalUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AanvraagItem:
    """De aanvrager wordt docent en krijgt een welkomstmail met een inloglink (48 uur)."""
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        aanvraag = await _aanvraag(session, tenant.id, aanvraag_id)
        res = await session.execute(
            select(PortalUser).where(
                PortalUser.tenant_id == tenant.id, func.lower(PortalUser.email) == aanvraag.email
            )
        )
        docent = res.scalars().first()
        nu = utc_now()
        if docent is None:
            docent = PortalUser(
                tenant_id=tenant.id,
                email=aanvraag.email,
                display_name=aanvraag.name,
                role=PortalRole.TEACHER,
                is_verified=True,
                email_verified=True,
                consent_given=True,
                consent_given_at=nu,
            )
            session.add(docent)
            await session.flush()
        elif docent.role not in _HOGERE_ROLLEN:
            # Nooit een curator of beheerder terugzetten naar docent.
            docent.role = PortalRole.TEACHER
            docent.is_blocked = False
        aanvraag.status = "approved"
        aanvraag.portal_user_id = docent.id
        aanvraag.decided_by_portal_user_id = user.id
        aanvraag.decided_at = nu
        ruw = secrets.token_urlsafe(32)
        session.add(
            MagicLinkToken(
                tenant_id=tenant.id,
                portal_user_id=docent.id,
                token_hash=hashlib.sha256(ruw.encode("utf-8")).hexdigest(),
                expires_at=nu + _WELKOMSTLINK_GELDIG,
            )
        )
        await session.flush()
        item = AanvraagItem.model_validate(aanvraag)
        naam = getattr(tenant, "name", None) or "Het Levend Monument"
        # Na de commit kunnen ORM-attributen verlopen zijn (lazy load buiten greenlet).
        aan, aanvrager = aanvraag.email, aanvraag.name
        await session.commit()
    link = f"{_portal_url()}/inloggen?token={ruw}&tenant={tenantSlug}"
    await _mail(
        aan,
        f"Uw docentaccount bij {naam} is klaar",
        [
            f"Beste {aanvrager},",
            f"Uw docentaccount bij {naam} is goedgekeurd.",
            f"Log de eerste keer in met deze link (48 uur geldig, eenmalig): {link}",
            f"Daarna logt u in via {_portal_url()}/inloggen met uw e-mailadres. U ontvangt dan steeds een nieuwe inloglink.",
            f"In het docentenportaal ({_portal_url()}/docenten) maakt u klassen en klascodes, zet u lessen open en leest u de antwoorden van uw leerlingen.",
        ],
        ["portal-docent", "goedgekeurd"],
    )
    logger.info("docentaanvraag goedgekeurd: id={} tenant={}", aanvraag_id, tenantSlug)
    return item


@router.post("/admin/docenten/aanvragen/{aanvraag_id}/afwijzen", response_model=AanvraagItem)
async def wijs_aanvraag_af(
    tenantSlug: str,
    aanvraag_id: int,
    data: AfwijsRequest | None = None,
    user: PortalUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AanvraagItem:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        aanvraag = await _aanvraag(session, tenant.id, aanvraag_id)
        aanvraag.status = "rejected"
        aanvraag.decided_by_portal_user_id = user.id
        aanvraag.decided_at = utc_now()
        await session.flush()
        item = AanvraagItem.model_validate(aanvraag)
        naam = getattr(tenant, "name", None) or "Het Levend Monument"
        beheer = await _contactadres(session, tenant.id)
        aan, aanvrager = aanvraag.email, aanvraag.name
        await session.commit()
    alineas = [
        f"Beste {aanvrager},",
        f"Helaas kunnen wij uw aanvraag voor een docentaccount bij {naam} nu niet goedkeuren.",
    ]
    reden = (data.reden or "").strip() if data else ""
    if reden:
        alineas.append(f"Toelichting: {reden}")
    if beheer:
        alineas.append(f"Vragen? Mail ons via {beheer}.")
    await _mail(
        aan, f"Uw aanvraag voor een docentaccount - {naam}", alineas, ["portal-docent", "afgewezen"]
    )
    return item


@router.get("/admin/docenten", response_model=list[DocentItem])
async def docenten(
    tenantSlug: str,
    user: PortalUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> list[DocentItem]:
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        res = await session.execute(
            select(PortalUser)
            .where(PortalUser.tenant_id == tenant.id, PortalUser.role == PortalRole.TEACHER)
            .order_by(PortalUser.email)
        )
        uit: list[DocentItem] = []
        for d in res.scalars().all():
            aantal = await session.execute(
                select(func.count())
                .select_from(StudyCollection)
                .where(
                    StudyCollection.tenant_id == tenant.id,
                    StudyCollection.owner_portal_user_id == d.id,
                )
            )
            uit.append(
                DocentItem(
                    id=d.id,
                    email=d.email,
                    display_name=d.display_name,
                    aantal_klassen=int(aantal.scalar() or 0),
                )
            )
        return uit


@router.post("/admin/docenten/{docent_id}/intrekken", response_model=DocentItem)
async def trek_docentrol_in(
    tenantSlug: str,
    docent_id: int,
    user: PortalUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> DocentItem:
    """Docentrol terug naar bezoeker; alle klascodes van deze docent werken direct niet meer."""
    async with public_tenant_scope(tenantSlug, session) as tenant:
        _eigen_tenant(user, tenant.id)
        res = await session.execute(
            select(PortalUser).where(
                PortalUser.id == docent_id,
                PortalUser.tenant_id == tenant.id,
                PortalUser.role == PortalRole.TEACHER,
            )
        )
        docent = res.scalar_one_or_none()
        if docent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NIET_GEVONDEN)
        docent.role = PortalRole.VISITOR
        klassen = await session.execute(
            select(StudyCollection).where(
                StudyCollection.tenant_id == tenant.id,
                StudyCollection.owner_portal_user_id == docent.id,
            )
        )
        aantal = 0
        for klas in klassen.scalars().all():
            toegang = await _toegang(session, tenant.id, klas.educational_access_id)
            toegang.is_active = False
            aantal += 1
        await session.flush()
        item = DocentItem(
            id=docent.id,
            email=docent.email,
            display_name=docent.display_name,
            aantal_klassen=aantal,
        )
        await session.commit()
    return item
