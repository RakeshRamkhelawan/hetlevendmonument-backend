"""Het art.-5(1)(e)-bewijs van de opruimactor is aan de keten gebonden (ADR-036 OP-121).

`records_deleted`, `cutoff_date` en `regulatory_basis` staan in `event_metadata`, buiten
`HashChainVerifier._compute_hash`. Wie met UPDATE-recht `records_deleted` van 0 naar 40.000 zet,
bleef daardoor onzichtbaar voor de ketenverificatie. `retention_evidence.py` bindt een digest
over die drie velden in `resource` (dezelfde non-destructieve aanpak als H-2's
`hitl_evidence.py`), en `HashChainVerifier._verify_bound_evidence` dispatcht nu naar beide
bindingen.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.governance.hash_chain import HashChainVerifier
from src.core.governance.models import AuditLog
from src.core.governance.retention_cleanup import (
    DataCategory,
    RetentionCleanupService,
    RetentionJurisdiction,
)
from src.core.governance.retention_evidence import build_resource, evidence_matches


@pytest.mark.unit
class TestBuildAndMatchRoundTrip:
    def test_the_built_resource_matches_its_own_values(self) -> None:
        resource = build_resource(
            category="financial",
            jurisdiction="eu",
            records_deleted=12,
            cutoff_date="2026-08-01T00:00:00+00:00",
            regulatory_basis="GDPR Art. 5(1)(e)",
        )

        assert (
            evidence_matches(
                resource,
                records_deleted=12,
                cutoff_date="2026-08-01T00:00:00+00:00",
                regulatory_basis="GDPR Art. 5(1)(e)",
            )
            is True
        )

    def test_the_prefix_is_unchanged_so_existing_prefix_queries_keep_working(self) -> None:
        resource = build_resource(
            category="financial",
            jurisdiction="eu",
            records_deleted=12,
            cutoff_date="2026-08-01T00:00:00+00:00",
            regulatory_basis="GDPR Art. 5(1)(e)",
        )

        assert resource.startswith("retention_cleanup:financial_eu|ev=")


@pytest.mark.unit
class TestTamperingIsDetected:
    def test_a_changed_records_deleted_no_longer_matches(self) -> None:
        """De kern van OP-121: wie `records_deleted` na het schrijven wijzigt (UPDATE-recht op
        `event_metadata`, buiten de hash-keten om), moet dat via `resource` alsnog blootgeven.
        """
        resource = build_resource(
            category="financial",
            jurisdiction="eu",
            records_deleted=12,
            cutoff_date="2026-08-01T00:00:00+00:00",
            regulatory_basis="GDPR Art. 5(1)(e)",
        )

        assert (
            evidence_matches(
                resource,
                records_deleted=40_000,
                cutoff_date="2026-08-01T00:00:00+00:00",
                regulatory_basis="GDPR Art. 5(1)(e)",
            )
            is False
        )

    def test_a_changed_regulatory_basis_no_longer_matches(self) -> None:
        resource = build_resource(
            category="financial",
            jurisdiction="eu",
            records_deleted=12,
            cutoff_date="2026-08-01T00:00:00+00:00",
            regulatory_basis="GDPR Art. 5(1)(e)",
        )

        assert (
            evidence_matches(
                resource,
                records_deleted=12,
                cutoff_date="2026-08-01T00:00:00+00:00",
                regulatory_basis="fabricated basis",
            )
            is False
        )


@pytest.mark.unit
class TestAnUnrelatedResourceIsNotFlagged:
    def test_a_non_retention_resource_returns_none_not_false(self) -> None:
        """Geen `retention_cleanup:`-vorm -> niets na te rekenen, geen manipulatie-melding."""
        assert (
            evidence_matches(
                "hitl_ticket:abc123",
                records_deleted=12,
                cutoff_date="2026-08-01T00:00:00+00:00",
                regulatory_basis="GDPR Art. 5(1)(e)",
            )
            is None
        )

    def test_a_resource_without_the_ev_suffix_returns_none(self) -> None:
        """Een rij van voor deze fix heeft geen `|ev=`-deel -- niet gedekt, geen valse melding."""
        assert (
            evidence_matches(
                "retention_cleanup:financial_eu",
                records_deleted=12,
                cutoff_date="2026-08-01T00:00:00+00:00",
                regulatory_basis="GDPR Art. 5(1)(e)",
            )
            is None
        )


@pytest.mark.unit
class TestTheVerifierDispatchesToRetentionEvidence:
    """Bewijst dat de binding ook daadwerkelijk WORDT GECONTROLEERD, niet alleen bestaat."""

    def test_an_intact_retention_row_verifies_true(self) -> None:
        verifier = HashChainVerifier(db_session=None)
        resource = build_resource(
            category="financial",
            jurisdiction="eu",
            records_deleted=12,
            cutoff_date="2026-08-01T00:00:00+00:00",
            regulatory_basis="GDPR Art. 5(1)(e)",
        )
        entry = AuditLog(
            resource=resource,
            event_metadata={
                "category": "financial",
                "jurisdiction": "eu",
                "records_deleted": 12,
                "cutoff_date": "2026-08-01T00:00:00+00:00",
                "regulatory_basis": "GDPR Art. 5(1)(e)",
            },
        )

        assert verifier._verify_bound_evidence(entry) is True

    def test_a_tampered_retention_row_verifies_false(self) -> None:
        """Het scenario uit de ADR: `records_deleted` gewijzigd na het schrijven."""
        verifier = HashChainVerifier(db_session=None)
        resource = build_resource(
            category="financial",
            jurisdiction="eu",
            records_deleted=12,
            cutoff_date="2026-08-01T00:00:00+00:00",
            regulatory_basis="GDPR Art. 5(1)(e)",
        )
        entry = AuditLog(
            resource=resource,
            event_metadata={
                "category": "financial",
                "jurisdiction": "eu",
                "records_deleted": 40_000,  # gewijzigd na het schrijven
                "cutoff_date": "2026-08-01T00:00:00+00:00",
                "regulatory_basis": "GDPR Art. 5(1)(e)",
            },
        )

        assert verifier._verify_bound_evidence(entry) is False

    def test_an_ordinary_row_without_any_binding_stays_unflagged(self) -> None:
        """Geen HITL-vorm en geen opruim-vorm -- de dispatch mag dit niet als manipulatie lezen."""
        verifier = HashChainVerifier(db_session=None)
        entry = AuditLog(
            resource="some_other_resource",
            event_metadata={},
        )

        assert verifier._verify_bound_evidence(entry) is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheCleanupActorActuallyBindsTheResource:
    """Bewijst dat `_create_audit_log` de binding ook echt AANROEPT -- de vorige klasse dekt
    alleen `retention_evidence.py` zelf; dit dekt de bedrading in `retention_cleanup.py`.
    """

    async def test_the_written_resource_matches_the_written_metadata(self) -> None:
        service = RetentionCleanupService(db=AsyncMock(), tenant_id=1)
        cutoff = datetime(2026, 8, 1, tzinfo=timezone.utc)

        with patch(
            "src.core.governance.retention_cleanup.AuditService.log_event",
            new_callable=AsyncMock,
        ) as mock_log_event:
            await service._create_audit_log(
                category=DataCategory.FINANCIAL,
                jurisdiction=RetentionJurisdiction.EU,
                records_deleted=12,
                cutoff_date=cutoff,
                regulatory_basis="GDPR Art. 5(1)(e)",
            )

        assert mock_log_event.await_args is not None, "log_event is niet aangeroepen"
        written_resource = mock_log_event.await_args.kwargs["resource"]
        assert (
            evidence_matches(
                written_resource,
                records_deleted=12,
                cutoff_date=cutoff.isoformat(),
                regulatory_basis="GDPR Art. 5(1)(e)",
            )
            is True
        ), (
            "De geschreven resource bevat geen (of een verkeerde) digest over de "
            "event_metadata-velden -- de binding uit retention_evidence.py is niet aangesloten "
            f"op _create_audit_log. resource was: {written_resource!r}"
        )
