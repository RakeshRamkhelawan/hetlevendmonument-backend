"""Een agent- of taalmodelstap voert geen tool uit zonder startertoets (brief 2026-10-23).

Sinds 4a3e258d toetst een TOOLstap het recht van de mens die de workflow startte. Voor een AGENTstap en een
TAALMODELstap is gemeten (statisch, 2026-10-23; de levende meting volgt in de eindmelding van de brief) dat zij vandaag
GEEN tool kunnen uitvoeren, om drie onafhankelijke redenen:

1. **Er is geen agent te vinden.** De werker geeft de agentstap aan `AgentRouterAgent.run_agent` ->
   `route_and_execute` -> `_resolve_agent`, en die zoekt een levende agent via `AgentFactory.get_instance`. Die
   methode bestaat NIET (`AgentFactory` in `src/core/agents/agent_factory.py` is een codegenerator voor
   markdown-agentdefinities). `_resolve_agent` geeft dus voor elke agent `None`, en elke agentstap eindigt met
   "Agent X not found in process" (live gemeten bij workflowstappen-draaien-echt, 2026-10-22).
2. **De terugvalroute is dood.** Zonder router gebruikt `ProductionAgentRuntime.execute_agent` een `BaseAgent`, en
   die klasse (`src/core/shared/interfaces.py`) is abstract: instantieren geeft `TypeError`.
3. **Een taalmodelstap kan geen functies aanroepen.** `TenantTaalmodel.tekst_met_gebruik` heeft geen parameter voor
   tools of functies; de stap geeft alleen tekst terug.

Deze test faalt zodra een van die drie verandert (en een gedragstest zorgt dat `_resolve_agent` voor geen enkele
agent iets teruggeeft, ook niet als iemand een ander register of een metaclass gebruikt): dan kan een agent- of
taalmodelstap mogelijk een tool uitvoeren zonder dat de starter is getoetst. De ontwikkelaar moet dan EERST de startertoets toevoegen (zelfde regel als bij de
toolstap: niet meer dan `workflow_engine` EN de starter, getoetst bij het uitvoeren, fail-closed) en pas daarna deze
test bijwerken. Een stap is "beveiligd" als `ProductionWorkflowEngine._execute_agent_task` (respectievelijk
`_execute_llm_task`) een parameter `starter` heeft die de aanroep ook werkelijk gebruikt.

**De vlag `enhanced_base_agent_initiator_check` is GEEN vervanging voor de startertoets:** hij eist alleen dat er
een initiator is en een Council-uitspraak; hij toetst het toolrecht van de starter niet.

**Beperking van de gedragstest:** hij meet een leeg proces. Een `_resolve_agent` die een register raadpleegt dat pas
bij het opstarten van de werker wordt gevuld (`app_lifespan`), geeft hier `None` en blijft groen terwijl een echte
werker wel agents vindt. Wie `_resolve_agent` aanpast, hoort de startertoets eerst toe te voegen; een reviewer
leest die wijziging zelf. Ook de startertoets-regel is heuristisch (functienaam met 'starter' of 'recht'): hij
bewijst niet dat de uitkomst wordt gebruikt.

**Wat deze test niet ziet (bewust, gemeld in de eindmelding):** een tweede engine voor andere workflows
(`src/core/agents/workflow_engine.py`, `src/core/tasks/workflow_tasks.py`); die zijn geen c7-workflowstappen.

**Mutatiebewijs (2026-10-23), beide richtingen:** elke controle heeft synthetische bronnen die hem moeten laten falen
(`get_instance` toegevoegd, `BaseAgent` niet meer abstract, een `tools=`-parameter) en bronnen die hem met rust laten
(zie `TestDeControlesVindenWatZeMoetenVinden` en `TestDeControlesLatenLegitiemeBronMetRust`). De echte bestanden worden
in `TestDeWerkelijkeStand` gelezen.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

WORTEL = Path(__file__).resolve().parents[2]
AGENT_FACTORY = "src/core/agents/agent_factory.py"
INTERFACES = "src/core/shared/interfaces.py"
TENANT_DEUR = "src/core/services/llm/tenant_deur.py"
ENGINE = "src/core/workflow/engine.py"
PROVIDERS = "src/core/workflow/providers.py"

# Namen waarmee een taalmodel tools of functies krijgt aangeboden (function calling).
_TOOL_PARAMETERS = frozenset(
    {"tools", "functions", "tool_choice", "function_call", "available_tools"}
)


def _lees(pad: str) -> str:
    return (WORTEL / pad).read_text(encoding="utf-8")


def _klasse(bron: str, naam: str) -> ast.ClassDef | None:
    for knoop in ast.walk(ast.parse(bron)):
        if isinstance(knoop, ast.ClassDef) and knoop.name == naam:
            return knoop
    return None


def _methode(klasse: ast.ClassDef, naam: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for knoop in klasse.body:
        if isinstance(knoop, ast.FunctionDef | ast.AsyncFunctionDef) and knoop.name == naam:
            return knoop
    return None


def klasse_definieert(bron: str, klasse: str, naam: str) -> bool:
    """Heeft deze klasse ZELF een methode of attribuut met deze naam (niet een andere klasse in het bestand)?"""
    k = _klasse(bron, klasse)
    if k is None:
        return False
    for knoop in k.body:
        if isinstance(knoop, ast.FunctionDef | ast.AsyncFunctionDef) and knoop.name == naam:
            return True
        if isinstance(knoop, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == naam for t in knoop.targets
        ):
            return True
        if (
            isinstance(knoop, ast.AnnAssign)
            and isinstance(knoop.target, ast.Name)
            and knoop.target.id == naam
        ):
            return True
    return False


def klasse_is_abstract(bron: str, klasse: str) -> bool:
    """Heeft de klasse minstens een `@abstractmethod` (en is hij dus niet te instantieren)?"""
    k = _klasse(bron, klasse)
    if k is None:
        return False
    for knoop in k.body:
        if isinstance(knoop, ast.FunctionDef | ast.AsyncFunctionDef):
            for deco in knoop.decorator_list:
                naam = deco.attr if isinstance(deco, ast.Attribute) else getattr(deco, "id", "")
                if naam == "abstractmethod":
                    return True
    return False


def methode_neemt_tools_aan(bron: str, klasse: str, methode: str) -> bool:
    """Heeft de methode een parameter waarmee een taalmodel tools of functies kan krijgen?"""
    k = _klasse(bron, klasse)
    m = _methode(k, methode) if k is not None else None
    if m is None:
        return False
    argumenten = m.args
    namen = {a.arg for a in [*argumenten.posonlyargs, *argumenten.args, *argumenten.kwonlyargs]}
    if argumenten.kwarg is not None:
        # een open **kwargs kan alles doorgeven, ook tools
        return True
    return bool(namen & _TOOL_PARAMETERS)


def aanroep_geeft_tools_door(bron: str, klasse: str, methode: str) -> bool:
    """Geeft de methode in een aanroep een keyword als `tools=` of `functions=` mee?"""
    k = _klasse(bron, klasse)
    m = _methode(k, methode) if k is not None else None
    if m is None:
        return False
    for knoop in ast.walk(m):
        if not isinstance(knoop, ast.Call):
            continue
        if any(kw.arg in _TOOL_PARAMETERS or kw.arg is None for kw in knoop.keywords):
            return True
        functie = knoop.func.attr if isinstance(knoop.func, ast.Attribute) else getattr(knoop.func, "id", "")
        if functie == "generate_with_tools":
            return True
    return False


def stap_toetst_de_starter(bron: str, klasse: str, methode: str) -> bool:
    """Heeft de stapmethode een parameter `starter` die in het lichaam ook werkelijk wordt gebruikt?"""
    k = _klasse(bron, klasse)
    m = _methode(k, methode) if k is not None else None
    if m is None:
        return False
    argumenten = m.args
    if "starter" not in {a.arg for a in [*argumenten.args, *argumenten.kwonlyargs]}:
        return False
    # `starter` moet ARGUMENT zijn van een aanroep van een toets (`starter_heeft_toolrecht(starter, ...)`), niet
    # alleen ergens voorkomen (een logregel of `_ = starter` is geen toets).
    for knoop in ast.walk(m):
        if not isinstance(knoop, ast.Call):
            continue
        functie = knoop.func.attr if isinstance(knoop.func, ast.Attribute) else getattr(knoop.func, "id", "")
        if "starter" not in functie and "recht" not in functie:
            continue
        for arg in [*knoop.args, *[kw.value for kw in knoop.keywords]]:
            if any(isinstance(n, ast.Name) and n.id == "starter" for n in ast.walk(arg)):
                return True
    return False


def agentstap_is_veilig(factory: str, interfaces: str, engine: str) -> tuple[bool, str]:
    """(veilig, reden): inert door ontwerp, of de stap toetst de starter."""
    inert_geen_agent = not klasse_definieert(factory, "AgentFactory", "get_instance")
    inert_terugval = klasse_is_abstract(interfaces, "BaseAgent")
    beveiligd = stap_toetst_de_starter(engine, "ProductionWorkflowEngine", "_execute_agent_task")
    if beveiligd:
        return True, "de agentstap toetst de starter"
    if inert_geen_agent and inert_terugval:
        return True, "geen agent te vinden en de terugval (BaseAgent) is abstract"
    redenen = []
    if not inert_geen_agent:
        redenen.append("`AgentFactory.get_instance` bestaat nu: de router kan een agent vinden")
    if not inert_terugval:
        redenen.append("`BaseAgent` is niet meer abstract: de terugvalroute kan een agent draaien")
    return False, "; ".join(redenen)


def taalmodelstap_is_veilig(tenant_deur: str, providers: str, engine: str) -> tuple[bool, str]:
    inert_signatuur = not methode_neemt_tools_aan(
        tenant_deur, "TenantTaalmodel", "tekst_met_gebruik"
    )
    inert_aanroep = not aanroep_geeft_tools_door(providers, "ProductionLLMProvider", "generate")
    beveiligd = stap_toetst_de_starter(engine, "ProductionWorkflowEngine", "_execute_llm_task")
    if beveiligd:
        return True, "de taalmodelstap toetst de starter"
    if inert_signatuur and inert_aanroep:
        return True, "het taalmodel krijgt geen tools aangeboden"
    redenen = []
    if not inert_signatuur:
        redenen.append("`TenantTaalmodel.tekst_met_gebruik` neemt nu tools of **kwargs aan")
    if not inert_aanroep:
        redenen.append("`ProductionLLMProvider.generate` geeft nu tools door")
    return False, "; ".join(redenen)


_MELDING = (
    "{kant} kan nu mogelijk een tool uitvoeren zonder dat de starter van de workflow is getoetst: {reden}. "
    "Voeg EERST de startertoets toe aan de stap (zelfde regel als de toolstap: `starter` doorgeven aan de stap en "
    "`starter_heeft_toolrecht` toetsen, fail-closed; zie brief 2026-10-23-sprint-dag-agentstap-niet-meer-dan-de-starter) "
    "en werk daarna deze test bij."
)


class TestDeWerkelijkeStand:
    def test_een_agentstap_kan_geen_tool_uitvoeren_zonder_startertoets(self) -> None:
        veilig, reden = agentstap_is_veilig(_lees(AGENT_FACTORY), _lees(INTERFACES), _lees(ENGINE))

        assert veilig, _MELDING.format(kant="Een agentstap", reden=reden)

    def test_een_taalmodelstap_kan_geen_tool_uitvoeren_zonder_startertoets(self) -> None:
        veilig, reden = taalmodelstap_is_veilig(_lees(TENANT_DEUR), _lees(PROVIDERS), _lees(ENGINE))

        assert veilig, _MELDING.format(kant="Een taalmodelstap", reden=reden)

    def test_de_gelezen_klassen_bestaan_nog(self) -> None:
        """Een hernoemde klasse zou elke controle hierboven stil groen of rood maken."""
        assert (
            _klasse(_lees(AGENT_FACTORY), "AgentFactory") is not None,
            _klasse(_lees(INTERFACES), "BaseAgent") is not None,
            _klasse(_lees(TENANT_DEUR), "TenantTaalmodel") is not None,
            _klasse(_lees(PROVIDERS), "ProductionLLMProvider") is not None,
            _klasse(_lees(ENGINE), "ProductionWorkflowEngine") is not None,
        ) == (True, True, True, True, True)

    def test_de_stapmethodes_bestaan_nog(self) -> None:
        engine = _klasse(_lees(ENGINE), "ProductionWorkflowEngine")
        assert engine is not None
        assert (
            _methode(engine, "_execute_agent_task") is not None,
            _methode(engine, "_execute_llm_task") is not None,
        ) == (True, True)


class TestHetGedragVanDeRouter:
    """De methode die een agent zoekt geeft voor GEEN enkele agent iets terug.

    Dit vangt elke omweg die de bronteksttoets niet ziet: een ander register, een metaclass, `setattr` bij het
    opstarten, een basisklasse met `get_instance`.
    """

    @staticmethod
    def _agentnamen() -> list[str]:
        namen = ["executor_agent_001", "summary_agent", "dunning", "skillsgaptraining", "workflow_engine"]
        namen += sorted(p.stem for p in (WORTEL / "config" / "agents").glob("*.yaml"))[:60]
        return namen

    def test_resolve_agent_vindt_geen_enkele_agent(self) -> None:
        from src.core.agents.agent_router_agent import AgentRouterAgent

        router = object.__new__(AgentRouterAgent)
        router.tenant_id = 1
        gevonden = [n for n in self._agentnamen() if router._resolve_agent(n) is not None]

        assert gevonden == [], (
            f"`_resolve_agent` vindt nu een agent ({gevonden[:3]}): dan kan een agentstap een agent draaien. "
            "Voeg EERST de startertoets toe aan `_execute_agent_task` en werk daarna deze test bij."
        )

    def test_de_lijst_met_agentnamen_is_niet_leeg(self) -> None:
        assert len(self._agentnamen()) > 10


class TestDeTerugvalImporteertDeAbstracteBaseAgent:
    def test_de_runtime_haalt_baseagent_uit_base_agent_en_dat_is_een_doorgifte(self) -> None:
        providers = ast.parse(_lees(PROVIDERS))
        importeert = any(
            isinstance(k, ast.ImportFrom)
            and k.module == "src.core.agents.base_agent"
            and any(a.name == "BaseAgent" for a in k.names)
            for k in ast.walk(providers)
        )
        base_agent = _lees("src/core/agents/base_agent.py")
        eigen_klasse = _klasse(base_agent, "BaseAgent") is not None
        uit_interfaces = any(
            isinstance(k, ast.ImportFrom)
            and (k.module or "").endswith("shared.interfaces")
            and any(a.name == "BaseAgent" for a in k.names)
            for k in ast.walk(ast.parse(base_agent))
        )

        assert (importeert, eigen_klasse, uit_interfaces) == (True, False, True), (
            "De terugvalroute importeert `BaseAgent` niet meer uit `src.core.agents.base_agent`, of dat bestand "
            "definieert nu een eigen (mogelijk concrete) `BaseAgent`: controleer of de terugval nog dood is."
        )


_FACTORY_ZONDER = "class AgentFactory:\n    def parse_agent_markdown(self):\n        pass\n"
_FACTORY_MET = "class AgentFactory:\n    @classmethod\n    def get_instance(cls, agent_id, tenant_id):\n        return None\n"
_FACTORY_ANDERE_KLASSE = "class AgentFactory:\n    def parse(self):\n        pass\n\nclass Anders:\n    def get_instance(self):\n        pass\n"
_BASE_ABSTRACT = (
    "from abc import ABC, abstractmethod\n"
    "class BaseAgent(ABC):\n"
    "    @abstractmethod\n"
    "    async def process_task(self, t):\n"
    "        ...\n"
)
_BASE_CONCREET = "class BaseAgent:\n    async def process_task(self, t):\n        return None\n"
_ENGINE_ZONDER = (
    "class ProductionWorkflowEngine:\n"
    "    async def _execute_agent_task(self, cfg, ctx, tenant_id=None):\n"
    "        return 1\n"
    "    async def _execute_llm_task(self, cfg, ctx, tenant_id=None):\n"
    "        return 1\n"
)
_ENGINE_MET_STARTER = (
    "class ProductionWorkflowEngine:\n"
    "    async def _execute_agent_task(self, cfg, ctx, tenant_id=None, starter=None):\n"
    "        return await starter_heeft_toolrecht(starter, cfg, tenant_id)\n"
    "    async def _execute_llm_task(self, cfg, ctx, tenant_id=None, starter=None):\n"
    "        return await starter_heeft_toolrecht(starter, cfg, tenant_id)\n"
)
_ENGINE_STARTER_ONGEBRUIKT = (
    "class ProductionWorkflowEngine:\n"
    "    async def _execute_agent_task(self, cfg, ctx, tenant_id=None, starter=None):\n"
    "        return 1\n"
    "    async def _execute_llm_task(self, cfg, ctx, tenant_id=None, starter=None):\n"
    "        return 1\n"
)
_ENGINE_STARTER_ALLEEN_GELOGD = (
    "class ProductionWorkflowEngine:\n"
    "    async def _execute_agent_task(self, cfg, ctx, tenant_id=None, starter=None):\n"
    "        logger.info(starter)\n"
    "        return 1\n"
    "    async def _execute_llm_task(self, cfg, ctx, tenant_id=None, starter=None):\n"
    "        return 1\n"
)
_PROVIDERS_MET_GENERATE_WITH_TOOLS = (
    "class ProductionLLMProvider:\n"
    "    async def generate(self, prompt):\n"
    "        return await deur.generate_with_tools(prompt, [1])\n"
)
_PROVIDERS_MET_DUBBELE_STERREN = (
    "class ProductionLLMProvider:\n"
    "    async def generate(self, prompt, **kwargs):\n"
    "        return await deur.tekst_met_gebruik(prompt, **kwargs)\n"
)
_DEUR_ZONDER = (
    "class TenantTaalmodel:\n"
    "    async def tekst_met_gebruik(self, prompt, *, systeem=None, temperature=None, max_tokens=None):\n"
    "        return ''\n"
)
_DEUR_MET_TOOLS = "class TenantTaalmodel:\n    async def tekst_met_gebruik(self, prompt, *, tools=None):\n        return ''\n"
_DEUR_MET_KWARGS = "class TenantTaalmodel:\n    async def tekst_met_gebruik(self, prompt, **kwargs):\n        return ''\n"
_PROVIDERS_ZONDER = (
    "class ProductionLLMProvider:\n"
    "    async def generate(self, prompt):\n"
    "        return await deur.tekst_met_gebruik(prompt, systeem=None)\n"
)
_PROVIDERS_MET_TOOLS = (
    "class ProductionLLMProvider:\n"
    "    async def generate(self, prompt):\n"
    "        return await deur.tekst_met_gebruik(prompt, tools=[1])\n"
)


class TestDeControlesVindenWatZeMoetenVinden:
    def test_een_nieuwe_get_instance_maakt_een_agent_vindbaar(self) -> None:
        veilig, reden = agentstap_is_veilig(_FACTORY_MET, _BASE_ABSTRACT, _ENGINE_ZONDER)

        assert (veilig, "get_instance" in reden) == (False, True)

    def test_een_concrete_baseagent_maakt_de_terugvalroute_levend(self) -> None:
        veilig, reden = agentstap_is_veilig(_FACTORY_ZONDER, _BASE_CONCREET, _ENGINE_ZONDER)

        assert (veilig, "BaseAgent" in reden) == (False, True)

    def test_beide_gaten_tegelijk_staan_allebei_in_de_melding(self) -> None:
        veilig, reden = agentstap_is_veilig(_FACTORY_MET, _BASE_CONCREET, _ENGINE_ZONDER)

        assert (veilig, "get_instance" in reden, "BaseAgent" in reden) == (False, True, True)

    def test_een_ongebruikte_starterparameter_telt_niet_als_toets(self) -> None:
        veilig, _ = agentstap_is_veilig(_FACTORY_MET, _BASE_ABSTRACT, _ENGINE_STARTER_ONGEBRUIKT)

        assert veilig is False

    def test_een_taalmodel_met_een_toolsparameter(self) -> None:
        veilig, reden = taalmodelstap_is_veilig(_DEUR_MET_TOOLS, _PROVIDERS_ZONDER, _ENGINE_ZONDER)

        assert (veilig, "tools" in reden) == (False, True)

    def test_een_taalmodel_met_open_kwargs_kan_alles_doorgeven(self) -> None:
        veilig, _ = taalmodelstap_is_veilig(_DEUR_MET_KWARGS, _PROVIDERS_ZONDER, _ENGINE_ZONDER)

        assert veilig is False

    def test_een_starter_die_alleen_wordt_gelogd_is_geen_toets(self) -> None:
        veilig, _ = agentstap_is_veilig(_FACTORY_MET, _BASE_ABSTRACT, _ENGINE_STARTER_ALLEEN_GELOGD)

        assert veilig is False

    def test_een_provider_die_generate_with_tools_aanroept(self) -> None:
        veilig, reden = taalmodelstap_is_veilig(_DEUR_ZONDER, _PROVIDERS_MET_GENERATE_WITH_TOOLS, _ENGINE_ZONDER)

        assert (veilig, "generate" in reden) == (False, True)

    def test_een_provider_die_alles_doorgeeft_met_dubbele_sterren(self) -> None:
        veilig, _ = taalmodelstap_is_veilig(_DEUR_ZONDER, _PROVIDERS_MET_DUBBELE_STERREN, _ENGINE_ZONDER)

        assert veilig is False

    def test_een_provider_die_tools_doorgeeft(self) -> None:
        veilig, reden = taalmodelstap_is_veilig(_DEUR_ZONDER, _PROVIDERS_MET_TOOLS, _ENGINE_ZONDER)

        assert (veilig, "generate" in reden) == (False, True)


class TestDeControlesLatenLegitiemeBronMetRust:
    def test_de_huidige_vorm_is_veilig_door_ontwerp(self) -> None:
        veilig, _ = agentstap_is_veilig(_FACTORY_ZONDER, _BASE_ABSTRACT, _ENGINE_ZONDER)

        assert veilig is True

    def test_get_instance_in_een_andere_klasse_van_hetzelfde_bestand_telt_niet(self) -> None:
        veilig, _ = agentstap_is_veilig(_FACTORY_ANDERE_KLASSE, _BASE_ABSTRACT, _ENGINE_ZONDER)

        assert veilig is True

    def test_met_een_echte_startertoets_mag_een_agent_wel_vindbaar_zijn(self) -> None:
        veilig, reden = agentstap_is_veilig(_FACTORY_MET, _BASE_CONCREET, _ENGINE_MET_STARTER)

        assert (veilig, reden) == (True, "de agentstap toetst de starter")

    def test_een_taalmodel_zonder_tools_is_veilig(self) -> None:
        veilig, _ = taalmodelstap_is_veilig(_DEUR_ZONDER, _PROVIDERS_ZONDER, _ENGINE_ZONDER)

        assert veilig is True

    def test_een_taalmodelstap_met_een_startertoets_mag_tools_hebben(self) -> None:
        veilig, reden = taalmodelstap_is_veilig(
            _DEUR_MET_TOOLS, _PROVIDERS_MET_TOOLS, _ENGINE_MET_STARTER
        )

        assert (veilig, reden) == (True, "de taalmodelstap toetst de starter")


@pytest.mark.parametrize(
    ("bron", "klasse", "naam", "verwacht"),
    [
        (_FACTORY_MET, "AgentFactory", "get_instance", True),
        (_FACTORY_ZONDER, "AgentFactory", "get_instance", False),
        ("class A:\n    get_instance = None\n", "A", "get_instance", True),
        ("class A:\n    get_instance: int = 1\n", "A", "get_instance", True),
        ("class B:\n    pass\n", "A", "get_instance", False),
    ],
)
def test_klasse_definieert_ziet_methoden_en_attributen_van_precies_die_klasse(
    bron: str, klasse: str, naam: str, verwacht: bool
) -> None:
    assert klasse_definieert(bron, klasse, naam) is verwacht
