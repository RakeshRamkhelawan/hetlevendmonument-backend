"""Sector department registry for template enrichment.

This module provides department configurations for different sectors and company types,
enabling sector-aware template instantiation.

Budget Philosophy:
- C-Level (CEO/CTO/CFO): 80k-100k (enterprise), 40k-60k (mkb), 15k-25k (zzp)
- Core Operations: 40k-70k (enterprise), 30k-40k (mkb), 15k-20k (zzp)
- Support: 15k-50k (enterprise), 15k-25k (mkb), 15k (zzp)

The budgets are expressed in monthly tokens allocated to each department.
"""

from typing import Any, Optional

# Generic department names that indicate a non-sector-specific template
GENERIC_DEPARTMENT_NAMES = frozenset(
    [
        "management",
        "algemeen management",
        "operations",
        "administratie",
        "zelfstandig",
        "freelancer",
        "directie",
        "executive",
        "backoffice",
        "hr",  # HR is generic across sectors
        "finance",  # Finance function exists in all sectors
        "sales",  # Sales exists in most sectors
        "marketing",  # Marketing is generic
        "admin",  # Admin is generic
        "general",  # General management
        "bedrijf",  # Generic Dutch term
    ]
)

# Sector-specific department configurations
# Each sector has 3 company types: zzp, mkb, enterprise
SECTOR_DEPARTMENTS = {
    "Technologie": {
        "zzp": [
            {"name": "Zelfstandig", "board_role": "Founder", "budget_monthly_tokens": 20000},
            {
                "name": "Development",
                "board_role": "Tech Lead",
                "budget_monthly_tokens": 15000,
            },
            {"name": "Operations", "board_role": "COO", "budget_monthly_tokens": 15000},
        ],
        "mkb": [
            {"name": "Engineering", "board_role": "CTO", "budget_monthly_tokens": 40000},
            {"name": "Product", "board_role": "CPO", "budget_monthly_tokens": 35000},
            {"name": "Sales", "board_role": "VP Sales", "budget_monthly_tokens": 30000},
            {"name": "HR", "board_role": "HR Manager", "budget_monthly_tokens": 20000},
            {"name": "Finance", "board_role": "CFO", "budget_monthly_tokens": 40000},
        ],
        "enterprise": [
            {"name": "Engineering", "board_role": "CTO", "budget_monthly_tokens": 100000},
            {"name": "Product", "board_role": "CPO", "budget_monthly_tokens": 80000},
            {"name": "DevOps", "board_role": "VP Infrastructure", "budget_monthly_tokens": 70000},
            {"name": "Security", "board_role": "CISO", "budget_monthly_tokens": 80000},
            {
                "name": "Data Science",
                "board_role": "Chief Data Officer",
                "budget_monthly_tokens": 70000,
            },
            {
                "name": "Sales",
                "board_role": "Chief Revenue Officer",
                "budget_monthly_tokens": 60000,
            },
            {"name": "HR", "board_role": "CHRO", "budget_monthly_tokens": 50000},
            {"name": "Finance", "board_role": "CFO", "budget_monthly_tokens": 100000},
            {"name": "Legal", "board_role": "General Counsel", "budget_monthly_tokens": 60000},
        ],
    },
    "Consultancy": {
        "zzp": [
            {
                "name": "Zelfstandig Consultant",
                "board_role": "Founder",
                "budget_monthly_tokens": 20000,
            },
            {"name": "Project Delivery", "board_role": "PM", "budget_monthly_tokens": 15000},
            {"name": "Administratie", "board_role": "COO", "budget_monthly_tokens": 15000},
        ],
        "mkb": [
            {
                "name": "Consulting",
                "board_role": "Managing Partner",
                "budget_monthly_tokens": 50000,
            },
            {
                "name": "Project Management",
                "board_role": "Delivery Director",
                "budget_monthly_tokens": 35000,
            },
            {
                "name": "Business Development",
                "board_role": "BD Director",
                "budget_monthly_tokens": 40000,
            },
            {"name": "HR", "board_role": "HR Manager", "budget_monthly_tokens": 20000},
            {"name": "Finance", "board_role": "CFO", "budget_monthly_tokens": 40000},
        ],
        "enterprise": [
            {
                "name": "Strategy Consulting",
                "board_role": "Managing Partner",
                "budget_monthly_tokens": 100000,
            },
            {
                "name": "Implementation",
                "board_role": "Delivery Partner",
                "budget_monthly_tokens": 80000,
            },
            {
                "name": "Technology Advisory",
                "board_role": "Tech Partner",
                "budget_monthly_tokens": 80000,
            },
            {
                "name": "Risk Advisory",
                "board_role": "Risk Partner",
                "budget_monthly_tokens": 80000,
            },
            {"name": "HR Advisory", "board_role": "HR Partner", "budget_monthly_tokens": 60000},
            {"name": "Finance", "board_role": "CFO", "budget_monthly_tokens": 100000},
            {"name": "BD & Marketing", "board_role": "CMO", "budget_monthly_tokens": 60000},
            {"name": "Operations", "board_role": "COO", "budget_monthly_tokens": 80000},
        ],
    },
    "Horeca": {
        "zzp": [
            {
                "name": "Zelfstandig Horeca",
                "board_role": "Eigenaar",
                "budget_monthly_tokens": 20000,
            },
            {"name": "Keuken", "board_role": "Chef", "budget_monthly_tokens": 15000},
            {"name": "Bediening", "board_role": "Manager", "budget_monthly_tokens": 15000},
        ],
        "mkb": [
            {"name": "Keuken", "board_role": "Executive Chef", "budget_monthly_tokens": 40000},
            {
                "name": "Bediening",
                "board_role": "Restaurant Manager",
                "budget_monthly_tokens": 30000,
            },
            {"name": "Bar", "board_role": "Bar Manager", "budget_monthly_tokens": 25000},
            {"name": "Events", "board_role": "Event Manager", "budget_monthly_tokens": 30000},
            {"name": "HR", "board_role": "HR Manager", "budget_monthly_tokens": 20000},
            {"name": "Finance", "board_role": "CFO", "budget_monthly_tokens": 35000},
        ],
        "enterprise": [
            {
                "name": "Keuken",
                "board_role": "Executive Chef",
                "budget_monthly_tokens": 100000,
            },
            {
                "name": "F&B Operations",
                "board_role": "F&B Director",
                "budget_monthly_tokens": 80000,
            },
            {
                "name": "Events & Banqueting",
                "board_role": "Events Director",
                "budget_monthly_tokens": 60000,
            },
            {
                "name": "Front Office",
                "board_role": "Front Office Manager",
                "budget_monthly_tokens": 50000,
            },
            {
                "name": "Housekeeping",
                "board_role": "Executive Housekeeper",
                "budget_monthly_tokens": 40000,
            },
            {"name": "HR", "board_role": "HR Director", "budget_monthly_tokens": 60000},
            {"name": "Finance", "board_role": "CFO", "budget_monthly_tokens": 100000},
            {
                "name": "Marketing",
                "board_role": "Marketing Director",
                "budget_monthly_tokens": 60000,
            },
        ],
    },
    "Retail": {
        "zzp": [
            {
                "name": "Zelfstandig Retail",
                "board_role": "Eigenaar",
                "budget_monthly_tokens": 20000,
            },
            {"name": "Verkoop", "board_role": "Manager", "budget_monthly_tokens": 15000},
            {"name": "Administratie", "board_role": "COO", "budget_monthly_tokens": 15000},
        ],
        "mkb": [
            {
                "name": "Winkeloperatie",
                "board_role": "Store Manager",
                "budget_monthly_tokens": 35000,
            },
            {"name": "Inkoop", "board_role": "Purchasing Manager", "budget_monthly_tokens": 30000},
            {
                "name": "Customer Service",
                "board_role": "Service Manager",
                "budget_monthly_tokens": 25000,
            },
            {
                "name": "Marketing",
                "board_role": "Marketing Manager",
                "budget_monthly_tokens": 30000,
            },
            {"name": "HR", "board_role": "HR Manager", "budget_monthly_tokens": 20000},
            {"name": "Finance", "board_role": "CFO", "budget_monthly_tokens": 35000},
        ],
        "enterprise": [
            {
                "name": "Retail Operations",
                "board_role": "COO Retail",
                "budget_monthly_tokens": 100000,
            },
            {
                "name": "Merchandising",
                "board_role": "Merchandising Director",
                "budget_monthly_tokens": 80000,
            },
            {
                "name": "E-Commerce",
                "board_role": "Digital Director",
                "budget_monthly_tokens": 80000,
            },
            {
                "name": "Supply Chain",
                "board_role": "Supply Chain Director",
                "budget_monthly_tokens": 80000,
            },
            {"name": "Marketing", "board_role": "CMO", "budget_monthly_tokens": 80000},
            {"name": "HR", "board_role": "CHRO", "budget_monthly_tokens": 60000},
            {"name": "Finance", "board_role": "CFO", "budget_monthly_tokens": 100000},
            {
                "name": "Real Estate",
                "board_role": "Property Director",
                "budget_monthly_tokens": 60000,
            },
        ],
    },
    "Gezondheidszorg": {
        "zzp": [
            {
                "name": "Zelfstandig Zorgverlener",
                "board_role": "Eigenaar",
                "budget_monthly_tokens": 20000,
            },
            {
                "name": "Patientenzorg",
                "board_role": "Zorgmanager",
                "budget_monthly_tokens": 15000,
            },
            {"name": "Administratie", "board_role": "COO", "budget_monthly_tokens": 15000},
        ],
        "mkb": [
            {
                "name": "Medische Zorg",
                "board_role": "Medisch Directeur",
                "budget_monthly_tokens": 50000,
            },
            {
                "name": "Verpleging",
                "board_role": "Hoofd Verpleging",
                "budget_monthly_tokens": 35000,
            },
            {
                "name": "Paramedisch",
                "board_role": "Paramedisch Manager",
                "budget_monthly_tokens": 30000,
            },
            {"name": "HR", "board_role": "HR Manager", "budget_monthly_tokens": 20000},
            {
                "name": "Kwaliteit",
                "board_role": "Kwaliteitsmanager",
                "budget_monthly_tokens": 25000,
            },
            {"name": "Finance", "board_role": "CFO", "budget_monthly_tokens": 40000},
        ],
        "enterprise": [
            {
                "name": "Klinische Zorg",
                "board_role": "Medisch Directeur",
                "budget_monthly_tokens": 100000,
            },
            {
                "name": "Verpleging & Zorg",
                "board_role": "Directeur Verpleging",
                "budget_monthly_tokens": 80000,
            },
            {
                "name": "Research & Development",
                "board_role": "R&D Director",
                "budget_monthly_tokens": 70000,
            },
            {
                "name": "Kwaliteit & Compliance",
                "board_role": "CQO",
                "budget_monthly_tokens": 80000,
            },
            {"name": "HR", "board_role": "CHRO", "budget_monthly_tokens": 60000},
            {"name": "Finance", "board_role": "CFO", "budget_monthly_tokens": 100000},
            {"name": "IT & Digital", "board_role": "CDO", "budget_monthly_tokens": 70000},
            {
                "name": "Facilitair",
                "board_role": "Facilities Director",
                "budget_monthly_tokens": 50000,
            },
        ],
    },
    "Financiele Dienstverlening": {
        "zzp": [
            {
                "name": "Zelfstandig Adviseur",
                "board_role": "Eigenaar",
                "budget_monthly_tokens": 20000,
            },
            {
                "name": "Advisory",
                "board_role": "Principal",
                "budget_monthly_tokens": 15000,
            },
            {"name": "Administratie", "board_role": "COO", "budget_monthly_tokens": 15000},
        ],
        "mkb": [
            {
                "name": "Wealth Management",
                "board_role": "Managing Director",
                "budget_monthly_tokens": 50000,
            },
            {"name": "Advisory", "board_role": "Advisory Director", "budget_monthly_tokens": 40000},
            {
                "name": "Compliance",
                "board_role": "Compliance Officer",
                "budget_monthly_tokens": 35000,
            },
            {"name": "HR", "board_role": "HR Manager", "budget_monthly_tokens": 20000},
            {"name": "Finance", "board_role": "CFO", "budget_monthly_tokens": 40000},
        ],
        "enterprise": [
            {
                "name": "Investment Banking",
                "board_role": "Managing Director",
                "budget_monthly_tokens": 100000,
            },
            {
                "name": "Asset Management",
                "board_role": "CIO",
                "budget_monthly_tokens": 100000,
            },
            {
                "name": "Risk Management",
                "board_role": "CRO",
                "budget_monthly_tokens": 100000,
            },
            {
                "name": "Compliance",
                "board_role": "CCO",
                "budget_monthly_tokens": 80000,
            },
            {"name": "Trading", "board_role": "Head of Trading", "budget_monthly_tokens": 80000},
            {"name": "HR", "board_role": "CHRO", "budget_monthly_tokens": 60000},
            {"name": "Finance", "board_role": "CFO", "budget_monthly_tokens": 100000},
            {"name": "Technology", "board_role": "CTO", "budget_monthly_tokens": 80000},
        ],
    },
}


def get_departments(sector: str, company_type: str) -> list[dict[str, Any]] | None:  # TODO(TYPE): replace Any with concrete type
    """Get department configuration for a sector and company type.

    Args:
        sector: The sector name (e.g., "Technologie", "Horeca")
        company_type: The company type ("zzp", "mkb", or "enterprise")

    Returns:
        List of department dictionaries with name, board_role, and budget_monthly_tokens,
        or None if sector not found, or empty list if company_type not found.

    Example:
        >>> depts = get_departments("Technologie", "mkb")
        >>> len(depts)
        5
        >>> depts[0]["name"]
        'Engineering'
    """
    # Case-insensitive sector lookup
    sector_normalized = sector.strip()
    if sector_normalized not in SECTOR_DEPARTMENTS:
        # Try case-insensitive match
        for key in SECTOR_DEPARTMENTS:
            if key.lower() == sector_normalized.lower():
                sector_normalized = key
                break
        else:
            return None

    sector_config = SECTOR_DEPARTMENTS[sector_normalized]

    # Return empty list if company_type not found
    if company_type not in sector_config:
        return []

    # Return a copy to prevent external mutation
    return [dict(dept) for dept in sector_config[company_type]]


def is_generic_template(departments: list[dict[str, Any]]) -> bool:  # TODO(TYPE): replace Any with concrete type
    """Check if a template contains only generic department names.

    A template is considered generic if ALL departments have names that are
    in the generic list. If ANY department has a sector-specific name
    (e.g., "Engineering", "Keuken"), the template is not generic.

    Args:
        departments: List of department dictionaries with "name" key

    Returns:
        True if all departments are generic, False if any is sector-specific.
        Empty list returns True.

    Example:
        >>> is_generic_template([{"name": "Management"}, {"name": "HR"}])
        True
        >>> is_generic_template([{"name": "Management"}, {"name": "Engineering"}])
        False
    """
    if not departments:
        return True

    for dept in departments:
        name = dept.get("name", "").strip().lower()
        if name not in GENERIC_DEPARTMENT_NAMES:
            return False

    return True
