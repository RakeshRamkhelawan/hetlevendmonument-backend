import json
import logging
import re
from pathlib import Path
from typing import Any

from src.core.als.agents.skill_manifest import SkillManifest
from src.core.als.agents.specialist_base import BaseSpecialistAgent
from src.core.services.llm.base import LLMMessage
from src.core.shared.interfaces import ExecutionResult

logger = logging.getLogger(__name__)

#: De tool waarvoor de brief uit het sjabloon wordt ingevuld voordat er een ticket komt.
_SEND_TOOL = "send_payment_reminder"


#: De zin waarmee de HITL-poort in `specialist_base._council_rejection` meldt dat er een ticket is.
_TICKET_RE = re.compile(r"goedkeuringsticket aangemaakt: (hitl_[0-9a-f]+)")

#: Dezelfde zin zonder eis aan de vorm van de ref: voor het TELLEN van klaargezette herinneringen telt alleen dat er
#: een ticket is aangemaakt (de zin staat er uitsluitend als dat echt gebeurde); de teststub geeft een andere ref.
_TICKET_AANGEMAAKT = re.compile(r"goedkeuringsticket aangemaakt: \S+")

#: De statussen van `receivables.status` die nog niet betaald zijn (de CHECK in de registry kent ook `betaald`).
_OPENSTAAND = ("open", "herinnerd", "geescaleerd")


def _uitkomst(receivable_id: int, resultaat: ExecutionResult) -> dict[str, object]:
    """Vertaal het resultaat van `act()` naar wat de gebruiker per factuur te zien krijgt.

    Een HIGH-actie wordt in `act()` nooit direct uitgevoerd: de vloer meldt hem als
    governance-melding met de ticketref erin. Staat die ref er, dan wacht de brief op een mens.
    Anders ging er iets mis; de melding gaat mee (zij bevat een reden, geen brieftekst).
    """
    data = resultaat.result_data if isinstance(resultaat.result_data, dict) else {}
    fouten = data.get("errors") or []
    for fout in fouten:
        tekst = str(fout.get("error", "")) if isinstance(fout, dict) else ""
        gevonden = _TICKET_RE.search(tekst)
        if gevonden:
            return {
                "receivable_id": receivable_id,
                "status": "wacht_op_goedkeuring",
                "ticket_ref": gevonden.group(1),
            }
    reden = (
        str(fouten[0].get("error", "")) if fouten and isinstance(fouten[0], dict) else ""
    ) or (resultaat.error_message or "onbekende uitkomst")
    return {"receivable_id": receivable_id, "status": "niet_gelukt", "reason": reden}


class DunningSkill(BaseSpecialistAgent):
    """De debiteurenagent: leest openstaande facturen en zet een herinnering of aanmaning klaar.

    Loaded from ``manifests/dunning.yml``. Bedraad in `packs.py::_PILOT_WIRED_AGENT_IDS` sinds
    dag 2 van de debiteurenagent (2026-10-05); het uitvoerpad is hetzelfde als dat van de eerste
    piloot (`skillsgaptraining.py`), zie daar de volledige toelichting per stap.

    **Wat deze skill zelf toevoegt: de brief komt uit het sjabloon, niet uit het model.** Voor
    `send_payment_reminder` vervangt `_prepare_tool_params` ontvanger, onderwerp en tekst door
    wat `preview_payment_reminder` uit de database en het sjabloon rendert. Wat het model voor
    die velden schreef, verdwijnt. Daardoor staat in het ticket precies de brief die verstuurd
    wordt, en kan de goedkeurder lezen wat er gebeurt, aan wie en met welke inhoud (meetlat
    scenario 5).
    """

    def __init__(self, tenant_id: int, **kwargs: Any) -> None:
        manifest = SkillManifest.load(Path(__file__).parent / "manifests/dunning.yml")
        config = manifest.to_config()
        # Merge any runtime overrides passed by the caller
        config.update(kwargs)
        super().__init__(config=config, tenant_id=tenant_id)

    async def act(self, decision: str) -> ExecutionResult:
        """Execute using the shared OODA/tool runtime instead of a hardcoded stub."""
        logger.info(f"[{self.agent_id}] Executing via shared runtime for tenant {self.tenant_id}")
        return await super().act(decision)

    async def _prepare_tool_params(
        self, tool_name: str, params: dict[str, object]
    ) -> dict[str, object] | str:
        """Zet de brief uit het sjabloon in de parameters van `send_payment_reminder`.

        Alleen `receivable_id` en `kind` komen van het model; de rest rendert de registry uit de
        debiteur van DEZE tenant. Bestaat de factuur niet binnen de tenant, dan een weigering:
        er gaat niets naar de Council en er komt geen ticket.

        `importlib`: dezelfde Ce-reden als elders in `specialist_base.py` -- een statische
        import vanuit de skillmap telt mee in de koppelingsmeting van `agent_runtime`.
        """
        if tool_name != _SEND_TOOL:
            return params
        import importlib

        registry_mod = importlib.import_module("src.core.tool_broker.receivables_registry")
        voorbeeld = await registry_mod.ReceivablesToolRegistry().preview_payment_reminder(
            self.tenant_id, params.get("receivable_id"), params.get("kind")
        )
        if voorbeeld.get("success") is not True:
            return f"de brief kon niet worden opgesteld: {voorbeeld.get('error')}"
        volledig = voorbeeld.get("params")
        if not isinstance(volledig, dict):
            return "de brief kon niet worden opgesteld"
        return dict(volledig)

    def _build_user_prompt(self, params: dict[str, object]) -> str:
        """De taak zoals het manifest hem declareert: `task` verplicht, `context` optioneel."""
        task = str(params.get("task", "")).strip()
        extra = {k: v for k, v in params.items() if k != "task"}
        lines = [f"Task: {task}" if task else "Task: (geen taakomschrijving meegegeven)"]
        if extra:
            lines.append(f"Context: {json.dumps(extra, ensure_ascii=True, default=str)}")
        return "\n".join(lines)

    def _met_toolnamen(self, system_prompt: str) -> str:
        """Zet de toegestane toolnamen en de TOOL_CALL-vorm IN de prompt.

        Zonder de namen verzint een model toolnamen (gemeten 2026-09-20 bij de eerste piloot,
        zie `skillsgaptraining.py::_met_toolnamen`). Afgeleid van `allowed_tools`, dus niet uit de
        pas te krijgen met wat de broker toestaat.
        """
        namen = [str(naam) for naam in self.allowed_tools if str(naam).strip()]
        if not namen:
            return system_prompt
        regels = [
            system_prompt.rstrip(),
            "",
            "The tools listed under allowed_tools in your manifest are exactly these, "
            "and nothing else is available to you:",
            "A TOOL_CALL must be alone on its own line and that line must START with "
            "TOOL_CALL: -- never put any word, label or prefix before it. The arguments "
            "are a single JSON object with double quotes. Exactly like this:",
            'TOOL_CALL: list_receivables {"status": "open"}',
        ]
        regels.extend("- " + naam for naam in namen)
        return "\n".join(regels)

    async def propose_reminders(
        self,
        receivable_ids: list[int],
        kind: str,
        *,
        initiated_by_user_id: int,
    ) -> list[dict[str, object]]:
        """Zet per gekozen factuur een herinnering of aanmaning klaar (debiteurenagent dag 3).

        Wat de knop "Herinnering voorstellen" aanroept. GEEN taalmodel: de mens heeft al gekozen
        welke factuur en welke soort brief. Elke factuur loopt apart door `act()`, dus door het
        sjabloon (`_prepare_tool_params`), de Council, de HITL-vloer en pas na goedkeuring de
        broker -- dezelfde keten als wanneer het model de actie had gekozen. Apart, zodat de
        uitkomst per factuur te melden is.

        Geeft per factuur `wacht_op_goedkeuring` met de ticketref, of `niet_gelukt` met de
        reden. De initiator wordt in een `finally` gewist, zoals in
        `execute_with_manifest_prompt`.
        """
        self._initiated_by_user_id = initiated_by_user_id
        uitkomsten: list[dict[str, object]] = []
        try:
            # Dubbele ids niet twee keer: anders twee brieven voor dezelfde factuur (security-review).
            for receivable_id in dict.fromkeys(receivable_ids):
                besluit = "TOOL_CALL: send_payment_reminder " + json.dumps(
                    {"receivable_id": receivable_id, "kind": kind}
                )

                async def _werk(besluit: str = besluit) -> ExecutionResult:
                    return await self.act(besluit)

                resultaat = await self._run_within_budget(
                    _werk, task_id=f"{self.agent_id}-voorstel-{receivable_id}"
                )
                uitkomsten.append(_uitkomst(receivable_id, resultaat))
        finally:
            self._initiated_by_user_id = None
        return uitkomsten

    async def execute_with_manifest_prompt(
        self,
        params: dict[str, object],
        *,
        initiated_by_user_id: int | None = None,
    ) -> ExecutionResult:
        """Het pad dat `packs.py::_execute_step` aanroept: uitvoeren met de manifest-prompt.

        Zelfde opbouw als `SkillsGapTrainingSkill.execute_with_manifest_prompt`: budget via
        `_run_within_budget`, een getelde LLM-aanroep, en `act()` voor de Council per actie, de
        HITL-vloer en de broker. De initiator wordt in een `finally` gewist, zodat een volgende
        actie nooit aan de gebruiker van een eerder verzoek wordt toegeschreven.
        """
        self._initiated_by_user_id = initiated_by_user_id

        async def _work() -> ExecutionResult:
            self._count_llm_call()
            messages: list[LLMMessage] = [
                LLMMessage(role="user", content=self._build_user_prompt(params))
            ]
            system_prompt = self.config["system_prompt"]
            if not isinstance(system_prompt, str) or not system_prompt.strip():
                raise ValueError(
                    f"Manifest van {self.agent_id} levert geen bruikbare system_prompt."
                )
            answer = await (await self._get_llm_service()).generate(
                messages,
                system_prompt=self._met_toolnamen(system_prompt),
            )
            decision = answer if isinstance(answer, str) else answer[0]
            return await self.act(decision)

        try:
            resultaat = await self._run_within_budget(_work, task_id=f"{self.agent_id}-manifest")
        finally:
            self._initiated_by_user_id = None
        return await self._met_tellingen(resultaat)

    async def _met_tellingen(self, resultaat: ExecutionResult) -> ExecutionResult:
        """Zet er twee tellingen bij die NIET van het model komen, zodat de uitslag kan zeggen wat er gebeurde.

        Gemeten (zero-admin afwerken, 2026-10-19): antwoordt het model zonder TOOL_CALL, dan was `result_data` alleen
        `{"output": ..., "tool_calls": 0}` en meldde de uitslag "Gelukt" zonder dat iemand wist of er vorderingen
        openstonden. `voorgesteld` telt de tickets van DEZE run, `openstaand` de niet-betaalde vorderingen van
        deze tenant (`None` als tellen mislukte: onbekend is geen nul).
        """
        if not isinstance(resultaat.result_data, dict):
            return resultaat
        data = dict(resultaat.result_data)
        data["voorgesteld"] = _tel_tickets(data.get("errors"))
        openstaand, afgekapt = await self._tel_openstaand()
        data["openstaand"] = openstaand
        if afgekapt:
            data["openstaand_afgekapt"] = True
        return resultaat.model_copy(update={"result_data": data})

    async def _tel_openstaand(self) -> tuple[int | None, bool]:
        """Het aantal niet-betaalde vorderingen van deze tenant, en of een lijst is afgekapt.

        Eerst per OPENSTAANDE status (open, herinnerd, geescaleerd) met het statusfilter van de tool: de tool geeft
        de eerste 200 rijen op vervaldatum, betaald of niet, dus zonder filter konden 200 betaalde vorderingen een
        open vordering verbergen en zei het scherm ten onrechte "Geen openstaande vorderingen" (Gate 2).

        Dit is een toegestaan LEES-pad: de skill leest de vorderingen van haar EIGEN tenant (nooit uit `params`)
        rechtstreeks via de registry en krijgt alleen een getal terug; `_prepare_tool_params` doet hetzelfde voor
        het voorbeeld van de brief. `importlib`: dezelfde Ce-reden als daar.
        """
        import importlib

        totaal = 0
        afgekapt = False
        try:
            # In een workflowstap leest alleen een starter die `list_receivables` mag het aantal (agentstap dag 1).
            if self._toolrecht_toets is not None and not await self._toolrecht_toets(
                "list_receivables"
            ):
                return None, False
            registry_mod = importlib.import_module("src.core.tool_broker.receivables_registry")
            registry = registry_mod.ReceivablesToolRegistry()
            for status in _OPENSTAAND:
                antwoord = await registry.execute_receivables_tool(
                    registry_mod.LIST_TOOL_NAME,
                    {"status": status, "limit": registry_mod.MAX_LIMIT},
                    tenant_id=self.tenant_id,
                )
                rijen = antwoord.get("receivables")
                if antwoord.get("success") is not True or not isinstance(rijen, list):
                    return None, False
                totaal += len(rijen)
                afgekapt = afgekapt or antwoord.get("truncated") is True
        except Exception as fout:  # noqa: BLE001 -- een telling mag de gelukte stap nooit laten falen
            logger.warning(
                "[%s] openstaande vorderingen tellen mislukt: %s",
                self.agent_id,
                type(fout).__name__,
                exc_info=True,
            )
            return None, False
        return totaal, afgekapt


def _tel_tickets(fouten: object) -> int:
    """Het aantal herinneringen dat in deze run als goedkeuringsticket is klaargezet.

    Alleen een melding van de governance-poort telt (`kind == "governance"`): een andere foutmelding kan tekst
    bevatten die het model of de gebruiker kiest, en mag de teller niet verhogen.
    """
    if not isinstance(fouten, list):
        return 0
    return sum(
        1
        for fout in fouten
        if isinstance(fout, dict)
        and fout.get("kind") == "governance"
        and _TICKET_AANGEMAAKT.search(str(fout.get("error", "")))
    )
