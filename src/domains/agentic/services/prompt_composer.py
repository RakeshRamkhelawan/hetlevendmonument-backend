"""
Prompt Composer - Domain-agnostic prompt composition for the agentic system.

Provides:
- Dynamic prompt template loading
- Domain context injection
- Multi-locale support
- User personalization
- Tool integration
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agentic.models import PromptTemplate, ToolDefinition, UserPersona
from src.domains.agentic.schemas import FeatureDefinition

logger = logging.getLogger(__name__)


@dataclass
class ComposedPrompt:
    """A fully composed prompt ready for LLM."""

    system_prompt: str
    tools: list[dict[str, object]]
    metadata: dict[str, object]


class DomainAgnosticPromptComposer:
    """
    Composes prompts dynamically based on feature, tenant, and user context.
    """

    # Base identity shared across all features
    BASE_IDENTITY = """Je bent een intelligente AI-assistent die werkt binnen een multi-tenant platform.
Je past je communicatiestijl aan op basis van de gebruiker en hun context.
Je bent behulpzaam, nauwkeurig, en geeft altijd actuele informatie.
Je respecteert privacy en volgt de richtlijnen van de organisatie."""

    # Domain-specific context templates
    DOMAIN_CONTEXTS = {
        "healthcare": """<domain_context>
Je werkt in de gezondheidszorg sector. BELANGRIJK:
- Geef NOOIT medisch advies of diagnoses
- Verwijs altijd naar gekwalificeerde zorgprofessionals voor medische vragen
- Focus op administratieve ondersteuning, planning, en informatieverstrekking
- Behandel alle patientgegevens als strikt vertrouwelijk (HIPAA/AVG compliant)
- Gebruik correcte medische terminologie maar leg uit in begrijpelijke taal
</domain_context>""",
        "finance": """<domain_context>
Je werkt in de financiele sector. BELANGRIJK:
- Geef NOOIT beleggingsadvies of financiele aanbevelingen
- Verwijs naar gekwalificeerde financiele adviseurs voor advies
- Focus op informatieverstrekking en administratieve ondersteuning
- Behandel alle financiele gegevens als strikt vertrouwelijk
- Vermeld altijd dat historische resultaten geen garantie zijn voor de toekomst
</domain_context>""",
        "cultural_heritage": """<domain_context>
Je werkt met cultureel erfgoed en historische collecties. RICHTLIJNEN:
- Behandel alle culturele items met respect
- Wees bewust van de culturele context en gevoeligheden
- Geef nauwkeurige historische informatie met bronvermelding
- Moedig educatief gebruik en culturele uitwisseling aan
- Wees inclusief en representeer diverse perspectieven
</domain_context>""",
        "education": """<domain_context>
Je werkt in het onderwijs. RICHTLIJNEN:
- Stimuleer kritisch denken en zelfstandig leren
- Geef antwoorden die aanzetten tot nadenken, niet alleen feiten
- Pas het niveau aan op de leerling (basis/gevorderd)
- Moedig vragen stellen aan
- Respecteer intellectuele eigendom en bronvermelding
</domain_context>""",
        "ecommerce": """<domain_context>
Je werkt in e-commerce en retail. RICHTLIJNEN:
- Help klanten met productvragen en bestellingen
- Wees transparant over prijzen, verzending en retourbeleid
- Respecteer consumentenrechten en privacywetgeving
- Focus op klanttevredenheid en probleemoplossing
- Geef eerlijke productinformatie zonder overdrijving
</domain_context>""",
        "legal": """<domain_context>
Je werkt in de juridische sector. BELANGRIJK:
- Geef NOOIT juridisch advies of interpretaties van wetgeving
- Verwijs altijd naar gekwalificeerde juristen voor juridische vragen
- Focus op informatieverstrekking en procedurele hulp
- Behandel alle juridische documenten als vertrouwelijk
- Wees precies in taalgebruik en terminologie
</domain_context>""",
    }

    def __init__(self) -> None:
        self._template_cache: dict[str, PromptTemplate] = {}
        self._tool_cache: dict[str, dict[str, object]] = {}

    async def compose_prompt(
        self,
        db: AsyncSession,
        feature: FeatureDefinition,
        tenant_industry: str | None = None,
        user_locale: str = "en_US",
        user_persona: UserPersona | None = None,
        additional_context: str | None = None,
    ) -> ComposedPrompt:
        """
        Compose a complete prompt for LLM interaction.
        """
        # Load prompt template
        template = await self._load_template(db, feature)

        # Build prompt sections
        sections: list[str] = []

        # 1. Base Identity
        sections.append(self._get_base_identity(user_locale))

        # 2. Domain Context (if applicable)
        domain_context = self._get_domain_context(feature.domain_context or tenant_industry)
        if domain_context:
            sections.append(domain_context)

        # 3. Feature Role (from template or feature)
        feature_role = self._get_feature_role(template, feature, user_locale)
        sections.append(feature_role)

        # 4. Capabilities (Removed - not in model)

        # 5. Constraints (Removed - not in model)

        # 6. User Personalization
        personalization = self._get_personalization(user_persona, user_locale)
        if personalization:
            sections.append(personalization)

        # 7. Output Format
        if template and template.output_format:
            sections.append(f"<output_format>\n{template.output_format}\n</output_format>")

        # 8. Additional Context
        if additional_context:
            sections.append(f"<additional_context>\n{additional_context}\n</additional_context>")

        # Load tools
        tools = await self._load_tools(db, feature)

        # Compose final prompt
        system_prompt = "\n\n".join(sections)

        return ComposedPrompt(
            system_prompt=system_prompt,
            tools=tools,
            metadata={
                "feature_id": feature.id,
                "template_id": template.id if template else None,
                "locale": user_locale,
                "domain": feature.domain_context or tenant_industry,
            },
        )

    async def _load_template(
        self, db: AsyncSession, feature: FeatureDefinition
    ) -> PromptTemplate | None:
        """Load prompt template for a feature."""
        if not feature.prompt_template_id:
            # Template ID is required - no fallback to explicit context search
            # as implicit linking is fragile and unsupported by Schema.
            return None

        # Load by ID
        stmt = select(PromptTemplate).where(
            PromptTemplate.id == feature.prompt_template_id,
            PromptTemplate.status == "active",
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_tools(
        self, db: AsyncSession, feature: FeatureDefinition
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Load tool definitions for a feature."""
        if not feature.available_tools:
            return []

        stmt = select(ToolDefinition).where(
            ToolDefinition.name.in_(feature.available_tools),
            ToolDefinition.is_active.is_(True),
        )
        result = await db.execute(stmt)
        tools = result.scalars().all()

        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.function_schema,  # Correct field mapping
            }
            for tool in tools
        ]

    def _get_base_identity(self, locale: str) -> str:
        """Get localized base identity."""
        # Could load from translation files
        return f"<identity>\n{self.BASE_IDENTITY}\n</identity>"

    def _get_domain_context(self, domain: str | None) -> str | None:
        """Get domain-specific context."""
        if not domain:
            return None

        context = self.DOMAIN_CONTEXTS.get(domain.lower())
        if context:
            return context

        # Generic domain context
        return f"""<domain_context>
Je werkt in het '{domain}' domein. Pas je communicatie en expertise
aan op deze context. Volg alle relevante industrie-standaarden en
regelgeving.
</domain_context>"""

    def _get_feature_role(
        self,
        template: PromptTemplate | None,
        feature: FeatureDefinition,
        locale: str,
    ) -> str:
        """Get feature-specific role description."""
        if template:
            # Use system_prompt from template as the role/core instruction
            # Ignoring localized_variants for now as it's JSON structure is complex/undefined here
            # Ideally would parse template.localized_variants
            return f"<feature_role>\n{template.system_prompt}\n</feature_role>"

        # Fallback to feature description DTO
        short_locale = locale.split("_")[0]
        description = feature.description.get(short_locale, feature.description.get("en", ""))
        return f"<feature_role>\nJe helpt met: {description}\n</feature_role>"

    def _get_personalization(self, persona: UserPersona | None, locale: str) -> str | None:
        """Get user personalization section."""
        if not persona:
            return None

        parts = ["<user_preferences>"]

        # Expertise level
        if persona.expertise_level <= 3:
            parts.append("- Geef uitgebreide uitleg met voorbeelden")
            parts.append("- Vermijd jargon of leg het uit")
        elif persona.expertise_level >= 8:
            parts.append("- Gebruiker is een expert, wees beknopt")
            parts.append("- Technische terminologie is acceptabel")

        # Structured output preference
        if persona.prefers_structured_output:
            parts.append("- Gebruik lijsten, tabellen en gestructureerde formats")

        # Concise preference
        if persona.prefers_concise_responses:
            parts.append("- Houd antwoorden kort en to-the-point")

        # Common topics
        if persona.common_topics:
            topics = ", ".join(persona.common_topics[:5])  # type: ignore[index]
            parts.append(f"- Frequente onderwerpen: {topics}")

        # Common mistakes to avoid
        if persona.common_mistakes:
            parts.append("- Let op veelgemaakte fouten en waarschuw proactief")

        # Common tools (from UserPersona)
        if persona.preferred_tools:
            # Just note them
            pass

        parts.append("</user_preferences>")

        if len(parts) > 2:  # More than just opening/closing tags
            return "\n".join(parts)
        return None

    def clear_cache(self) -> None:
        """Clear internal caches."""
        self._template_cache.clear()
        self._tool_cache.clear()


# Singleton instance
_composer_instance: DomainAgnosticPromptComposer | None = None


def get_prompt_composer() -> DomainAgnosticPromptComposer:
    """Get or create the global prompt composer instance."""
    global _composer_instance
    if _composer_instance is None:
        _composer_instance = DomainAgnosticPromptComposer()
    return _composer_instance
