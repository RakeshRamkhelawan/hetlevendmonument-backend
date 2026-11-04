import json
import logging
from pathlib import Path
from typing import Any

from src.core.als.agents.skill_manifest import SkillManifest
from src.core.als.agents.specialist_base import BaseSpecialistAgent
from src.core.services.llm.base import LLMMessage
from src.core.shared.interfaces import ExecutionResult

logger = logging.getLogger(__name__)


class SkillsGapTrainingSkill(BaseSpecialistAgent):
    """
    Skills Gap Training worker agent.

    Loaded from ``manifests/skillsgaptraining.yml``; behavior is driven by the manifest
    and executed through the shared BaseSpecialistAgent OODA loop.
    """

    def __init__(self, tenant_id: int, **kwargs: Any) -> None:
        manifest = SkillManifest.load(Path(__file__).parent / "manifests/skillsgaptraining.yml")
        config = manifest.to_config()
        # Merge any runtime overrides passed by the caller
        config.update(kwargs)
        super().__init__(config=config, tenant_id=tenant_id)

    async def act(self, decision: str) -> ExecutionResult:
        """Execute using the shared OODA/tool runtime instead of a hardcoded stub."""
        logger.info(f"[{self.agent_id}] Executing via shared runtime for tenant {self.tenant_id}")
        return await super().act(decision)

    def _build_user_prompt(self, params: dict[str, object]) -> str:
        """De taak zoals het manifest hem declareert: `task` verplicht, `context` optioneel.

        `input_schema` in `manifests/skillsgaptraining.yml` schrijft precies deze twee velden
        voor. Onbekende sleutels gaan bewust MEE in plaats van weggefilterd te worden: de
        aanroeper (`packs.py::_execute_step`) geeft de stap-parameters door, en stil weglaten
        zou het model laten werken met minder dan de gebruiker heeft gevraagd -- dezelfde
        klasse fout als het stille afkappen dat AUDIT-009 blootlegde.
        """
        task = str(params.get("task", "")).strip()
        extra = {k: v for k, v in params.items() if k != "task"}
        lines = [f"Task: {task}" if task else "Task: (geen taakomschrijving meegegeven)"]
        if extra:
            lines.append(f"Context: {json.dumps(extra, ensure_ascii=True, default=str)}")
        return "\n".join(lines)

    def _met_toolnamen(self, system_prompt: str) -> str:
        """Zet de toegestane toolnamen IN de prompt, want anders ziet het model ze nooit.

        **Gemeten 2026-09-20, en dit was een echte storing.** De manifest-prompt zegt "You may
        use only the tools listed under allowed_tools in your manifest", maar geen van de zes
        namen staat in die tekst -- het model krijgt een verwijzing naar een lijst die hij niet
        heeft. Gevolg, drie keer gemeten tegen llama3.2:3b: het model verzon toolnamen
        (`databroker.get-organisaties`, `get_department_training`) en zelfs een eigen
        directive-vorm (`DATA_REQUEST:`). Nul van de drie antwoorden leverde een bruikbare
        TOOL_CALL op. Dat is geen modelprobleem: zonder de namen kan geen enkel model kiezen.

        **Waarom hier en niet in het manifest.** Een lijst die je in de prompttekst typt, loopt
        uit de pas met `allowed_tools` zodra iemand er een toevoegt of weghaalt -- en dan
        verwijst de prompt naar rechten die de agent niet heeft, of andersom. Hier afgeleid van
        dezelfde bron die de broker gebruikt, dus ze kunnen niet uit elkaar lopen. Bewaakt door
        `tests/unit/als/test_de_prompt_noemt_de_toegestane_tools.py`.

        Lege lijst -> prompt ongewijzigd: dan is er niets te noemen, en een zin als "je mag
        deze tools gebruiken: (niets)" nodigt juist uit tot verzinnen.
        """
        namen = [str(naam) for naam in self.allowed_tools if str(naam).strip()]
        if not namen:
            return system_prompt
        regels = [system_prompt.rstrip(), "",
                  "The tools listed under allowed_tools in your manifest are exactly these, "
                  "and nothing else is available to you:"]
        # De parser is verankerd op regelbegin (`^TOOL_CALL:`) en dat blijft zo: die ankering
        # voorkomt dat een tool-aanroep die ergens IN een tekst staat -- bijvoorbeeld in een
        # geciteerd document -- wordt uitgevoerd. Gemeten 2026-09-20 zette llama3.2:3b er
        # regelmatig "Directive:" voor, waardoor een verder correcte aanroep werd genegeerd.
        # Het model bijsturen is de goede kant op; de veiligheidsankering oprekken niet.
        regels.append(
            "A TOOL_CALL must be alone on its own line and that line must START with "
            "TOOL_CALL: -- never put any word, label or prefix before it. The arguments "
            "are a single JSON object with double quotes, never command-line flags. "
            "Exactly like this:"
        )
        # Een VOORBEELD en niet alleen een beschrijving. Gemeten 2026-09-20 tegen
        # llama3.2:3b: met alleen de beschrijving koos het model vijf van de vijf keer de
        # juiste tool op de juiste regel, maar schreef het de argumenten als
        # `-- department="Financieel"` in plaats van JSON. Een klein model leest een
        # voorbeeld beter dan een specificatie; dat is geen theorie maar de meting hierboven.
        # Het voorbeeld gebruikt bewust een rol die NIET in de piloot-taken voorkomt. Met
        # "Finance Analyst" als voorbeeldwaarde is niet te zien of het model het formaat
        # begrijpt of de waarde overschrijft -- dan meet je napraten. Gecontroleerd op
        # 2026-09-20 met een taak over een andere rol: het model vulde de eigen rol in.
        regels.append('TOOL_CALL: ' + (namen[0] if namen else 'tool_name') + ' {"role": "Warehouse Operator"}')
        regels.extend("- " + naam for naam in namen)
        return "\n".join(regels)

    async def execute_with_manifest_prompt(
        self,
        params: dict[str, object],
        *,
        initiated_by_user_id: int | None = None,
    ) -> ExecutionResult:
        """Het piloot-pad van ADR-036 D10: uitvoeren met de systeemprompt UIT het manifest.

        Dit is de methode die `packs.py::_execute_step` aanroept en die het `_ManifestPromptSkill`
        Protocol daar voorschrijft. Tot 2026-08-15 bestond hij niet: de aanroep stond er, achter
        een `cast` die de typecontrole op precies die regel uitzette, en elke uitvoering van de
        piloot eindigde daardoor in een `AttributeError` die als "mislukt" werd gerapporteerd.
        Elf tests legden het gedrag al volledig vast (BE-AGT-041/042/044) en stonden rood.

        **Waarom hier en niet op `BaseSpecialistAgent`.** De OODA-weg bouwt zijn eigen
        systeemprompt uit `config["name"]`/`["description"]` (`specialist_base.orient()`) en
        negeert `system_prompt` uit het manifest -- dat is ADR-036 OP-10, en of dat globaal of
        per skill wordt opgelost is een openstaande beslissing. Deze methode alleen op de piloot
        zetten respecteert die beslissing en houdt de basisklasse generiek, precies zoals
        `loader.get_agent_instance()` het beschrijft.

        **Wat het budget doet.** Alles loopt via `_run_within_budget()`, hetzelfde afdwingpunt
        als de OODA-weg: tenant-prana vooraf, `timeout_seconds` als binnenste tijdsgrens,
        afrekening met `prana_cost_limit` uit het manifest, en een teller die per invocatie op
        nul begint. De begrenzing op `max_steps` en de behandeling van een tool die zelf
        `success=false` meldt, zitten in `act()` -- gedeeld met de OODA-weg, dus er is een
        implementatie en geen tweede die kan weglopen.

        **Waarom de initiator in een `finally` wordt gewist.** Vandaag bouwt de loader per stap
        een verse skill, dus een achterblijvende waarde raakt niemand. Zodra iemand instanties
        cachet of poolt, wordt een volgende actie toegeschreven aan de gebruiker van een eerder
        verzoek -- exact de foutklasse waartegen de Council-poort bestaat (BE-AGT-042).
        """
        self._initiated_by_user_id = initiated_by_user_id

        async def _work() -> ExecutionResult:
            # De teller staat hier en niet in `_get_llm_service()`: aanroepers mogen die
            # methode vervangen (tests doen dat), en een teller die je kunt wegpatchen telt
            # niets. `_count_llm_call()` gooit `SkillBudgetExceeded`, en `_run_within_budget`
            # vangt dat af tot een expliciete foutmelding met de naam van de limiet erin.
            self._count_llm_call()
            messages: list[LLMMessage] = [
                LLMMessage(role="user", content=self._build_user_prompt(params))
            ]
            # `config` is een losse dict, dus de waarde komt binnen als `object`. Expliciet
            # omzetten in plaats van casten: het manifest maakt `system_prompt` verplicht
            # (`skill_manifest.py:86`), dus een ontbrekende waarde is een kapot manifest en
            # hoort hier hard op te vallen, niet stil een lege prompt op te leveren.
            system_prompt = self.config["system_prompt"]
            if not isinstance(system_prompt, str) or not system_prompt.strip():
                raise ValueError(
                    f"Manifest van {self.agent_id} levert geen bruikbare system_prompt; "
                    "het piloot-pad bestaat juist om die prompt te gebruiken (ADR-036 D10)."
                )
            system_prompt = self._met_toolnamen(system_prompt)
            answer = await (await self._get_llm_service()).generate(
                messages,
                system_prompt=system_prompt,
            )
            decision = answer if isinstance(answer, str) else answer[0]
            return await self.act(decision)

        try:
            return await self._run_within_budget(_work, task_id=f"{self.agent_id}-manifest")
        finally:
            self._initiated_by_user_id = None
