"""
AI Persona models for customizing agent behavior.
"""

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.database import Base


class PersonaCategory(str, enum.Enum):
    """Categories for AI personas."""

    TECHNICAL = "technical"
    CREATIVE = "creative"
    ANALYTICAL = "analytical"
    SUPPORTIVE = "supportive"
    EXPERT = "expert"
    CUSTOM = "custom"


class Persona(Base):  # type: ignore[misc]
    """AI Persona model - defines behavior and tone of AI interactions."""

    __tablename__ = "personas"
    __table_args__ = (UniqueConstraint("id", "tenant_id", name="uq_personas_id_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    category = mapped_column(Enum(PersonaCategory), default=PersonaCategory.CUSTOM, nullable=False)

    # The actual system prompt that modifies AI behavior
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional style parameters
    temperature: Mapped[str | None] = mapped_column(String(10), default="0.7")  # LLM temperature
    verbosity: Mapped[str | None] = mapped_column(
        String(20), default="balanced"
    )  # brief, balanced, detailed
    tone = mapped_column(
        String(50), default="professional"
    )  # professional, friendly, formal, casual

    # Metadata
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool | None] = mapped_column(Boolean, default=False)
    is_system: Mapped[bool | None] = mapped_column(
        Boolean, default=False
    )  # System-defined vs user-created

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    #
    # `foreign_keys` is VERPLICHT sinds de samengestelde sleutels van OP-160 (2026-09-15).
    # `user_persona_preferences` verwijst nu op TWEE manieren naar `personas`: de
    # enkelvoudige `persona_id -> personas.id` en de samengestelde
    # `(persona_id, tenant_id) -> personas(id, tenant_id)`. SQLAlchemy kan dan niet meer
    # zelf bepalen waarop het moet koppelen en werpt `AmbiguousForeignKeysError` zodra
    # deze relatie wordt geconfigureerd.
    #
    # Gemeten 2026-09-16: dat raakte 371 tests in de volledige poort. De fout zat er sinds
    # 2026-09-15 al in, maar bleef verborgen zolang deze twee modellen in een testrun niet
    # samen geladen werden; imports die op 2026-09-16 zijn toegevoegd trokken de rest van
    # de modelgraaf wel mee en maakten hem overal zichtbaar.
    #
    # De koppeling gaat bewust via de ENKELVOUDIGE sleutel: dat is precies het gedrag van
    # voor OP-160. De samengestelde sleutel blijft doen waarvoor hij is toegevoegd -- de
    # tenant-integriteit in de DATABASE afdwingen -- en dat staat los van hoe de ORM leest.
    user_preferences = relationship(
        "UserPersonaPreference",
        back_populates="persona",
        foreign_keys="UserPersonaPreference.persona_id",
    )


class UserPersonaPreference(Base):  # type: ignore[misc]
    """User's active persona selection."""

    __tablename__ = "user_persona_preferences"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "tenant_id",
            name="uq_user_persona_preferences_user_tenant",
        ),
        # SAMENGESTELDE verwijzingen: die dwingen af dat een voorkeur bij een gebruiker en
        # een persona van DEZELFDE tenant hoort. Een enkelvoudige verwijzing naar `users.id`
        # doet dat niet -- daarmee kan een rij van tenant A naar een gebruiker van tenant B
        # wijzen.
        #
        # Deze twee stonden tot 2026-09-15 alleen in
        # `20260529b_harden_user_persona_preferences_tenant_integrity.py:58-73` en NIET in
        # dit model (ADR-036 OP-160). Dat is geen cosmetisch verschil: een schema dat uit de
        # MODELLEN wordt gebouwd -- `Base.metadata.create_all`, wat een deel van de tests
        # doet -- kreeg de zwakkere variant. Een cross-tenant schrijf die productie weigert,
        # liet zo'n test gewoon door; de test was dan groen over iets wat in productie niet
        # kan. Gemeten op een verse keten: de database heeft vijf verwijzingen op deze
        # tabel, het model had er drie.
        #
        # De enkelvoudige verwijzingen hieronder blijven staan: die bestaan in de database
        # ook nog (`user_persona_preferences_user_id_fkey`,
        # `user_persona_preferences_persona_id_fkey`), en het model hoort de database te
        # beschrijven zoals hij IS.
        ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_user_persona_preferences_user_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["persona_id", "tenant_id"],
            ["personas.id", "personas.tenant_id"],
            name="fk_user_persona_preferences_persona_tenant",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    persona_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("personas.id", ondelete="CASCADE"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    # Zie de toelichting bij `Persona.user_preferences`: `foreign_keys` is nodig omdat er
    # twee verwijzingen naar `personas` bestaan sinds OP-160.
    persona = relationship(
        "Persona",
        back_populates="user_preferences",
        foreign_keys=[persona_id],
    )


# Default system personas to seed
DEFAULT_PERSONAS = [
    {
        "name": "Technical Expert",
        "description": "Precise, code-focused responses with technical depth. Ideal for development tasks.",
        "category": PersonaCategory.TECHNICAL,
        "system_prompt": """You are a highly skilled technical expert with deep knowledge in software development,
architecture, and best practices. Provide precise, code-focused responses. When explaining concepts,
include code examples where appropriate. Focus on accuracy, efficiency, and following established patterns.""",
        "temperature": "0.3",
        "verbosity": "detailed",
        "tone": "professional",
        "is_system": True,
    },
    {
        "name": "Creative Collaborator",
        "description": "Imaginative and exploratory, perfect for brainstorming and ideation.",
        "category": PersonaCategory.CREATIVE,
        "system_prompt": """You are a creative collaborator who thinks outside the box. Offer imaginative solutions
and explore multiple possibilities. Encourage brainstorming and build upon ideas. Be enthusiastic
and supportive while maintaining practical considerations.""",
        "temperature": "0.9",
        "verbosity": "balanced",
        "tone": "friendly",
        "is_system": True,
    },
    {
        "name": "Data Analyst",
        "description": "Structured, metrics-driven insights with focus on data interpretation.",
        "category": PersonaCategory.ANALYTICAL,
        "system_prompt": """You are a data analyst focused on structured, metrics-driven insights. Approach problems
methodically, break down complex analyses into steps, and provide evidence-based recommendations.
Use tables and structured formats when presenting data. Be precise with numbers and statistics.""",
        "temperature": "0.4",
        "verbosity": "detailed",
        "tone": "formal",
        "is_system": True,
    },
    {
        "name": "Mentor Guide",
        "description": "Patient and educational, focuses on teaching and explaining concepts.",
        "category": PersonaCategory.SUPPORTIVE,
        "system_prompt": """You are a patient mentor and guide. Explain concepts clearly and break down complex topics
into digestible parts. Encourage learning and ask guiding questions. Celebrate progress and provide
constructive feedback. Adapt explanations to the user's level of understanding.""",
        "temperature": "0.6",
        "verbosity": "detailed",
        "tone": "friendly",
        "is_system": True,
    },
    {
        "name": "Efficiency Expert",
        "description": "Concise and action-oriented, provides quick solutions and direct answers.",
        "category": PersonaCategory.EXPERT,
        "system_prompt": """You are an efficiency expert who values brevity and action. Provide concise,
direct answers without unnecessary elaboration. Focus on actionable recommendations and quick solutions.
Use bullet points and clear structure. Time is valuable - get to the point quickly.""",
        "temperature": "0.5",
        "verbosity": "brief",
        "tone": "professional",
        "is_system": True,
    },
]
