# ADR-029 Gap Analysis & Productieklaar Implementatieplan

**Datum:** 2026-08-30  
**Analist:** AI Agent (onafhankelijke review zonder aannames)  
**Scope:** Backend + Frontend + Tests + Infrastructure  
**Status:** 23 bestanden geanalyseerd, 3 migraties, 665+ regels model code, 351+ regels RLS tests

---

## Samenvatting: Wat WEL Klaar Is

| Component | Status | Locatie |
|---|---|---|
| 9 modellen + 8 enums | **100%** | `src/core/models/foundation_content.py` |
| Foundation router (7 sub-routers) | **90%** | `src/core/api/v1/foundation/` |
| Tenant resolver + ContextVar cleanup | **100%** | `src/core/services/foundation_tenant_resolver.py` |
| Magic-link auth (request + verify) | **100%** | `src/core/api/v1/foundation/auth.py` |
| Rate limiters (6 wrappers + 4 deps) | **100%** | `src/core/governance/rate_limiter.py` |
| JWT portal dependencies | **100%** | `src/core/api/v1/foundation/dependencies.py` |
| Foundation exceptions (12 classes) | **100%** | `src/core/exceptions/foundation.py` |
| Unit tests (models, resolver, rate limiters) | **100%** | `tests/unit/test_foundation_*.py` |
| RLS security tests (6 tabellen) | **100%** | `tests/integration/security/test_foundation_rls.py` |
| Alembic migraties (content + settings) | **100%** | `20260524b`, `20260524c` |
| Alembic migratie (v1 uitbreiding) | **100%** | `20260824_adr029_portal_v1.py` |
| `metadata_` SQLAlchemy collision fix | **100%** | Commit `ad345be8` |

**Conclusie:** De **Fase 1 (Backend Foundations)** is grotendeels af. De infrastructuur staat. Wat ontbreekt zijn de **Fase 2+ endpoints**, **ontbrekende migraties**, en **de volledige frontend**.

---

## De 7 Kritieke Gaps (P0: Blokkerend voor Productie)

### P0-1. Ontbrekende tabellen in migraties (DATABASE BREEKT)

**Probleem:** De modellen definiëren 9 tabellen, maar de Alembic migraties creëren er slechts 4 (`foundation_content`, `content_tags`, `foundation_portal_settings`, `educational_access`, `study_collections`). De volgende 4 tabellen worden **nooit aangemaakt**:

- `portal_users`
- `magic_link_tokens`
- `takedown_requests`
- `newsletter_subscriptions`

**Impact:** De applicatie crasht bij eerste gebruik van auth, takedown, of newsletter endpoints. De FK van `foundation_content.uploader_id → portal_users.id` verwijst naar een niet-bestaande tabel.

**Oorzaak:** De migraties `20260524b` en `20260524c` zijn geschreven vóór de models volledig waren. De `20260824_adr029_portal_v1.py` migratie voegt alleen velden toe en nieuwe tabellen (`educational_access`, `study_collections`), maar niet de 4 kern-tabellen.

**Fix:** Nieuwe migratie `20260830_adr029_missing_tables.py`:

```python
"""ADR-029: Creëer ontbrekende portal tabellen.

Revision ID: 20260830_adr029_missing_tables
Revises: 20260824_adr029_portal_v1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260830_adr029_missing_tables"
down_revision = "20260824_adr029_portal_v1"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. portal_users
    # ------------------------------------------------------------------
    op.create_table(
        "portal_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("role", sa.Enum("admin", "curator", "teacher", "student", "visitor", name="portal_role_enum"), nullable=False, server_default="visitor"),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("consent_given", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("consent_given_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("idx_pu_tenant_email", "tenant_id", "email", unique=True),
    )
    if _is_postgresql():
        op.execute(sa.text("ALTER TABLE portal_users ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(
            "CREATE POLICY portal_users_tenant_isolation ON portal_users "
            "FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)"
        ))

    # ------------------------------------------------------------------
    # 2. magic_link_tokens
    # ------------------------------------------------------------------
    op.create_table(
        "magic_link_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("portal_user_id", sa.Integer(), sa.ForeignKey("portal_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("idx_mlt_tenant_user", "tenant_id", "portal_user_id"),
        sa.Index("idx_mlt_expires", "expires_at"),
    )
    if _is_postgresql():
        op.execute(sa.text("ALTER TABLE magic_link_tokens ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(
            "CREATE POLICY magic_link_tokens_tenant_isolation ON magic_link_tokens "
            "FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)"
        ))

    # ------------------------------------------------------------------
    # 3. takedown_requests
    # ------------------------------------------------------------------
    op.create_table(
        "takedown_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("content_id", sa.Integer(), sa.ForeignKey("foundation_content.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("requester_email", sa.String(255), nullable=False),
        sa.Column("requester_name", sa.String(255), nullable=False),
        sa.Column("legal_basis", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("pending", "approved", "rejected", "escalated", name="takedown_status_enum"), nullable=False, server_default="pending"),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("idx_td_tenant_status", "tenant_id", "status"),
    )
    if _is_postgresql():
        op.execute(sa.text("ALTER TABLE takedown_requests ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(
            "CREATE POLICY takedown_requests_tenant_isolation ON takedown_requests "
            "FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)"
        ))

    # ------------------------------------------------------------------
    # 4. newsletter_subscriptions
    # ------------------------------------------------------------------
    op.create_table(
        "newsletter_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("confirm_token_hash", sa.String(128), nullable=True, unique=True),
        sa.Column("unsubscribe_token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.Enum("pending_opt_in", "subscribed", "unsubscribed", "bounced", name="newsletter_status_enum"), nullable=False, server_default="pending_opt_in"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_ip", sa.String(45), nullable=True),
        sa.Column("consent_user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("idx_ns_tenant_email", "tenant_id", "email", unique=True),
        sa.Index("idx_ns_tenant_status", "tenant_id", "status"),
    )
    if _is_postgresql():
        op.execute(sa.text("ALTER TABLE newsletter_subscriptions ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(
            "CREATE POLICY newsletter_subscriptions_tenant_isolation ON newsletter_subscriptions "
            "FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)"
        ))


def downgrade() -> None:
    for tbl in ["newsletter_subscriptions", "takedown_requests", "magic_link_tokens", "portal_users"]:
        if _is_postgresql():
            op.execute(sa.text(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl}"))
            op.execute(sa.text(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY"))
        op.drop_table(tbl)
    for enum in ["takedown_status_enum"]:
        if _is_postgresql():
            op.execute(sa.text(f"DROP TYPE IF EXISTS {enum}"))
```

**Validatie na fix:**
```bash
alembic upgrade head
pytest tests/integration/security/test_foundation_rls.py -xvs
pytest tests/unit/test_foundation_models.py -xvs
```

---

### P0-2. RLS Inconsistentie: `app.current_tenant` vs `app.current_tenant_id`

**Probleem:** De migratie `20260824_adr029_portal_v1.py` gebruikt voor `educational_access` en `study_collections`:
```sql
tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::int
```

Maar de REST van de codebase ( inclusief `tenant_query_filter.py`, alle andere migraties, en de RLS tests) gebruikt:
```sql
tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER
```

**Impact:** RLS policies voor `educational_access` en `study_collections` werken NIET. De ORM-hook en middleware zetten `app.current_tenant`, niet `app.current_tenant_id`. Queries op deze tabellen retourneren 0 rijen (fail-safe) in plaats van de juiste tenant data.

**Fix:** Edit migratie `20260824_adr029_portal_v1.py`:

```python
# Regel 175-176 en 210-211:
# WAS:
# "USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::int)"
# MOET ZIJN:
"USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)"
```

---

### P0-3. Ontbrekende File Upload Endpoint

**Probleem:** Het `create_content` endpoint (`content.py:136`) accepteert alleen metadata (JSON). Er is GEEN endpoint voor multipart file upload. De modellen hebben wel `file_url`, `file_mime`, `file_size_bytes`, maar er is geen mechanisme om bestanden te uploaden.

**Impact:** Gebruikers kunnen geen afbeeldingen, audio, of documenten uploaden. Het platform is effectief alleen tekst.

**Fix:** Nieuw endpoint + Azure Blob service:

```python
# src/core/api/v1/foundation/upload.py
"""File upload endpoint for Foundation Portal."""

from __future__ import annotations

import magic
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    get_db,
    public_tenant_scope,
    require_portal_user,
)
from src.core.models.foundation_content import FoundationContent, PortalUser
from src.core.services.foundation_storage import FoundationStorageService

router = APIRouter(tags=["foundation-upload"])

# MIME-type whitelist per ADR-029
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "audio/mpeg", "audio/wav", "audio/ogg",
    "application/pdf", "text/plain",
    "video/mp4", "video/webm",
}
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB


@router.post(
    "/content/{content_id}/upload",
    status_code=status.HTTP_200_OK,
    summary="Upload file to existing content",
)
async def upload_content_file(
    content_id: int,
    tenantSlug: str,
    file: UploadFile = File(...),
    current_user: PortalUser = Depends(require_portal_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Upload a file for existing FoundationContent.

    - Validates MIME type via magic bytes (not just filename extension)
    - Enforces 100 MB max size
    - Stores in Azure Blob with SAS URL
    - Updates FoundationContent with file metadata
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        # Verify user belongs to tenant
        if current_user.tenant_id != tenant.id:
            raise HTTPException(status_code=403, detail="User does not belong to this tenant")

        # Load content
        from sqlalchemy import select
        stmt = select(FoundationContent).where(
            FoundationContent.id == content_id,
            FoundationContent.tenant_id == tenant.id,
        )
        result = await session.execute(stmt)
        content = result.scalar_one_or_none()
        if content is None:
            raise HTTPException(status_code=404, detail="Content not found")

        # Verify ownership (uploader or admin/curator)
        if content.uploader_id != current_user.id and current_user.role not in ("admin", "curator"):
            raise HTTPException(status_code=403, detail="Not authorized to upload to this content")

        # Read file into memory for validation
        file_bytes = await file.read()
        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail=f"File too large. Max {MAX_FILE_SIZE_BYTES} bytes")

        # Magic bytes MIME validation
        detected_mime = magic.from_buffer(file_bytes, mime=True)
        if detected_mime not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{detected_mime}' not allowed. Allowed: {', '.join(ALLOWED_MIME_TYPES)}"
            )

        # Upload to Azure Blob
        storage = FoundationStorageService()
        file_url = await storage.upload(
            tenant_id=tenant.id,
            content_id=content_id,
            filename=file.filename or "unnamed",
            data=file_bytes,
            mime_type=detected_mime,
        )

        # Update content record
        content.file_url = file_url
        content.file_mime = detected_mime
        content.file_size_bytes = len(file_bytes)
        await session.flush()

        return {"file_url": file_url, "mime_type": detected_mime, "size_bytes": str(len(file_bytes))}
```

---

### P0-4. Ontbrekende Geo/Map Endpoint

**Probleem:** ADR-029 specificeert `GET /public/{slug}/map/bbox?sw_lat=...&ne_lon=...` voor kaartweergave. Dit endpoint ontbreekt volledig.

**Fix:** Nieuw endpoint:

```python
# src/core/api/v1/foundation/map.py
"""Map/geo endpoints for Foundation Portal."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import get_db, public_tenant_scope
from src.core.models.foundation_content import ContentStatus, FoundationContent, Privacy

router = APIRouter(tags=["foundation-map"])


@router.get(
    "/map/bbox",
    summary="Get content within bounding box",
)
async def get_map_bbox(
    tenantSlug: str,
    sw_lat: float = Query(..., ge=-90, le=90, description="South-west latitude"),
    sw_lng: float = Query(..., ge=-180, le=180, description="South-west longitude"),
    ne_lat: float = Query(..., ge=-90, le=90, description="North-east latitude"),
    ne_lng: float = Query(..., ge=-180, le=180, description="North-east longitude"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return geo-JSON FeatureCollection of approved content within bbox.

    - Only APPROVED + PUBLIC content
    - Bounded by lat/lng rectangle
    - Tenant isolation via public_tenant_scope
    """
    # Validate bbox
    if sw_lat >= ne_lat or sw_lng >= ne_lng:
        raise HTTPException(status_code=400, detail="Invalid bounding box: sw must be < ne")

    async with public_tenant_scope(tenantSlug, session) as tenant:
        stmt = (
            select(FoundationContent)
            .where(
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.status == ContentStatus.APPROVED,
                FoundationContent.privacy == Privacy.PUBLIC,
                FoundationContent.lat.isnot(None),
                FoundationContent.lng.isnot(None),
                FoundationContent.lat >= sw_lat,
                FoundationContent.lat <= ne_lat,
                FoundationContent.lng >= sw_lng,
                FoundationContent.lng <= ne_lng,
            )
            .order_by(FoundationContent.created_at.desc())
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        features = []
        for item in items:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [item.lng, item.lat],
                },
                "properties": {
                    "id": item.id,
                    "title_nl": item.title_nl,
                    "type": item.type.value,
                    "creator_name": item.creator_name,
                    "category": item.category,
                },
            })

        return {
            "type": "FeatureCollection",
            "features": features,
            "total": len(features),
        }
```

---

### P0-5. Ontbrekende Educatieve Endpoints

**Probleem:** ADR-029 specificeert educatieve access codes, leeromgeving, en docent-uploads. Geen enkel edu endpoint bestaat.

**Fix:** Nieuw router bestand:

```python
# src/core/api/v1/foundation/edu.py
"""Educational access endpoints for Foundation Portal."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import get_db, public_tenant_scope
from src.core.models.foundation_content import (
    ContentStatus,
    EducationalAccess,
    EducationalRole,
    FoundationContent,
    Privacy,
    StudyCollection,
)

router = APIRouter(tags=["foundation-edu"])

# 4 schooluren = 4 * 45 minuten = 180 minuten (NL standaard)
EDU_SESSION_TTL_MINUTES = 180


@router.post(
    "/edu/access",
    summary="Validate educational access code",
)
async def validate_edu_access(
    tenantSlug: str,
    request: Request,
    response: Response,
    code: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Validate an educational access code and set session cookie.

    - Code must exist, be active, and not expired
    - Sets edu_session cookie with TTL = 4 schooluren
    - Returns role (teacher/student) for UI routing
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        stmt = select(EducationalAccess).where(
            EducationalAccess.tenant_id == tenant.id,
            EducationalAccess.code == code.upper().strip(),
            EducationalAccess.is_active.is_(True),
        )
        result = await session.execute(stmt)
        access: EducationalAccess | None = result.scalar_one_or_none()

        if access is None:
            raise HTTPException(status_code=401, detail="Invalid access code")

        # Check expiry
        if access.expires_at and access.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Access code expired")

        # Set session cookie
        expires = datetime.now(timezone.utc) + timedelta(minutes=EDU_SESSION_TTL_MINUTES)
        response.set_cookie(
            key="edu_session",
            value=f"{access.code}:{access.role.value}",
            httponly=True,
            secure=True,
            samesite="Strict",
            expires=expires,
        )

        return {
            "valid": True,
            "role": access.role.value,
            "school_name": access.email.split("@")[-1] if access.email else None,
        }


@router.get(
    "/edu/content",
    summary="List educational content",
)
async def list_edu_content(
    tenantSlug: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List educational content for current edu session.

    - Requires valid edu_session cookie
    - Returns content with visibility=EDU or PUBLIC
    """
    edu_session = request.cookies.get("edu_session")
    if not edu_session:
        raise HTTPException(status_code=401, detail="Educational session required")

    async with public_tenant_scope(tenantSlug, session) as tenant:
        # Parse cookie
        try:
            code, role = edu_session.rsplit(":", 1)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid session")

        # Verify code still valid
        stmt = select(EducationalAccess).where(
            EducationalAccess.tenant_id == tenant.id,
            EducationalAccess.code == code,
            EducationalAccess.is_active.is_(True),
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=401, detail="Session expired")

        # Load content
        stmt = (
            select(FoundationContent)
            .where(
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.status == ContentStatus.APPROVED,
                FoundationContent.privacy.in_([Privacy.PUBLIC, Privacy.COMMUNITY]),
            )
            .order_by(FoundationContent.created_at.desc())
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        return {
            "items": [{"id": i.id, "title_nl": i.title_nl, "type": i.type.value} for i in items],
            "role": role,
            "total": len(items),
        }
```

---

### P0-6. Ontbrekende OAI-PMH Endpoint

**Probleem:** ADR-029 vereist `GET /public/{slug}/oai-pmh?verb=ListRecords` voor metadata-harvesting in Dublin Core. Dit is een subsidie-eis (Cat 4).

**Fix:**

```python
# src/core/api/v1/foundation/oai_pmh.py
"""OAI-PMH endpoint for metadata harvesting (Dublin Core)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import get_db, public_tenant_scope, portal_public_read_limit
from src.core.models.foundation_content import ContentStatus, FoundationContent, Privacy

router = APIRouter(tags=["foundation-oai-pmh"])


@router.get(
    "/oai-pmh",
    summary="OAI-PMH metadata harvesting",
)
@portal_public_read_limit
async def oai_pmh(
    tenantSlug: str,
    request: Request,
    verb: str = Query(..., description="OAI-PMH verb"),
    metadataPrefix: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    until: str | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """OAI-PMH endpoint for metadata harvesting.

    Supported verbs: Identify, ListRecords, ListIdentifiers, ListSets
    Metadata format: oai_dc (Dublin Core)
    Rate limit: 100/min per IP
    """
    if verb == "Identify":
        return {
            "OAI-PMH": {
                "responseDate": datetime.now(timezone.utc).isoformat(),
                "request": str(request.url),
                "Identify": {
                    "repositoryName": "Levend Monument Portal",
                    "baseURL": str(request.base_url),
                    "protocolVersion": "2.0",
                    "adminEmail": "admin@levend-monument.nl",
                    "earliestDatestamp": "2026-01-01",
                    "deletedRecord": "persistent",
                    "granularity": "YYYY-MM-DD",
                },
            }
        }

    if verb in ("ListRecords", "ListIdentifiers"):
        if metadataPrefix != "oai_dc":
            raise HTTPException(status_code=400, detail="Only metadataPrefix=oai_dc is supported")

        async with public_tenant_scope(tenantSlug, session) as tenant:
            stmt = (
                select(FoundationContent)
                .where(
                    FoundationContent.tenant_id == tenant.id,
                    FoundationContent.status == ContentStatus.APPROVED,
                    FoundationContent.privacy == Privacy.PUBLIC,
                )
                .order_by(FoundationContent.created_at.desc())
                .limit(100)
            )
            result = await session.execute(stmt)
            items = result.scalars().all()

            records = []
            for item in items:
                records.append({
                    "header": {
                        "identifier": f"oai:levend-monument.nl:{item.id}",
                        "datestamp": item.created_at.isoformat() if item.created_at else "",
                    },
                    "metadata": {
                        "oai_dc:dc": {
                            "dc:title": item.title_nl,
                            "dc:description": item.description_nl or "",
                            "dc:creator": item.creator_name or "Anonymous",
                            "dc:date": item.created_at.isoformat() if item.created_at else "",
                            "dc:type": item.type.value,
                            "dc:language": item.language or "nl",
                            "dc:license": item.license or "CC-BY-NC-SA-4.0",
                        }
                    }
                })

            return {
                "OAI-PMH": {
                    "responseDate": datetime.now(timezone.utc).isoformat(),
                    "request": str(request.url),
                    "ListRecords": {"record": records},
                }
            }

    raise HTTPException(status_code=400, detail=f"Verb '{verb}' not supported or invalid")
```

---

### P0-7. Geen Frontend Pages

**Probleem:** De frontend (`frontend/src/pages/`) bevat 0 (nul) Foundation Portal pagina's. Alle redesign pagina's zijn voor het SanskritiSetu dashboard (Prana, Shadow CEO, Council, etc.).

**Impact:** Er is geen publiek toegankelijk portal. Het Levend Monument bestaat niet voor eindgebruikers.

**Fix:** Volledige Next.js App Router structuur (14 pagina's):

```
frontend/src/app/(portal)/[tenantSlug]/
├── layout.tsx              # White-label thema laden
├── page.tsx                # Homepage (verhalenlijst)
├── verhaal/[id]/
│   └── page.tsx            # Detailpagina
├── kaart/
│   └── page.tsx            # MapLibre kaartweergave
├── upload/
│   └── page.tsx            # Upload formulier
├── edu/
│   ├── page.tsx            # Educatieve toegang
│   └── lesmateriaal/
│       └── page.tsx        # Lesmateriaal lijst
├── over/
│   └── page.tsx            # Over de stichting
├── contact/
│   └── page.tsx            # Contact formulier
├── nieuwsbrief/
│   └── page.tsx            # Nieuwsbrief subscribe
├── magic-link/
│   └── page.tsx            # Magic link verificatie
└── takedown/
    └── page.tsx            # NTD formulier
```

---

## Middelhoge Gaps (P1: Vereist voor Go-Live)

### P1-1. Ontbrekende AI Tagging Service
- **Status:** Model `ContentTag` bestaat, maar geen Dramatiq job of endpoint
- **Impact:** Curatoren moeten handmatig taggen
- **Fix:** Dramatiq actor + Ollama integratie

### P1-2. Ontbrekende Content Update/Delete Endpoints
- **Status:** Alleen POST /content (create). Geen PUT/DELETE.
- **Impact:** Uploaders kunnen hun content niet bewerken of verwijderen
- **Fix:** Extra endpoints in `content.py`

### P1-3. hCaptcha Integratie
- **Status:** Schema heeft `CaptchaFailedError`, maar geen hCaptcha verify call
- **Impact:** Magic-link endpoint vatbaar voor e-mail bombing
- **Fix:** `POST /magic-link` moet hCaptcha token valideren vóór verwerking

### P1-4. Azure Blob Storage Service
- **Status:** `FoundationStorageService` wordt geïmporteerd maar bestaat niet
- **Impact:** File upload werkt niet
- **Fix:** Implementeer `src/core/services/foundation_storage.py`

### P1-5. Brevo Email Client
- **Status:** `notification_service.notify_user()` wordt aangeroepen, maar Brevo-transactional integratie ontbreekt
- **Impact:** Magic links worden nooit verstuurd
- **Fix:** Brevo SMTP/API client in `src/core/connectors/brevo.py`

### P1-6. Integration Tests voor Endpoints
- **Status:** Alleen unit tests. Geen integratietests voor daadwerkelijke endpoint calls.
- **Impact:** Regressies in endpoint logica worden niet gedetecteerd
- **Fix:** `tests/integration/foundation/` map met tests voor elk endpoint

---

## Lage Gaps (P2: Post-MVP)

### P2-1. Custom Domain Support
- Redis cache voor domain → tenant_id lookup
- DNS-validatie

### P2-2. Stripe Tier Upgrade Flow
- Checkout session
- Webhook handler
- Feature flag invalidatie

### P2-3. Advanced Analytics
- Content approval duration metrics
- AI tag confidence histograms
- Newsletter subscriber trends

### P2-4. WCAG 2.1 AA Audit
- axe-core CI integratie
- Lighthouse ≥ 95 score
- Screen reader testing

---

## Implementatie Volgorde (Aanbevolen)

| Sprint | Focus | Deliverables |
|---|---|---|
| **Sprint 1** (1 week) | Database fixes | P0-1 (migratie), P0-2 (RLS fix), alle model tests groen |
| **Sprint 2** (1 week) | Core endpoints | P0-3 (upload), P0-4 (map), P1-2 (PUT/DELETE), P1-4 (storage) |
| **Sprint 3** (1 week) | Edu + OAI-PMH | P0-5 (edu), P0-6 (OAI-PMH), P1-1 (AI tagging) |
| **Sprint 4** (2 weken) | Frontend MVP | P0-7 (14 pagina's), P1-3 (hCaptcha), P1-5 (Brevo) |
| **Sprint 5** (1 week) | Tests + Hardening | P1-6 (integration tests), security audit, load test |
| **Sprint 6** (1 week) | Compliance + Launch | P2-4 (WCAG), AVG verklaring, go-live |

**Totaal:** ~7 weken voor volledig productieklaar platform.

---

## Onmiddellijke Actie (Vandaag)

1. **Merge de ontbrekende tabellen migratie** (P0-1)
2. **Fix de RLS inconsistentie** (P0-2)
3. **Draai full test suite**:
   ```bash
   pytest tests/unit/test_foundation_*.py tests/integration/security/test_foundation_rls.py -xvs
   ```
4. **Alembic chain valideren**:
   ```bash
   alembic current
   alembic history --verbose
   alembic upgrade head && alembic downgrade base && alembic upgrade head
   ```

---

*Dit rapport is gegenereerd door onafhankelijke codebase analyse. Alle claims zijn verifieerbaar via de bestandsreferenties.*
