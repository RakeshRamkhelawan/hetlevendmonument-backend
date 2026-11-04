#!/usr/bin/env python3
"""Generate skill manifests and rewrite skill stubs to use BaseSpecialistAgent.

This script converts the 135+ ALS skill stubs into real WorkerAgent implementations
by giving each skill a declarative manifest and a generated `act()` that delegates
to the shared BaseSpecialistAgent OODA-loop instead of returning hardcoded stubs.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

SKILLS_DIR = Path("src/core/als/agents/skills")
MANIFESTS_DIR = SKILLS_DIR / "manifests"
TOOL_PERMISSIONS_YML = Path("config/tool_permissions.yml")
NON_SKILL_PROFILES = {"copilot"}


@lru_cache(maxsize=1)
def _profiled_skill_ids() -> frozenset[str]:
    """Skill IDs that have a tool permission profile (AUDIT-008).

    A skill with a profile may attempt TOOL_CALL, so its regenerated manifest
    must NOT contain the text-only stopgap -- otherwise regeneration would
    recreate the exact inconsistency that
    tests/architecture/test_als_skills_tool_permissions.py guards against.
    """
    if not TOOL_PERMISSIONS_YML.exists():
        return frozenset()
    data = yaml.safe_load(TOOL_PERMISSIONS_YML.read_text(encoding="utf-8")) or {}
    return frozenset(
        str(p["agent_id"])
        for p in data.get("agent_profiles", []) or []
        if isinstance(p, dict) and p.get("agent_id") not in NON_SKILL_PROFILES
    )

# Human-readable department context
DEPARTMENT_DESCRIPTIONS: dict[str, str] = {
    "product_innovation": "Product design, UX/UI, architecture, prototyping and market analysis.",
    "operations_supply_chain": "Inventory, logistics, scheduling, maintenance and supplier management.",
    "sales_marketing": "Lead generation, content, campaigns, CRM, SEO, pricing and partnerships.",
    "finance_treasury": "Invoicing, accounting, tax, forecasting, M&A and investment analysis.",
    "hr_culture": "Recruiting, employee development, well-being, scheduling and workforce planning.",
    "it_security": "Cloud, DevOps, code review, database, MLOps, security operations and QA.",
    "legal_compliance": "Contracts, compliance, privacy, IP, regulatory tracking and vendor negotiation.",
    "customer_experience": "Customer success, community management, sentiment and onboarding.",
    "strategy_business": "Competitive intelligence, geopolitical risk, crisis management and strategy.",
    "data_ai_governance": "Data quality, analytics, visualization, AI governance and research synthesis.",
}

#: De BELOFTE in de instructietekst van een geprofileerde skill, als constante.
#:
#: Hij staat hier en nergens anders, omdat een guard hem moet kunnen vastpinnen.
#: `tests/unit/scripts/test_generate_skill_manifests_stopgap.py::
#: test_the_prompt_only_promises_working_tools_while_they_all_work` toetst deze string
#: ONVOORWAARDELIJK plus de vraag of elke gedeclareerde tool echt bestaat. Een eerdere versie van
#: die guard zocht de zin als substring en gaf hem een `if`: een HERFORMULERING zette de guard
#: daarmee uit terwijl de belofte bleef staan -- gemeten in Gate 2 op 2026-09-21, de vorm
#: "tekst doorzoeken waar structuur hoort" uit quality-gates.md.
TOOL_PROMISE = "Every tool in that list is connected and will really run."

#: Tools per SKILL, waar een departementslijst te grof is. Leidend boven DEPARTMENT_TOOLS.
#:
#: Vandaag exact een regel: de piloot mag ook schrijven, de andere HR-skills niet. Dat is geen
#: uitzondering maar het punt -- een HIGH-risk schrijftool hoort per skill te worden toegekend,
#: niet per departement.
SKILL_TOOL_OVERRIDES: dict[str, list[str]] = {
    "skillsgaptraining": [
        "query_hr_database",
        "analyze_skill_gap",
        "schedule_training",
    ],
}

#: De versie van de instructietekst per skill (ADR-036 OP-02). Alleen skills die hier staan
#: krijgen het veld; zonder deze regel schreef de generator het manifest van de piloot zonder
#: `manifest_version`, terwijl het gecommitte manifest hem WEL heeft -- een van de drie velden
#: waarop generator en artefact uit elkaar liepen (Gate 2, 2026-09-21).
SKILL_MANIFEST_VERSIONS: dict[str, int] = {
    "skillsgaptraining": 3,
}

#: Een extra alinea in de instructietekst van een skill, vlak voor "Never invent data". Vandaag een regel: de piloot
#: adviseert en stelt voor (besluit Rakesh 2026-10-24, agentkaart dag 1); een mens beslist altijd. Staat ook in de agentkaart.
SKILL_PROMPT_TOEVOEGINGEN: dict[str, str] = {
    "skillsgaptraining": (
        "You advise and propose; a human always decides. schedule_training only creates a proposal for "
        "a training: it is carried out only after a human approves it. Present every recommendation as "
        "advice and never as a decision.\n"
    ),
}

# Tools available to each department family
DEPARTMENT_TOOLS: dict[str, list[str]] = {
    "product_innovation": [
        "query_documents",
        "generate_text",
        "generate_design_brief",
        "search_web",
        "notify_stakeholder",
    ],
    "operations_supply_chain": [
        "query_database",
        "run_optimization",
        "send_notification",
        "schedule_action",
        "query_inventory",
    ],
    "sales_marketing": [
        "query_crm",
        "generate_text",
        "send_email",
        "schedule_action",
        "search_web",
        "publish_content",
    ],
    "finance_treasury": [
        "query_database",
        "calculate",
        "generate_report",
        "send_notification",
        "search_documents",
    ],
    # Gewijzigd 2026-09-21. Hier stonden vijf namen waarvan er drie niet bestonden
    # (`search_documents`, `generate_text`, `send_notification`) en waarvan `schedule_training`
    # een HIGH-risk SCHRIJFtool op personeelsdata is geworden. Een departementslijst geldt voor
    # ELKE skill in dat departement -- vijftien manifesten kregen die naam zonder dat iemand per
    # skill afwoog of een pauzeherinnering trainingen mag toewijzen. De piloot krijgt zijn extra
    # tools daarom via SKILL_TOOL_OVERRIDES hieronder, per naam in plaats van per departement.
    #
    # In de eerste versie van deze wijziging stond hier ook `analyze_skill_gap`, met "veilig voor
    # iedere HR-skill" als toelichting. Een Gate 2-reviewer mat dat dat de lijst niet alleen
    # verkleinde maar ook VERBREEDDE: die tool stond er niet, en 15 skills hebben
    # `department: hr_culture`. Een regeneratie zou veertien skills (`breakreminder`,
    # `digitaldetox`, ...) toegang geven tot dezelfde personeelsdata waarvoor `admin` nodig is,
    # zonder dat iemand per skill heeft afgewogen of een pauzeherinnering de bezetting mag
    # opvragen. "Veilig" was een bewering en geen meting, en de nieuwe profielguard dekt alleen
    # HIGH -- deze tool is MEDIUM en valt er dus buiten.
    "hr_culture": [
        "query_hr_database",
    ],
    "it_security": [
        "query_database",
        "run_code_analysis",
        "run_security_scan",
        "execute_shell_command",
        "search_web",
        "create_ticket",
    ],
    "legal_compliance": [
        "search_documents",
        "generate_text",
        "compare_clauses",
        "send_notification",
        "query_regulatory_db",
    ],
    "customer_experience": [
        "query_crm",
        "search_documents",
        "generate_text",
        "send_notification",
        "escalate_to_human",
    ],
    "strategy_business": [
        "search_web",
        "query_database",
        "generate_text",
        "generate_report",
        "send_notification",
    ],
    "data_ai_governance": [
        "query_database",
        "run_analysis",
        "generate_chart",
        "search_documents",
        "generate_report",
    ],
}

# Explicit department overrides for skills that do not match keyword heuristics.
DEPARTMENT_OVERRIDES: dict[str, str] = {
    # HR
    "talentacquisition": "hr_culture",
    "employeesentiment": "hr_culture",
    "internalmobility": "hr_culture",
    "skillsgaptraining": "hr_culture",
    "skillpathfinder": "hr_culture",
    "leavemanager": "hr_culture",
    "burnoutcoach": "hr_culture",
    "breakreminder": "hr_culture",
    "meetingnotes": "hr_culture",
    "emotionalmirror": "hr_culture",
    "negotiationcoach": "hr_culture",
    "focusguardian": "hr_culture",
    "digitaldetox": "hr_culture",
    "knowledgecurator": "hr_culture",
    "taskmanager": "hr_culture",
    # Sales/Marketing
    "brandguardian": "sales_marketing",
    "competitorshadow": "sales_marketing",
    "contentpersonalization": "sales_marketing",
    "discountcampaign": "sales_marketing",
    "emailmarketer": "sales_marketing",
    "coldemailer": "sales_marketing",
    "leadfinder": "sales_marketing",
    "leadgen": "sales_marketing",
    "linkedinoptimizer": "sales_marketing",
    "localseospecialist": "sales_marketing",
    "multichannelcontent": "sales_marketing",
    "pitchdeckgen": "sales_marketing",
    "portfoliogen": "sales_marketing",
    "pricingstrategist": "sales_marketing",
    "proposalwriter": "sales_marketing",
    "publicrelations": "sales_marketing",
    "reviewresponder": "sales_marketing",
    "seospecialist": "sales_marketing",
    "socialmediastrategist": "sales_marketing",
    "socialscheduler": "sales_marketing",
    "growthlead": "sales_marketing",
    "crmmanager": "sales_marketing",
    # Product/Innovation
    "bioarchitect": "product_innovation",
    "competitiveintelligence": "product_innovation",
    "marketgapanalysis": "product_innovation",
    "marketintelligence": "product_innovation",
    "mergeracquisitionscout": "product_innovation",
    "prototypeoptimizer": "product_innovation",
    "technicalarchitect": "product_innovation",
    "uxuidesigner": "product_innovation",
    "routinebuilder": "product_innovation",
    # Operations
    "carbontracker": "operations_supply_chain",
    "inventoryforecasting": "operations_supply_chain",
    "logisticsoptimization": "operations_supply_chain",
    "maintenancescheduler": "operations_supply_chain",
    "officesupplybot": "operations_supply_chain",
    "orderfulfillment": "operations_supply_chain",
    "routeoptimizer": "operations_supply_chain",
    "shiftplanner": "operations_supply_chain",
    "sustainablesourcing": "operations_supply_chain",
    "workflowrefactoring": "operations_supply_chain",
    # Finance
    "accountsreceivablepayable": "finance_treasury",
    "dunning": "finance_treasury",
    "crediteuren": "finance_treasury",
    "dynamicpricing": "finance_treasury",
    "expenseclassifier": "finance_treasury",
    "forecasting": "finance_treasury",
    "investmentallocation": "finance_treasury",
    "invoicegen": "finance_treasury",
    "latepaymentchaser": "finance_treasury",
    "maanalyst": "finance_treasury",
    "profitoptimizer": "finance_treasury",
    "receiptscanner": "finance_treasury",
    "receipt_scanner": "finance_treasury",
    "taxcompliance": "finance_treasury",
    "taxpredictor": "finance_treasury",
    "vatcompliance": "finance_treasury",
    # Legal/Compliance
    "aiethicsauditor": "legal_compliance",
    "auditcompliance": "legal_compliance",
    "contractanalysis": "legal_compliance",
    "contractlifecycle": "legal_compliance",
    "contractnegotiatorlite": "legal_compliance",
    "copyrightcheck": "legal_compliance",
    "customscompliance": "legal_compliance",
    "dataintegrityethics": "legal_compliance",
    "esgauditor": "legal_compliance",
    "gdprprivacy": "legal_compliance",
    "gdprprivacyguard": "legal_compliance",
    "liabilityaudit": "legal_compliance",
    "patentscout": "legal_compliance",
    "regulatorytracking": "legal_compliance",
    "solocontract": "legal_compliance",
    "tosgenerator": "legal_compliance",
    "vendornegotiation": "legal_compliance",
    # IT/Security
    "autodevops": "it_security",
    "chaosengineering": "it_security",
    "cloudarchitect": "it_security",
    "cloudorchestration": "it_security",
    "codereviewer": "it_security",
    "databaseadmin": "it_security",
    "dataengineer": "it_security",
    "datascience": "it_security",
    "djangopro": "it_security",
    "fastapipro": "it_security",
    "incidentresponder": "it_security",
    "javascriptpro": "it_security",
    "kubernetesarchitect": "it_security",
    "mlopsspecialist": "it_security",
    "pythonpro": "it_security",
    "qabugdetection": "it_security",
    "redteaming": "it_security",
    "securityauditor": "it_security",
    "technicalwriter": "it_security",
    "terraformspecialist": "it_security",
    "testautomator": "it_security",
    "threathunter": "it_security",
    "typescriptpro": "it_security",
    "zerodaypredictor": "it_security",
    # Customer Experience
    "communitymanagement": "customer_experience",
    "customersuccess": "customer_experience",
    "sentimentsupport": "customer_experience",
    "useronboarding": "customer_experience",
    # Strategy/Business
    "crisismanager": "strategy_business",
    "dharmaalignment": "strategy_business",
    "geopoliticalrisk": "strategy_business",
    "karmaauditor": "strategy_business",
    "partnerships": "strategy_business",
    "researchsynthesizer": "strategy_business",
    "shareholderrelations": "strategy_business",
    # Data/AI Governance
    "calendarshield": "data_ai_governance",
    "churnpredictor": "data_ai_governance",
    "dataintegrity": "data_ai_governance",
    "datavisualization": "data_ai_governance",
    "ghostwriter": "data_ai_governance",
    "hallucinationhunter": "data_ai_governance",
    "inboxzero": "data_ai_governance",
    "nlpexpert": "data_ai_governance",
    "processmining": "data_ai_governance",
    "retailpriceoptimizer": "data_ai_governance",
    "safetycompliance": "data_ai_governance",
    "sdr": "data_ai_governance",
    "shopifysync": "data_ai_governance",
}

# Skills that have a direct external-system footprint and need HITL by default
ANNEX_III_SKILLS: set[str] = {
    "talentacquisition",
    "employeesentiment",
    "internalmobility",
}


def classify_department(skill_id: str) -> str:
    """Map a skill id to one of the 10 ALS departments."""
    if skill_id in DEPARTMENT_OVERRIDES:
        return DEPARTMENT_OVERRIDES[skill_id]
    return "data_ai_governance"


def readable_name(class_name: str) -> str:
    """Convert ClassName like SkillsGapTrainingSkill to 'Skills Gap Training'."""
    name = class_name.removesuffix("Skill")
    # Insert spaces before capitals, keep acronyms together
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return spaced.strip()


def build_manifest(skill_id: str, class_name: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Build a declarative manifest for a skill."""
    dept = classify_department(skill_id)
    readable = readable_name(class_name)

    annex_iii = "annex_iii" if skill_id in ANNEX_III_SKILLS else "none"
    human_loop = "hitl" if annex_iii == "annex_iii" else "hotl"

    if skill_id in _profiled_skill_ids():
        # AUDIT-008: the skill has a tool permission profile, so the stopgap is
        # replaced by an honest TOOL_CALL instruction.
        #
        # BE-AGT-040: this used to open with "You have working tools", which was false --
        # a profile grants PERMISSION, it does not wire a tool. None of the 27 tools
        # declared across the manifests resolves in ToolBrokerService.execute_tool
        # (BE-AGT-039 F1), so the claim promised something that does not exist.
        #
        # 2026-09-21: the sentence "Some listed tools are not connected yet" is GONE, and
        # that is a correction, not a rewording. It was true on 2026-08-01 and it stopped
        # being true today: every tool in the pilot profile now resolves (measured with
        # scripts/acceptance_thread.py, step 3 -- "alle 4 tools bestaan"). Two of the six
        # names were removed from the manifest because they will not be built, and one was
        # renamed to the name it already had in the local registry.
        #
        # Keeping the sentence would not be merely stale. Telling a model that some of its
        # declared tools may refuse is what breaks its ability to judge whether a task is
        # solvable at all, and that -- not the refusal itself -- is the measured primary
        # cause of invented tool results. A declared tool must therefore either work or not
        # be declared.
        #
        # The claim is only allowed to stand while it is true, and that is enforced:
        # tests/unit/scripts/test_generate_skill_manifests_stopgap.py::
        # test_the_prompt_only_promises_working_tools_while_they_all_work compares this text
        # with the tools the profile grants, so a tool that disappears turns it red.
        #
        # It deliberately keeps the TOOL_CALL contract (the day-1 evaluation set asserts on
        # it) and must NOT fall back to the text-only stopgap: profile + stopgap is exactly
        # the inconsistency that independent review IR-001 forced out, guarded by
        # tests/architecture/test_als_skills_tool_permissions.py.
        tool_instruction = (
            "You may use only the tools listed under allowed_tools in your manifest. "
            "When a tool is needed, emit exactly one directive per line in the format "
            'TOOL_CALL: tool_name {"param": "value"} -- anything outside that list '
            f"is denied by the ToolBroker (ADR-015). {TOOL_PROMISE} A tool that writes "
            "may need human approval first and can therefore come back refused; that is "
            "not a broken tool. Report any failure plainly and never invent a tool "
            "result. Otherwise provide your analysis and recommendation as a concise "
            "final answer, in text.\n"
        )
    else:
        # STOPGAP (see docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md
        # Onderdeel 7 / plan remediation): tool execution for this skill family is not
        # yet wired to a real ToolBroker registry -- issuing TOOL_CALL directives would
        # be silently denied. Return a textual analysis/recommendation only until the
        # real tool integration lands. Do not fabricate a tool result.
        tool_instruction = (
            "You do not have working tools available yet -- provide your analysis and "
            "recommendation as a concise final answer, in text, without attempting a "
            "TOOL_CALL.\n"
        )
    return {
        "skill_id": skill_id,
        # Alleen voor skills in SKILL_MANIFEST_VERSIONS, en op dezelfde plek als in het
        # gecommitte manifest: direct na `skill_id`.
        **(
            {"manifest_version": SKILL_MANIFEST_VERSIONS[skill_id]}
            if skill_id in SKILL_MANIFEST_VERSIONS
            else {}
        ),
        "class_name": class_name,
        "department": dept,
        "annex_iii_classification": annex_iii,
        "human_in_the_loop": human_loop,
        "technology": "llm",
        "role": f"{readable} Specialist",
        "goal": f"Execute {readable.lower()} tasks using allowed tools, tenant-scoped data and the OODA loop.",
        "system_prompt": (
            f"You are the {readable} Specialist for your tenant.\n"
            f"Department context: {DEPARTMENT_DESCRIPTIONS[dept]}\n"
            "Follow the OODA loop: observe the task, orient using available data, "
            "and decide on the best course of action.\n"
            f"{tool_instruction}"
            f"{SKILL_PROMPT_TOEVOEGINGEN.get(skill_id, '')}"
            "Never invent data; if information is missing, say so explicitly."
        ),
        "allowed_tools": SKILL_TOOL_OVERRIDES.get(skill_id, DEPARTMENT_TOOLS[dept]),
        "memory": {
            "read": [dept, "shared"],
            "write": [skill_id],
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "context": {"type": "object"},
            },
            "required": ["task"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "details": {"type": "object"},
                "confidence": {"type": "number"},
            },
            "required": ["summary"],
        },
        "budget": {
            "max_steps": 8,
            "max_llm_calls": 5,
            "timeout_seconds": 60,
            "prana_cost_limit": 100,
        },
    }


def generate_skill_file(skill_id: str, class_name: str) -> str:
    """Generate a real skill file that loads its manifest and uses the shared runtime."""
    manifest_path = f"manifests/{skill_id}.yml"
    return f'''\
import logging
from pathlib import Path
from typing import Any

from src.core.als.agents.skill_manifest import SkillManifest
from src.core.als.agents.specialist_base import BaseSpecialistAgent
from src.core.shared.interfaces import ExecutionResult

logger = logging.getLogger(__name__)


class {class_name}(BaseSpecialistAgent):
    """
    {readable_name(class_name)} worker agent.

    Loaded from ``{manifest_path}``; behavior is driven by the manifest
    and executed through the shared BaseSpecialistAgent OODA loop.
    """

    def __init__(self, tenant_id: int, **kwargs: Any) -> None:
        manifest = SkillManifest.load(Path(__file__).parent / "{manifest_path}")
        config = manifest.to_config()
        # Merge any runtime overrides passed by the caller
        config.update(kwargs)
        super().__init__(config=config, tenant_id=tenant_id)

    async def act(self, decision: str) -> ExecutionResult:
        """Execute using the shared OODA/tool runtime instead of a hardcoded stub."""
        logger.info(f"[{{self.agent_id}}] Executing via shared runtime for tenant {{self.tenant_id}}")
        return await super().act(decision)
'''


def parse_class_name(source: str) -> str | None:
    """Extract the skill class name from a source file."""
    match = re.search(r"class\s+(\w+)\s*\(", source)
    return match.group(1) if match else None


def generate_init_file(skill_files: list[Path]) -> None:
    """Generate src/core/als/agents/skills/__init__.py with all skill imports."""
    lines = [
        '"""Auto-generated skills package."""',
        "",
        "from pathlib import Path",
        "",
        "from src.core.als.agents.specialist_base import BaseSpecialistAgent",
        "",
        '_SKILL_MANIFEST_DIR = Path(__file__).parent / "manifests"',
        "",
    ]

    imports: list[str] = []
    all_names: list[str] = []
    for path in skill_files:
        if path.name == "__init__.py":
            continue
        skill_id = path.stem
        source = path.read_text(encoding="utf-8")
        class_name = parse_class_name(source) or f"{skill_id.title().replace('_', '')}Skill"
        imports.append(f"from src.core.als.agents.skills.{skill_id} import {class_name}")
        all_names.append(class_name)

    # __all__ must be a list of string literals (Python convention); SKILL_CLASSES
    # is a list of the actual class objects. Building both from the same bare
    # identifier list previously produced `__all__ = [SomeSkill, ...]` -- a list
    # of class objects, not strings -- which is what caused the 138 mypy errors
    # and the pyright reportCallIssue (see plan Onderdeel 7).
    quoted_list = "[" + ", ".join(f'"{name}"' for name in all_names) + "]"
    class_list = "[" + ", ".join(all_names) + "]"
    lines.extend(imports)
    lines.extend(
        [
            "",
            f"__all__: list[str] = {quoted_list}",
            "",
            f"SKILL_CLASSES: list[type[BaseSpecialistAgent]] = {class_list}",
            "",
            "",
            "def list_skill_manifests() -> list[Path]:",
            '    """Return all generated skill manifest paths."""',
            '    return sorted(_SKILL_MANIFEST_DIR.glob("*.yml"))',
            "",
        ]
    )

    init_path = SKILLS_DIR / "__init__.py"
    init_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nGenerated {init_path}")


def heeft_agentkaart(manifest_path: Path) -> bool:
    """Heeft dit manifest al een handmatig onderhouden agentkaart? Dan schrijft de generator het niet opnieuw.

    De generator schrijft elk manifest en elk skillbestand onvoorwaardelijk; een agent met een kaart (agentkaart dag 1) heeft
    een Nederlandse rolbeschrijving en velden die de generator niet kent, en die zouden bij een run verdwijnen.
    """
    if not manifest_path.is_file():
        return False
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    return isinstance(data, dict) and data.get("agentkaart") is not None


def main() -> None:
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)

    skill_files = sorted(SKILLS_DIR.glob("*.py"))
    generated = 0

    for path in skill_files:
        if path.name == "__init__.py":
            continue
        skill_id = path.stem
        source = path.read_text(encoding="utf-8")
        class_name = parse_class_name(source) or f"{skill_id.title().replace('_', '')}Skill"

        manifest = build_manifest(skill_id, class_name)
        manifest_path = MANIFESTS_DIR / f"{skill_id}.yml"
        if heeft_agentkaart(manifest_path):
            print(f"Overgeslagen {skill_id}: heeft een agentkaart (handmatig onderhouden)")
            continue
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

        new_source = generate_skill_file(skill_id, class_name)
        path.write_text(new_source, encoding="utf-8")

        generated += 1
        print(f"Generated {skill_id}: {manifest['department']} -> {class_name}")

    generate_init_file(skill_files)
    print(f"\nDone. Generated {generated} manifests and skill files in {SKILLS_DIR}")


if __name__ == "__main__":
    main()
