"""Department to agent type mappings.

This module provides mappings between company departments and the types of
AI agents that are relevant for each department. It is used during onboarding
to suggest appropriate agents based on the departments a company defines.

Usage:
    from src.core.company.agent_mappings import get_agents_for_department

    agents = get_agents_for_department("Engineering")
    # Returns: ["Code Reviewer", "Tech Lead", "DevOps Specialist", ...]

The mapping covers departments across multiple sectors:
- Technology (Engineering, Product, DevOps, IT)
- Sales & Marketing (Sales, Marketing, Business Development)
- Consultancy (Consulting, Strategy)
- Hospitality/Horeca (Keuken, Bediening, Bar)
- Retail (Winkel, Webshop, Voorraad, etc.)
- Healthcare (Patientenzorg, Kwaliteit, Compliance)
- Finance (Advisering, Risk, Front Office)
- Generic departments (Management, HR, Finance, Operations, etc.)

Unknown departments return a "Generalist" fallback.
"""


# Mapping of department names to relevant agent types
DEPARTMENT_AGENTS: dict[str, list[str]] = {
    # Technology departments
    "Engineering": [
        "Code Reviewer",
        "Tech Lead",
        "DevOps Specialist",
        "Security Engineer",
    ],
    "Product": [
        "Product Manager",
        "UX Researcher",
        "Business Analyst",
    ],
    "DevOps": [
        "Infrastructure Engineer",
        "CI_CD Specialist",
        "Cloud Architect",
    ],
    "IT": [
        "System Administrator",
        "Network Engineer",
        "IT Support",
    ],
    # Sales & Marketing
    "Sales": [
        "Sales Development Rep",
        "Account Executive",
        "Sales Manager",
    ],
    "Marketing": [
        "Content Creator",
        "SEO Specialist",
        "Marketing Manager",
    ],
    "Business Development": [
        "BD Rep",
        "Partnerships Manager",
        "Market Analyst",
    ],
    # Consultancy
    "Consulting": [
        "Junior Consultant",
        "Senior Consultant",
        "Principal Consultant",
    ],
    "Strategy": [
        "Strategy Analyst",
        "Management Consultant",
        "Industry Expert",
    ],
    # Horeca (Hospitality)
    "Keuken": [
        "Sous Chef",
        "Line Cook",
        "Pastry Chef",
    ],
    "Bediening": [
        "Waiter",
        "Host",
        "Shift Supervisor",
    ],
    "Bar": [
        "Bartender",
        "Barista",
        "Mixologist",
    ],
    # Retail
    "Winkel": [
        "Store Associate",
        "Visual Merchandiser",
        "Store Manager",
    ],
    "Webshop": [
        "E-commerce Specialist",
        "Digital Marketer",
    ],
    "Voorraad": [
        "Inventory Clerk",
        "Warehouse Manager",
    ],
    "Retail Operations": [
        "Operations Analyst",
        "Store Operations Manager",
    ],
    "E-commerce": [
        "Online Marketing Specialist",
        "Conversion Optimizer",
    ],
    "Supply Chain": [
        "Supply Chain Analyst",
        "Procurement Specialist",
    ],
    "Klantenservice": [
        "Customer Support",
        "Customer Success Manager",
    ],
    # Healthcare
    "Patientenzorg": [
        "Care Coordinator",
        "Medical Assistant",
    ],
    "Kwaliteit": [
        "Quality Inspector",
        "Compliance Auditor",
    ],
    "Compliance": [
        "Compliance Officer",
        "Privacy Officer",
    ],
    # Finance
    "Advisering": [
        "Financial Advisor",
        "Investment Analyst",
    ],
    "Risk": [
        "Risk Analyst",
        "Credit Analyst",
    ],
    "Front Office": [
        "Relationship Manager",
        "Trader",
    ],
    # Generic departments (fallback)
    "Management": [
        "Executive Assistant",
        "Strategy Analyst",
    ],
    "Executive": [
        "Chief of Staff",
        "Strategy Advisor",
    ],
    "Directie": [
        "Chief of Staff",
        "Strategy Advisor",
    ],
    "Administratie": [
        "Bookkeeper",
        "Office Manager",
    ],
    "Finance": [
        "Accountant",
        "Financial Controller",
    ],
    "HRM": [
        "Recruiter",
        "HR Business Partner",
    ],
    "HR": [
        "Recruiter",
        "HR Generalist",
    ],
    "Operations": [
        "Operations Analyst",
        "Process Manager",
    ],
    "Inkoop": [
        "Procurement Assistant",
        "Vendor Manager",
    ],
    "Legal": [
        "Legal Counsel",
        "Contract Manager",
    ],
    "Ondernemer": [
        "Generalist",
    ],
    "Consultant": [
        "Generalist Consultant",
    ],
    "Zorgverlener": [
        "Care Assistant",
    ],
    "Adviseur": [
        "Financial Planner",
    ],
    "Freelancer": [
        "Generalist",
    ],
    "Zelfstandig": [
        "Generalist",
    ],
}


def get_agents_for_department(department_name: str) -> list[str]:
    """Get agent types for a department.

    Args:
        department_name: Name of the department (case-insensitive)

    Returns:
        List of agent types relevant to the department.
        Returns ["Generalist"] if the department is not found.

    Examples:
        >>> get_agents_for_department("Engineering")
        ['Code Reviewer', 'Tech Lead', 'DevOps Specialist', 'Security Engineer']

        >>> get_agents_for_department("UnknownDept")
        ['Generalist']
    """
    # Normalize department name for case-insensitive lookup
    normalized_name = department_name.strip()

    # Direct lookup
    if normalized_name in DEPARTMENT_AGENTS:
        return DEPARTMENT_AGENTS[normalized_name]

    # Case-insensitive lookup
    for dept, agents in DEPARTMENT_AGENTS.items():
        if dept.lower() == normalized_name.lower():
            return agents

    # Fallback for unknown departments
    return ["Generalist"]
