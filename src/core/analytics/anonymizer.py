"""
Data Anonymization Pipeline for Cross-Company Analytics

Provides privacy-preserving data transformation for benchmarking:
- k-anonymity enforcement (minimum 5 companies per sector)
- Company ID hashing with salt (irreversible)
- PII stripping (no names, emails)
- Employee count bucketing

GDPR Compliance:
- Opt-out support via company config
- Data minimization (only aggregated metrics)
- Purpose limitation (benchmarking only)

Usage:
    from src.core.analytics.anonymizer import DataAnonymizer

    # Hash company ID
    hash_id = DataAnonymizer.hash_company_id(str(company.id))

    # Anonymize company data
    anon_data = DataAnonymizer.anonymize_company(company_dict)
"""

import hashlib
import os
from typing import Any



class DataAnonymizer:
    """
    Privacy-preserving data anonymizer for cross-company analytics.

    Implements k-anonymity guarantees and GDPR-compliant data handling.
    All company identifiers are hashed with a salt to prevent reversal.
    """

    # Salt for hashing - loaded from environment or uses fallback
    # In production, this MUST be set via ANALYTICS_HASH_SALT env var
    COMPANY_HASH_SALT: str = os.getenv(
        "ANALYTICS_HASH_SALT", "sanskritisetu_analytics_salt_change_in_production"
    )

    # Minimum companies per sector for k-anonymity (k=5)
    K_ANONYMITY_THRESHOLD: int = 5

    @classmethod
    def hash_company_id(cls, company_id: str) -> str:
        """
        Hash company ID with salt to create irreversible identifier.

        Uses SHA-256 with a salt to ensure:
        - Same company always produces same hash (for trend analysis)
        - Hash cannot be reversed to reveal company ID
        - Different salts produce different hashes (security)

        Args:
            company_id: Original company UUID as string

        Returns:
            16-character hexadecimal hash string

        Example:
            >>> DataAnonymizer.hash_company_id("550e8400-e29b-41d4-a716-446655440000")
            "a1b2c3d4e5f67890"
        """
        if not company_id:
            raise ValueError("company_id cannot be empty")

        hash_input = f"{company_id}:{cls.COMPANY_HASH_SALT}"
        full_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        return full_hash[:16]

    @classmethod
    def anonymize_company(cls, company: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Anonymize company data for benchmarking.

        Strips all PII and returns only non-identifying attributes:
        - Hashed ID (not reversible)
        - Sector (for grouping)
        - Company type (for categorization)
        - Employee count bucket (not exact count)

        Args:
            company: Dictionary with company data including:
                - id: Company UUID
                - sector: Industry sector
                - company_type: mkb, zzp, or enterprise
                - employee_count: Number of employees (optional)
                - config: Company configuration dict (optional)

        Returns:
            Anonymized dictionary with only benchmarking-relevant fields

        Example:
            >>> company = {
            ...     "id": "550e8400-e29b-41d4-a716-446655440000",
            ...     "name": "Acme Corp",  # Will be stripped
            ...     "sector": "Technology",
            ...     "company_type": "mkb",
            ...     "employee_count": 45,
            ...     "email": "admin@acme.com",  # Will be stripped
            ... }
            >>> DataAnonymizer.anonymize_company(company)
            {
                "id_hash": "a1b2c3d4e5f67890",
                "sector": "Technology",
                "company_type": "mkb",
                "employee_count_bucket": "10-49",
                "opted_out": False
            }
        """
        if not company or not isinstance(company, dict):
            raise ValueError("company must be a non-empty dictionary")

        if "id" not in company:
            raise ValueError("company must have 'id' field")

        # Get company config for opt-out check
        config = company.get("config", {})
        opted_out = config.get("opt_out_analytics", False) if isinstance(config, dict) else False

        return {
            "id_hash": cls.hash_company_id(str(company["id"])),
            "sector": company.get("sector"),
            "company_type": company.get("company_type"),
            "employee_count_bucket": cls._bucket_employees(company.get("employee_count", 0)),
            "opted_out": opted_out,
        }

    @staticmethod
    def _bucket_employees(count: int) -> str:
        """
        Bucket employee count into ranges for privacy.

        Prevents identification via exact employee counts while
        still allowing meaningful size-based comparisons.

        Buckets:
            - "1-9": Micro companies
            - "10-49": Small companies
            - "50-249": Medium companies
            - "250+": Large companies

        Args:
            count: Exact employee count

        Returns:
            String bucket identifier

        Example:
            >>> DataAnonymizer._bucket_employees(5)
            "1-9"
            >>> DataAnonymizer._bucket_employees(150)
            "50-249"
        """
        if not isinstance(count, (int, float)):
            count = 0

        count = int(count)

        if count < 10:
            return "1-9"
        elif count < 50:
            return "10-49"
        elif count < 250:
            return "50-249"
        else:
            return "250+"

    @classmethod
    def filter_k_anonymous_sectors(
        cls, companies: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
        """
        Filter companies to only include sectors with k-anonymity.

        Groups companies by sector and only returns sectors with
        at least K_ANONYMITY_THRESHOLD companies.

        Args:
            companies: List of (already anonymized) company dictionaries

        Returns:
            Dictionary mapping sector name to list of companies,
            only including sectors meeting k-anonymity threshold

        Example:
            >>> companies = [
            ...     {"id_hash": "abc", "sector": "Tech"},
            ...     {"id_hash": "def", "sector": "Tech"},
            ...     {"id_hash": "ghi", "sector": "Tech"},
            ...     {"id_hash": "jkl", "sector": "Tech"},
            ...     {"id_hash": "mno", "sector": "Tech"},
            ...     {"id_hash": "pqr", "sector": "Rare"},  # Too few
            ... ]
            >>> DataAnonymizer.filter_k_anonymous_sectors(companies)
            {"Tech": [{...}, {...}, {...}, {...}, {...}]}
            # "Rare" sector excluded (only 1 company < k=5)
        """
        # Group by sector
        sector_groups: dict[str, list[dict[str, Any]]] = {}  # TODO(TYPE): replace Any with concrete type
        for company in companies:
            sector = company.get("sector")
            if not sector:
                continue

            # Skip opted-out companies
            if company.get("opted_out", False):
                continue

            if sector not in sector_groups:
                sector_groups[sector] = []
            sector_groups[sector].append(company)

        # Filter to only k-anonymous sectors
        return {
            sector: companies
            for sector, companies in sector_groups.items()
            if len(companies) >= cls.K_ANONYMITY_THRESHOLD
        }

    @classmethod
    def validate_sector_k_anonymity(cls, sector_companies: list[Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """
        Check if a sector meets k-anonymity requirements.

        Args:
            sector_companies: List of companies in the sector

        Returns:
            True if sector has enough companies for anonymity
        """
        if not sector_companies:
            return False
        return len(sector_companies) >= cls.K_ANONYMITY_THRESHOLD

    @classmethod
    def strip_pii_from_pack_usage(cls, usage_data: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Remove all PII from pack usage data.

        Ensures only aggregated, non-identifying metrics remain.

        Args:
            usage_data: Raw pack usage data dictionary

        Returns:
            Usage data with all PII fields removed
        """
        # Fields that could identify individuals or companies
        pii_fields = {
            "company_name",
            "user_name",
            "user_email",
            "created_by_name",
            "department_name",
            "contact_person",
            "phone",
            "address",
        }

        return {k: v for k, v in usage_data.items() if k not in pii_fields}


# Module exports
__all__ = ["DataAnonymizer"]
