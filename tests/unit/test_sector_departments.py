"""Tests for sector department registry."""

import pytest


class TestSectorDepartments:
    """User behavior tests for sector department configurations."""

    def test_user_gets_technology_departments_when_instantiating_mkb_template(self):
        """User instantiating Technologie MKB template sees proper departments."""
        from src.core.company.sector_departments import get_departments

        depts = get_departments("Technologie", "mkb")

        # User sees 5 departments
        assert len(depts) == 5

        # User sees Engineering with CTO board role
        engineering = next(d for d in depts if d["name"] == "Engineering")
        assert engineering["board_role"] == "CTO"

        # User sees 40k budget for Engineering
        assert engineering["budget_monthly_tokens"] == 40000

    def test_user_gets_horeca_departments_when_instantiating_enterprise_template(self):
        """User instantiating Horeca Enterprise template sees 8 departments."""
        from src.core.company.sector_departments import get_departments

        depts = get_departments("Horeca", "enterprise")

        assert len(depts) == 8
        assert any(d["name"] == "Keuken" for d in depts)
        keuken = next(d for d in depts if d["name"] == "Keuken")
        assert keuken["board_role"] == "Executive Chef"

    def test_user_gets_empty_result_for_unknown_sector(self):
        """User selecting unknown sector gets no departments."""
        from src.core.company.sector_departments import get_departments

        result = get_departments("UnknownSector", "mkb")
        assert result is None

    def test_user_gets_empty_list_for_unknown_company_type(self):
        """User selecting unknown company type gets empty list."""
        from src.core.company.sector_departments import get_departments

        result = get_departments("Technologie", "unknown_type")
        assert result == []


class TestIsGenericTemplate:
    """Tests for is_generic_template() function."""

    def test_generic_template_with_management_operations_admin(self):
        """Template with only generic names is generic."""
        from src.core.company.sector_departments import is_generic_template

        generic = [
            {"name": "Management"},
            {"name": "Operations"},
            {"name": "Administratie"},
        ]
        assert is_generic_template(generic) is True

    def test_non_generic_template_with_engineering(self):
        """Template with any sector-specific name is not generic."""
        from src.core.company.sector_departments import is_generic_template

        specific = [{"name": "Management"}, {"name": "Engineering"}]
        assert is_generic_template(specific) is False

    def test_mixed_template_with_management_and_keuken(self):
        """Template mixing generic and sector-specific is not generic."""
        from src.core.company.sector_departments import is_generic_template

        mixed = [{"name": "Management"}, {"name": "Keuken"}]
        assert is_generic_template(mixed) is False

    def test_empty_template_is_generic(self):
        """Empty template is considered generic."""
        from src.core.company.sector_departments import is_generic_template

        assert is_generic_template([]) is True

    def test_template_with_directie_is_generic(self):
        """Template with generic names like Directie is generic."""
        from src.core.company.sector_departments import is_generic_template

        generic = [{"name": "Directie"}, {"name": "HR"}]
        assert is_generic_template(generic) is True

    def test_template_with_zelfstandig_is_generic(self):
        """ZZP template with 'Zelfstandig' is generic."""
        from src.core.company.sector_departments import is_generic_template

        generic = [{"name": "Zelfstandig"}]
        assert is_generic_template(generic) is True

    def test_template_with_freelancer_is_generic(self):
        """ZZP template with 'Freelancer' is generic."""
        from src.core.company.sector_departments import is_generic_template

        generic = [{"name": "Freelancer"}]
        assert is_generic_template(generic) is True

    def test_template_with_backoffice_is_generic(self):
        """Template with 'Backoffice' is generic."""
        from src.core.company.sector_departments import is_generic_template

        generic = [{"name": "Backoffice"}]
        assert is_generic_template(generic) is True


class TestAllSectorsAndTypes:
    """Comprehensive tests for all sector/type combinations."""

    def test_all_six_sectors_exist(self):
        """All 6 sectors have configurations."""
        from src.core.company.sector_departments import SECTOR_DEPARTMENTS, get_departments

        expected_sectors = [
            "Technologie",
            "Consultancy",
            "Horeca",
            "Retail",
            "Gezondheidszorg",
            "Financiele Dienstverlening",
        ]

        for sector in expected_sectors:
            assert sector in SECTOR_DEPARTMENTS, f"Missing sector: {sector}"
            result = get_departments(sector, "mkb")
            assert result is not None, f"Sector {sector} returned None"
            assert len(result) > 0, f"Sector {sector} has no departments"

    def test_all_three_company_types_exist_per_sector(self):
        """Each sector has zzp, mkb, and enterprise configurations."""
        from src.core.company.sector_departments import SECTOR_DEPARTMENTS, get_departments

        company_types = ["zzp", "mkb", "enterprise"]

        for sector, configs in SECTOR_DEPARTMENTS.items():
            for company_type in company_types:
                assert company_type in configs, f"Missing {company_type} for {sector}"
                result = get_departments(sector, company_type)
                assert isinstance(result, list), f"{sector}/{company_type} not a list"
                assert len(result) > 0, f"{sector}/{company_type} is empty"

    def test_budgets_follow_philosophy(self):
        """Budgets follow C-Level > Core Operations > Support pattern."""
        from src.core.company.sector_departments import get_departments

        # Test Technology enterprise
        depts = get_departments("Technologie", "enterprise")
        cto = next(d for d in depts if d["board_role"] == "CTO")
        engineering = next(d for d in depts if d["name"] == "Engineering")
        hr = next(d for d in depts if d["name"] == "HR")

        assert cto["budget_monthly_tokens"] >= engineering["budget_monthly_tokens"]
        assert engineering["budget_monthly_tokens"] >= hr["budget_monthly_tokens"]

    def test_case_insensitive_sector_lookup(self):
        """Sector lookup is case insensitive."""
        from src.core.company.sector_departments import get_departments

        result_lower = get_departments("technologie", "mkb")
        result_upper = get_departments("TECHNOLOGIE", "mkb")
        result_mixed = get_departments("Technologie", "mkb")

        assert result_lower == result_mixed
        assert result_upper == result_mixed


class TestDepartmentStructure:
    """Tests for department structure validation."""

    def test_department_has_required_fields(self):
        """Each department has name, board_role, and budget_monthly_tokens."""
        from src.core.company.sector_departments import SECTOR_DEPARTMENTS

        for sector, configs in SECTOR_DEPARTMENTS.items():
            for company_type, departments in configs.items():
                for dept in departments:
                    assert "name" in dept, f"Missing name in {sector}/{company_type}"
                    assert "board_role" in dept, f"Missing board_role in {sector}/{company_type}"
                    assert (
                        "budget_monthly_tokens" in dept
                    ), f"Missing budget in {sector}/{company_type}"
                    assert isinstance(
                        dept["budget_monthly_tokens"], int
                    ), f"Budget not int in {sector}/{company_type}"
                    assert (
                        dept["budget_monthly_tokens"] > 0
                    ), f"Budget <= 0 in {sector}/{company_type}"
