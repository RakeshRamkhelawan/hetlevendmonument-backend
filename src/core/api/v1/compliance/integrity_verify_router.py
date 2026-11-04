"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
Integrity Verify sub-router (ADR-033 Laag 1).

Routes:
- GET /integrity/verify
- POST /integrity/verify-entry
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from loguru import logger

from src.core.api.v1.compliance.dependencies import (
    HashChainVerifier,
    get_current_user,
    get_hash_chain_verifier,
    governance_read_limit,
    governance_write_limit,
)
from src.core.api.v1.compliance.schemas import (
    ChainPeriod,
    ChainVerificationResponse,
    EntryVerificationResponse,
    VerifyEntryRequest,
)
from src.core.models.rbac_models import User

integrity_verify_router = APIRouter()


@integrity_verify_router.get(
    "/integrity/verify",
    response_model=ChainVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify hash chain integrity",
    description="""
    Verifies the integrity of the audit log hash chain for the authenticated tenant.

    Query parameters:
    - start_date: Optional start date filter (ISO format)
    - end_date: Optional end date filter (ISO format)

    Requires authentication.
    """,
    responses={
        status.HTTP_200_OK: {
            "description": "Chain verification completed successfully",
            "model": ChainVerificationResponse,
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
@governance_read_limit
async def verify_chain_integrity(
    request: Request,
    start_date: datetime | None = Query(
        None,
        description="Optional start date filter (ISO format)",
    ),
    end_date: datetime | None = Query(
        None,
        description="Optional end date filter (ISO format)",
    ),
    current_user: User = Depends(get_current_user),
    verifier: HashChainVerifier = Depends(get_hash_chain_verifier),
) -> ChainVerificationResponse:
    """Verify hash chain integrity for the authenticated tenant."""
    tenant_id = current_user.tenant_id

    if start_date is not None and start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date is not None and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    logger.info(
        "Verifying hash chain integrity",
        tenant_id=tenant_id,
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
    )

    try:
        result = await verifier.verify_chain(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
        )

        logger.info(
            "Hash chain verification completed",
            tenant_id=tenant_id,
            is_valid=result.is_valid,
            tampering_detected=result.tampering_detected,
            unhashed_entries=result.unhashed_entries,
            total_entries=result.total_entries,
            verification_time_ms=result.verification_time_ms,
        )

        period = ChainPeriod(
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
        )

        return ChainVerificationResponse(
            is_valid=result.is_valid,
            # Een GAT is iets anders dan MANIPULATIE, en dat onderscheid hoort naar buiten
            # (ADR-036 OP-108). `is_valid` blijft False bij manipulatie EN bij een gat van na
            # de fixdatum; een bekend legacy-gat van ervoor weegt niet meer mee (OP-118).
            tampering_detected=result.tampering_detected,
            unhashed_entries=result.unhashed_entries,
            # Beide tellers gaan naar buiten zodat een auditor de bekende legacy-gaten nog
            # steeds ziet staan in plaats van ze kwijt te raken aan het watermerk.
            unhashed_before_watermark=result.unhashed_before_watermark,
            unhashed_after_watermark=result.unhashed_after_watermark,
            total_entries=result.total_entries,
            verified_entries=result.verified_entries,
            broken_at_entry_id=result.broken_at_entry_id,
            broken_at_index=result.broken_at_index,
            expected_hash=result.expected_hash,
            actual_hash=result.actual_hash,
            verification_time_ms=result.verification_time_ms,
            tenant_id=result.tenant_id,
            checked_at=result.checked_at,
            period=period,
        )

    except Exception as e:
        logger.error(
            "Failed to verify hash chain: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            tenant_id=tenant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify hash chain",
        )


@integrity_verify_router.post(
    "/integrity/verify-entry",
    response_model=EntryVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify single entry",
    description="""
    Verifies the integrity of a single audit log entry.

    Request body:
    - entry_id: ID of the entry to verify

    Requires authentication.
    """,
    responses={
        status.HTTP_200_OK: {
            "description": "Entry verification completed successfully",
            "model": EntryVerificationResponse,
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Invalid request body"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
@governance_write_limit
async def verify_entry(
    request: VerifyEntryRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    verifier: HashChainVerifier = Depends(get_hash_chain_verifier),
) -> EntryVerificationResponse:
    """Verify a single audit log entry for the authenticated tenant."""
    tenant_id = current_user.tenant_id
    entry_id = request.entry_id

    logger.info(
        "Verifying audit log entry",
        tenant_id=tenant_id,
        user_id=current_user.id,
        entry_id=entry_id,
    )

    try:
        result = await verifier.verify_entry(
            entry_id=entry_id,
            tenant_id=tenant_id,
        )

        logger.info(
            "Entry verification completed",
            tenant_id=tenant_id,
            entry_id=entry_id,
            is_valid=result.is_valid,
            hash_matches=result.hash_matches,
        )

        return EntryVerificationResponse(
            entry_id=result.entry_id,
            is_valid=result.is_valid,
            hash_matches=result.hash_matches,
            previous_hash_matches=result.previous_hash_matches,
            computed_hash=result.computed_hash,
            stored_hash=result.stored_hash,
            tenant_id=result.tenant_id,
            verified_at=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error(
            "Failed to verify entry: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            tenant_id=tenant_id,
            entry_id=entry_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify entry",
        )
