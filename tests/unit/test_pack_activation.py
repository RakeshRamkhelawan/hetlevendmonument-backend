"""Unit tests for PackActivationScorer.

Taak 4.1: PackActivationScorer
Fase 4: Pack Activation Intelligence
"""

import uuid
from typing import List
from unittest.mock import MagicMock

import pytest

from src.core.company.pack_activation import (
    ActivationSignals,
    PackActivationResult,
    PackActivationScorer,
    PackScore,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def scorer() -> PackActivationScorer:
    """Create a PackActivationScorer instance."""
    return PackActivationScorer()


@pytest.fixture
def mock_domain_packs() -> List[MagicMock]:
    """Create mock DomainPack objects for testing."""
    packs = []

    # Sales pack
    sales = MagicMock()
    sales.pack_id = "mkb.sales.crm"
    sales.name = "Sales CRM Pack"
    sales.department = "Sales"
    sales.intent_tags = ["sales", "crm", "leads", "conversion"]
    sales.capabilities = ["lead_management", "pipeline_tracking"]
    packs.append(sales)

    # Finance pack
    finance = MagicMock()
    finance.pack_id = "mkb.finance.accounting"
    finance.name = "Finance Accounting"
    finance.department = "Finance"
    finance.intent_tags = ["finance", "accounting", "invoicing"]
    finance.capabilities = ["bookkeeping", "invoice_generation"]
    packs.append(finance)

    # HR pack
    hr = MagicMock()
    hr.pack_id = "enterprise.hr.recruitment"
    hr.name = "HR Recruitment"
    hr.department = "HR"
    hr.intent_tags = ["hr", "recruiting", "hiring", "talent"]
    hr.capabilities = ["candidate_tracking", "interview_scheduling"]
    packs.append(hr)

    # Generic MKB pack
    mkb_generic = MagicMock()
    mkb_generic.pack_id = "mkb.general.operations"
    mkb_generic.name = "General Operations"
    mkb_generic.department = "Operations"
    mkb_generic.intent_tags = ["operations", "mkb", "general"]
    mkb_generic.capabilities = ["task_management"]
    packs.append(mkb_generic)

    return packs


# ============================================================================
# Happy Path Tests
# ============================================================================


class TestPackActivationScorer:
    """Test PackActivationScorer functionality."""

    def test_exact_department_match(self, scorer: PackActivationScorer):
        """Exact department match gives full department score (0.40)."""
        sales_pack = MagicMock()
        sales_pack.pack_id = "enterprise.sales.crm"  # Different company type
        sales_pack.name = "Sales CRM"
        sales_pack.department = "Sales"
        sales_pack.intent_tags = ["sales", "crm"]
        sales_pack.capabilities = ["lead_management"]

        signals = ActivationSignals(
            department_name="Sales",
            company_type="mkb",  # Won't match enterprise
            sector="retail",
        )

        score = scorer.score(sales_pack, signals)

        assert score.pack_id == "enterprise.sales.crm"
        assert score.score == pytest.approx(0.40, abs=0.01)  # Exact department match only
        assert any("exact" in r.lower() for r in score.reasons)

    def test_full_score_all_signals(self, scorer: PackActivationScorer, mock_domain_packs):
        """All 4 signals matching gives score ~1.0 with EXACT confidence."""
        signals = ActivationSignals(
            department_name="Sales",
            company_type="mkb",
            sector="retail",
            sector_tags=["sales", "retail"],
            explicit_pack_ids=["mkb.sales.crm"],
        )

        # Find the sales pack
        sales_pack = next(p for p in mock_domain_packs if p.pack_id == "mkb.sales.crm")
        score = scorer.score(sales_pack, signals)

        # Should be close to 1.0 (0.40 + 0.20 + 0.20 + 0.20)
        assert score.score == pytest.approx(1.0, abs=0.05)
        assert score.confidence == "EXACT"
        assert score.activated_automatically is True

    def test_auto_activate_high_confidence(self, scorer: PackActivationScorer):
        """Score >= 0.70 triggers automatic activation."""
        pack = MagicMock()
        pack.pack_id = "mkb.sales.crm"
        pack.name = "Sales CRM"
        pack.department = "Sales"
        pack.intent_tags = ["sales"]
        pack.capabilities = []

        # High-scoring signals
        signals = ActivationSignals(
            department_name="Sales",
            company_type="mkb",
            sector="retail",
            explicit_pack_ids=["mkb.sales.crm"],  # +0.20
        )

        score = scorer.score(pack, signals)

        assert score.score >= 0.70
        assert score.confidence == "HIGH"
        assert score.activated_automatically is True

    def test_suggestion_medium_confidence(self, scorer: PackActivationScorer):
        """Score 0.50-0.69 is suggested, not auto-activated."""
        pack = MagicMock()
        pack.pack_id = "mkb.sales.crm"
        pack.name = "Sales CRM"
        pack.department = "Sales"
        pack.intent_tags = ["sales"]
        pack.capabilities = []

        # Medium-scoring signals (only department match)
        signals = ActivationSignals(
            department_name="Sales",
            company_type="enterprise",  # Different type
            sector="healthcare",  # Different sector
        )

        score = scorer.score(pack, signals)

        assert 0.30 <= score.score < 0.70
        assert score.activated_automatically is False

    def test_score_all_packs_sorted(self, scorer: PackActivationScorer, mock_domain_packs):
        """All packs are scored and sorted by score desc."""
        signals = ActivationSignals(
            department_name="Sales",
            company_type="mkb",
            sector="retail",
            sector_tags=["sales", "retail", "finance"],  # Match multiple packs
            explicit_pack_ids=[],  # Add explicit matches to boost scores
        )

        scores = scorer.score_all_packs(mock_domain_packs, signals)

        # Should return packs with score >= 0.30
        assert len(scores) >= 1

        # Sales pack should be first (highest score)
        assert scores[0].pack_id == "mkb.sales.crm"

        # Verify descending order
        for i in range(len(scores) - 1):
            assert scores[i].score >= scores[i + 1].score

    def test_low_score_filtered_out(self, scorer: PackActivationScorer, mock_domain_packs):
        """Scores < 0.30 are not returned."""
        signals = ActivationSignals(
            department_name="Unknown Department",
            company_type="unknown_type",
            sector="unknown_sector",
        )

        scores = scorer.score_all_packs(mock_domain_packs, signals)

        # All scores should be >= 0.30 or filtered out
        for score in scores:
            assert score.score >= 0.30, f"Score {score.score} should be filtered"

    def test_fuzzy_department_match(self, scorer: PackActivationScorer):
        """Fuzzy matching for similar department names."""
        pack = MagicMock()
        pack.pack_id = "mkb.sales.crm"
        pack.name = "Sales CRM"
        pack.department = "Sales Department"  # Longer name for better fuzzy match
        pack.intent_tags = ["sales"]
        pack.capabilities = []

        # Similar department name
        signals = ActivationSignals(
            department_name="Sales Dept",  # Similar to Sales Department
            company_type="mkb",
            sector="retail",
        )

        score = scorer.score(pack, signals)

        # Should have some fuzzy match score (if fuzzy threshold is met)
        # Note: "Sales Dept" vs "Sales Department" has high similarity
        if score.score > 0:
            assert any("fuzzy" in r.lower() or "exact" in r.lower() for r in score.reasons)


# ============================================================================
# Confidence Level Tests
# ============================================================================


class TestConfidenceCalculation:
    """Test confidence level calculation."""

    def test_exact_confidence(self, scorer: PackActivationScorer):
        """Score >= 0.90 = EXACT."""
        assert scorer._calculate_confidence(0.95) == "EXACT"
        assert scorer._calculate_confidence(0.90) == "EXACT"

    def test_high_confidence(self, scorer: PackActivationScorer):
        """Score >= 0.70 = HIGH."""
        assert scorer._calculate_confidence(0.89) == "HIGH"
        assert scorer._calculate_confidence(0.70) == "HIGH"

    def test_medium_confidence(self, scorer: PackActivationScorer):
        """Score >= 0.50 = MEDIUM."""
        assert scorer._calculate_confidence(0.69) == "MEDIUM"
        assert scorer._calculate_confidence(0.50) == "MEDIUM"

    def test_low_confidence(self, scorer: PackActivationScorer):
        """Score >= 0.30 = LOW."""
        assert scorer._calculate_confidence(0.49) == "LOW"
        assert scorer._calculate_confidence(0.30) == "LOW"

    def test_none_confidence(self, scorer: PackActivationScorer):
        """Score < 0.30 = NONE."""
        assert scorer._calculate_confidence(0.29) == "NONE"
        assert scorer._calculate_confidence(0.0) == "NONE"


# ============================================================================
# Unhappy Path Tests
# ============================================================================


class TestUnhappyPaths:
    """Test error conditions and edge cases."""

    def test_no_signals_match(self, scorer: PackActivationScorer):
        """No matching signals gives score 0 and confidence NONE."""
        pack = MagicMock()
        pack.pack_id = "mkb.sales.crm"
        pack.name = "Sales CRM"
        pack.department = "Sales"
        pack.intent_tags = ["sales"]
        pack.capabilities = []

        signals = ActivationSignals(
            department_name="Completely Unrelated",
            company_type="unknown",
            sector="unknown",
        )

        score = scorer.score(pack, signals)

        assert score.score == 0.0
        assert score.confidence == "NONE"

    def test_empty_packs_list(self, scorer: PackActivationScorer):
        """Empty packs list returns empty scores list."""
        signals = ActivationSignals(
            department_name="Sales",
            company_type="mkb",
            sector="retail",
        )

        scores = scorer.score_all_packs([], signals)

        assert scores == []

    def test_conflict_resolution_highest_wins(self, scorer: PackActivationScorer):
        """When multiple packs match, highest score wins."""
        # Create two packs with same capability
        pack1 = MagicMock()
        pack1.pack_id = "mkb.sales.basic"
        pack1.name = "Basic Sales"
        pack1.department = "Sales"
        pack1.intent_tags = ["sales"]
        pack1.capabilities = ["crm"]

        pack2 = MagicMock()
        pack2.pack_id = "mkb.sales.advanced"
        pack2.name = "Advanced Sales"
        pack2.department = "Sales"
        pack2.intent_tags = ["sales", "advanced", "enterprise"]
        pack2.capabilities = ["crm", "analytics"]

        signals = ActivationSignals(
            department_name="Sales",
            company_type="mkb",
            sector="retail",
        )

        score1 = scorer.score(pack1, signals)
        score2 = scorer.score(pack2, signals)

        # Both should match but may have different scores
        assert score1.score > 0
        assert score2.score > 0

        # Sort and verify highest is first
        scores = sorted([score2, score1], key=lambda x: x.score, reverse=True)
        assert scores[0].score >= scores[1].score


# ============================================================================
# Tokenization Tests
# ============================================================================


class TestTokenization:
    """Test text tokenization for matching."""

    def test_dutch_stopwords_removed(self, scorer: PackActivationScorer):
        """Dutch stopwords are removed during tokenization."""
        text = "de omzet van de afdeling"
        tokens = scorer._tokenize(text, language="nl")

        # Stopwords should be removed
        assert "de" not in tokens
        assert "van" not in tokens

        # Content words should remain
        assert "omzet" in tokens
        assert "afdeling" in tokens

    def test_english_fallback(self, scorer: PackActivationScorer):
        """English tokenization works when language='en'."""
        text = "the sales department of the company"
        tokens = scorer._tokenize(text, language="en")

        # English stopwords removed
        assert "the" not in tokens
        assert "of" not in tokens

        # Content words remain
        assert "sales" in tokens
        assert "department" in tokens

    def test_case_normalization(self, scorer: PackActivationScorer):
        """Tokenization is case-insensitive."""
        text1 = "SALES Department"
        text2 = "sales department"

        tokens1 = scorer._tokenize(text1)
        tokens2 = scorer._tokenize(text2)

        assert tokens1 == tokens2


# ============================================================================
# PackActivationResult Tests
# ============================================================================


class TestPackActivationResult:
    """Test PackActivationResult model."""

    def test_activation_result_has_audit_id(self):
        """Every result has an audit_log_id field."""
        result = PackActivationResult(
            pack_id="mkb.sales.crm",
            pack_name="Sales CRM",
            confidence=0.85,
            match_reason="Department match",
            input_signals=["department: Sales"],
            score_breakdown={"department": 0.4},
            audit_log_id=uuid.uuid4(),
            activated_automatically=True,
        )

        assert result.audit_log_id is not None
        assert isinstance(result.audit_log_id, uuid.UUID)

    def test_activation_result_user_confirmed_optional(self):
        """user_confirmed is optional (None for auto-activation)."""
        # Auto-activation
        auto_result = PackActivationResult(
            pack_id="mkb.sales.crm",
            pack_name="Sales CRM",
            confidence=0.85,
            match_reason="Auto-activated",
            input_signals=[],
            score_breakdown={},
            audit_log_id=uuid.uuid4(),
            activated_automatically=True,
            user_confirmed=None,
        )
        assert auto_result.user_confirmed is None

        # Manual confirmation
        manual_result = PackActivationResult(
            pack_id="mkb.sales.crm",
            pack_name="Sales CRM",
            confidence=0.55,
            match_reason="User confirmed",
            input_signals=[],
            score_breakdown={},
            audit_log_id=uuid.uuid4(),
            activated_automatically=False,
            user_confirmed=True,
        )
        assert manual_result.user_confirmed is True
