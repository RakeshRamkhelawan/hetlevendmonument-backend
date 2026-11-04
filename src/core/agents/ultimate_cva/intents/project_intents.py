
from src.domains.projects.models import ProjectConfig, ProjectIteration
from src.domains.projects.repository import ProjectRepository


class ProjectIntentHandler:
    """
    Handles CVA intents related to Project Management.
    Translates user chat -> ProjectConfig.
    """

    async def handle_create_project(self, user_text: str, user_id: str, tenant_id: str = "") -> str:
        """
        Analyzes text, detects recurring patterns, creates project.
        """
        # 1. LLM Extraction (Simulated here for speed/determinism)
        # In real CVA, we would ask: "Extract project_name, iterations, etc."

        # Hardcoded extraction based on your specific use-case description for the demo
        is_eu_visit = "werkbezoek" in user_text.lower() and "9" in user_text

        if not is_eu_visit:
            # Fallback for generic projects
            return "I detected a project request, but could not extract the details. Please specify the name and number of iterations."

        # 2. Construct Configuration
        config = ProjectConfig(
            name="EU Werkbezoek Cyclus",
            description="Maandelijkse werkbezoeken met content creatie en stakeholder communicatie.",
            domain="MARKETING",
            tenant_id=tenant_id,
            owner_id=user_id,
            sop_ref="SOP-RECURRING-EVENT",  # The Meta-SOP we will create next
            static_context={
                "tone": "British English",
                "guidelines": "Standard Corp Guidelines",
                "fixed_program": "Oktober Event Presentatie",
            },
            required_vars=["location", "ilo_name", "date", "security_details"],
        )

        # 3. Create Iterations (The 9 visits)
        for i in range(1, 10):
            config.iterations.append(ProjectIteration(index=i))

        # 4. Save to Memory
        repo = ProjectRepository(tenant_id=tenant_id)
        await repo.save(config)

        return (
            f"Begrepen. Ik heb het project **'{config.name}'** aangemaakt.\n"
            f"- **Iteraties:** {len(config.iterations)}\n"
            f"- **Vaste Context:** British English, Oktober Event.\n"
            f"- **Variabelen per keer:** Locatie, ILO Naam, Datum.\n\n"
            f"Ik heb de eerste iteratie (Bezoek 1) klaargezet. Zodra je de locatie weet, begin ik."
        )


# Singleton
project_handler = ProjectIntentHandler()
