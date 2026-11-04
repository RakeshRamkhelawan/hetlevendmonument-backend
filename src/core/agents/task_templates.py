"""
Task Generation Templates for CVA Agent
Provides structured templates for generating different types of tasks
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.shared.interfaces import TaskData
from src.core.types import TaskPriority, TaskStatus

logger = logging.getLogger(__name__)


class TaskTemplate(Enum):
    """Available task templates"""

    STRATEGIC_ANALYSIS = "strategic_analysis"
    MARKET_RESEARCH = "market_research"
    COMPETITIVE_ANALYSIS = "competitive_analysis"
    FEATURE_SPECIFICATION = "feature_specification"
    RISK_ASSESSMENT = "risk_assessment"
    USER_RESEARCH = "user_research"
    TECHNICAL_REVIEW = "technical_review"
    STAKEHOLDER_ALIGNMENT = "stakeholder_alignment"
    ROADMAP_PLANNING = "roadmap_planning"
    PERFORMANCE_ANALYSIS = "performance_analysis"


@dataclass
class TaskGenerationConfig:
    """Configuration for task generation"""

    template: TaskTemplate
    priority: TaskPriority = TaskPriority.MEDIUM
    estimated_duration: int = 60  # minutes
    required_skills: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)
    context_variables: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


@dataclass
class GeneratedTask:
    """A generated task with all necessary details"""

    task_data: TaskData
    template_used: TaskTemplate
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    success_criteria: list[str]
    quality_gates: list[str]
    follow_up_tasks: list[str] = field(default_factory=list)


class TaskTemplateGenerator:
    """Generates tasks from predefined templates"""

    def __init__(self) -> None:
        self.templates = self._initialize_templates()
        self._generated_count = 0
        logger.info("Task Template Generator initialized")

    def _initialize_templates(self) -> dict[TaskTemplate, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Initialize all task templates"""
        return {
            TaskTemplate.STRATEGIC_ANALYSIS: self._create_strategic_analysis_template(),
            TaskTemplate.MARKET_RESEARCH: self._create_market_research_template(),
            TaskTemplate.COMPETITIVE_ANALYSIS: self._create_competitive_analysis_template(),
            TaskTemplate.FEATURE_SPECIFICATION: self._create_feature_specification_template(),
            TaskTemplate.RISK_ASSESSMENT: self._create_risk_assessment_template(),
            TaskTemplate.USER_RESEARCH: self._create_user_research_template(),
            TaskTemplate.TECHNICAL_REVIEW: self._create_technical_review_template(),
            TaskTemplate.STAKEHOLDER_ALIGNMENT: self._create_stakeholder_alignment_template(),
            TaskTemplate.ROADMAP_PLANNING: self._create_roadmap_planning_template(),
            TaskTemplate.PERFORMANCE_ANALYSIS: self._create_performance_analysis_template(),
        }

    async def generate_task(self, config: TaskGenerationConfig) -> GeneratedTask:
        """Generate a task from a template"""
        template_data = self.templates.get(config.template)
        if not template_data:
            raise ValueError(f"Template {config.template} not found")

        # Generate unique task ID
        self._generated_count += 1
        task_id = f"{config.template.value}_{self._generated_count}_{int(datetime.now(timezone.utc).timestamp())}"

        # Merge context variables with template variables
        context = {**template_data["default_context"], **config.context_variables}

        # Generate task title and description
        title = self._format_template_string(template_data["title_template"], context)
        description = self._format_template_string(template_data["description_template"], context)

        # Create task metadata
        metadata = {
            "type": config.template.value,
            "generated_from_template": True,
            "template_version": "1.0",
            "estimated_duration": config.estimated_duration,
            "required_skills": config.required_skills,
            "deliverables": config.deliverables or template_data["default_deliverables"],
            "context": context,
        }

        # Add template-specific metadata
        metadata.update(template_data.get("metadata", {}))

        # Create TaskData
        task_data = TaskData(
            id=task_id,
            title=title,
            description=description,
            priority=config.priority,
            status=TaskStatus.PENDING,
            metadata=metadata,
        )

        # Generate success criteria
        success_criteria = [
            self._format_template_string(criteria, context)
            for criteria in template_data["success_criteria"]
        ]

        # Generate quality gates
        quality_gates = [
            self._format_template_string(gate, context) for gate in template_data["quality_gates"]
        ]

        # Generate follow-up tasks if specified
        follow_up_tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if template_data.get("follow_up_templates"):
            for follow_up_template in template_data["follow_up_templates"]:
                follow_up_tasks.append(self._format_template_string(follow_up_template, context))

        return GeneratedTask(
            task_data=task_data,
            template_used=config.template,
            context=context,
            success_criteria=success_criteria,
            quality_gates=quality_gates,
            follow_up_tasks=follow_up_tasks,
        )

    def _format_template_string(self, template: str, context: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format a template string with context variables"""
        try:
            return template.format(**context)
        except KeyError as e:
            logger.warning(f"Missing template variable: {e}")
            return template  # Return unformatted if variables missing

    def _create_strategic_analysis_template(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create strategic analysis task template"""
        return {
            "title_template": "Strategic Analysis: {focus_area}",
            "description_template": """Conduct comprehensive strategic analysis for {focus_area}.

Scope: {scope}
Timeline: {timeline}
Key stakeholders: {stakeholders}

This analysis should provide actionable insights and recommendations to guide strategic decision-making.""",
            "default_context": {
                "focus_area": "Business Initiative",
                "scope": "Full strategic assessment",
                "timeline": "2-3 weeks",
                "stakeholders": "Leadership team, Product team, Users",
            },
            "success_criteria": [
                "Clear strategic assessment with data-driven insights",
                "Actionable recommendations with implementation roadmap",
                "Risk analysis with mitigation strategies",
                "Stakeholder alignment on strategic direction",
            ],
            "quality_gates": [
                "Analysis backed by quantitative and qualitative data",
                "Recommendations are specific and measurable",
                "Risk assessment covers major concern areas",
                "Strategic options evaluated with trade-offs",
            ],
            "default_deliverables": [
                "Strategic analysis report",
                "Executive summary",
                "Implementation roadmap",
                "Risk mitigation plan",
            ],
            "follow_up_templates": [
                "Risk Assessment: {focus_area} Implementation",
                "Roadmap Planning: {focus_area} Execution",
            ],
            "metadata": {
                "complexity": "high",
                "requires_stakeholder_input": True,
                "typical_duration_days": 14,
            },
        }

    def _create_market_research_template(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create market research task template"""
        return {
            "title_template": "Market Research: {market_segment}",
            "description_template": """Conduct comprehensive market research for {market_segment}.

Research Areas:
- Market size and growth trends
- Customer segments and personas
- Competitive landscape
- Market opportunities and threats
- Pricing analysis

Target Markets: {target_markets}
Research Methods: {research_methods}""",
            "default_context": {
                "market_segment": "Target Market",
                "target_markets": "Primary and secondary markets",
                "research_methods": "Surveys, interviews, competitor analysis, market data",
            },
            "success_criteria": [
                "Comprehensive market size and growth analysis",
                "Detailed competitive landscape mapping",
                "Clear customer persona definitions",
                "Identified market opportunities and threats",
            ],
            "quality_gates": [
                "Data from multiple reliable sources",
                "Quantitative analysis supported by qualitative insights",
                "Competitive analysis covers key players",
                "Customer insights validated through primary research",
            ],
            "default_deliverables": [
                "Market research report",
                "Competitive analysis",
                "Customer personas",
                "Opportunity assessment",
            ],
        }

    def _create_competitive_analysis_template(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create competitive analysis task template"""
        return {
            "title_template": "Competitive Analysis: {competitor_focus}",
            "description_template": """Analyze competitive landscape for {competitor_focus}.

Key Competitors: {key_competitors}
Analysis Framework: {analysis_framework}
Focus Areas: {focus_areas}

This analysis will inform strategic positioning and competitive strategy.""",
            "default_context": {
                "competitor_focus": "Market Segment",
                "key_competitors": "Top 3-5 direct and indirect competitors",
                "analysis_framework": "Feature comparison, pricing, market positioning",
                "focus_areas": "Product features, pricing, marketing, strengths/weaknesses",
            },
            "success_criteria": [
                "Comprehensive competitor feature mapping",
                "Pricing strategy analysis and comparison",
                "SWOT analysis for each key competitor",
                "Competitive positioning recommendations",
            ],
            "quality_gates": [
                "Analysis covers both direct and indirect competitors",
                "Data is current and from reliable sources",
                "Includes both product and business model analysis",
                "Identifies clear competitive advantages and gaps",
            ],
            "default_deliverables": [
                "Competitive analysis report",
                "Feature comparison matrix",
                "SWOT analysis for key competitors",
                "Competitive positioning strategy",
            ],
        }

    def _create_feature_specification_template(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create feature specification task template"""
        return {
            "title_template": "Feature Specification: {feature_name}",
            "description_template": """Create detailed specification for {feature_name}.

User Stories: {user_stories}
Success Metrics: {success_metrics}
Technical Requirements: {technical_requirements}
Design Requirements: {design_requirements}

This specification will guide development and ensure feature meets user needs.""",
            "default_context": {
                "feature_name": "New Feature",
                "user_stories": "User journey and requirements",
                "success_metrics": "KPIs and success criteria",
                "technical_requirements": "System requirements and constraints",
                "design_requirements": "UX/UI requirements and guidelines",
            },
            "success_criteria": [
                "Complete user stories with acceptance criteria",
                "Technical requirements clearly defined",
                "Success metrics are measurable and trackable",
                "Design requirements align with user needs",
            ],
            "quality_gates": [
                "User stories follow standard format (As a... I want... So that...)",
                "Technical requirements are feasible and well-scoped",
                "Success metrics are SMART (Specific, Measurable, Achievable, Relevant, Time-bound)",
                "Edge cases and error scenarios covered",
            ],
            "default_deliverables": [
                "Feature specification document",
                "User stories with acceptance criteria",
                "Technical requirements",
                "Success metrics definition",
            ],
        }

    def _create_risk_assessment_template(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create risk assessment task template"""
        return {
            "title_template": "Risk Assessment: {risk_area}",
            "description_template": """Conduct comprehensive risk assessment for {risk_area}.

Assessment Scope: {assessment_scope}
Risk Categories: {risk_categories}
Impact Timeline: {impact_timeline}

This assessment will identify, analyze, and provide mitigation strategies for key risks.""",
            "default_context": {
                "risk_area": "Project/Initiative",
                "assessment_scope": "Full project lifecycle",
                "risk_categories": "Technical, Business, Operational, External",
                "impact_timeline": "Short-term (3 months) and long-term (1 year)",
            },
            "success_criteria": [
                "Comprehensive risk identification across all categories",
                "Risk prioritization based on probability and impact",
                "Detailed mitigation strategies for high-priority risks",
                "Monitoring and contingency plans defined",
            ],
            "quality_gates": [
                "Risk assessment covers all relevant categories",
                "Probability and impact assessments are data-driven",
                "Mitigation strategies are actionable and specific",
                "Contingency plans for high-impact scenarios",
            ],
            "default_deliverables": [
                "Risk assessment report",
                "Risk register with prioritization",
                "Mitigation strategies",
                "Contingency plans",
            ],
        }

    def _create_user_research_template(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create user research task template"""
        return {
            "title_template": "User Research: {research_focus}",
            "description_template": """Conduct user research study on {research_focus}.

Research Questions: {research_questions}
Target Users: {target_users}
Research Methods: {research_methods}
Timeline: {research_timeline}

This research will provide insights to inform product decisions and improve user experience.""",
            "default_context": {
                "research_focus": "User Behavior/Needs",
                "research_questions": "Key questions to answer about user needs and behavior",
                "target_users": "Primary user segments",
                "research_methods": "Interviews, surveys, usability testing, analytics",
                "research_timeline": "2-3 weeks for execution and analysis",
            },
            "success_criteria": [
                "Clear insights about user needs and behavior",
                "Actionable recommendations for product improvements",
                "User personas updated with new insights",
                "Research findings validated across user segments",
            ],
            "quality_gates": [
                "Research methodology appropriate for research questions",
                "Sample size sufficient for reliable insights",
                "Findings supported by both quantitative and qualitative data",
                "Insights translate to actionable product recommendations",
            ],
            "default_deliverables": [
                "User research report",
                "Key findings and insights",
                "Updated user personas",
                "Product recommendations",
            ],
        }

    def _create_technical_review_template(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create technical review task template"""
        return {
            "title_template": "Technical Review: {technical_area}",
            "description_template": """Conduct technical review of {technical_area}.

Review Scope: {review_scope}
Technical Criteria: {technical_criteria}
Quality Standards: {quality_standards}

This review will assess technical implementation and provide recommendations for improvement.""",
            "default_context": {
                "technical_area": "System/Component",
                "review_scope": "Architecture, code quality, performance, security",
                "technical_criteria": "Best practices, standards compliance, maintainability",
                "quality_standards": "Industry standards and internal guidelines",
            },
            "success_criteria": [
                "Comprehensive technical assessment completed",
                "Issues identified with severity classification",
                "Improvement recommendations prioritized",
                "Technical debt quantified and prioritized",
            ],
            "quality_gates": [
                "Review covers all specified technical areas",
                "Findings are well-documented with evidence",
                "Recommendations include implementation effort estimates",
                "Critical issues have immediate action plans",
            ],
            "default_deliverables": [
                "Technical review report",
                "Issues and recommendations matrix",
                "Technical debt assessment",
                "Improvement roadmap",
            ],
        }

    def _create_stakeholder_alignment_template(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create stakeholder alignment task template"""
        return {
            "title_template": "Stakeholder Alignment: {alignment_topic}",
            "description_template": """Facilitate stakeholder alignment on {alignment_topic}.

Key Stakeholders: {stakeholders}
Alignment Areas: {alignment_areas}
Decision Framework: {decision_framework}

This process will ensure stakeholders are aligned on key decisions and next steps.""",
            "default_context": {
                "alignment_topic": "Strategic Decision",
                "stakeholders": "Executive team, Product team, Engineering team",
                "alignment_areas": "Goals, priorities, resource allocation, timeline",
                "decision_framework": "Consensus building with clear decision criteria",
            },
            "success_criteria": [
                "Clear consensus on key decisions",
                "Stakeholder commitments documented",
                "Action items assigned with owners and timelines",
                "Communication plan for broader organization",
            ],
            "quality_gates": [
                "All key stakeholders participated in alignment process",
                "Decisions are documented with rationale",
                "Commitment levels clearly understood",
                "Escalation process defined for future conflicts",
            ],
            "default_deliverables": [
                "Stakeholder alignment summary",
                "Decision documentation",
                "Action items with owners",
                "Communication plan",
            ],
        }

    def _create_roadmap_planning_template(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create roadmap planning task template"""
        return {
            "title_template": "Roadmap Planning: {roadmap_scope}",
            "description_template": """Develop strategic roadmap for {roadmap_scope}.

Planning Horizon: {planning_horizon}
Key Initiatives: {key_initiatives}
Resource Constraints: {resource_constraints}
Success Metrics: {roadmap_metrics}

This roadmap will provide strategic direction and execution plan.""",
            "default_context": {
                "roadmap_scope": "Product/Initiative",
                "planning_horizon": "6-12 months with quarterly milestones",
                "key_initiatives": "Major features, improvements, technical initiatives",
                "resource_constraints": "Team capacity, budget, timeline constraints",
                "roadmap_metrics": "KPIs for measuring roadmap success",
            },
            "success_criteria": [
                "Clear roadmap with prioritized initiatives",
                "Resource allocation plan aligned with capacity",
                "Milestone definitions with success criteria",
                "Risk assessment for roadmap execution",
            ],
            "quality_gates": [
                "Initiatives prioritized based on strategic value",
                "Resource requirements realistic given constraints",
                "Dependencies identified and managed",
                "Roadmap flexibility built in for adjustments",
            ],
            "default_deliverables": [
                "Strategic roadmap",
                "Initiative prioritization matrix",
                "Resource allocation plan",
                "Milestone tracking framework",
            ],
        }

    def _create_performance_analysis_template(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create performance analysis task template"""
        return {
            "title_template": "Performance Analysis: {performance_area}",
            "description_template": """Analyze performance of {performance_area}.

Analysis Period: {analysis_period}
Key Metrics: {key_metrics}
Benchmarks: {benchmarks}
Improvement Areas: {improvement_focus}

This analysis will identify performance trends and improvement opportunities.""",
            "default_context": {
                "performance_area": "System/Product/Team",
                "analysis_period": "Last quarter with historical comparison",
                "key_metrics": "KPIs relevant to performance area",
                "benchmarks": "Industry standards and internal targets",
                "improvement_focus": "Areas with greatest improvement potential",
            },
            "success_criteria": [
                "Comprehensive performance assessment completed",
                "Performance trends identified and explained",
                "Improvement opportunities prioritized",
                "Action plan developed for key improvements",
            ],
            "quality_gates": [
                "Analysis based on reliable and comprehensive data",
                "Trends explained with root cause analysis",
                "Benchmarking provides meaningful context",
                "Improvement recommendations are actionable",
            ],
            "default_deliverables": [
                "Performance analysis report",
                "Trend analysis and insights",
                "Benchmark comparison",
                "Improvement action plan",
            ],
        }

    def list_available_templates(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get list of available templates with descriptions"""
        templates_info: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for template_type, template_data in self.templates.items():
            templates_info.append(
                {
                    "type": template_type.value,
                    "title_template": template_data["title_template"],
                    "default_deliverables": template_data["default_deliverables"],
                    "complexity": template_data.get("metadata", {}).get("complexity", "medium"),
                    "typical_duration_days": template_data.get("metadata", {}).get(
                        "typical_duration_days", 7
                    ),
                }
            )
        return templates_info

    def get_template_details(self, template_type: TaskTemplate) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get detailed information about a specific template"""
        template_data = self.templates.get(template_type)
        if not template_data:
            return None

        return {
            "type": template_type.value,
            "template_data": template_data,
            "required_context_variables": list(template_data["default_context"].keys()),
            "success_criteria_count": len(template_data["success_criteria"]),
            "quality_gates_count": len(template_data["quality_gates"]),
            "deliverables_count": len(template_data["default_deliverables"]),
        }

    def get_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get task generation metrics"""
        return {
            "total_generated": self._generated_count,
            "available_templates": len(self.templates),
            "template_types": [t.value for t in self.templates.keys()],
        }


# Global task template generator
_task_generator = TaskTemplateGenerator()


def get_task_generator() -> TaskTemplateGenerator:
    """Get the global task generator instance"""
    return _task_generator
