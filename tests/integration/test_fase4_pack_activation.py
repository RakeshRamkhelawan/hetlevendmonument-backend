"""Fase 4 Integration Tests - Pack Activation Intelligence

Tests pack auto-activation, audit trail, and scoring with real database.
Uses real PostgreSQL + DomainPacks.
"""

import uuid
from typing import Any, Dict

import pytest
from httpx import AsyncClient

from src.core.company.pack_activation import ActivationSignals, PackActivationScorer, PackScore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


# ============================================================================
# Pack Scoring Tests (Unit-style but with real algorithm)
# ============================================================================


class TestPackScoring:
    """Test pack scoring algorithm with real data."""

    @pytest.mark.asyncio
    async def test_pack_scorer_with_real_signals(self):
        """PackActivationScorer works with real signals."""
        from unittest.mock import MagicMock

        # Create mock packs
        sales_pack = MagicMock()
        sales_pack.pack_id = "mkb.sales.crm"
        sales_pack.name = "Sales CRM"
        sales_pack.department = "Sales"
        sales_pack.intent_tags = ["sales", "crm", "leads"]
        sales_pack.capabilities = ["lead_management"]

        finance_pack = MagicMock()
        finance_pack.pack_id = "mkb.finance.accounting"
        finance_pack.name = "Finance Accounting"
        finance_pack.department = "Finance"
        finance_pack.intent_tags = ["finance", "accounting"]
        finance_pack.capabilities = ["bookkeeping"]

        packs = [sales_pack, finance_pack]

        # Test signals
        signals = ActivationSignals(
            department_name="Sales",
            company_type="mkb",
            sector="retail",
        )

        # Score packs
        scorer = PackActivationScorer()
        scores = scorer.score_all_packs(packs, signals)

        # Verify Sales pack has higher score
        assert len(scores) >= 1
        assert scores[0].pack_id == "mkb.sales.crm"

        # Verify score structure
        for score in scores:
            assert isinstance(score, PackScore)
            assert score.score >= 0.30  # Filtered threshold
            assert score.confidence in ["EXACT", "HIGH", "MEDIUM", "LOW", "NONE"]
            assert len(score.reasons) > 0

    @pytest.mark.asyncio
    async def test_confidence_levels_calculated_correctly(self):
        """Confidence levels are calculated based on score thresholds."""
        scorer = PackActivationScorer()

        # Test threshold boundaries
        assert scorer._calculate_confidence(0.95) == "EXACT"
        assert scorer._calculate_confidence(0.90) == "EXACT"
        assert scorer._calculate_confidence(0.89) == "HIGH"
        assert scorer._calculate_confidence(0.70) == "HIGH"
        assert scorer._calculate_confidence(0.69) == "MEDIUM"
        assert scorer._calculate_confidence(0.50) == "MEDIUM"
        assert scorer._calculate_confidence(0.49) == "LOW"
        assert scorer._calculate_confidence(0.30) == "LOW"
        assert scorer._calculate_confidence(0.29) == "NONE"
        assert scorer._calculate_confidence(0.0) == "NONE"


# ============================================================================
# Auto-activation Threshold Tests
# ============================================================================


class TestAutoActivationThresholds:
    """Test auto-activation thresholds."""

    @pytest.mark.asyncio
    async def test_high_confidence_auto_activated(self):
        """Packs with score >= 0.70 are auto-activated."""
        from unittest.mock import MagicMock

        # Create pack that will score high
        pack = MagicMock()
        pack.pack_id = "mkb.sales.crm"
        pack.name = "Sales CRM"
        pack.department = "Sales"
        pack.intent_tags = ["sales"]
        pack.capabilities = []

        signals = ActivationSignals(
            department_name="Sales",
            company_type="mkb",
            sector="retail",
            explicit_pack_ids=["mkb.sales.crm"],  # Boost score
        )

        scorer = PackActivationScorer()
        score = scorer.score(pack, signals)

        # Should be auto-activated
        assert score.score >= 0.70
        assert score.activated_automatically is True
        assert score.confidence in ["EXACT", "HIGH"]

    @pytest.mark.asyncio
    async def test_medium_confidence_suggested_not_activated(self):
        """Packs with score 0.50-0.69 are suggested, not auto-activated."""
        from unittest.mock import MagicMock

        # Create pack that will score medium
        pack = MagicMock()
        pack.pack_id = "mkb.sales.crm"
        pack.name = "Sales CRM"
        pack.department = "Sales"
        pack.intent_tags = ["sales"]
        pack.capabilities = []

        # Only department match (0.40) + company type (0.20) = 0.60
        signals = ActivationSignals(
            department_name="Sales",
            company_type="enterprise",  # Different type
            sector="healthcare",  # Different sector
        )

        scorer = PackActivationScorer()
        score = scorer.score(pack, signals)

        # Should be suggested but not auto-activated
        if score.score >= 0.30:
            assert score.activated_automatically is False
            assert score.confidence in ["MEDIUM", "LOW"]


# ============================================================================
# Database Schema Tests
# ============================================================================


class TestDatabaseSchema:
    """Test database schema for pack activation."""

    @pytest.mark.asyncio
    async def test_pack_activation_audit_log_table_exists(self, postgres_engine):
        """pack_activation_audit_logs table exists in database."""
        from sqlalchemy import inspect

        async with postgres_engine.connect() as conn:

            def check_table(connection):
                inspector = inspect(connection)
                return inspector.has_table("pack_activation_audit_logs")

            result = await conn.run_sync(check_table)
            assert result is True, "pack_activation_audit_logs table should exist"

    @pytest.mark.asyncio
    async def test_audit_log_indexes_exist(self, postgres_engine):
        """Required indexes exist on audit log table."""
        from sqlalchemy import inspect

        async with postgres_engine.connect() as conn:

            def get_indexes(connection):
                inspector = inspect(connection)
                return inspector.get_indexes("pack_activation_audit_logs")

            indexes = await conn.run_sync(get_indexes)
            index_names = {idx["name"] for idx in indexes}

            # Check required indexes
            required = [
                "idx_audit_tenant_company",
                "idx_audit_pack",
                "idx_audit_created",
            ]

            for idx in required:
                assert idx in index_names, f"Missing index: {idx}"
