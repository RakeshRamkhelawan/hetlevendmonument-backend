import logging
import re
from pathlib import Path
from typing import Any, Protocol, cast

from src.core.als.agents.skill_manifest import SkillManifest
from src.core.als.agents.specialist_base import BaseSpecialistAgent
from src.core.shared.interfaces import ExecutionResult

logger = logging.getLogger(__name__)

#: Zo lang mag een verwerking `bezig` staan voor een andere start haar overneemt (de agent doet er seconden over).
VERLOOP_MINUTEN = 10

_RECORD_TOOL = "record_supplier_invoice"
_PROPOSE_TOOL = "propose_supplier_invoice"
_PAYRUN_TOOL = "propose_payment_run"

#: De zin waarmee de HITL-poort in `specialist_base._council_rejection` meldt dat er een ticket is (zie `dunning.py`).
_TICKET_RE = re.compile(r"goedkeuringsticket aangemaakt: (hitl_[0-9a-f]+)")

class _Koppeling(Protocol):
    """Wat de skill van de koppeling tussen een upload en zijn factuur gebruikt (`als/bonlezer/factuur.py`)."""

    def claim(self, tenant_id: int, bestand_id: str, door: int | None = None) -> bool: ...

    def lees(self, tenant_id: int, bestand_id: str) -> dict[str, object] | None: ...

    def geef_vrij(self, tenant_id: int, bestand_id: str) -> None: ...

    def markeer_eerder_verlopen(self, tenant_id: int, bestand_id: str) -> None: ...

    def is_verlopen(self, stand: dict[str, object], minuten: int) -> bool: ...

    def schrijf(self, tenant_id: int, bestand_id: str, record: dict[str, object]) -> None: ...


class _Registry(Protocol):
    """Wat de skill van `PayablesToolRegistry` gebruikt; een Protocol zodat de skill niet statisch naar `tool_broker` koppelt."""

    async def beoordeel(self, tenant_id: int, bestand_id: str) -> dict[str, object]: ...

    async def ticket_is_verlopen(self, tenant_id: int, ticket_ref: str) -> bool: ...

    def koppeling(self) -> _Koppeling: ...

    async def schrijf_audit(
        self, tenant_id: int, event_type: str, description: str, details: dict[str, object]
    ) -> None: ...


class _BetaalrunRegistry(Protocol):
    """Wat de skill van `BetaalrunToolRegistry` gebruikt (betaalvoorstel, crediteuren dag 3); een Protocol om dezelfde reden als `_Registry`."""

    async def selecteer(self, tenant_id: int) -> dict[str, object]: ...

    async def schrijf_audit(
        self, tenant_id: int, event_type: str, description: str, details: dict[str, object]
    ) -> None: ...


_GEEN_INITIATOR = "Er is geen verantwoordelijke gebruiker bekend; de crediteurenagent verwerkt niets (AI Act art. 14)."


class CrediteurenSkill(BaseSpecialistAgent):
    """De crediteurenagent: verwerkt een inkoopfactuur die de bonlezer las, zelf (crediteuren dag 2, Keten F).

    Loaded from ``manifests/crediteuren.yml``. Naar het voorbeeld van `DunningSkill`, met een belangrijk verschil: er is GEEN taalmodel.
    De stappen staan vast en elke actie loopt toch door `act()`, dus door de Council, de HITL-vloer en de broker.

    Wat de agent doet (`verwerk_upload`):

    1. **Beoordelen** (een LEESpad via de registry, zoals `DunningSkill._tel_openstaand`): de gelezen velden, de leverancier zoeken
       (IBAN, dan naam), een afwijkend IBAN en een dubbele factuur opsporen.
    2. **Schoon**: zelf vastleggen met `record_supplier_invoice` (MEDIUM). De tool beoordeelt zelf opnieuw en weigert een uitzondering.
    3. **Uitzondering** (onbekende leverancier, afwijkend IBAN, onzeker of ontbrekend veld): `propose_supplier_invoice` (HIGH), dus een
       ticket in `hitl_tickets` met het waarom. Na goedkeuren legt de broker vast; afwijzen vraagt een reden.
    4. **Dubbel**: geen tweede factuur en geen ticket; een Nederlandse reden in het logboek.

    Een upload wordt hooguit een keer verwerkt (een claim naast de upload). Zonder verantwoordelijke gebruiker doet de agent niets:
    de Council legt zijn besluit vast op een `user_id` en een autonome actie mag niet aan iemand worden toegeschreven die hem niet startte.
    """

    def __init__(self, tenant_id: int, **kwargs: Any) -> None:
        manifest = SkillManifest.load(Path(__file__).parent / "manifests/crediteuren.yml")
        config = manifest.to_config()
        config.update(kwargs)
        super().__init__(config=config, tenant_id=tenant_id)
        self._laatste_selectie: dict[str, object] | None = None

    async def act(self, decision: str) -> ExecutionResult:
        """Execute using the shared OODA/tool runtime instead of a hardcoded stub."""
        logger.info(f"[{self.agent_id}] Executing via shared runtime for tenant {self.tenant_id}")
        return await super().act(decision)

    # -- de registry (LEESpad en koppeling) ---------------------------------------------------------

    @staticmethod
    def _registry() -> _Registry:
        """`importlib`: dezelfde reden als in `dunning.py` -- een statische import vanuit de skillmap telt mee in de koppelingsmeting."""
        import importlib

        module = importlib.import_module("src.core.tool_broker.payables_registry")
        return cast(_Registry, module.PayablesToolRegistry())

    async def _prepare_tool_params(
        self, tool_name: str, params: dict[str, object]
    ) -> dict[str, object] | str:
        """Zet de feiten uit de BEOORDELING in de parameters; wat van buiten komt (behalve `bestand_id`) verdwijnt.

        De mens in het ticket leest precies deze parameters en de goedkeuringsbinding dekt ze. Daarom komen ze nooit van een model of
        van een aanroeper: de tenant en het bestandsnummer volstaan, de rest leest de registry uit de upload van DEZE tenant.
        """
        if tool_name == _PAYRUN_TOOL:
            # Het voorstel komt uit de SELECTIE van deze tenant; wat van buiten komt telt niet. De mens leest precies deze regels.
            selectie = await self._betaalrun_registry().selecteer(self.tenant_id)
            regels = selectie.get("regels")
            if not isinstance(regels, list) or not regels:
                return "er is niets om te betalen voor te leggen"
            self._laatste_selectie = selectie
            return {
                "regels": regels,
                "totaal_cents": selectie["totaal_cents"],
                "drempel_cents": selectie["drempel_cents"],
                "vier_ogen_vereist": selectie["vier_ogen_vereist"],
                "waarom": selectie["waarom"],
            }
        bestand_id = params.get("bestand_id")
        if tool_name not in (_RECORD_TOOL, _PROPOSE_TOOL) or not isinstance(bestand_id, str):
            return "alleen een bestandsnummer van een upload is een geldige opdracht"
        if tool_name == _RECORD_TOOL:
            return {"bestand_id": bestand_id}
        oordeel = await self._registry().beoordeel(self.tenant_id, bestand_id)
        feiten = oordeel.get("ticketfeiten")
        if oordeel.get("uitkomst") != "uitzondering" or not isinstance(feiten, dict):
            return "er is geen uitzondering om voor te leggen aan een mens"
        # `ticketfeiten`: het IBAN is gemaskeerd, want de inhoudswachter laat een geldig IBAN in een tool-parameter nooit door.
        return {"bestand_id": bestand_id, **feiten, "waarom": oordeel.get("waarom", "")}

    @staticmethod
    def _betaalrun_registry() -> _BetaalrunRegistry:
        """`importlib`: zelfde reden als `_registry`."""
        import importlib

        module = importlib.import_module("src.core.tool_broker.payment_run_registry")
        return cast(_BetaalrunRegistry, module.BetaalrunToolRegistry())

    # -- het werk -----------------------------------------------------------------------------------

    async def stel_betaling_voor(self, *, initiated_by_user_id: int | None) -> dict[str, object]:
        """Maak een betaalvoorstel: EEN ticket met alle facturen die nu aan de beurt zijn (crediteuren dag 3).

        De agent betaalt niets en keurt niets goed; hij legt voor aan een mens. `uitkomst`: `ticket` (met `ticket_ref`, `aantal`,
        `totaal_cents`, `vier_ogen_vereist`), `niets_te_betalen`, `geweigerd` (geen verantwoordelijke gebruiker) of `niet_gelukt`.
        De initiator wordt in een `finally` gewist, zoals bij `verwerk_upload`.
        """
        if initiated_by_user_id is None:
            return {"uitkomst": "geweigerd", "reden": _GEEN_INITIATOR}
        selectie = await self._betaalrun_registry().selecteer(self.tenant_id)
        regels = selectie.get("regels")
        if not isinstance(regels, list) or not regels:
            return {
                "uitkomst": "niets_te_betalen",
                "overgeslagen": selectie.get("overgeslagen", []),
            }
        self._initiated_by_user_id = initiated_by_user_id
        self._laatste_selectie = None
        try:
            resultaat = await self._run_within_budget(
                lambda: self.act(f"TOOL_CALL: {_PAYRUN_TOOL} {{}}"),
                task_id=f"{self.agent_id}-{_PAYRUN_TOOL}",
            )
            data = resultaat.result_data if isinstance(resultaat.result_data, dict) else {}
            for fout in data.get("errors") or []:
                tekst = str(fout.get("error", "")) if isinstance(fout, dict) else ""
                gevonden = _TICKET_RE.search(tekst)
                if gevonden and self._laatste_selectie is not None:
                    voorgelegd = self._laatste_selectie
                    ticket_ref = gevonden.group(1)
                    await self._betaalrun_registry().schrijf_audit(
                        self.tenant_id,
                        "payment_run_proposed",
                        f"payment_run_proposed: voorstel {ticket_ref}",
                        {
                            "ticket_ref": ticket_ref,
                            "aantal": len(voorgelegd["regels"]),
                            "totaal_cents": voorgelegd["totaal_cents"],
                            "vier_ogen_vereist": voorgelegd["vier_ogen_vereist"],
                            "initiated_by": initiated_by_user_id,
                        },
                    )
                    return {
                        "uitkomst": "ticket",
                        "ticket_ref": ticket_ref,
                        "aantal": len(voorgelegd["regels"]),
                        "totaal_cents": voorgelegd["totaal_cents"],
                        "vier_ogen_vereist": voorgelegd["vier_ogen_vereist"],
                        "overgeslagen": voorgelegd.get("overgeslagen", []),
                    }
            reden = _eerste_fout(data) or resultaat.error_message or "onbekende uitkomst"
            return {"uitkomst": "niet_gelukt", "reden": reden}
        except Exception as fout:  # noqa: BLE001 -- een mislukt voorstel mag de aanroeper nooit met een stacktrace laten zitten
            logger.error(
                "crediteurenagent: betaalvoorstel mislukt: tenant=%s fouttype=%s",
                self.tenant_id,
                type(fout).__name__,
                exc_info=True,
            )
            return {
                "uitkomst": "niet_gelukt",
                "reden": "De crediteurenagent kon geen betaalvoorstel maken.",
            }
        finally:
            self._initiated_by_user_id = None
            self._laatste_selectie = None

    async def verwerk_upload(
        self, bestand_id: str, *, initiated_by_user_id: int | None
    ) -> dict[str, object]:
        """Verwerk een upload die als inkoopfactuur is gelezen. Geeft altijd een dict met `uitkomst`.

        `uitkomst`: `vastgelegd`, `ticket`, `dubbel`, `nog_niet_klaar` (later opnieuw proberen), `onleesbaar`, `onbekend`,
        `al_verwerkt`, `geweigerd` of `niet_gelukt`. De initiator wordt in een `finally` gewist, zoals bij `DunningSkill`.
        """
        if initiated_by_user_id is None:
            return {"uitkomst": "geweigerd", "reden": _GEEN_INITIATOR}
        registry = self._registry()
        oordeel = await registry.beoordeel(self.tenant_id, bestand_id)
        uitkomst = str(oordeel["uitkomst"])
        if uitkomst in ("nog_niet_klaar", "onleesbaar", "onbekend"):
            return {"uitkomst": uitkomst}
        koppeling = registry.koppeling()
        if not koppeling.claim(self.tenant_id, bestand_id, initiated_by_user_id):
            stand = koppeling.lees(self.tenant_id, bestand_id) or {}
            if not await self._laat_verlopen_ticket_los(
                registry, koppeling, bestand_id, stand, initiated_by_user_id
            ):
                # Een claim die te lang `bezig` staat zonder uitkomst is een verwerking die onderbroken is (de API viel weg): overnemen.
                if not (
                    koppeling.is_verlopen(stand, VERLOOP_MINUTEN)
                    and self._neem_over(koppeling, bestand_id, initiated_by_user_id)
                ):
                    # De eigen stand van de upload (`uitkomst` van de agent) mag `al_verwerkt` niet overschrijven: eerst de stand, dan de uitkomst.
                    return {
                        **{k: v for k, v in stand.items() if k not in ("door", "uitkomst", "aangemaakt")},
                        "uitkomst": "al_verwerkt",
                        "stand": stand.get("uitkomst"),
                    }
        self._initiated_by_user_id = initiated_by_user_id
        try:
            if uitkomst == "dubbel":
                return await self._weiger_dubbel(registry, koppeling, bestand_id, oordeel)
            if uitkomst == "schoon":
                return await self._leg_vast(koppeling, bestand_id)
            return await self._leg_voor(koppeling, bestand_id, oordeel)
        except Exception as fout:  # noqa: BLE001 -- een stap na de claim mag de upload nooit op `bezig` laten staan
            logger.error(
                "crediteurenagent: verwerken mislukt: tenant=%s fouttype=%s",
                self.tenant_id,
                type(fout).__name__,
                exc_info=True,
            )
            reden = "De crediteurenagent kon deze factuur niet verwerken."
            koppeling.schrijf(
                self.tenant_id,
                bestand_id,
                {"payable_id": None, "uitkomst": "mislukt", "reden": reden, "door": initiated_by_user_id},
            )
            return {"uitkomst": "niet_gelukt", "reden": reden}
        finally:
            self._initiated_by_user_id = None

    async def _laat_verlopen_ticket_los(
        self,
        registry: _Registry,
        koppeling: _Koppeling,
        bestand_id: str,
        stand: dict[str, object],
        door: int,
    ) -> bool:
        """Laat de claim los als zijn ticket niet op tijd is beoordeeld, en pak de upload opnieuw. `True` als dat gelukt is.

        Zonder dit staat de factuur voor altijd op "al verwerkt" achter een ticket dat niemand meer kan goedkeuren (crediteuren nazorg,
        punt 3). Het ticket telt als verlopen op het moment van lezen, ook als de uurlijkse opruimtaak nog niet draaide. Het volgende
        ticket van deze upload zegt dat het eerder is voorgelegd.
        """
        ticket_ref = stand.get("ticket_ref") if stand.get("uitkomst") == "ticket" else None
        if not isinstance(ticket_ref, str) or not await registry.ticket_is_verlopen(
            self.tenant_id, ticket_ref
        ):
            return False
        koppeling.markeer_eerder_verlopen(self.tenant_id, bestand_id)
        koppeling.geef_vrij(self.tenant_id, bestand_id)
        return koppeling.claim(self.tenant_id, bestand_id, door)

    def _neem_over(self, koppeling: _Koppeling, bestand_id: str, door: int) -> bool:
        koppeling.geef_vrij(self.tenant_id, bestand_id)
        return koppeling.claim(self.tenant_id, bestand_id, door)

    async def _doe(self, tool: str, bestand_id: str) -> ExecutionResult:
        besluit = f'TOOL_CALL: {tool} {{"bestand_id": "{bestand_id}"}}'

        async def _werk() -> ExecutionResult:
            return await self.act(besluit)

        return await self._run_within_budget(_werk, task_id=f"{self.agent_id}-{tool}")

    async def _weiger_dubbel(
        self,
        registry: _Registry,
        koppeling: _Koppeling,
        bestand_id: str,
        oordeel: dict[str, object],
    ) -> dict[str, object]:
        reden = str(oordeel.get("reden", ""))
        koppeling.schrijf(
            self.tenant_id,
            bestand_id,
            {"payable_id": None, "uitkomst": "dubbel", "reden": reden},
        )
        feiten = oordeel.get("feiten")
        nummer = feiten.get("invoice_number") if isinstance(feiten, dict) else None
        await registry.schrijf_audit(
            self.tenant_id,
            "payable_duplicate_refused",
            reden,
            {"bestand_id": bestand_id, "invoice_number": nummer, "via": "agent"},
        )
        return {"uitkomst": "dubbel", "reden": reden}

    async def _leg_vast(self, koppeling: _Koppeling, bestand_id: str) -> dict[str, object]:
        resultaat = await self._doe(_RECORD_TOOL, bestand_id)
        data = resultaat.result_data if isinstance(resultaat.result_data, dict) else {}
        for stap in data.get("results") or []:
            uit = stap.get("output") if isinstance(stap, dict) else None
            if isinstance(uit, dict) and uit.get("success") is True:
                return {"uitkomst": "vastgelegd", "payable_id": uit.get("payable_id")}
        reden = _eerste_fout(data) or resultaat.error_message or "onbekende uitkomst"
        koppeling.schrijf(
            self.tenant_id, bestand_id, {"payable_id": None, "uitkomst": "mislukt", "reden": reden}
        )
        return {"uitkomst": "niet_gelukt", "reden": reden}

    async def _leg_voor(
        self, koppeling: _Koppeling, bestand_id: str, oordeel: dict[str, object]
    ) -> dict[str, object]:
        resultaat = await self._doe(_PROPOSE_TOOL, bestand_id)
        data = resultaat.result_data if isinstance(resultaat.result_data, dict) else {}
        for fout in data.get("errors") or []:
            tekst = str(fout.get("error", "")) if isinstance(fout, dict) else ""
            gevonden = _TICKET_RE.search(tekst)
            if gevonden:
                ticket_ref = gevonden.group(1)
                koppeling.schrijf(
                    self.tenant_id,
                    bestand_id,
                    {"payable_id": None, "uitkomst": "ticket", "ticket_ref": ticket_ref},
                )
                return {
                    "uitkomst": "ticket",
                    "ticket_ref": ticket_ref,
                    "redenen": oordeel.get("redenen", []),
                    "waarom": oordeel.get("waarom", ""),
                }
        reden = _eerste_fout(data) or resultaat.error_message or "onbekende uitkomst"
        koppeling.schrijf(
            self.tenant_id, bestand_id, {"payable_id": None, "uitkomst": "mislukt", "reden": reden}
        )
        return {"uitkomst": "niet_gelukt", "reden": reden}

    async def execute_with_manifest_prompt(
        self,
        params: dict[str, object],
        *,
        initiated_by_user_id: int | None = None,
    ) -> ExecutionResult:
        """Het pad dat `packs.py::_execute_step` aanroept. Geen taalmodel: met een `bestand_id` verwerkt de agent die upload.

        Zonder `bestand_id` is er niets te doen; dat is een uitkomst, geen fout. Dezelfde `verwerk_upload` als de directe start.
        Met `{"actie": "betaalvoorstel"}` maakt de agent een betaalvoorstel (`stel_betaling_voor`); ook dat vraagt een verantwoordelijke
        gebruiker en legt alleen voor aan een mens.
        """
        if params.get("actie") == "betaalvoorstel":
            voorstel = await self.stel_betaling_voor(initiated_by_user_id=initiated_by_user_id)
            return ExecutionResult(
                task_id=f"{self.agent_id}-manifest",
                success=voorstel["uitkomst"] not in ("niet_gelukt", "geweigerd"),
                result_data=dict(voorstel),
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
            )
        bestand_id = params.get("bestand_id")
        if not isinstance(bestand_id, str):
            return ExecutionResult(
                task_id=f"{self.agent_id}-manifest",
                success=True,
                result_data={"uitkomst": "niets_te_doen"},
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
            )
        uitkomst = await self.verwerk_upload(bestand_id, initiated_by_user_id=initiated_by_user_id)
        return ExecutionResult(
            task_id=f"{self.agent_id}-manifest",
            success=uitkomst["uitkomst"] not in ("niet_gelukt", "geweigerd"),
            result_data=dict(uitkomst),
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
        )


def _eerste_fout(data: dict[str, object]) -> str:
    fouten = data.get("errors")
    if isinstance(fouten, list) and fouten and isinstance(fouten[0], dict):
        return str(fouten[0].get("error", ""))
    return ""
