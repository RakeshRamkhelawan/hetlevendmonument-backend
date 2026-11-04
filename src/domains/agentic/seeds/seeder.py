"""
Agentic System Seeder - Seeds the database with initial features, prompts, and tools.

This seeder creates:
- 8 platform features (general, workflow, data_analysis, etc.)
- 5 prompt templates
- 9 tool definitions
- Domain context configurations

Run with: python -m src.domains.agentic.seeds.seeder
"""

import asyncio
import logging
import os
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.database.bypass_session import adopt_tenant

from src.domains.agentic.models import Feature, PromptTemplate, ToolDefinition

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Platform Features
# ============================================================================

PLATFORM_FEATURES: list[dict[str, Any]] = [  # TODO(TYPE): replace Any with concrete type
    {
        "id": "general_assistant",
        "category": "general",
        "display_name": {
            "en": "General Assistant",
            "nl": "Algemene Assistent",
            "hi": "General Assistant",
        },
        "description": {
            "en": "General purpose AI assistant for any task",
            "nl": "Algemene AI-assistent voor elke taak",
            "hi": "General purpose AI assistant",
        },
        "domain_context": None,
        "route_patterns": ["/dashboard*", "/home*"],
        "intent_keywords": {
            "en": ["help", "question", "how to", "what is"],
            "nl": ["help", "vraag", "hoe", "wat is"],
        },
        "available_tools": ["search_knowledge", "web_search"],
        "required_permissions": [],
    },
    {
        "id": "workflow_builder",
        "category": "productivity",
        "display_name": {
            "en": "Workflow Builder",
            "nl": "Workflow Bouwer",
            "hi": "Workflow Builder",
        },
        "description": {
            "en": "Build and automate workflows with AI assistance",
            "nl": "Bouw en automatiseer workflows met AI-hulp",
            "hi": "Build and automate workflows",
        },
        "domain_context": None,
        "route_patterns": ["/workflows*", "/automation*", "/focus-builder*"],
        "intent_keywords": {
            "en": ["workflow", "automate", "trigger", "action", "flow"],
            "nl": ["workflow", "automatiseren", "trigger", "actie", "flow"],
        },
        "available_tools": ["create_workflow", "list_workflows", "execute_workflow"],
        "required_permissions": ["workflows:read", "workflows:write"],
    },
    {
        "id": "data_analyst",
        "category": "analytics",
        "display_name": {
            "en": "Data Analyst",
            "nl": "Data Analist",
            "hi": "Data Analyst",
        },
        "description": {
            "en": "Analyze data and generate insights",
            "nl": "Analyseer data en genereer inzichten",
            "hi": "Analyze data and generate insights",
        },
        "domain_context": None,
        "route_patterns": ["/analytics*", "/reports*", "/data*"],
        "intent_keywords": {
            "en": ["analyze", "data", "chart", "report", "statistics", "trend"],
            "nl": ["analyseer", "data", "grafiek", "rapport", "statistieken", "trend"],
        },
        "available_tools": ["query_database", "generate_chart", "export_report"],
        "required_permissions": ["analytics:read"],
    },
    {
        "id": "content_creator",
        "category": "content",
        "display_name": {
            "en": "Content Creator",
            "nl": "Content Creator",
            "hi": "Content Creator",
        },
        "description": {
            "en": "Create and edit content with AI assistance",
            "nl": "Maak en bewerk content met AI-hulp",
            "hi": "Create and edit content",
        },
        "domain_context": None,
        "route_patterns": ["/content*", "/editor*", "/posts*"],
        "intent_keywords": {
            "en": ["write", "content", "article", "post", "edit", "create"],
            "nl": ["schrijf", "content", "artikel", "post", "bewerk", "maak"],
        },
        "available_tools": ["generate_text", "summarize", "translate"],
        "required_permissions": ["content:write"],
    },
    {
        "id": "customer_support",
        "category": "support",
        "display_name": {
            "en": "Customer Support",
            "nl": "Klantenservice",
            "hi": "Customer Support",
        },
        "description": {
            "en": "Help customers with questions and issues",
            "nl": "Help klanten met vragen en problemen",
            "hi": "Help customers with questions",
        },
        "domain_context": None,
        "route_patterns": ["/support*", "/tickets*", "/help*"],
        "intent_keywords": {
            "en": ["support", "ticket", "issue", "problem", "customer"],
            "nl": ["support", "ticket", "probleem", "klant", "hulp"],
        },
        "available_tools": ["search_knowledge", "create_ticket", "lookup_customer"],
        "required_permissions": ["support:read"],
    },
    {
        "id": "code_assistant",
        "category": "development",
        "display_name": {
            "en": "Code Assistant",
            "nl": "Code Assistent",
            "hi": "Code Assistant",
        },
        "description": {
            "en": "Help with coding, debugging, and technical questions",
            "nl": "Help met coderen, debuggen en technische vragen",
            "hi": "Help with coding and debugging",
        },
        "domain_context": None,
        "route_patterns": ["/code*", "/dev*", "/api*"],
        "intent_keywords": {
            "en": ["code", "debug", "error", "function", "api", "programming"],
            "nl": ["code", "debug", "fout", "functie", "api", "programmeren"],
        },
        "available_tools": ["analyze_code", "execute_code", "search_docs"],
        "required_permissions": ["code:execute"],
    },
    {
        "id": "translator",
        "category": "content",
        "display_name": {"en": "Translator", "nl": "Vertaler", "hi": "Translator"},
        "description": {
            "en": "Translate content between languages",
            "nl": "Vertaal content tussen talen",
            "hi": "Translate content between languages",
        },
        "domain_context": None,
        "route_patterns": ["/translate*"],
        "intent_keywords": {
            "en": ["translate", "translation", "language", "convert"],
            "nl": ["vertaal", "vertaling", "taal", "converteer"],
        },
        "available_tools": ["translate"],
        "required_permissions": [],
    },
    {
        "id": "scheduler",
        "category": "productivity",
        "display_name": {"en": "Scheduler", "nl": "Planner", "hi": "Scheduler"},
        "description": {
            "en": "Schedule meetings and manage calendar",
            "nl": "Plan vergaderingen en beheer agenda",
            "hi": "Schedule meetings and manage calendar",
        },
        "domain_context": None,
        "route_patterns": ["/calendar*", "/schedule*", "/meetings*"],
        "intent_keywords": {
            "en": ["schedule", "meeting", "calendar", "appointment", "time"],
            "nl": ["plannen", "vergadering", "agenda", "afspraak", "tijd"],
        },
        "available_tools": ["create_event", "list_events", "check_availability"],
        "required_permissions": ["calendar:write"],
    },
]


# ============================================================================
# Prompt Templates
# ============================================================================

PROMPT_TEMPLATES: list[dict[str, Any]] = [  # TODO(TYPE): replace Any with concrete type
    {
        "name": "general_assistant_v1",
        "feature_context": "general_assistant",
        "version": 1,
        "status": "active",
        "feature_role": """Je bent een behulpzame, nauwkeurige en vriendelijke AI-assistent.
Je helpt gebruikers met allerlei taken en vragen.
Je geeft duidelijke, beknopte antwoorden tenzij meer detail gevraagd wordt.
Je bent eerlijk als je iets niet weet en voorkomt hallucinaties.""",
        "capabilities": """- Beantwoord algemene vragen
- Help met informatie zoeken
- Geef uitleg over complexe onderwerpen
- Assisteer met schrijftaken
- Brainstorm ideeen""",
        "constraints": """- Geef geen medisch, juridisch of financieel advies
- Vermijd controversiele onderwerpen
- Respecteer privacy en vertrouwelijkheid
- Wees transparant over je beperkingen""",
        "output_format": """Antwoord in Markdown formaat waar mogelijk.
Gebruik lijsten voor opsommingen.
Gebruik codeblokken voor code of technische content.""",
    },
    {
        "name": "workflow_builder_v1",
        "feature_context": "workflow_builder",
        "version": 1,
        "status": "active",
        "feature_role": """Je bent een expert workflow automatisering assistent.
Je helpt gebruikers bij het ontwerpen, bouwen en debuggen van geautomatiseerde workflows.
Je begrijpt triggers, acties, condities en loops in workflow context.""",
        "capabilities": """- Ontwerp workflows stap voor stap
- Stel triggers en acties voor
- Debug workflow problemen
- Optimaliseer bestaande workflows
- Leg workflow concepten uit""",
        "constraints": """- Test geen workflows in productie zonder bevestiging
- Vraag om verduidelijking bij complexe requirements
- Waarschuw voor potentiele infinite loops of fouten""",
        "output_format": """Beschrijf workflows als genummerde stappen.
Gebruik mermaid diagrammen voor visualisatie.
Geef YAML/JSON voorbeelden waar relevant.""",
    },
    {
        "name": "data_analyst_v1",
        "feature_context": "data_analyst",
        "version": 1,
        "status": "active",
        "feature_role": """Je bent een data analyse expert.
Je helpt gebruikers data te begrijpen, analyseren en visualiseren.
Je geeft inzichten en aanbevelingen op basis van data.""",
        "capabilities": """- Analyseer datasets
- Genereer statistieken en samenvattingen
- Maak grafieken en visualisaties
- Identificeer trends en patronen
- Exporteer rapporten""",
        "constraints": """- Trek geen conclusies uit onvoldoende data
- Vermeld altijd sample sizes en beperkingen
- Respecteer data privacy regelgeving""",
        "output_format": """Gebruik tabellen voor numerieke data.
Beschrijf bevindingen in bullets.
Voeg altijd een samenvatting toe.""",
    },
    {
        "name": "content_creator_v1",
        "feature_context": "content_creator",
        "version": 1,
        "status": "active",
        "feature_role": """Je bent een creatieve content specialist.
Je helpt met het schrijven, bewerken en verbeteren van content.
Je past je stijl aan op het doel en de doelgroep.""",
        "capabilities": """- Schrijf artikelen, blogs, posts
- Bewerk en verbeter teksten
- Suggereer headlines en hooks
- Pas tone of voice aan
- Genereer SEO-optimalisatie ideeen""",
        "constraints": """- Plagieer nooit bestaande content
- Respecteer copyright en intellectueel eigendom
- Vraag om context bij onduidelijke opdrachten""",
        "output_format": """Lever content in het gevraagde formaat.
Geef meerdere opties waar mogelijk.
Markeer suggesties voor wijzigingen duidelijk.""",
    },
    {
        "name": "code_assistant_v1",
        "feature_context": "code_assistant",
        "version": 1,
        "status": "active",
        "feature_role": """Je bent een senior software engineer en code mentor.
Je helpt met coderen, debuggen en beste practices.
Je schrijft schone, leesbare en goed gedocumenteerde code.""",
        "capabilities": """- Schrijf en review code
- Debug fouten en exceptions
- Leg technische concepten uit
- Suggereer verbeteringen en refactoring
- Help met API integraties""",
        "constraints": """- Schrijf geen malicieuze code
- Vermijd onveilige praktijken
- Geef security waarschuwingen waar nodig
- Test code mentaal voor suggesties""",
        "output_format": """Gebruik altijd syntax-highlighted codeblokken.
Voeg inline comments toe voor uitleg.
Geef voorbeelden van gebruik.""",
    },
]


# ============================================================================
# Tool Definitions
# ============================================================================

TOOL_DEFINITIONS: list[dict[str, Any]] = [  # TODO(TYPE): replace Any with concrete type
    {
        "name": "search_knowledge",
        "description": "Search the knowledge base for relevant information",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "description": "Max results",
                },
            },
            "required": ["query"],
        },
        "returns_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "score": {"type": "number"},
                },
            },
        },
        "category": "knowledge",
        "required_permissions": [],
        "rate_limit": 60,
    },
    {
        "name": "web_search",
        "description": "Search the web for current information",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        "returns_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "snippet": {"type": "string"},
                },
            },
        },
        "category": "search",
        "required_permissions": ["web:access"],
        "rate_limit": 30,
    },
    {
        "name": "create_workflow",
        "description": "Create a new automated workflow",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Workflow name"},
                "trigger": {"type": "object", "description": "Trigger configuration"},
                "actions": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["name", "trigger"],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "status": {"type": "string"},
            },
        },
        "category": "workflow",
        "required_permissions": ["workflows:write"],
        "rate_limit": 10,
    },
    {
        "name": "list_workflows",
        "description": "List user's workflows",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "draft", "disabled"]},
                "limit": {"type": "integer", "default": 20},
            },
        },
        "returns_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
        },
        "category": "workflow",
        "required_permissions": ["workflows:read"],
        "rate_limit": 60,
    },
    {
        "name": "query_database",
        "description": "Execute a safe read-only database query",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query_description": {
                    "type": "string",
                    "description": "Natural language query",
                },
                "table": {"type": "string", "description": "Target table/dataset"},
                "filters": {"type": "object"},
            },
            "required": ["query_description"],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "array"},
                "row_count": {"type": "integer"},
                "columns": {"type": "array", "items": {"type": "string"}},
            },
        },
        "category": "data",
        "required_permissions": ["data:query"],
        "rate_limit": 30,
    },
    {
        "name": "generate_chart",
        "description": "Generate a chart visualization from data",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "line", "pie", "scatter", "area"],
                },
                "data": {"type": "array"},
                "x_axis": {"type": "string"},
                "y_axis": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["chart_type", "data"],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "chart_url": {"type": "string"},
                "chart_config": {"type": "object"},
            },
        },
        "category": "visualization",
        "required_permissions": ["analytics:read"],
        "rate_limit": 30,
    },
    {
        "name": "translate",
        "description": "Translate text between languages",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to translate"},
                "source_lang": {
                    "type": "string",
                    "description": "Source language code",
                },
                "target_lang": {
                    "type": "string",
                    "description": "Target language code",
                },
            },
            "required": ["text", "target_lang"],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "translated_text": {"type": "string"},
                "detected_source": {"type": "string"},
            },
        },
        "category": "language",
        "required_permissions": [],
        "rate_limit": 60,
    },
    {
        "name": "create_event",
        "description": "Create a calendar event",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_time": {"type": "string", "format": "date-time"},
                "end_time": {"type": "string", "format": "date-time"},
                "attendees": {"type": "array", "items": {"type": "string"}},
                "description": {"type": "string"},
            },
            "required": ["title", "start_time", "end_time"],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "calendar_link": {"type": "string"},
            },
        },
        "category": "calendar",
        "required_permissions": ["calendar:write"],
        "rate_limit": 20,
    },
    {
        "name": "send_notification",
        "description": "Send a notification to user or channel",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "channel": {
                    "type": "string",
                    "enum": ["email", "slack", "in_app", "sms"],
                },
                "recipient": {"type": "string"},
            },
            "required": ["message", "channel"],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "notification_id": {"type": "string"},
                "status": {"type": "string"},
            },
        },
        "category": "notification",
        "required_permissions": ["notifications:send"],
        "rate_limit": 30,
    },
]


# ============================================================================
# Seeder Functions
# ============================================================================


async def seed_features(session: AsyncSession, tenant_id: int = 1) -> int:
    """Seed platform features.

    SP-DATA-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 Groep D): Feature.tenant_id is
    NOT NULL (ADR-005) -- tenant_id is now an explicit parameter (default 1,
    the system/platform tenant, for backward-compatible standalone script usage)
    instead of being silently omitted.
    """
    count: int = 0
    for feature_data in PLATFORM_FEATURES:
        # Prepare data for new schema
        data = feature_data.copy()

        # Transform display_name (dict) -> name (string)
        if isinstance(data.get("display_name"), dict):
            data["name"] = data["display_name"].get("en", "Unknown")
            del data["display_name"]

        # Transform description (dict) -> description (string)
        if isinstance(data.get("description"), dict):
            data["description"] = data["description"].get("en", "")

        # Remove fields dropped in schema
        if "available_tools" in data:
            del data["available_tools"]
        if "required_permissions" in data:
            del data["required_permissions"]

        if "tenant_id" not in data:
            data["tenant_id"] = tenant_id

        # Check if exists
        stmt = select(Feature).where(Feature.id == data["id"], Feature.tenant_id == tenant_id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"Feature '{data['id']}' already exists, updating...")
            for key, value in data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
        else:
            feature = Feature(**data)
            session.add(feature)
            count += 1

    await session.commit()
    logger.info(f"Seeded {count} new features")
    return count


async def seed_prompts(session: AsyncSession, tenant_id: int = 1) -> int:
    """Seed prompt templates.

    SP-DATA-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 Groep D): tenant_id is now an
    explicit parameter (default 1, the system/platform tenant) instead of a
    hardcoded literal.
    """
    count: int = 0
    for template_data in PROMPT_TEMPLATES:
        data = template_data.copy()

        # Construct system_prompt from role/capabilities/constraints
        role = data.pop("feature_role", "")
        caps = data.pop("capabilities", "")
        cons = data.pop("constraints", "")

        data["system_prompt"] = f"{role}\n\nCapabilities:\n{caps}\n\nConstraints:\n{cons}".strip()

        # Ensure version is string (DB mismatch)
        if "version" in data:
            data["version"] = str(data["version"])

        # Remove dropped fields
        if "feature_context" in data:
            del data["feature_context"]
        if "output_format" in data:
            # output_format kept but shorter? Check length.
            # If too long, maybe move to system_prompt?
            # Model: String(50). Seeder: Long string.
            # Move output_format to system_prompt appendix
            out_fmt = data.pop("output_format", "")
            if out_fmt:
                data["system_prompt"] += f"\n\nOutput Format:\n{out_fmt}"

        # Add required defaults
        if "supported_locales" not in data:
            data["supported_locales"] = ["en", "nl"]
        if "tenant_id" not in data:
            data["tenant_id"] = tenant_id
        if "created_by" not in data:
            data["created_by"] = 1

        # Check if exists
        stmt = select(PromptTemplate).where(
            PromptTemplate.name == data["name"], PromptTemplate.tenant_id == tenant_id
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"Template '{data['name']}' already exists, updating...")
            for key, value in data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            template = existing
        else:
            template = PromptTemplate(**data)
            session.add(template)
            count += 1

        # Link to Feature
        feature_id = template_data.get("feature_context")
        if feature_id:
            await session.flush()  # Get template ID
            stmt = select(Feature).where(Feature.id == feature_id)
            result = await session.execute(stmt)
            feature = result.scalar_one_or_none()
            if feature:
                feature.prompt_template_id = template.id
                session.add(feature)
                logger.info(f"Linked template '{template.name}' to feature '{feature.id}'")

    await session.commit()
    logger.info(f"Seeded {count} new prompt templates")
    return count


async def seed_tools(session: AsyncSession, tenant_id: int = 1) -> int:
    """Seed tool definitions.

    SP-DATA-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 Groep D): ToolDefinition.tenant_id
    is NOT NULL (ADR-005) -- tenant_id is now an explicit parameter (default 1,
    the system/platform tenant) instead of being silently omitted.
    """
    count: int = 0
    for tool_data in TOOL_DEFINITIONS:
        data = tool_data.copy()

        # Add display_name
        if "display_name" not in data:
            data["display_name"] = data["name"].replace("_", " ").title()

        # Rename parameters_schema -> function_schema
        if "parameters_schema" in data:
            data["function_schema"] = data.pop("parameters_schema")
        elif "function_schema" not in data:
            data["function_schema"] = {}  # Should not happen if data is correct

        # Remove dropped fields
        if "module_path" in data:
            del data["module_path"]
        if "compatible_features" in data:
            del data["compatible_features"]
        if "returns_schema" in data:
            del data["returns_schema"]
        if "rate_limit" in data:
            del data["rate_limit"]

        if "tenant_id" not in data:
            data["tenant_id"] = tenant_id

        # Check if exists
        stmt = select(ToolDefinition).where(
            ToolDefinition.name == data["name"], ToolDefinition.tenant_id == tenant_id
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"Tool '{data['name']}' already exists, updating...")
            for key, value in data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
        else:
            tool = ToolDefinition(**data)
            session.add(tool)
            count += 1

    await session.commit()
    logger.info(f"Seeded {count} new tool definitions")
    return count


async def run_seeder(
    database_url: str | None = None,
    tenant_id: int = 1,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Run all seeders voor EEN klant.

    `tenant_id` stond tot 2026-09-16 alleen als default op de drie zaaifuncties zelf en
    was hier niet zichtbaar. Nu staat hij waar hij hoort: dit script zaait platformdata
    voor precies een klant, en die keuze hoort aanwijsbaar te zijn (ADR-036 OP-153).
    """
    url = database_url or os.getenv("DATABASE_URL")

    if not url:
        raise ValueError("DATABASE_URL must be provided or set as environment variable")

    # Convert to async URL if needed
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        # De klant wordt AANGENOMEN en niet alleen als default doorgegeven (OP-153).
        #
        # Dit script draait met de hand (`python -m src.domains.agentic.seeds.seeder`),
        # buiten elk verzoek, dus de ContextVar is leeg. De drie zaaifuncties filteren op
        # `tenant_id` in Python, maar `features`, `prompt_templates` en `tool_definitions`
        # hebben ook een afschermingsregel in de database en die leest de klant uit
        # `app.current_tenant`. Zonder deze regel faalt elke INSERT zodra `DATABASE_URL`
        # naar `sanskritisetu_app` wijst.
        #
        # De commits zitten IN de zaaifuncties en dus binnen dit blok. Dat is nodig:
        # `session.add(...)` stuurt nog geen SQL, de INSERT volgt pas bij de flush die de
        # commit veroorzaakt -- een commit buiten het blok zou de INSERTs alsnog zonder
        # klantcontext uitvoeren.
        async with adopt_tenant(session, tenant_id):
            features = await seed_features(session, tenant_id)
            prompts = await seed_prompts(session, tenant_id)
            tools = await seed_tools(session, tenant_id)

    await engine.dispose()

    return {
        "features_seeded": features,
        "prompts_seeded": prompts,
        "tools_seeded": tools,
    }


if __name__ == "__main__":
    import sys

    # Allow DB URL override
    db_url: str | None = sys.argv[1] if len(sys.argv) > 1 else None

    if db_url is None:
        db_url = os.getenv("DATABASE_URL")

    if db_url is None:
        print("Error: DATABASE_URL must be provided or set as environment variable")
        sys.exit(1)

    result = asyncio.run(run_seeder(db_url))
    print("\nSeeding complete!")
    print(f"  Features: {result['features_seeded']}")
    print(f"  Prompts: {result['prompts_seeded']}")
    print(f"  Tools: {result['tools_seeded']}")
