"""Elk omgebouwd pad volgt de modelkeuze van de klant, ook als dat een EIGEN model is (brief 2026-10-20).

De tenant van deze tests koos `ollama`. Alles op de HTTP-laag (`tests/fixtures/taalmodel_verkeer.py`): met
alle sleutels van de andere leveranciers in de omgeving mag het verkeer ALLEEN naar het lokale model gaan, nooit
naar Google, DeepSeek of Mistral. Bij een storing van het lokale model is de uitkomst een FOUT en gaat er
niets naar een ander model.

Gemeten op 8fdb38cb: deze paden gebruikten het platformmodel (Ollama of Google op basis van sleutels in de
omgeving, of een vast `gemini-1.5-flash`), ongeacht de keuze van de tenant.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from tests.fixtures.taalmodel_verkeer import Verkeer, installeer_verkeer

TENANT = 5
SLEUTEL = "test-" + "andere-" + "nepsleutel-0123456789"
LOKAAL = ("localhost", "127.0.0.1")


@pytest.fixture(autouse=True)
def _alle_andere_leveranciers_zijn_beschikbaar(monkeypatch: pytest.MonkeyPatch) -> None:
    for naam in ("GOOGLE_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(naam, SLEUTEL)
    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")


@pytest.fixture
def ollama_tenant(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """`for_tenant` geeft een tenant met keuze `ollama` zijn lokale model; onthoudt de tenant."""
    from src.core.services.llm.base import LLMConfig
    from src.core.services.llm.providers.ollama import OllamaProvider
    from src.core.services.llm.service import LLMService

    opgevraagd: list[int] = []

    async def nep(tenant_id: int) -> LLMService:
        opgevraagd.append(tenant_id)
        return LLMService(
            provider_instance=OllamaProvider(
                LLMConfig(model="llama3", base_url="http://localhost:11434")
            )
        )

    monkeypatch.setattr(LLMService, "for_tenant", staticmethod(nep))
    return opgevraagd


def _alleen_lokaal(verkeer: Verkeer) -> None:
    assert (
        verkeer.verboden(),
        "api.mistral.ai" in verkeer.hosts,
        set(verkeer.hosts) <= set(LOKAAL),
    ) == ([], False, True)


@pytest.mark.asyncio
class TestDeAgentsVolgenDeKeuzeVanDeKlant:
    async def test_een_agent_uit_de_fabriek_krijgt_het_model_van_zijn_tenant(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.agents.base_agent import _setup_llm_client
        from src.core.shared.llm_client import LLMMessage

        verkeer = installeer_verkeer(monkeypatch, "antwoord")

        client = await _setup_llm_client(TENANT)
        assert client is not None
        antwoord = await client.chat_completion([LLMMessage(role="user", content="hallo")])

        assert (antwoord.success, ollama_tenant) == (True, [TENANT])
        _alleen_lokaal(verkeer)

    async def test_de_criticus_gebruikt_het_model_van_zijn_tenant_voor_elke_rechter(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.agents.critic_agent import CriticAgent

        CriticAgent._instances.clear()
        verkeer = installeer_verkeer(monkeypatch, '{"score": 0.7, "issues": [], "suggestions": []}')

        uitslag = await CriticAgent(tenant_id=TENANT)._run_judge_panel("beoordeel", 2, 5.0)

        assert ([s for _, s in uitslag], ollama_tenant) == ([0.7, 0.7], [TENANT])
        _alleen_lokaal(verkeer)

    async def test_de_leerlus_analyseert_met_het_model_van_zijn_tenant(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.agents.learning_loop import LearningLoop

        verkeer = installeer_verkeer(monkeypatch, "een patroon")
        lus = LearningLoop(tenant_id=TENANT)
        assert lus.llm_client is not None

        antwoord = await lus.llm_client.text_completion("beschrijf het patroon")

        assert (antwoord.content, ollama_tenant) == ("een patroon", [TENANT])
        _alleen_lokaal(verkeer)

    async def test_de_ultimate_cva_agent_gebruikt_het_model_van_zijn_tenant(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.agents.ultimate_cva.agent import UltimateCVAAgent

        verkeer = installeer_verkeer(monkeypatch, "antwoord")
        agent = UltimateCVAAgent(tenant_id=TENANT)

        antwoord = await agent.llm_service.generate_response("hallo")

        assert (antwoord["success"], ollama_tenant) == (True, [TENANT])
        _alleen_lokaal(verkeer)


@pytest.mark.asyncio
class TestDeOverigeKlantpaden:
    async def test_de_evaluatie_gebruikt_het_model_van_de_tenant_van_de_evaluatie(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        import importlib

        modul = importlib.import_module("src.core.evaluation.evaluation_service")
        verkeer = installeer_verkeer(monkeypatch, "oordeel")
        dienst = modul.EvaluationService()
        dienst._loop = asyncio.get_running_loop()
        dienst._loop_thread_id = threading.get_ident()

        token = modul._EVALUATIE_TENANT.set(TENANT)
        try:
            uitkomst = dienst._custom_llm_wrapper(["vraag"])
        finally:
            modul._EVALUATIE_TENANT.reset(token)

        assert (uitkomst, ollama_tenant) == (["oordeel"], [TENANT])
        _alleen_lokaal(verkeer)

    async def test_de_copilot_stream_gebruikt_het_model_van_de_tenant(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.api.v1.ai_copilot.router import stream_generator

        verkeer = installeer_verkeer(monkeypatch, "een antwoord")

        brokken = [b async for b in stream_generator("help me", TENANT)]

        assert ("event: text" in "".join(brokken), ollama_tenant) == (True, [TENANT])
        _alleen_lokaal(verkeer)

    async def test_het_llm_generate_tool_gebruikt_het_model_van_de_tenant_uit_de_context(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.middleware.tenant_context import set_tenant_id
        from src.core.tool_broker.local_registry import LocalToolRegistry

        verkeer = installeer_verkeer(monkeypatch, "tekst")
        set_tenant_id(TENANT)
        try:
            uitkomst = await LocalToolRegistry()._tool_llm_generate({"prompt": "schrijf iets"})
        finally:
            set_tenant_id(None)

        assert (uitkomst, ollama_tenant) == ({"success": True, "content": "tekst"}, [TENANT])
        _alleen_lokaal(verkeer)

    async def test_het_llm_generate_tool_zonder_tenantcontext_is_een_fout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.tool_broker.local_registry import LocalToolRegistry

        verkeer = installeer_verkeer(monkeypatch, "tekst")

        uitkomst = await LocalToolRegistry()._tool_llm_generate({"prompt": "schrijf iets"})

        assert (uitkomst["success"], verkeer.hosts) == (False, [])

    async def test_de_twin_geeft_een_suggestie_van_het_model_van_de_tenant(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.learning.interfaces.llm_provider import TenantSuggestionProvider

        verkeer = installeer_verkeer(monkeypatch, "  Neem even pauze.  ")
        provider = TenantSuggestionProvider(TENANT)

        tekst = await provider.suggest({"recent_edits_same_line": 3}, {})

        assert (tekst, ollama_tenant, provider.get_last_token_usage().input_tokens) == (
            "Neem even pauze.",
            [TENANT],
            1,
        )
        _alleen_lokaal(verkeer)


@pytest.mark.asyncio
class TestEenStoringVanHetGekozenModelIsEenFout:
    async def test_de_twin_geeft_dan_geen_suggestie_en_geen_tekst_van_een_ander_model(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.learning.interfaces.llm_provider import TenantSuggestionProvider

        verkeer = installeer_verkeer(monkeypatch, "x", onbereikbaar=LOKAAL)

        tekst = await TenantSuggestionProvider(TENANT).suggest({}, {})

        assert (tekst, verkeer.verboden(), "api.mistral.ai" in verkeer.hosts) == ("", [], False)

    async def test_het_llm_generate_tool_meldt_een_fout_en_valt_niet_terug(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.middleware.tenant_context import set_tenant_id
        from src.core.tool_broker.local_registry import LocalToolRegistry

        verkeer = installeer_verkeer(monkeypatch, "x", onbereikbaar=LOKAAL)
        set_tenant_id(TENANT)
        try:
            uitkomst = await LocalToolRegistry()._tool_llm_generate({"prompt": "p"})
        finally:
            set_tenant_id(None)

        assert (uitkomst["success"], verkeer.verboden(), "api.mistral.ai" in verkeer.hosts) == (
            False,
            [],
            False,
        )

    async def test_de_criticus_telt_de_rechters_als_mislukt_en_valt_niet_terug(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.agents.critic_agent import CriticAgent

        CriticAgent._instances.clear()
        verkeer = installeer_verkeer(monkeypatch, "x", onbereikbaar=LOKAAL)

        uitslag = await CriticAgent(tenant_id=TENANT)._run_judge_panel("beoordeel", 2, 5.0)

        assert ([s for _, s in uitslag], verkeer.verboden(), "api.mistral.ai" in verkeer.hosts) == (
            [None, None],
            [],
            False,
        )


@pytest.mark.asyncio
class TestDeRoutering:
    async def test_de_agentrouter_routeert_met_het_model_van_zijn_tenant(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.agents.agent_router_agent import AgentManifest, AgentRouterAgent
        from src.core.shared.interfaces import TaskData

        verkeer = installeer_verkeer(monkeypatch, '{"agent_id": "financieel"}')
        router = AgentRouterAgent(tenant_id=TENANT)
        router._manifests = {
            "financieel": AgentManifest(
                agent_id="financieel",
                agent_type="specialist",
                capabilities=["boekhouden"],
                department="finance",
            )
        }

        gekozen = await router._llm_route(
            TaskData(title="Betaling controleren", description="factuur 12", metadata={})
        )

        assert (gekozen, ollama_tenant) == ("financieel", [TENANT])
        _alleen_lokaal(verkeer)

    async def test_de_agentrouter_valt_bij_een_storing_niet_terug_op_een_ander_model(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.agents.agent_router_agent import AgentManifest, AgentRouterAgent
        from src.core.shared.interfaces import TaskData

        verkeer = installeer_verkeer(monkeypatch, "x", onbereikbaar=LOKAAL)
        router = AgentRouterAgent(tenant_id=TENANT)
        router._manifests = {
            "financieel": AgentManifest(
                agent_id="financieel", agent_type="specialist", capabilities=["x"], department="f"
            )
        }

        gekozen = await router._llm_route(TaskData(title="t", description="d", metadata={}))

        assert (gekozen, verkeer.verboden(), "api.mistral.ai" in verkeer.hosts) == (None, [], False)

    async def test_de_orkestrator_plant_met_het_model_van_zijn_tenant(
        self, monkeypatch: pytest.MonkeyPatch, ollama_tenant: list[int]
    ) -> None:
        from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent
        from src.core.shared.interfaces import TaskData

        verkeer = installeer_verkeer(monkeypatch, '{"sub_tasks": [{"title": "stap een"}]}')
        agent = MasterOrchestratorAgent(tenant_id=TENANT)

        plan = await agent._plan_workflow(
            "wf1", TaskData(title="Maandafsluiting", description="doe het", metadata={})
        )

        assert ([s.title for s in plan.sub_tasks], ollama_tenant) == (["stap een"], [TENANT])
        _alleen_lokaal(verkeer)


AGENTKLASSEN_VIA_DE_LOADER = [
    ("src.core.agents.analyzer.agent", "AnalyzerAgent"),
    ("src.core.agents.code_agent", "CodeAgent"),
    ("src.core.agents.security_agent", "SecurityAgent"),
    ("src.core.agents.executor_agent", "ExecutorAgent"),
    ("src.core.agents.research_agent", "ResearchAgent"),
    ("src.core.agents.financial_agent", "FinancialAgent"),
    ("src.core.agents.marketing_agent", "MarketingAgent"),
    ("src.core.agents.product_agent", "ProductAgent"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("modulenaam", "klassenaam"), AGENTKLASSEN_VIA_DE_LOADER)
async def test_een_door_de_loader_laadbare_agent_krijgt_het_model_van_zijn_tenant(
    monkeypatch: pytest.MonkeyPatch,
    ollama_tenant: list[int],
    modulenaam: str,
    klassenaam: str,
) -> None:
    """De SubagentLoader kan deze klassen op naam laden (Gate 2 ronde 1, 2026-10-20); hun model is dat van de tenant."""
    import importlib
    from unittest.mock import AsyncMock, MagicMock

    from src.core.shared.llm_client import LLMMessage

    modul = importlib.import_module(modulenaam)
    klasse = getattr(modul, klassenaam)
    if hasattr(modul, "SandboxManagerFactory"):
        monkeypatch.setattr(modul.SandboxManagerFactory, "create_manager", MagicMock())
    if hasattr(klasse, "_setup_execution_environment"):
        monkeypatch.setattr(klasse, "_setup_execution_environment", AsyncMock())
    verkeer = installeer_verkeer(monkeypatch, "antwoord")

    agent = klasse(tenant_id=TENANT)
    assert await agent.initialize() is True
    antwoord = await agent.llm_client.chat_completion([LLMMessage(role="user", content="hallo")])

    assert (antwoord.success, ollama_tenant) == (True, [TENANT])
    _alleen_lokaal(verkeer)
