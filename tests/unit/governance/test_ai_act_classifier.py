"""Tests for AI Act Risk Classifier.

EU AI Act Compliance - Task 1: Risk Classification
Tests for classifying agents into EU AI Act risk levels.
"""

from __future__ import annotations

import pytest

from src.core.governance.ai_act_classifier import (
    UNACCEPTABLE_CAPABILITIES,
    AIActRiskLevel,
    classify_agent,
    is_high_risk_capability,
    is_unacceptable_capability,
)


class TestAIActRiskLevel:
    """Test AIActRiskLevel enum."""

    def test_risk_level_values(self) -> None:
        """Risk levels should have correct string values."""
        assert AIActRiskLevel.MINIMAL.value == "minimal"
        assert AIActRiskLevel.LIMITED.value == "limited"
        assert AIActRiskLevel.HIGH_RISK.value == "high_risk"


class TestIsHighRiskCapability:
    """Test high-risk capability detection."""

    def test_recruitment_is_high_risk(self) -> None:
        """Recruitment capabilities should be high risk (Annex III)."""
        assert is_high_risk_capability("recruitment") is True
        assert is_high_risk_capability("talent_acquisition") is True
        assert is_high_risk_capability("hiring") is True

    def test_credit_scoring_is_high_risk(self) -> None:
        """Credit scoring capabilities should be high risk (Annex III)."""
        assert is_high_risk_capability("credit_scoring") is True
        assert is_high_risk_capability("loan_assessment") is True
        assert is_high_risk_capability("creditworthiness") is True

    def test_fraud_detection_is_high_risk(self) -> None:
        """Fraud detection should be high risk (Annex III)."""
        assert is_high_risk_capability("fraud_detection") is True
        assert is_high_risk_capability("anomaly_detection") is True

    def test_biometric_is_high_risk(self) -> None:
        """Biometric capabilities should be high risk (Annex III)."""
        assert is_high_risk_capability("face_recognition") is True
        assert is_high_risk_capability("emotion_recognition") is True

    def test_employee_evaluation_is_high_risk(self) -> None:
        """Employee evaluation should be high risk (Annex III)."""
        assert is_high_risk_capability("performance_evaluation") is True
        assert is_high_risk_capability("promotion_recommendation") is True

    def test_general_capabilities_not_high_risk(self) -> None:
        """General capabilities should not be high risk."""
        assert is_high_risk_capability("document_processing") is False
        assert is_high_risk_capability("data_analysis") is False
        assert is_high_risk_capability("reporting") is False


class TestClassifyAgent:
    """Test agent risk classification."""

    def test_hr_recruitment_agent_is_high_risk(self) -> None:
        """HR recruitment agent should be HIGH_RISK (Annex III)."""
        result = classify_agent(
            name="Talent Acquisition Bot",
            department="HR",
            specialisation="recruitment",
            capabilities=["resume_screening", "candidate_ranking"],
        )
        assert result == AIActRiskLevel.HIGH_RISK

    def test_credit_scoring_agent_is_high_risk(self) -> None:
        """Credit scoring agent should be HIGH_RISK (Annex III)."""
        result = classify_agent(
            name="Credit Assessor",
            department="Finance",
            specialisation="credit_analysis",
            capabilities=["credit_scoring", "risk_assessment"],
        )
        assert result == AIActRiskLevel.HIGH_RISK

    def test_fraud_detection_agent_is_high_risk(self) -> None:
        """Fraud detection agent should be HIGH_RISK (Annex III)."""
        result = classify_agent(
            name="Fraud Monitor",
            department="Finance",
            specialisation="security",
            capabilities=["fraud_detection", "transaction_monitoring"],
        )
        assert result == AIActRiskLevel.HIGH_RISK

    def test_employee_evaluation_agent_is_high_risk(self) -> None:
        """Employee evaluation agent should be HIGH_RISK (Annex III)."""
        result = classify_agent(
            name="Performance Reviewer",
            department="HR",
            specialisation="employee_management",
            capabilities=["performance_evaluation", "promotion_recommendation"],
        )
        assert result == AIActRiskLevel.HIGH_RISK

    def test_biometric_agent_is_high_risk(self) -> None:
        """Biometric agent should be HIGH_RISK (Annex III)."""
        result = classify_agent(
            name="Face Recognition System",
            department="Security",
            specialisation="access_control",
            capabilities=["face_recognition", "identity_verification"],
        )
        assert result == AIActRiskLevel.HIGH_RISK

    def test_llm_agent_is_limited_risk(self) -> None:
        """Agent with LLM capabilities should be LIMITED (Article 52)."""
        result = classify_agent(
            name="Content Assistant",
            department="Marketing",
            specialisation="content_creation",
            capabilities=["text_generation", "document_processing"],
        )
        assert result == AIActRiskLevel.LIMITED

    def test_general_agent_is_limited_risk(self) -> None:
        """Agent with general AI capabilities should be LIMITED."""
        result = classify_agent(
            name="Data Analyzer",
            department="Analytics",
            specialisation="data_processing",
            capabilities=["data_analysis", "reporting"],
        )
        assert result == AIActRiskLevel.LIMITED

    def test_simple_agent_is_minimal_risk(self) -> None:
        """Agent without AI capabilities should be MINIMAL."""
        result = classify_agent(
            name="Simple Bot",
            department="Operations",
            specialisation="automation",
            capabilities=[],
        )
        assert result == AIActRiskLevel.MINIMAL

    def test_no_department_no_capabilities_is_minimal(self) -> None:
        """Agent with no department and no capabilities should be MINIMAL."""
        result = classify_agent(
            name="Basic Bot",
            department="",
            specialisation="",
            capabilities=[],
        )
        assert result == AIActRiskLevel.MINIMAL

    def test_single_high_risk_capability_is_high_risk(self) -> None:
        """Single high-risk capability should trigger HIGH_RISK."""
        result = classify_agent(
            name="Risky Bot",
            department="Unknown",
            specialisation="unknown",
            capabilities=["credit_scoring"],
        )
        assert result == AIActRiskLevel.HIGH_RISK

    def test_case_insensitive_matching(self) -> None:
        """Classification should be case-insensitive."""
        result = classify_agent(
            name="HR Bot",
            department="hr",
            specialisation="RECRUITMENT",
            capabilities=["Resume_Screening"],
        )
        assert result == AIActRiskLevel.HIGH_RISK


class TestHighRiskSignalCounting:
    """Test that classification requires 2 of 3 signals OR direct capability match."""

    def test_two_signals_high_risk(self) -> None:
        """Two matching signals (dept + spec) should be HIGH_RISK."""
        result = classify_agent(
            name="HR Recruiter",
            department="HR",  # Signal 1
            specialisation="recruitment",  # Signal 2
            capabilities=["basic_task"],  # Not high risk
        )
        assert result == AIActRiskLevel.HIGH_RISK

    def test_one_signal_not_high_risk(self) -> None:
        """One signal alone should NOT be HIGH_RISK."""
        result = classify_agent(
            name="HR Bot",
            department="HR",  # Only signal
            specialisation="general",
            capabilities=["basic_task"],
        )
        # HR dept alone is not enough - needs capabilities or spec
        assert result != AIActRiskLevel.HIGH_RISK

    def test_three_signals_high_risk(self) -> None:
        """All three signals matching should be HIGH_RISK."""
        result = classify_agent(
            name="HR Recruiter",
            department="HR",  # Signal 1
            specialisation="recruitment",  # Signal 2
            capabilities=["resume_screening"],  # Signal 3
        )
        assert result == AIActRiskLevel.HIGH_RISK


class TestAIActRiskLevelUnacceptable:
    """Art. 5: UNACCEPTABLE risk level enum tests."""

    def test_unacceptable_enum_value(self) -> None:
        """UNACCEPTABLE should have string value 'unacceptable'."""
        assert AIActRiskLevel.UNACCEPTABLE.value == "unacceptable"

    def test_unacceptable_is_str_enum(self) -> None:
        """UNACCEPTABLE should be comparable to its string value."""
        assert AIActRiskLevel.UNACCEPTABLE == "unacceptable"

    def test_all_four_levels_exist(self) -> None:
        """All four risk levels should exist: UNACCEPTABLE, HIGH_RISK, LIMITED, MINIMAL."""
        levels = {level.value for level in AIActRiskLevel}
        assert "unacceptable" in levels
        assert "high_risk" in levels
        assert "limited" in levels
        assert "minimal" in levels


class TestUnacceptableCapabilities:
    """Art. 5: Tests for prohibited capability detection."""

    def test_unacceptable_capabilities_set_exists(self) -> None:
        """UNACCEPTABLE_CAPABILITIES set should be importable and non-empty."""
        assert isinstance(UNACCEPTABLE_CAPABILITIES, set)
        assert len(UNACCEPTABLE_CAPABILITIES) >= 8

    def test_social_scoring_is_unacceptable(self) -> None:
        """Social scoring is prohibited under Art. 5."""
        assert is_unacceptable_capability("social_scoring") is True

    def test_mass_surveillance_is_unacceptable(self) -> None:
        """Mass surveillance is prohibited under Art. 5."""
        assert is_unacceptable_capability("mass_surveillance") is True

    def test_biometric_categorization_sensitive_is_unacceptable(self) -> None:
        """Sensitive biometric categorization is prohibited under Art. 5."""
        assert is_unacceptable_capability("biometric_categorization_sensitive") is True

    def test_emotion_recognition_workplace_is_unacceptable(self) -> None:
        """Emotion recognition in workplace is prohibited under Art. 5."""
        assert is_unacceptable_capability("emotion_recognition_workplace") is True

    def test_emotion_recognition_education_is_unacceptable(self) -> None:
        """Emotion recognition in educational settings is prohibited under Art. 5."""
        assert is_unacceptable_capability("emotion_recognition_education") is True

    def test_predictive_policing_individual_is_unacceptable(self) -> None:
        """Individual predictive policing is prohibited under Art. 5."""
        assert is_unacceptable_capability("predictive_policing_individual") is True

    def test_subliminal_manipulation_is_unacceptable(self) -> None:
        """Subliminal manipulation is prohibited under Art. 5."""
        assert is_unacceptable_capability("subliminal_manipulation") is True

    def test_exploitation_vulnerable_groups_is_unacceptable(self) -> None:
        """Exploitation of vulnerable groups is prohibited under Art. 5."""
        assert is_unacceptable_capability("exploitation_vulnerable_groups") is True

    def test_high_risk_capability_not_unacceptable(self) -> None:
        """HIGH_RISK capabilities (e.g. credit_scoring) should NOT be unacceptable."""
        assert is_unacceptable_capability("credit_scoring") is False
        assert is_unacceptable_capability("recruitment") is False

    def test_general_capability_not_unacceptable(self) -> None:
        """General capabilities should not be unacceptable."""
        assert is_unacceptable_capability("data_analysis") is False
        assert is_unacceptable_capability("text_generation") is False

    def test_case_insensitive_matching(self) -> None:
        """Unacceptable detection should be case-insensitive."""
        assert is_unacceptable_capability("Social_Scoring") is True
        assert is_unacceptable_capability("MASS_SURVEILLANCE") is True


class TestClassifyAgentUnacceptable:
    """Art. 5: Tests that classify_agent returns UNACCEPTABLE for prohibited capabilities."""

    def test_social_scoring_agent_is_unacceptable(self) -> None:
        """Agent with social_scoring capability must be UNACCEPTABLE (Art. 5)."""
        result = classify_agent(
            name="Social Score Bot",
            department="Government",
            specialisation="citizen_evaluation",
            capabilities=["social_scoring"],
        )
        assert result == AIActRiskLevel.UNACCEPTABLE

    def test_mass_surveillance_agent_is_unacceptable(self) -> None:
        """Agent with mass_surveillance capability must be UNACCEPTABLE (Art. 5)."""
        result = classify_agent(
            name="Surveillance System",
            department="Security",
            specialisation="monitoring",
            capabilities=["mass_surveillance", "video_analysis"],
        )
        assert result == AIActRiskLevel.UNACCEPTABLE

    def test_emotion_recognition_workplace_is_unacceptable(self) -> None:
        """Workplace emotion recognition must be UNACCEPTABLE (Art. 5)."""
        result = classify_agent(
            name="Employee Mood Tracker",
            department="HR",
            specialisation="employee_monitoring",
            capabilities=["emotion_recognition_workplace"],
        )
        assert result == AIActRiskLevel.UNACCEPTABLE

    def test_subliminal_manipulation_is_unacceptable(self) -> None:
        """Subliminal manipulation must be UNACCEPTABLE regardless of other signals."""
        result = classify_agent(
            name="Influence Bot",
            department="Marketing",
            specialisation="engagement",
            capabilities=["subliminal_manipulation", "content_generation"],
        )
        assert result == AIActRiskLevel.UNACCEPTABLE

    def test_unacceptable_takes_priority_over_high_risk_signals(self) -> None:
        """UNACCEPTABLE capability must override HIGH_RISK classification signals."""
        result = classify_agent(
            name="HR Social Scorer",
            department="HR",  # HIGH_RISK signal
            specialisation="recruitment",  # HIGH_RISK signal
            capabilities=["social_scoring"],  # UNACCEPTABLE
        )
        assert result == AIActRiskLevel.UNACCEPTABLE

    def test_high_risk_cap_without_unacceptable_stays_high_risk(self) -> None:
        """HIGH_RISK capability without unacceptable flag must remain HIGH_RISK."""
        result = classify_agent(
            name="Credit Bot",
            department="Finance",
            specialisation="credit_analysis",
            capabilities=["credit_scoring"],
        )
        assert result == AIActRiskLevel.HIGH_RISK
