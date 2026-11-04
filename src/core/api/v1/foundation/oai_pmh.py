"""Foundation Portal OAI-PMH metadata harvesting endpoint (BE-EP-040, ADR-029).

Implements Open Archives Initiative Protocol for Metadata Harvesting (OAI-PMH) v2.0:
- URL: /{tenantSlug}/foundation/oai-pmh
- Both HTTP GET and POST methods supported (Section 3.1.1)
- Content-Type: text/xml; charset=utf-8 (never JSON)
- Verbs: Identify, ListMetadataFormats, ListSets, GetRecord, ListIdentifiers, ListRecords
- Strict parameter validation (exclusivity of resumptionToken, granularity matching)
- Keyset-based flow control with signed resumptionToken
- N-2 invariant: only PUBLIC visibility and APPROVED/REMOVED statuses are exposed
- Removed content emitted as <header status="deleted">
- Anonymity masking on dc:creator (BE-EP-038)
- Protocol errors return HTTP 200 OK with XML <error code="...">
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    PAGE_SIZE,
    OaiPmhError,
    OaiPmhErrorCode,
    OaiPmhService,
    OaiRecord,
    OaiResumptionToken,
    get_db,
    public_tenant_scope,
    validate_oai_parameters,
)
from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    FoundationContent,
    Visibility,
)
from src.core.shared.datetime_utils import to_utc, utc_now

router = APIRouter(tags=["foundation-oai-pmh"])


def _extract_content_id(identifier: str, tenant_slug: str) -> int | None:
    """Extract integer content ID from oai:{tenantSlug}:{id} or raw {id}."""
    prefix = f"oai:{tenant_slug}:"
    if identifier.startswith(prefix):
        raw_id = identifier[len(prefix) :]
    elif identifier.isdigit():
        raw_id = identifier
    else:
        return None

    if raw_id.isdigit():
        return int(raw_id)
    return None


def _to_oai_record(item: FoundationContent, slug: str) -> OaiRecord:
    created_dt = to_utc(item.created_at) or utc_now()
    datestamp = created_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    is_deleted = item.status == ContentStatus.REMOVED

    date_str = None
    if item.metadata_ and isinstance(item.metadata_, dict):
        date_str = str(item.metadata_.get("date_recorded") or item.metadata_.get("year") or "") or None
    if not date_str and item.created_at:
        date_str = str(item.created_at.year)

    return OaiRecord(
        identifier=f"oai:{slug}:{item.id}",
        datestamp=datestamp,
        title=item.title_nl,
        creator=item.creator_name,
        description=item.description_nl,
        date_recorded=date_str,
        content_type=item.type.value if item.type else None,
        rights=item.license or "CC BY-NC-SA 4.0",
        location_name=item.location_name,
        is_anonymous=item.is_anonymous,
        is_deleted=is_deleted,
        set_specs=[item.type.value] if item.type else [],
    )


def _parse_filter_date(datestr: str, is_until: bool = False) -> datetime | None:
    """Parse OAI-PMH date string (YYYY-MM-DD or YYYY-MM-DDThh:mm:ssZ)."""
    try:
        if len(datestr) == 10:
            dt = datetime.strptime(datestr, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if is_until:
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        elif len(datestr) == 20:
            return datetime.strptime(datestr, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    return None


@router.api_route(
    "/oai-pmh",
    methods=["GET", "POST"],
    summary="OAI-PMH v2.0 metadata harvesting",
)
async def oai_pmh_endpoint(
    tenantSlug: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """OAI-PMH v2.0 metadata harvesting endpoint.

    Supports both HTTP GET and POST methods.
    Returns XML with media_type='text/xml; charset=utf-8'.
    Protocol errors are returned under HTTP 200 with <error> tags.
    """
    # 1. Extract parameters from query string (GET) and form body (POST)
    raw_params: dict[str, str] = dict(request.query_params)
    if request.method == "POST":
        try:
            form = await request.form()
            for k, v in form.items():
                if isinstance(v, str):
                    raw_params[k] = v
        except Exception:
            pass

    base_url = str(request.url).split("?")[0]
    service = OaiPmhService(base_url=base_url)

    # 2. Protocol parameter validation
    validation_error = validate_oai_parameters(raw_params)
    if validation_error is not None:
        xml_bytes = service.build_error_response(validation_error, params=raw_params)
        return Response(content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200)

    # 3. Tenant scope validation
    async with public_tenant_scope(tenantSlug, session) as tenant:
        verb = raw_params.get("verb", "")

        # --------------------------------------------------------------------
        # Verb: Identify
        # --------------------------------------------------------------------
        if verb == "Identify":
            min_date_res = await session.execute(
                select(func.min(FoundationContent.created_at)).where(
                    FoundationContent.tenant_id == tenant.id,
                    FoundationContent.visibility == Visibility.PUBLIC,
                    FoundationContent.status == ContentStatus.APPROVED,
                )
            )
            earliest_dt = min_date_res.scalar()
            if earliest_dt:
                earliest_utc = to_utc(earliest_dt) or utc_now()
                earliest_str = earliest_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                earliest_str = "2026-01-01T00:00:00Z"

            xml_bytes = service.build_identify_response(
                repository_name=f"{tenant.name} Archief",
                admin_email=f"archief@{tenant.slug}.levendmonument.nl",
                earliest_datestamp=earliest_str,
            )
            return Response(content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200)

        # --------------------------------------------------------------------
        # Verb: ListMetadataFormats
        # --------------------------------------------------------------------
        if verb == "ListMetadataFormats":
            identifier = raw_params.get("identifier")
            if identifier:
                rec_id = _extract_content_id(identifier, tenant.slug)
                if rec_id is None:
                    err = OaiPmhError(
                        OaiPmhErrorCode.ID_DOES_NOT_EXIST,
                        f"No record with identifier '{identifier}' exists.",
                    )
                    xml_bytes = service.build_error_response(err, params=raw_params)
                    return Response(
                        content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200
                    )

                exists_res = await session.execute(
                    select(FoundationContent.id).where(
                        FoundationContent.id == rec_id,
                        FoundationContent.tenant_id == tenant.id,
                        FoundationContent.visibility == Visibility.PUBLIC,
                        FoundationContent.status.in_(
                            [ContentStatus.APPROVED, ContentStatus.REMOVED]
                        ),
                    )
                )
                if exists_res.scalar_one_or_none() is None:
                    err = OaiPmhError(
                        OaiPmhErrorCode.ID_DOES_NOT_EXIST,
                        f"No record with identifier '{identifier}' exists.",
                    )
                    xml_bytes = service.build_error_response(err, params=raw_params)
                    return Response(
                        content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200
                    )

            xml_bytes = service.build_list_metadata_formats_response(identifier=identifier)
            return Response(content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200)

        # --------------------------------------------------------------------
        # Verb: ListSets
        # --------------------------------------------------------------------
        if verb == "ListSets":
            xml_bytes = service.build_list_sets_response()
            return Response(content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200)

        # --------------------------------------------------------------------
        # Verb: GetRecord
        # --------------------------------------------------------------------
        if verb == "GetRecord":
            identifier = raw_params.get("identifier", "")
            rec_id = _extract_content_id(identifier, tenant.slug)
            if rec_id is None:
                err = OaiPmhError(
                    OaiPmhErrorCode.ID_DOES_NOT_EXIST,
                    f"No record with identifier '{identifier}' exists.",
                )
                xml_bytes = service.build_error_response(err, params=raw_params)
                return Response(
                    content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200
                )

            item_res = await session.execute(
                select(FoundationContent).where(
                    FoundationContent.id == rec_id,
                    FoundationContent.tenant_id == tenant.id,
                    FoundationContent.visibility == Visibility.PUBLIC,
                    FoundationContent.status.in_(
                        [ContentStatus.APPROVED, ContentStatus.REMOVED]
                    ),
                )
            )
            item = item_res.scalar_one_or_none()
            if item is None:
                err = OaiPmhError(
                    OaiPmhErrorCode.ID_DOES_NOT_EXIST,
                    f"No record with identifier '{identifier}' exists.",
                )
                xml_bytes = service.build_error_response(err, params=raw_params)
                return Response(
                    content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200
                )

            rec = _to_oai_record(item, tenant.slug)
            xml_bytes = service.build_get_record_response(rec)
            return Response(content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200)

        # --------------------------------------------------------------------
        # Verb: ListIdentifiers & ListRecords
        # --------------------------------------------------------------------
        if verb in ("ListIdentifiers", "ListRecords"):
            resumption_token_raw = raw_params.get("resumptionToken")

            if resumption_token_raw:
                try:
                    token = service.decode_resumption_token(resumption_token_raw)
                except OaiPmhError as exc:
                    xml_bytes = service.build_error_response(exc, params=raw_params)
                    return Response(
                        content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200
                    )
                cursor = token.cursor
                last_id = token.last_id
                last_created_at = token.last_created_at
                metadata_prefix = token.metadata_prefix
                set_spec = token.set_spec
                from_date = token.from_date
                until_date = token.until_date
            else:
                cursor = 0
                last_id = 0
                last_created_at = None
                metadata_prefix = raw_params.get("metadataPrefix", "oai_dc")
                set_spec = raw_params.get("set")
                from_date = raw_params.get("from")
                until_date = raw_params.get("until")

            # Base query: Public visibility and Approved/Removed only
            stmt = select(FoundationContent).where(
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.visibility == Visibility.PUBLIC,
                FoundationContent.status.in_([ContentStatus.APPROVED, ContentStatus.REMOVED]),
            )

            # Filter on set (matches content_type)
            if set_spec:
                try:
                    type_val = ContentType(set_spec)
                    stmt = stmt.where(FoundationContent.type == type_val)
                except ValueError:
                    err = OaiPmhError(
                        OaiPmhErrorCode.NO_RECORDS_MATCH,
                        f"No records match the requested set '{set_spec}'.",
                    )
                    xml_bytes = service.build_error_response(err, params=raw_params)
                    return Response(
                        content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200
                    )

            # Filter on from/until datestamps
            if from_date:
                from_dt = _parse_filter_date(from_date, is_until=False)
                if from_dt:
                    stmt = stmt.where(FoundationContent.created_at >= from_dt)

            if until_date:
                until_dt = _parse_filter_date(until_date, is_until=True)
                if until_dt:
                    stmt = stmt.where(FoundationContent.created_at <= until_dt)

            # Total count for completeListSize
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total_res = await session.execute(count_stmt)
            complete_list_size = total_res.scalar() or 0

            if complete_list_size == 0 and cursor == 0:
                err = OaiPmhError(
                    OaiPmhErrorCode.NO_RECORDS_MATCH,
                    "No records match the requested parameters.",
                )
                xml_bytes = service.build_error_response(err, params=raw_params)
                return Response(
                    content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200
                )

            # Keyset pagination cursor condition
            if last_created_at and last_id > 0:
                last_dt = datetime.strptime(last_created_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
                stmt = stmt.where(
                    or_(
                        FoundationContent.created_at > last_dt,
                        and_(
                            FoundationContent.created_at == last_dt,
                            FoundationContent.id > last_id,
                        ),
                    )
                )

            stmt = stmt.order_by(
                FoundationContent.created_at.asc(), FoundationContent.id.asc()
            ).limit(PAGE_SIZE + 1)

            result = await session.execute(stmt)
            rows = list(result.scalars().all())

            has_next = len(rows) > PAGE_SIZE
            records_page = rows[:PAGE_SIZE]
            new_cursor = cursor + len(records_page)

            # Resumption token generation
            resumption_token_str: str | None = None
            if has_next and records_page:
                last_item = records_page[-1]
                last_item_dt = to_utc(last_item.created_at) or utc_now()
                last_item_str = last_item_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                next_token_obj = OaiResumptionToken(
                    cursor=new_cursor,
                    last_id=last_item.id,
                    last_created_at=last_item_str,
                    metadata_prefix=metadata_prefix,
                    set_spec=set_spec,
                    from_date=from_date,
                    until_date=until_date,
                    complete_list_size=complete_list_size,
                )
                resumption_token_str = service.encode_resumption_token(next_token_obj)
            elif cursor > 0:
                # Final response in a resumed sequence emits an empty token
                resumption_token_str = ""

            records = [_to_oai_record(it, tenant.slug) for it in records_page]

            if verb == "ListIdentifiers":
                xml_bytes = service.build_list_identifiers_response(
                    records=records,
                    params=raw_params,
                    resumption_token_str=resumption_token_str,
                    complete_list_size=complete_list_size,
                    cursor=cursor,
                )
            else:
                xml_bytes = service.build_list_records_response(
                    records=records,
                    params=raw_params,
                    resumption_token_str=resumption_token_str,
                    complete_list_size=complete_list_size,
                    cursor=cursor,
                )

            return Response(content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200)

        # Fallback for unexpected verbs that passed initial check
        err = OaiPmhError(OaiPmhErrorCode.BAD_VERB, f"Unknown verb '{verb}'.")
        xml_bytes = service.build_error_response(err, params=raw_params)
        return Response(content=xml_bytes, media_type="text/xml; charset=utf-8", status_code=200)
