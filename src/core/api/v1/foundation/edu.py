"""Foundation Portal educational environment endpoints (BE-EP-039, ADR-029 Sprint D).

Protected /edu/* section: students/teachers get access via an 8-character
alphanumeric access code, no individual accounts. The session cookie holds
ONLY an opaque ID; role and code validity are re-validated against the
database on every request (audit P0-5 fix). Edu content (visibility=edu)
never appears in the public archive (content.py O5 filter).
"""

from __future__ import annotations

import os
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    EducationalAccess,
    EducationalRole,
    FoundationContent,
    PortalUser,
    StudyCollection,
    Visibility,
)

from src.core.api.v1.foundation.dependencies import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    EduSessionContext,
    EduSessionService,
    EduSessionStoreUnavailableError,
    get_db,
    get_edu_session_service,
    hash_edu_code,
    public_tenant_scope,
    require_curator,
    require_edu_session,
    require_portal_auth_rate_limit,
)
from src.core.api.v1.foundation.schemas import (
    CreateEduCodeRequest,
    EduCodeCreateResponse,
    EduCodeItem,
    EduCodeListResponse,
    EduSessionRequest,
    EduSessionResponse,
    FoundationContentDetail,
    FoundationContentListItem,
    FoundationContentListResponse,
)
from src.core.api.v1.foundation.dependencies import toegestane_les_ids
from src.core.shared.datetime_utils import to_utc, utc_now

router = APIRouter(tags=["foundation-edu"])

# Safe alphabet for educational access codes: 32 uppercase characters (5 bits entropy each).
# Excluding ambiguous characters: 0, O, 1, I, L.
SAFE_EDU_ALPHABET: str = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def generate_edu_code(length: int = 8) -> str:
    """Generate cryptographically secure uppercase alphanumeric access code of exact length (BE-EP-044)."""
    return "".join(secrets.choice(SAFE_EDU_ALPHABET) for _ in range(length))


# Uniform 401 for every code-validation failure (spec O4): no distinction
# between unknown / inactive / expired, so codes cannot be enumerated.
_INVALID_CODE_DETAIL = "Invalid or expired code"

_UNIFORM_404_DETAIL = "Content not found"


def _set_session_cookie(request: Request, response: Response, session_id: str) -> None:
    """Set the edu_session cookie (spec O3).

    secure flag: production or HTTPS only -- same pattern as the portal
    login cookies (router_login.py); over plain HTTP (local dev, tests) a
    Secure cookie would be dropped by the client.
    """
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
    secure_flag = is_production or request.url.scheme == "https"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=secure_flag,
        samesite="strict",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )


@router.post(
    "/edu/session",
    response_model=EduSessionResponse,
    summary="Create edu session with access code",
)
async def create_edu_session(
    tenantSlug: str,
    request: Request,
    response: Response,
    data: EduSessionRequest,
    session: AsyncSession = Depends(get_db),
    edu_sessions: EduSessionService = Depends(get_edu_session_service),
    _check_ip: None = Depends(require_portal_auth_rate_limit),
) -> EduSessionResponse:
    """Exchange a valid access code for a server-side edu session.

    - Public endpoint (code entry), rate-limited at auth level (5/min/IP)
    - Uniform 401 for unknown/inactive/expired codes (no enumeration)
    - Cookie holds only the opaque session ID; role comes from the DB
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        result = await session.execute(
            select(EducationalAccess).where(
                EducationalAccess.tenant_id == tenant.id,
                EducationalAccess.code_hash == hash_edu_code(data.code),
            )
        )
        access: EducationalAccess | None = result.scalar_one_or_none()

        now = utc_now()
        expires_at = to_utc(access.expires_at) if access is not None else None
        if access is None or not access.is_active or (expires_at is not None and expires_at <= now):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_CODE_DETAIL,
            )

        try:
            session_id = await edu_sessions.create_session(access.id, tenant.id)
        except EduSessionStoreUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Edu session store unavailable",
            ) from exc

        _set_session_cookie(request, response, session_id)
        return EduSessionResponse(role=access.role.value, expires_at=access.expires_at)


@router.get(
    "/edu/session",
    response_model=EduSessionResponse,
    summary="Get current edu session info",
)
async def get_edu_session(
    tenantSlug: str,
    ctx: EduSessionContext = Depends(require_edu_session),
) -> EduSessionResponse:
    """Return role + code expiry after full DB revalidation (401 otherwise)."""
    return EduSessionResponse(
        role=ctx.access.role.value,
        expires_at=ctx.access.expires_at,
    )


@router.delete(
    "/edu/session",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete edu session (logout)",
)
async def delete_edu_session(
    tenantSlug: str,
    response: Response,
    ctx: EduSessionContext = Depends(require_edu_session),
    edu_sessions: EduSessionService = Depends(get_edu_session_service),
) -> None:
    """Invalidate the server-side session and clear the cookie."""
    try:
        await edu_sessions.delete_session(ctx.session_id)
    except EduSessionStoreUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Edu session store unavailable",
        ) from exc
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
    )
    return None


@router.get(
    "/edu/content",
    response_model=FoundationContentListResponse,
    summary="List edu content (session required)",
)
async def list_edu_content(
    tenantSlug: str,
    content_type: str | None = Query(None, alias="type", description="Filter by content type"),
    target_age_group: str | None = Query(None, description="Filter by target age group"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    ctx: EduSessionContext = Depends(require_edu_session),
    session: AsyncSession = Depends(get_db),
) -> FoundationContentListResponse:
    """List edu-channel content: visibility=edu AND status=approved only.

    Same pagination pattern as the public content list; anonymity masking is
    applied by the shared serializers (BE-EP-038).
    """
    if content_type is not None:
        try:
            type_filter = ContentType(content_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Unknown content type",
            ) from None
    else:
        type_filter = None

    async with public_tenant_scope(tenantSlug, session) as tenant:
        stmt = (
            select(FoundationContent)
            .where(
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.visibility == Visibility.EDU,
                FoundationContent.status == ContentStatus.APPROVED,
            )
            .order_by(FoundationContent.created_at.desc())
        )
        if type_filter is not None:
            stmt = stmt.where(FoundationContent.type == type_filter)
        # BE-EP-055: een klas van een docent ziet alleen de opengezette lessen.
        toegestaan = await toegestane_les_ids(session, tenant.id, ctx.access.id)
        if toegestaan is not None:
            stmt = stmt.where(FoundationContent.id.in_(sorted(toegestaan) or [-1]))
        if target_age_group:
            stmt = stmt.where(FoundationContent.target_age_group == target_age_group)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(stmt)
        items = result.scalars().all()

        return FoundationContentListResponse(
            items=[FoundationContentListItem.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get(
    "/edu/content/{content_id}",
    response_model=FoundationContentDetail,
    summary="Get edu content detail (session required)",
)
async def get_edu_content(
    content_id: int,
    tenantSlug: str,
    ctx: EduSessionContext = Depends(require_edu_session),
    session: AsyncSession = Depends(get_db),
) -> FoundationContentDetail:
    """Edu content detail. Uniform 404 for non-edu / non-approved / other
    tenant / unknown IDs (no information leakage about what exists)."""
    async with public_tenant_scope(tenantSlug, session) as tenant:
        # BE-EP-055: een les die de docent niet heeft opengezet bestaat voor deze klas niet.
        toegestaan = await toegestane_les_ids(session, tenant.id, ctx.access.id)
        if toegestaan is not None and content_id not in toegestaan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_UNIFORM_404_DETAIL,
            )
        result = await session.execute(
            select(FoundationContent)
            .options(selectinload(FoundationContent.tags))
            .where(
                FoundationContent.id == content_id,
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.visibility == Visibility.EDU,
                FoundationContent.status == ContentStatus.APPROVED,
            )
        )
        content = result.scalar_one_or_none()

        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_UNIFORM_404_DETAIL,
            )

        return FoundationContentDetail.model_validate(content)


# ============================================================================
# Educational Access Code Management Endpoints (BE-EP-044)
# ============================================================================


@router.post(
    "/edu/codes",
    response_model=EduCodeCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate new educational access code (BE-EP-044)",
)
async def create_edu_code(
    tenantSlug: str,
    data: CreateEduCodeRequest,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
    _check_ip: None = Depends(require_portal_auth_rate_limit),
) -> EduCodeCreateResponse:
    """Generate a new 8-character educational access code for teachers/students.

    - Exact 8 uppercase alphanumeric characters from safe alphabet (no 0/O, 1/I/L)
    - Stored in DB strictly as sha256 hash (EducationalAccess.code_hash)
    - Raw plaintext code is returned ONLY once in this response
    - Links class_name as a StudyCollection
    - BE-SEC-057: curator/admin JWT required, scoped to the caller's own tenant
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )
        raw_code = ""
        code_hash = ""
        for _ in range(5):
            candidate = generate_edu_code(8)
            candidate_hash = hash_edu_code(candidate)
            existing = await session.execute(
                select(EducationalAccess.id).where(
                    EducationalAccess.tenant_id == tenant.id,
                    EducationalAccess.code_hash == candidate_hash,
                )
            )
            if existing.scalar_one_or_none() is None:
                raw_code = candidate
                code_hash = candidate_hash
                break

        if not raw_code:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate unique access code",
            )

        now = utc_now()
        expires_at = now + timedelta(hours=data.valid_hours)
        role = EducationalRole(data.role)

        access = EducationalAccess(
            tenant_id=tenant.id,
            code_hash=code_hash,
            email=str(data.teacher_email),
            role=role,
            is_active=True,
            expires_at=expires_at,
            created_at=now,
        )
        session.add(access)
        await session.flush()
        await session.refresh(access)

        # Create linked study collection with class_name
        collection = StudyCollection(
            tenant_id=tenant.id,
            educational_access_id=access.id,
            name=data.class_name,
            description=f"Lesmateriaal voor {data.class_name}",
            created_at=now,
        )
        session.add(collection)
        await session.commit()

        return EduCodeCreateResponse(
            id=access.id,
            code=raw_code,
            class_name=data.class_name,
            teacher_email=access.email,
            role=access.role.value,
            expires_at=access.expires_at,
            created_at=access.created_at,
            is_active=access.is_active,
        )


@router.get(
    "/edu/codes",
    response_model=EduCodeListResponse,
    summary="List educational access codes for tenant (BE-EP-044)",
)
async def list_edu_codes(
    tenantSlug: str,
    teacher_email: str | None = Query(None, description="Filter by teacher email"),
    active_only: bool = Query(True, description="Only show active, non-expired codes"),
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> EduCodeListResponse:
    """List educational access codes for a tenant.

    For security, plaintext codes and code hashes are NEVER returned.
    BE-SEC-057: curator/admin JWT required; the response contains PII
    (teacher emails, class names) and stays within the caller's own tenant.
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )
        stmt = (
            select(EducationalAccess)
            .options(selectinload(EducationalAccess.study_collections))
            .where(EducationalAccess.tenant_id == tenant.id)
            .order_by(EducationalAccess.created_at.desc())
        )
        if teacher_email:
            stmt = stmt.where(EducationalAccess.email == teacher_email.strip())
        if active_only:
            now = utc_now()
            stmt = stmt.where(
                EducationalAccess.is_active.is_(True),
                (EducationalAccess.expires_at.is_(None) | (EducationalAccess.expires_at > now)),
            )

        result = await session.execute(stmt)
        rows = result.scalars().all()

        items: list[EduCodeItem] = []
        for r in rows:
            class_name = r.study_collections[0].name if r.study_collections else "Algemeen"
            items.append(
                EduCodeItem(
                    id=r.id,
                    class_name=class_name,
                    teacher_email=r.email,
                    role=r.role.value,
                    expires_at=r.expires_at,
                    created_at=r.created_at,
                    is_active=r.is_active,
                )
            )

        return EduCodeListResponse(items=items, total=len(items))


@router.delete(
    "/edu/codes/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an educational access code (BE-EP-044)",
)
async def revoke_edu_code(
    tenantSlug: str,
    id: int,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Revoke an educational access code (sets is_active=False).

    BE-SEC-057: curator/admin JWT required, scoped to the caller's own tenant.
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )
        result = await session.execute(
            select(EducationalAccess).where(
                EducationalAccess.id == id,
                EducationalAccess.tenant_id == tenant.id,
            )
        )
        access = result.scalar_one_or_none()
        if access is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Educational code not found",
            )
        access.is_active = False
        await session.commit()
    return None
