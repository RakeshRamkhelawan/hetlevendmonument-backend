"""Seed templates for TemplateService.

Provides 10 starter templates for immediate use:
- 3x MKB (Midden- en Kleinbedrijf)
- 3x ZZP (Freelancers)
- 4x Enterprise

Templates include realistic departments, goals, and configurations
matching common business scenarios.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.company.models import CompanyTemplate
from src.core.database.tenant_query_filter import TenantFilterBypass

# 10 Starter Templates
SEED_TEMPLATES: list[dict[str, Any]] = [  # TODO(TYPE): replace Any with concrete type
    # ========== MKB (Small/Medium Business) ==========
    {
        "name": "Tech Startup MKB",
        "company_type": "mkb",
        "sector": "Technologie",
        "description": "Ideaal voor technologie startups en scale-ups met agile teams",
        "template_definition": {
            "mission": "Innoveren en schalen met focus op productontwikkeling",
            "departments": [
                {
                    "name": "Development",
                    "board_role": "CTO",
                    "budget_monthly_tokens": 5000,
                    "domain_pack_ids": ["pack_dev_001", "pack_agile_001"],
                },
                {
                    "name": "Sales",
                    "board_role": "Sales",
                    "budget_monthly_tokens": 3000,
                    "domain_pack_ids": ["pack_sales_001"],
                },
                {
                    "name": "Marketing",
                    "board_role": "CMO",
                    "budget_monthly_tokens": 2000,
                    "domain_pack_ids": ["pack_marketing_001"],
                },
            ],
            "goals": [
                {
                    "goal_type": "strategic",
                    "title": "MVP Lanceren",
                    "description": "Minimal Viable Product live binnen 3 maanden",
                    "department_name": "Development",
                    "kpis": {"features_completed": 10, "bugs_critical": 0},
                },
                {
                    "goal_type": "operational",
                    "title": "Eerste 10 Klanten",
                    "description": "Acquisitie van eerste betaalde klanten",
                    "department_name": "Sales",
                    "kpis": {"leads_converted": 10, "revenue_eur": 10000},
                },
            ],
            "board_role_config": {
                "budget": "CFO",
                "agent_hire": "CTO",
                "agent_management": "CTO",
                "default": "CEO",
                "thresholds": {"auto_approve_below": "LOW"},
            },
        },
    },
    {
        "name": "Horeca MKB",
        "company_type": "mkb",
        "sector": "Horeca",
        "description": "Restaurant of cafe met focus op gastvrijheid en efficientie",
        "template_definition": {
            "mission": "Uitstekende gastervaring met efficiente bedrijfsvoering",
            "departments": [
                {
                    "name": "Keuken",
                    "board_role": "Chef",
                    "budget_monthly_tokens": 2000,
                    "domain_pack_ids": ["pack_kitchen_001"],
                },
                {
                    "name": "Bediening",
                    "board_role": "Manager",
                    "budget_monthly_tokens": 1500,
                    "domain_pack_ids": ["pack_service_001"],
                },
                {
                    "name": "Inkoop",
                    "board_role": "Manager",
                    "budget_monthly_tokens": 1000,
                    "domain_pack_ids": ["pack_procurement_001"],
                },
            ],
            "goals": [
                {
                    "goal_type": "operational",
                    "title": "4.5+ Beoordeling",
                    "description": "Google Reviews gemiddelde boven 4.5",
                    "department_name": "Bediening",
                    "kpis": {"avg_rating": 4.5, "review_count": 50},
                },
                {
                    "goal_type": "operational",
                    "title": "Voedselverspilling < 5%",
                    "description": "Minimaliseer verspilling door slim inkoopbeheer",
                    "department_name": "Keuken",
                    "kpis": {"waste_percentage": 5, "cost_per_meal": 3.5},
                },
            ],
            "board_role_config": {
                "budget": "Eigenaar",
                "agent_hire": "Manager",
                "default": "Eigenaar",
                "thresholds": {"auto_approve_below": "MEDIUM"},
            },
        },
    },
    {
        "name": "Retail Winkel MKB",
        "company_type": "mkb",
        "sector": "Retail",
        "description": "Fysieke winkel met webshop integratie",
        "template_definition": {
            "mission": "Klanten een naadloze winkelervaring bieden online en offline",
            "departments": [
                {
                    "name": "Winkel",
                    "board_role": "Manager",
                    "budget_monthly_tokens": 2000,
                    "domain_pack_ids": ["pack_retail_001"],
                },
                {
                    "name": "Webshop",
                    "board_role": "E-Commerce",
                    "budget_monthly_tokens": 2500,
                    "domain_pack_ids": ["pack_ecommerce_001", "pack_marketing_001"],
                },
                {
                    "name": "Voorraad",
                    "board_role": "Manager",
                    "budget_monthly_tokens": 1500,
                    "domain_pack_ids": ["pack_inventory_001"],
                },
            ],
            "goals": [
                {
                    "goal_type": "strategic",
                    "title": "Omzetgroei 20%",
                    "description": "Jaarlijkse omzetgroei via omnichannel strategie",
                    "department_name": "Winkel",
                    "kpis": {"revenue_growth_pct": 20, "conversion_rate": 3.5},
                },
                {
                    "goal_type": "operational",
                    "title": "Voorraadoptimalisatie",
                    "description": "Turnover ratio van 8x per jaar",
                    "department_name": "Voorraad",
                    "kpis": {"inventory_turnover": 8, "stockout_rate": 2},
                },
            ],
            "board_role_config": {
                "budget": "Eigenaar",
                "agent_hire": "Manager",
                "default": "Eigenaar",
                "thresholds": {"auto_approve_below": "LOW"},
            },
        },
    },
    # ========== ZZP (Freelancers) ==========
    {
        "name": "Freelance Consultant",
        "company_type": "zzp",
        "sector": "Consultancy",
        "description": "Zelfstandige consultant met focus op projectwerk",
        "template_definition": {
            "mission": "Waardevolle adviesdiensten leveren aan klanten",
            "departments": [
                {
                    "name": "Projecten",
                    "board_role": "ZZP-er",
                    "budget_monthly_tokens": 1000,
                    "domain_pack_ids": ["pack_pm_001"],
                },
                {
                    "name": "Administratie",
                    "board_role": "ZZP-er",
                    "budget_monthly_tokens": 500,
                    "domain_pack_ids": ["pack_admin_001"],
                },
            ],
            "goals": [
                {
                    "goal_type": "strategic",
                    "title": "Billable Hours 80%",
                    "description": "80% van beschikbare tijd factureerbaar",
                    "department_name": "Projecten",
                    "kpis": {"billable_pct": 80, "hourly_rate": 125},
                },
                {
                    "goal_type": "operational",
                    "title": "Klanttevredenheid 9+",
                    "description": "NPS score boven 50",
                    "department_name": "Projecten",
                    "kpis": {"nps_score": 50, "repeat_customers": 3},
                },
            ],
            "board_role_config": {
                "default": "ZZP-er",
                "thresholds": {"auto_approve_below": "HIGH"},
            },
        },
    },
    {
        "name": "Freelance Designer",
        "company_type": "zzp",
        "sector": "Design",
        "description": "Creatief designer met focus op branding en UX",
        "template_definition": {
            "mission": "Visuele verhalen vertellen die impact maken",
            "departments": [
                {
                    "name": "Design",
                    "board_role": "Designer",
                    "budget_monthly_tokens": 1200,
                    "domain_pack_ids": ["pack_design_001", "pack_brand_001"],
                },
                {
                    "name": "Klanten",
                    "board_role": "Designer",
                    "budget_monthly_tokens": 400,
                    "domain_pack_ids": ["pack_crm_001"],
                },
            ],
            "goals": [
                {
                    "goal_type": "strategic",
                    "title": "Portfolio 15 Projecten",
                    "description": "Sterk portfolio voor acquisitie",
                    "department_name": "Design",
                    "kpis": {"portfolio_items": 15, "case_studies": 5},
                },
                {
                    "goal_type": "operational",
                    "title": "Ontwerpiteratie < 3",
                    "description": "Gemiddeld maximaal 3 revisierondes",
                    "department_name": "Design",
                    "kpis": {"avg_revisions": 3, "approval_rate": 90},
                },
            ],
            "board_role_config": {
                "default": "Designer",
                "thresholds": {"auto_approve_below": "HIGH"},
            },
        },
    },
    {
        "name": "Freelance Developer",
        "company_type": "zzp",
        "sector": "Software Development",
        "description": "Software ontwikkelaar als zzp-er",
        "template_definition": {
            "mission": "Kwalitatieve software oplossingen bouwen",
            "departments": [
                {
                    "name": "Development",
                    "board_role": "Developer",
                    "budget_monthly_tokens": 1500,
                    "domain_pack_ids": ["pack_dev_001", "pack_devops_001"],
                },
                {
                    "name": "Project Management",
                    "board_role": "Developer",
                    "budget_monthly_tokens": 500,
                    "domain_pack_ids": ["pack_pm_001"],
                },
            ],
            "goals": [
                {
                    "goal_type": "strategic",
                    "title": "Langdurige Contracts",
                    "description": "Minimaal 2 langdurige klantrelaties",
                    "department_name": "Development",
                    "kpis": {"retention_months": 12, "contract_value": 50000},
                },
                {
                    "goal_type": "operational",
                    "title": "Code Quality 90%+",
                    "description": "Hoge codekwaliteit en testdekking",
                    "department_name": "Development",
                    "kpis": {"test_coverage": 90, "bugs_per_sprint": 2},
                },
            ],
            "board_role_config": {
                "default": "Developer",
                "thresholds": {"auto_approve_below": "HIGH"},
            },
        },
    },
    # ========== Enterprise ==========
    {
        "name": "Enterprise Corporate",
        "company_type": "enterprise",
        "sector": "Corporate",
        "description": "Groot enterprise met meerdere divisies en governance",
        "template_definition": {
            "mission": "Marktleiderschap behouden door innovatie en efficientie",
            "departments": [
                {
                    "name": "Sales",
                    "board_role": "CSO",
                    "budget_monthly_tokens": 10000,
                    "domain_pack_ids": ["pack_sales_001", "pack_crm_001"],
                },
                {
                    "name": "Marketing",
                    "board_role": "CMO",
                    "budget_monthly_tokens": 8000,
                    "domain_pack_ids": ["pack_marketing_001", "pack_brand_001"],
                },
                {
                    "name": "Engineering",
                    "board_role": "CTO",
                    "budget_monthly_tokens": 15000,
                    "domain_pack_ids": [
                        "pack_dev_001",
                        "pack_devops_001",
                        "pack_security_001",
                    ],
                },
                {
                    "name": "HR",
                    "board_role": "CHRO",
                    "budget_monthly_tokens": 5000,
                    "domain_pack_ids": ["pack_hr_001", "pack_recruitment_001"],
                },
                {
                    "name": "Finance",
                    "board_role": "CFO",
                    "budget_monthly_tokens": 6000,
                    "domain_pack_ids": ["pack_finance_001", "pack_accounting_001"],
                },
                {
                    "name": "Legal & Compliance",
                    "board_role": "General Counsel",
                    "budget_monthly_tokens": 4000,
                    "domain_pack_ids": ["pack_compliance_001", "pack_legal_001"],
                },
            ],
            "goals": [
                {
                    "goal_type": "strategic",
                    "title": "Marktaandeel 25%",
                    "description": "Marktleiderschap in core segment",
                    "department_name": "Sales",
                    "kpis": {"market_share_pct": 25, "revenue_meur": 100},
                },
                {
                    "goal_type": "strategic",
                    "title": "ESG Score A",
                    "description": "Duurzaamheidsrating verbeteren",
                    "department_name": "Legal & Compliance",
                    "kpis": {"esg_score": "A", "co2_reduction_pct": 30},
                },
                {
                    "goal_type": "operational",
                    "title": "Talent retentie 90%",
                    "description": "Behouden van top talent",
                    "department_name": "HR",
                    "kpis": {"retention_rate": 90, "time_to_hire_days": 30},
                },
            ],
            "board_role_config": {
                "budget": "CFO",
                "agent_hire": "CTO",
                "agent_firing": "CHRO",
                "data_export": "General Counsel",
                "security": "CISO",
                "cross_department": "CEO",
                "default": "CEO",
                "thresholds": {"auto_approve_below": "LOW"},
            },
        },
    },
    {
        "name": "Enterprise SaaS",
        "company_type": "enterprise",
        "sector": "Software as a Service",
        "description": "SaaS enterprise met focus op subscriptions en growth",
        "template_definition": {
            "mission": "Schaalbare software die klanten helpt groeien",
            "departments": [
                {
                    "name": "Product",
                    "board_role": "CPO",
                    "budget_monthly_tokens": 12000,
                    "domain_pack_ids": ["pack_product_001", "pack_ux_001"],
                },
                {
                    "name": "Engineering",
                    "board_role": "CTO",
                    "budget_monthly_tokens": 20000,
                    "domain_pack_ids": [
                        "pack_dev_001",
                        "pack_cloud_001",
                        "pack_sre_001",
                    ],
                },
                {
                    "name": "Customer Success",
                    "board_role": "CCO",
                    "budget_monthly_tokens": 8000,
                    "domain_pack_ids": ["pack_success_001", "pack_support_001"],
                },
                {
                    "name": "Growth",
                    "board_role": "CGO",
                    "budget_monthly_tokens": 10000,
                    "domain_pack_ids": ["pack_growth_001", "pack_analytics_001"],
                },
                {
                    "name": "Revenue Operations",
                    "board_role": "CRO",
                    "budget_monthly_tokens": 6000,
                    "domain_pack_ids": ["pack_revenue_001", "pack_sales_001"],
                },
            ],
            "goals": [
                {
                    "goal_type": "strategic",
                    "title": "ARR EUR10M",
                    "description": "Annual Recurring Revenue target",
                    "department_name": "Revenue Operations",
                    "kpis": {"arr_eur": 10000000, "growth_rate": 50},
                },
                {
                    "goal_type": "strategic",
                    "title": "NRR 110%+",
                    "description": "Net Revenue Retention boven 110%",
                    "department_name": "Customer Success",
                    "kpis": {"net_revenue_retention": 110, "churn_rate": 5},
                },
                {
                    "goal_type": "operational",
                    "title": "Uptime 99.99%",
                    "description": "Platform beschikbaarheid",
                    "department_name": "Engineering",
                    "kpis": {"uptime_pct": 99.99, "mttr_minutes": 15},
                },
            ],
            "board_role_config": {
                "budget": "CFO",
                "agent_hire": "CTO",
                "cross_department": "CEO",
                "default": "CEO",
                "thresholds": {"auto_approve_below": "MEDIUM"},
            },
        },
    },
    {
        "name": "Enterprise Fintech",
        "company_type": "enterprise",
        "sector": "Financiele Dienstverlening",
        "description": "Fintech enterprise met hoge compliance eisen",
        "template_definition": {
            "mission": "Veilige en innovatieve financiele diensten leveren",
            "departments": [
                {
                    "name": "Platform",
                    "board_role": "CTO",
                    "budget_monthly_tokens": 18000,
                    "domain_pack_ids": [
                        "pack_fintech_001",
                        "pack_security_001",
                        "pack_cloud_001",
                    ],
                },
                {
                    "name": "Risk & Compliance",
                    "board_role": "CRO",
                    "budget_monthly_tokens": 10000,
                    "domain_pack_ids": [
                        "pack_risk_001",
                        "pack_compliance_001",
                        "pack_audit_001",
                    ],
                },
                {
                    "name": "Klantenservice",
                    "board_role": "COO",
                    "budget_monthly_tokens": 7000,
                    "domain_pack_ids": ["pack_support_001", "pack_kyc_001"],
                },
                {
                    "name": "Finance",
                    "board_role": "CFO",
                    "budget_monthly_tokens": 8000,
                    "domain_pack_ids": ["pack_finance_001", "pack_reporting_001"],
                },
                {
                    "name": "Legal",
                    "board_role": "General Counsel",
                    "budget_monthly_tokens": 6000,
                    "domain_pack_ids": ["pack_legal_001", "pack_regulatory_001"],
                },
            ],
            "goals": [
                {
                    "goal_type": "strategic",
                    "title": "PSD2 Compliant",
                    "description": "Volledige PSD2 compliance",
                    "department_name": "Risk & Compliance",
                    "kpis": {"audit_findings": 0, "compliance_score": 100},
                },
                {
                    "goal_type": "strategic",
                    "title": "Transactievolume 1M+",
                    "description": "1 miljoen transacties per maand",
                    "department_name": "Platform",
                    "kpis": {"monthly_transactions": 1000000, "fraud_rate_pct": 0.01},
                },
                {
                    "goal_type": "operational",
                    "title": "Security Rating A+",
                    "description": "Hoogste security ratings behalen",
                    "department_name": "Platform",
                    "kpis": {"pentest_findings": 0, "soc2_compliant": True},
                },
            ],
            "board_role_config": {
                "budget": "CFO",
                "agent_hire": "CTO",
                "data_export": "General Counsel",
                "security": "CRO",
                "default": "CEO",
                "thresholds": {"auto_approve_below": "LOW"},
            },
        },
    },
    {
        "name": "Enterprise Healthcare",
        "company_type": "enterprise",
        "sector": "Gezondheidszorg",
        "description": "Zorgorganisatie met patient focus en compliance",
        "template_definition": {
            "mission": "Patient-centered zorg leveren van hoge kwaliteit",
            "departments": [
                {
                    "name": "Patient Zorg",
                    "board_role": "CMO",
                    "budget_monthly_tokens": 8000,
                    "domain_pack_ids": ["pack_care_001", "pack_ehr_001"],
                },
                {
                    "name": "Operations",
                    "board_role": "COO",
                    "budget_monthly_tokens": 6000,
                    "domain_pack_ids": ["pack_operations_001", "pack_scheduling_001"],
                },
                {
                    "name": "IT & Security",
                    "board_role": "CIO",
                    "budget_monthly_tokens": 10000,
                    "domain_pack_ids": ["pack_healthcare_it_001", "pack_hipaa_001"],
                },
                {
                    "name": "Compliance",
                    "board_role": "CCO",
                    "budget_monthly_tokens": 7000,
                    "domain_pack_ids": [
                        "pack_hipaa_001",
                        "pack_audit_001",
                        "pack_privacy_001",
                    ],
                },
                {
                    "name": "HR & Opleiding",
                    "board_role": "CHRO",
                    "budget_monthly_tokens": 5000,
                    "domain_pack_ids": ["pack_hr_001", "pack_training_001"],
                },
            ],
            "goals": [
                {
                    "goal_type": "strategic",
                    "title": "Patienttevredenheid 95%",
                    "description": "Hoge patienttevredenheidsscores",
                    "department_name": "Patient Zorg",
                    "kpis": {"satisfaction_pct": 95, "nps_score": 70},
                },
                {
                    "goal_type": "strategic",
                    "title": "HIPAA Compliant",
                    "description": "Volledige HIPAA compliance",
                    "department_name": "Compliance",
                    "kpis": {"audit_score": 100, "breaches": 0},
                },
                {
                    "goal_type": "operational",
                    "title": "Wachttijd < 15 min",
                    "description": "Gemiddelde wachttijd verminderen",
                    "department_name": "Operations",
                    "kpis": {"avg_wait_min": 15, "capacity_utilization": 85},
                },
            ],
            "board_role_config": {
                "budget": "CFO",
                "agent_hire": "CIO",
                "data_export": "CCO",
                "security": "CIO",
                "default": "CEO",
                "thresholds": {"auto_approve_below": "LOW"},
            },
        },
    },
]


async def seed_platform_templates(session: AsyncSession) -> int:
    """Seed platform templates if they don't exist.

    Args:
        session: Database session

    Returns:
        Number of templates seeded
    """
    count = 0

    with TenantFilterBypass():
        for template_data in SEED_TEMPLATES:
            # Platform templates are global (cross-tenant), so bypass auto tenant filtering.
            result = await session.execute(
                select(CompanyTemplate).where(
                    CompanyTemplate.name == template_data["name"],
                    CompanyTemplate.is_platform_template.is_(True),  # noqa: E712
                )
            )
            existing = result.scalar_one_or_none()

            if not existing:
                template = CompanyTemplate(
                    name=template_data["name"],
                    company_type=template_data["company_type"],
                    sector=template_data["sector"],
                    description=template_data["description"],
                    template_definition=template_data["template_definition"],
                    is_platform_template=True,
                    contributed_by_tenant_id=None,
                    usage_count=0,
                    rating_sum=0,
                    rating_count=0,
                    status="active",
                )
                session.add(template)
                count += 1

    await session.commit()
    return count
