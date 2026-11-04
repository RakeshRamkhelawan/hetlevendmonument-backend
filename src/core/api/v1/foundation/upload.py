"""Foundation Portal file upload endpoint (BE-EP-036, ADR-029 gap P0-3).

POST /{tenantSlug}/foundation/content/{content_id}/upload
Uploads a file onto EXISTING FoundationContent. See
docs/backend/features/BE-EP-036-upload-endpoint-storage.md for the
12-step API flow and design decisions O1..O10.
"""

from __future__ import annotations

import asyncio
import email.utils
import hashlib
import logging
from pathlib import Path

import aiofiles
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    _MIME_TO_EXT,
    SESSION_COOKIE_NAME,
    AuditService,
    BestandOnleesbaarError,
    EduSessionService,
    FoundationStorageNotConfiguredError,
    FoundationStorageService,
    detect_allowed_mime,
    get_db,
    get_edu_session_service,
    get_foundation_storage,
    get_optional_portal_user,
)
from src.core.api.v1.foundation.dependencies import portal_public_read_limit
from src.core.api.v1.foundation.dependencies import (
    portal_public_read_limit as portal_media_read_limit,
)
from src.core.api.v1.foundation.dependencies import (
    portal_public_write_limit,
    public_tenant_scope,
    require_portal_user,
    secure_filename,
    verwijder_metadata,
)
from src.core.api.v1.foundation.schemas import (
    FoundationFileUploadResponse,
    FoundationMediaResponse,
)
from src.core.models.foundation_content import (
    MAX_BESTANDEN_PER_VERHAAL,
    ContentStatus,
    EducationalAccess,
    FoundationContent,
    FoundationContentBestand,
    PortalRole,
    PortalUser,
    Privacy,
    Visibility,
)
from src.core.models.rbac_models import Tenant
from src.core.shared.datetime_utils import to_utc, utc_now
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

router = APIRouter(tags=["foundation-upload"])

# 1 MiB chunks with a running counter: no whole-file read into RAM before the
# size check (O3, memory-DoS guard from the audit).
_CHUNK_SIZE = 1024 * 1024


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload in chunks and abort with 413 as soon as cap+1 is seen."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="File too large",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/content/{content_id}/upload",
    response_model=FoundationFileUploadResponse,
    summary="Upload a file for existing content",
)
@portal_public_write_limit
async def upload_content_file(
    content_id: int,
    tenantSlug: str,
    request: Request,
    file: UploadFile = File(...),
    extra: bool = Query(
        False,
        description=(
            "BE-EP-057: true = voeg dit bestand toe als extra bestand bij het verhaal "
            "(alleen als er al een hoofdbestand is). false = hoofdbestand (zoals altijd)."
        ),
    ),
    current_user: PortalUser = Depends(require_portal_user),
    session: AsyncSession = Depends(get_db),
    storage: FoundationStorageService = Depends(get_foundation_storage),
) -> FoundationFileUploadResponse:
    """Attach a file to existing content.

    - Rate limit: 10/min per IP (portal_public_write_limit)
    - Auth: portal JWT (aud=portal, scope=portal_uploader)
    - Authorization: uploader of the content, or role ADMIN/CURATOR (O8)
    - MIME validated on magic bytes via puremagic (O1); text/plain only via
      the documented .txt + declared-type + UTF-8 fallback
    - Cap: settings.max_upload_size_bytes, 50 MB (O2)
    - BE-EP-057, ``extra=true``: maximaal MAX_BESTANDEN_PER_VERHAAL bestanden per verhaal
      (409 daarboven). Een inzender (geen curator) kan alleen extra bestanden toevoegen
      zolang het verhaal nog niet is beoordeeld (status pending, anders 409): zo komt er
      niets ongezien bij een goedgekeurd verhaal.
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        # Cross-tenant: user tenant must match the resolved tenant (O8)
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        # Content must exist within this tenant (explicit tenant_id WHERE)
        stmt = select(FoundationContent).where(
            FoundationContent.id == content_id,
            FoundationContent.tenant_id == tenant.id,
        )
        result = await session.execute(stmt)
        content: FoundationContent | None = result.scalar_one_or_none()

        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Content not found",
            )

        # Authorization: uploader of the content, or curator/admin.
        # Gate-2 review MEDIUM (2026-09-09): a non-owner without curator/admin
        # role gets the SAME 404 as non-existent content -- otherwise the 403
        # vs 404 difference would leak which content IDs exist (existence
        # oracle; IDs are sequential).
        if content.uploader_id != current_user.id and current_user.role not in (
            PortalRole.ADMIN,
            PortalRole.CURATOR,
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Content not found",
            )

        # BE-EP-057: extra bestand? Alleen als er al een hoofdbestand is; anders wordt dit
        # het hoofdbestand. Grenzen controleren VOOR het inlezen van het bestand.
        als_extra = extra and content.file_url is not None
        volgende = 0
        if als_extra:
            is_curator = current_user.role in (PortalRole.ADMIN, PortalRole.CURATOR)
            if not is_curator and content.status != ContentStatus.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Content already reviewed",
                )
            aantal, hoogste = (
                await session.execute(
                    select(
                        func.count(FoundationContentBestand.id),
                        func.max(FoundationContentBestand.volgorde),
                    ).where(
                        FoundationContentBestand.content_id == content.id,
                        FoundationContentBestand.tenant_id == tenant.id,
                    )
                )
            ).one()
            if 1 + int(aantal or 0) >= MAX_BESTANDEN_PER_VERHAAL:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Maximum number of files reached",
                )
            volgende = max(int(hoogste or 1), 1) + 1

        # Chunked read with running counter; abort at cap+1 (O3)
        data = await _read_capped(file, storage.max_upload_size_bytes)

        # MIME detection on magic bytes; allowlist from ADR-029 (O1)
        mime_type = detect_allowed_mime(
            data,
            filename=file.filename,
            declared_content_type=file.content_type,
        )
        if mime_type is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File type not allowed",
            )

        # BE-EP-056: locatie en andere metadata uit foto's, video's en opnames halen voordat
        # ze worden opgeslagen. In een thread: dit is rekenwerk.
        try:
            data = await asyncio.to_thread(verwijder_metadata, data, mime_type)
        except BestandOnleesbaarError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File could not be processed",
            ) from exc

        sha256 = hashlib.sha256(data).hexdigest()

        try:
            file_url = await storage.upload(
                tenant_id=tenant.id,
                content_id=content.id,
                filename=file.filename,
                data=data,
                mime_type=mime_type,
            )
        except FoundationStorageNotConfiguredError as exc:
            logger.error("foundation upload: storage backend not configured", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage backend not configured",
            ) from exc
        except Exception as exc:
            logger.error("foundation upload: storage write failed", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="File storage failed",
            ) from exc

        bestand_id: int | None = None
        if als_extra:
            bestand = FoundationContentBestand(
                tenant_id=tenant.id,
                content_id=content.id,
                volgorde=volgende,
                file_url=file_url,
                file_mime=mime_type,
                file_size_bytes=len(data),
                sha256=sha256,
            )
            try:
                async with session.begin_nested():
                    session.add(bestand)
                    await session.flush()
            except IntegrityError as exc:
                # Twee uploads tegelijk kregen dezelfde volgorde; de tweede mag het opnieuw proberen.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Concurrent upload, please retry",
                ) from exc
            bestand_id = bestand.id
        else:
            content.file_url = file_url
            content.file_mime = mime_type
            content.file_size_bytes = len(data)
            session.add(content)
            await session.flush()
        content_pk = content.id
        # Patroon #3 (Gate-2 review MEDIUM, 2026-09-09): commit de primaire
        # wijziging EXPLICIET voor de audit, zoals documents/upload_router.py.
        # Daarmee is bewezen dat een audit-failure de content-update niet meer
        # kan terugrollen: best_effort roept bij een failure hooguit
        # session.rollback() aan op de nieuwe, lege transactie die na deze
        # commit begint -- de al gecommitte update valt daar buiten. De
        # afsluitende commit in get_db is daarna een no-op.
        await session.commit()

        # Audit after the commit, best-effort so it never blocks the
        # upload (O9/O10). Metadata: sha256/mime/size/content_id only --
        # never file contents or PII.
        async with best_effort("foundation content file upload audit", db_session=session):
            await AuditService.log_event(
                db=session,
                event_type="foundation_content_file_upload",
                severity="low",
                source_ip=request.client.host if request.client else "unknown",
                endpoint=f"/{tenantSlug}/foundation/content/{content_id}/upload",
                description=f"File uploaded for content #{content_pk}",
                user_id=current_user.id,
                tenant_id=tenant.id,
                action="foundation.content.file_upload",
                resource=f"content:{content_pk}",
                metadata={
                    "content_id": content_pk,
                    "bestand_id": bestand_id,
                    "sha256": sha256,
                    "mime": mime_type,
                    "size_bytes": len(data),
                },
            )

        return FoundationFileUploadResponse(
            file_url=file_url,
            file_mime=mime_type,
            file_size_bytes=len(data),
            sha256=sha256,
            bestand_id=bestand_id,
        )


async def stream_local_file(
    path: Path,
    request: Request,
    *,
    mime_type: str = "application/octet-stream",
    download: bool = False,
    filename: str | None = None,
) -> Response:
    """Stream a local media file with full RFC 9110 HTTP Range (206 Partial Content) support.

    Enforces:
    - Status 206 with Content-Range for Range requests (audio/video scrubbing)
    - Status 200 with Content-Length for non-range requests
    - Status 416 with Content-Range: bytes */size if range is unsatisfiable
    - Header X-Content-Type-Options: nosniff
    - Header Content-Disposition: inline or attachment with sanitized filename
    - Chunked async reading via aiofiles
    """
    stat_res = path.stat()
    file_size = stat_res.st_size
    mtime = stat_res.st_mtime
    last_modified = email.utils.formatdate(mtime, usegmt=True)
    etag = f'"{int(mtime):x}-{file_size:x}"'

    safe_name = secure_filename(filename or path.name)
    disposition_type = "attachment" if download else "inline"

    base_headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'{disposition_type}; filename="{safe_name}"',
        "ETag": etag,
        "Last-Modified": last_modified,
    }

    range_header = request.headers.get("range")
    if_range = request.headers.get("if-range")

    # RFC 9110 Section 14.4 If-Range check:
    # If the validator doesn't match, the range request is ignored and full 200 OK is returned
    if_range_matches = True
    if if_range:
        clean_if_range = if_range.strip()
        if clean_if_range != etag and clean_if_range != last_modified:
            if_range_matches = False

    if (
        not range_header
        or not range_header.strip().lower().startswith("bytes=")
        or not if_range_matches
    ):
        # Non-range request (or mismatching If-Range): stream full file with 200 OK
        headers = {**base_headers, "Content-Length": str(file_size)}

        async def _full_file_iterator(chunk_size: int = 65536):
            async with aiofiles.open(path, mode="rb") as f:
                while chunk := await f.read(chunk_size):
                    yield chunk

        return StreamingResponse(
            _full_file_iterator(),
            status_code=status.HTTP_200_OK,
            headers=headers,
            media_type=mime_type,
        )

    # Range request handling (RFC 9110)
    range_val = range_header.strip()[6:].strip()
    if "," in range_val:
        # Multi-range: take first range for single byterange response
        range_val = range_val.split(",")[0].strip()

    if "-" not in range_val:
        # Malformed: treat as non-range
        headers = {**base_headers, "Content-Length": str(file_size)}

        async def _full_file_iterator(chunk_size: int = 65536):
            async with aiofiles.open(path, mode="rb") as f:
                while chunk := await f.read(chunk_size):
                    yield chunk

        return StreamingResponse(
            _full_file_iterator(),
            status_code=status.HTTP_200_OK,
            headers=headers,
            media_type=mime_type,
        )

    raw_start, raw_end = range_val.split("-", 1)
    raw_start = raw_start.strip()
    raw_end = raw_end.strip()

    try:
        if raw_start and raw_end:
            start = int(raw_start)
            end = int(raw_end)
        elif raw_start:
            start = int(raw_start)
            end = file_size - 1
        elif raw_end:
            suffix_len = int(raw_end)
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        else:
            start = 0
            end = file_size - 1
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            headers={**base_headers, "Content-Range": f"bytes */{file_size}"},
            detail="Range Not Satisfiable",
        )

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            headers={**base_headers, "Content-Range": "bytes */0"},
            detail="Range Not Satisfiable",
        )

    if start >= file_size or start < 0 or start > end:
        raise HTTPException(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            headers={**base_headers, "Content-Range": f"bytes */{file_size}"},
            detail="Range Not Satisfiable",
        )

    end = min(end, file_size - 1)
    content_length = end - start + 1

    headers = {
        **base_headers,
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(content_length),
    }

    async def _ranged_file_iterator(start_pos: int, bytes_to_read: int, chunk_size: int = 65536):
        async with aiofiles.open(path, mode="rb") as f:
            await f.seek(start_pos)
            remaining = bytes_to_read
            while remaining > 0:
                chunk = await f.read(min(chunk_size, remaining))
                if not chunk:
                    break
                yield chunk
                remaining -= len(chunk)

    return StreamingResponse(
        _ranged_file_iterator(start, content_length),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        headers=headers,
        media_type=mime_type,
    )


async def verify_content_media_access(
    content: FoundationContent,
    tenant: Tenant,
    current_user: PortalUser | None,
    request: Request,
    session: AsyncSession,
    edu_sessions: EduSessionService,
) -> None:
    """Enforce privacy, visibility and moderation authorization for media access."""
    # 1. Moderation status checks
    if content.status == ContentStatus.REMOVED:
        if (
            current_user is None
            or current_user.tenant_id != tenant.id
            or current_user.role
            not in (
                PortalRole.ADMIN,
                PortalRole.CURATOR,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media not found for this content",
            )
        return

    if content.status in (ContentStatus.PENDING, ContentStatus.REJECTED):
        is_owner = current_user is not None and current_user.id == content.uploader_id
        is_curator = (
            current_user is not None
            and current_user.tenant_id == tenant.id
            and current_user.role
            in (
                PortalRole.ADMIN,
                PortalRole.CURATOR,
            )
        )
        if not is_owner and not is_curator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media not found for this content",
            )
        return

    # 2. Curators and admins bypass public/community/edu visibility checks
    is_curator = (
        current_user is not None
        and current_user.tenant_id == tenant.id
        and current_user.role in (PortalRole.ADMIN, PortalRole.CURATOR)
    )
    if is_curator:
        return

    # 3. Community content requires authenticated portal user of same tenant
    if content.visibility == Visibility.COMMUNITY or content.privacy == Privacy.COMMUNITY:
        if current_user is None or current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authentication required for community media",
            )
        return

    # 4. Educational content requires active valid edu_session
    if content.visibility == Visibility.EDU:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Educational session required for educational media",
            )
        try:
            data = await edu_sessions.get_session(session_id)
        except Exception:
            data = None

        if data is None or data.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Educational session required for educational media",
            )

        result = await session.execute(
            select(EducationalAccess).where(
                EducationalAccess.id == data.access_id,
                EducationalAccess.tenant_id == data.tenant_id,
            )
        )
        access = result.scalar_one_or_none()
        now = utc_now()
        expires_at = to_utc(access.expires_at) if access is not None else None
        if access is None or not access.is_active or (expires_at is not None and expires_at <= now):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Educational session required for educational media",
            )
        return


@router.get(
    "/content/{content_id}/media",
    response_model=FoundationMediaResponse,
    summary="Get secure media URL, SAS token, or stream media directly",
)
@portal_media_read_limit
async def get_content_media(
    content_id: int,
    tenantSlug: str,
    request: Request,
    redirect: bool = Query(False, description="Redirect directly to media URL"),
    download: bool = Query(False, description="Set Content-Disposition to attachment for download"),
    stream: bool = Query(False, description="Stream local media content directly (HTTP 206)"),
    current_user: PortalUser | None = Depends(get_optional_portal_user),
    session: AsyncSession = Depends(get_db),
    storage: FoundationStorageService = Depends(get_foundation_storage),
    edu_sessions: EduSessionService = Depends(get_edu_session_service),
) -> Response | FoundationMediaResponse:
    """Return a time-limited signed URL (User-Delegation SAS) or stream media directly (ADR-029 P1-4, BE-EP-052).

    - Content must exist and media must be attached
    - Moderation checks: PENDING/REJECTED only visible to uploader and curators; REMOVED only to curators
    - Privacy checks: COMMUNITY requires authenticated portal user; EDU requires valid edu_session cookie
    - If redirect=True: sends 307 Temporary Redirect to media URL
    - If stream=True: streams local file with HTTP 206 Partial Content (Range requests)
    - download=True adds Content-Disposition: attachment
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        stmt = select(FoundationContent).where(
            FoundationContent.id == content_id,
            FoundationContent.tenant_id == tenant.id,
        )
        content: FoundationContent | None = (await session.execute(stmt)).scalar_one_or_none()
        if content is None or not content.file_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media not found for this content",
            )

        await verify_content_media_access(
            content=content,
            tenant=tenant,
            current_user=current_user,
            request=request,
            session=session,
            edu_sessions=edu_sessions,
        )

        return await _lever_media(
            storage=storage,
            request=request,
            file_url=content.file_url,
            mime_type=content.file_mime,
            file_size_bytes=content.file_size_bytes,
            naam=content.title_nl or f"content_{content.id}",
            redirect=redirect,
            download=download,
            stream=stream,
        )


async def _lever_media(
    *,
    storage: FoundationStorageService,
    request: Request,
    file_url: str,
    mime_type: str | None,
    file_size_bytes: int | None,
    naam: str,
    redirect: bool,
    download: bool,
    stream: bool,
) -> Response | FoundationMediaResponse:
    """Lever een bestand af: streamen, doorsturen of een tijdelijke URL (BE-EP-052, BE-EP-057).

    Gedeeld door het hoofdbestand en de extra bestanden van een verhaal. Roep dit pas aan
    NA ``verify_content_media_access``.
    """
    ext = _MIME_TO_EXT.get(mime_type or "", "")
    filename = f"{secure_filename(naam)}{ext}"

    # Externe opslag (Azure): de blobopslag ondersteunt zelf Range-verzoeken, dus een
    # ``stream``-verzoek gaat naar een tijdelijke URL. Zonder dit gaf ``stream`` op
    # productie altijd 404 en speelde een goedgekeurde video of opname niet af.
    if stream and file_url.startswith(("http://", "https://")):
        stream = False
        redirect = True

    if stream:
        local_path = storage.get_local_file_path(file_url)
        if local_path is None or not local_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Local media file not found on disk",
            )
        return await stream_local_file(
            local_path,
            request,
            mime_type=mime_type or "application/octet-stream",
            download=download,
            filename=filename,
        )

    read_url = await storage.generate_read_url(
        file_url,
        expiry_minutes=30,
        download=download,
        filename=filename,
        mime_type=mime_type,
    )

    if redirect:
        return RedirectResponse(url=read_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    return FoundationMediaResponse(
        url=read_url,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        expires_in_seconds=1800,
    )


@router.get(
    "/content/{content_id}/bestanden/{bestand_id}/media",
    response_model=FoundationMediaResponse,
    summary="Get an extra file of a story (BE-EP-057)",
)
@portal_media_read_limit
async def get_content_bestand_media(
    content_id: int,
    bestand_id: int,
    tenantSlug: str,
    request: Request,
    redirect: bool = Query(False, description="Redirect directly to media URL"),
    download: bool = Query(False, description="Set Content-Disposition to attachment for download"),
    stream: bool = Query(False, description="Stream local media content directly (HTTP 206)"),
    current_user: PortalUser | None = Depends(get_optional_portal_user),
    session: AsyncSession = Depends(get_db),
    storage: FoundationStorageService = Depends(get_foundation_storage),
    edu_sessions: EduSessionService = Depends(get_edu_session_service),
) -> Response | FoundationMediaResponse:
    """Een extra bestand van een verhaal, met EXACT dezelfde toegangsregels als het hoofdbestand.

    Het bestand moet bij dit verhaal EN deze tenant horen; anders 404 (geen verschil tussen
    'bestaat niet' en 'hoort ergens anders bij').
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        content: FoundationContent | None = (
            await session.execute(
                select(FoundationContent).where(
                    FoundationContent.id == content_id,
                    FoundationContent.tenant_id == tenant.id,
                )
            )
        ).scalar_one_or_none()
        bestand: FoundationContentBestand | None = None
        if content is not None:
            bestand = (
                await session.execute(
                    select(FoundationContentBestand).where(
                        FoundationContentBestand.id == bestand_id,
                        FoundationContentBestand.content_id == content.id,
                        FoundationContentBestand.tenant_id == tenant.id,
                    )
                )
            ).scalar_one_or_none()
        if content is None or bestand is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media not found for this content",
            )

        await verify_content_media_access(
            content=content,
            tenant=tenant,
            current_user=current_user,
            request=request,
            session=session,
            edu_sessions=edu_sessions,
        )

        return await _lever_media(
            storage=storage,
            request=request,
            file_url=bestand.file_url,
            mime_type=bestand.file_mime,
            file_size_bytes=bestand.file_size_bytes,
            naam=f"{content.title_nl or f'content_{content.id}'}_{bestand.volgorde}",
            redirect=redirect,
            download=download,
            stream=stream,
        )


@router.get(
    "/content/{content_id}/media/stream",
    summary="Stream local media content directly with HTTP 206 Range support (BE-EP-052)",
)
@portal_media_read_limit
async def stream_content_media(
    content_id: int,
    tenantSlug: str,
    request: Request,
    download: bool = Query(False, description="Set Content-Disposition to attachment for download"),
    current_user: PortalUser | None = Depends(get_optional_portal_user),
    session: AsyncSession = Depends(get_db),
    storage: FoundationStorageService = Depends(get_foundation_storage),
    edu_sessions: EduSessionService = Depends(get_edu_session_service),
) -> Response:
    """Stream media content directly with partial content (Range requests) support."""
    return await get_content_media(
        content_id=content_id,
        tenantSlug=tenantSlug,
        request=request,
        redirect=False,
        download=download,
        stream=True,
        current_user=current_user,
        session=session,
        storage=storage,
        edu_sessions=edu_sessions,
    )
