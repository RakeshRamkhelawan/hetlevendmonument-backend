"""
Unit tests for DataAnonymizer.

Tests the privacy-preserving data anonymization pipeline.
"""

import pytest

from src.core.analytics.anonymizer import DataAnonymizer


class TestDataAnonymizer:
    """Test cases for DataAnonymizer class."""

    def test_hash_company_id_consistency(self):
        """Same company ID should always produce same hash."""
        company_id = "550e8400-e29b-41d4-a716-446655440000"

        hash1 = DataAnonymizer.hash_company_id(company_id)
        hash2 = DataAnonymizer.hash_company_id(company_id)

        assert hash1 == hash2
        assert len(hash1) == 16

    def test_hash_company_id_different_inputs(self):
        """Different company IDs should produce different hashes."""
        hash1 = DataAnonymizer.hash_company_id("company-1")
        hash2 = DataAnonymizer.hash_company_id("company-2")

        assert hash1 != hash2

    def test_hash_company_id_not_reversible(self):
        """Hash should not reveal original company ID."""
        company_id = "sensitive-company-name-123"
        hash_val = DataAnonymizer.hash_company_id(company_id)

        # Hash should not contain any part of original
        assert company_id not in hash_val
        assert "sensitive" not in hash_val.lower()
        assert "company" not in hash_val.lower()

    def test_hash_company_id_empty_raises_error(self):
        """Empty company ID should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            DataAnonymizer.hash_company_id("")

        with pytest.raises(ValueError, match="cannot be empty"):
            DataAnonymizer.hash_company_id(None)

    def test_bucket_employees_micro(self):
        """Companies with <10 employees should be in 1-9 bucket."""
        assert DataAnonymizer._bucket_employees(0) == "1-9"
        assert DataAnonymizer._bucket_employees(1) == "1-9"
        assert DataAnonymizer._bucket_employees(9) == "1-9"

    def test_bucket_employees_small(self):
        """Companies with 10-49 employees should be in 10-49 bucket."""
        assert DataAnonymizer._bucket_employees(10) == "10-49"
        assert DataAnonymizer._bucket_employees(25) == "10-49"
        assert DataAnonymizer._bucket_employees(49) == "10-49"

    def test_bucket_employees_medium(self):
        """Companies with 50-249 employees should be in 50-249 bucket."""
        assert DataAnonymizer._bucket_employees(50) == "50-249"
        assert DataAnonymizer._bucket_employees(150) == "50-249"
        assert DataAnonymizer._bucket_employees(249) == "50-249"

    def test_bucket_employees_large(self):
        """Companies with >=250 employees should be in 250+ bucket."""
        assert DataAnonymizer._bucket_employees(250) == "250+"
        assert DataAnonymizer._bucket_employees(1000) == "250+"
        assert DataAnonymizer._bucket_employees(10000) == "250+"

    def test_bucket_employees_invalid_input(self):
        """Invalid inputs should return 1-9 bucket."""
        assert DataAnonymizer._bucket_employees(None) == "1-9"
        assert DataAnonymizer._bucket_employees("invalid") == "1-9"
        assert DataAnonymizer._bucket_employees(-5) == "1-9"

    def test_anonymize_company_basic(self):
        """Test basic company anonymization."""
        company = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Acme Corp",
            "sector": "Technology",
            "company_type": "mkb",
            "employee_count": 45,
        }

        result = DataAnonymizer.anonymize_company(company)

        assert "id_hash" in result
        assert result["sector"] == "Technology"
        assert result["company_type"] == "mkb"
        assert result["employee_count_bucket"] == "10-49"
        assert result["opted_out"] is False

        # PII should be removed
        assert "name" not in result
        assert "Acme" not in str(result)

    def test_anonymize_company_with_opt_out(self):
        """Test that opt-out config is respected."""
        company = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sector": "Technology",
            "company_type": "mkb",
            "config": {"opt_out_analytics": True},
        }

        result = DataAnonymizer.anonymize_company(company)

        assert result["opted_out"] is True

    def test_anonymize_company_without_id_raises(self):
        """Company without ID should raise ValueError."""
        company = {
            "sector": "Technology",
            "company_type": "mkb",
        }

        with pytest.raises(ValueError, match="must have 'id' field"):
            DataAnonymizer.anonymize_company(company)

    def test_anonymize_company_empty_raises(self):
        """Empty company should raise ValueError."""
        with pytest.raises(ValueError, match="non-empty dictionary"):
            DataAnonymizer.anonymize_company({})

        with pytest.raises(ValueError, match="non-empty dictionary"):
            DataAnonymizer.anonymize_company(None)

    def test_filter_k_anonymous_sectors(self):
        """Test k-anonymity filtering."""
        companies = [
            {"id_hash": "a", "sector": "Tech", "opted_out": False},
            {"id_hash": "b", "sector": "Tech", "opted_out": False},
            {"id_hash": "c", "sector": "Tech", "opted_out": False},
            {"id_hash": "d", "sector": "Tech", "opted_out": False},
            {"id_hash": "e", "sector": "Tech", "opted_out": False},
            {"id_hash": "f", "sector": "Rare", "opted_out": False},  # Too few
        ]

        result = DataAnonymizer.filter_k_anonymous_sectors(companies)

        assert "Tech" in result
        assert "Rare" not in result
        assert len(result["Tech"]) == 5

    def test_filter_k_anonymous_sectors_excludes_opted_out(self):
        """Opted-out companies should be excluded from k-anonymity check."""
        companies = [
            {"id_hash": "a", "sector": "Tech", "opted_out": False},
            {"id_hash": "b", "sector": "Tech", "opted_out": False},
            {"id_hash": "c", "sector": "Tech", "opted_out": False},
            {"id_hash": "d", "sector": "Tech", "opted_out": False},
            {"id_hash": "e", "sector": "Tech", "opted_out": True},  # Opted out
        ]

        result = DataAnonymizer.filter_k_anonymous_sectors(companies)

        # Only 4 non-opted-out companies, so Tech should be excluded
        assert "Tech" not in result

    def test_validate_sector_k_anonymity(self):
        """Test k-anonymity validation."""
        # Meets threshold
        assert DataAnonymizer.validate_sector_k_anonymity([1, 2, 3, 4, 5]) is True
        assert DataAnonymizer.validate_sector_k_anonymity([1] * 10) is True

        # Below threshold
        assert DataAnonymizer.validate_sector_k_anonymity([1, 2, 3, 4]) is False
        assert DataAnonymizer.validate_sector_k_anonymity([]) is False
        assert DataAnonymizer.validate_sector_k_anonymity([1]) is False

    def test_strip_pii_from_pack_usage(self):
        """Test PII stripping from pack usage data."""
        usage_data = {
            "pack_id": "pack-123",
            "usage_count": 10,
            "company_name": "Acme Corp",
            "user_name": "John Doe",
            "user_email": "john@example.com",
            "department_name": "Engineering",
        }

        result = DataAnonymizer.strip_pii_from_pack_usage(usage_data)

        # Non-PII should remain
        assert result["pack_id"] == "pack-123"
        assert result["usage_count"] == 10

        # PII should be removed
        assert "company_name" not in result
        assert "user_name" not in result
        assert "user_email" not in result
        assert "department_name" not in result

    def test_k_anonymity_threshold_constant(self):
        """Verify k-anonymity threshold is set to 5."""
        assert DataAnonymizer.K_ANONYMITY_THRESHOLD == 5


class TestDataAnonymizerIntegration:
    """Integration-style tests for DataAnonymizer."""

    def test_full_anonymization_pipeline(self):
        """Test complete anonymization pipeline."""
        raw_companies = [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "TechCorp Inc",
                "sector": "Technology",
                "company_type": "enterprise",
                "employee_count": 500,
                "email": "admin@techcorp.com",
                "config": {},
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "name": "StartupXYZ",
                "sector": "Technology",
                "company_type": "mkb",
                "employee_count": 25,
                "email": "hello@startup.xyz",
                "config": {},
            },
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "name": "HealthFirst",
                "sector": "Healthcare",
                "company_type": "enterprise",
                "employee_count": 1000,
                "email": "contact@healthfirst.org",
                "config": {"opt_out_analytics": True},
            },
        ]

        # Step 1: Anonymize all companies
        anonymized = [DataAnonymizer.anonymize_company(c) for c in raw_companies]

        # Step 2: Filter k-anonymous sectors
        # Healthcare has only 1 company (and it's opted out)
        # Technology has 2 companies
        # Neither meets k=5 threshold
        k_anonymous = DataAnonymizer.filter_k_anonymous_sectors(anonymized)

        # Verify results
        assert len(anonymized) == 3

        # No sectors meet k-anonymity with only 2-3 companies
        assert len(k_anonymous) == 0

        # Verify all PII removed
        for company in anonymized:
            assert "name" not in company
            assert "email" not in company
            assert "id" not in company  # Replaced with id_hash
            assert "id_hash" in company

    def test_different_salts_produce_different_hashes(self):
        """Different salts should produce different hashes."""
        company_id = "test-company-123"

        original_salt = DataAnonymizer.COMPANY_HASH_SALT
        try:
            hash1 = DataAnonymizer.hash_company_id(company_id)

            # Change salt
            DataAnonymizer.COMPANY_HASH_SALT = "different_salt"
            hash2 = DataAnonymizer.hash_company_id(company_id)

            assert hash1 != hash2
        finally:
            # Restore original salt
            DataAnonymizer.COMPANY_HASH_SALT = original_salt
