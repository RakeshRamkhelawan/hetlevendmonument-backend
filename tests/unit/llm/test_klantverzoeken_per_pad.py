"""Per gemeld pad: met `DEEPSEEK_API_KEY` gezet gaat een tenantverzoek NIET naar DeepSeek (brief 2026-10-19).

Alles op de HTTP-laag (`tests/fixtures/taalmodel_verkeer.py`): geen mock van een clientklasse, want dat
ziet een eigen `openai.OpenAI(...)` of `ChatOpenAI` niet. Een tenant heeft hier de standaardkeuze (Mistral):
`LLMService.for_tenant` wordt vervangen door een echte stapel-B-service met een Mistral-provider, zodat het
verkeer er werkelijk naar `api.mistral.ai` gaat.

Elk pad krijgt alle niet-gekozen sleutels in de omgeving (DeepSeek, Qwen, Google), omdat de oude code juist
op het bestaan van een sleutel een leverancier koos.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tests.fixtures.taalmodel_verkeer import Verkeer, installeer_verkeer

NEPSLEUTEL = "test-" + "mistral-" + "nepsleutel-0123456789"
ANDERE_SLEUTEL = "test-" + "andere-" + "nepsleutel-0123456789"
TENANT = 7


@pytest.fixture(autouse=True)
def _alle_sleutels_en_een_deepseek_uitrol(monkeypatch: pytest.MonkeyPatch) -> None:
    """De uitrol van vandaag: DeepSeek als platformstandaard en alle andere sleutels gezet."""
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", ANDERE_SLEUTEL)
    monkeypatch.setenv("QWEN_API_KEY", ANDERE_SLEUTEL)
    monkeypatch.setenv("GOOGLE_API_KEY", ANDERE_SLEUTEL)
    monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)


@pytest.fixture
def klantmodel(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """`for_tenant` levert de Mistralservice van een tenant met de standaardkeuze, en onthoudt de tenant."""
    from src.core.services.llm.base import LLMConfig
    from src.core.services.llm.providers.mistral import MistralProvider
    from src.core.services.llm.service import LLMService

    opgevraagd: list[int] = []

    async def nep(tenant_id: int) -> LLMService:
        opgevraagd.append(tenant_id)
        return LLMService(
            provider_instance=MistralProvider(
                LLMConfig(model="mistral-small-latest", api_key=NEPSLEUTEL)
            )
        )

    monkeypatch.setattr(LLMService, "for_tenant", staticmethod(nep))
    return opgevraagd


def _alleen_mistral(verkeer: Verkeer) -> None:
    assert (verkeer.verboden(), sorted(set(verkeer.hosts))) == ([], ["api.mistral.ai"])


@pytest.mark.asyncio
class TestDeRouterstuurtGeenTaakNaarDeepseek:
    async def test_tier_vier_van_de_routering_gebruikt_de_keuze_van_de_klant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.als import router as router_module

        verkeer = installeer_verkeer(monkeypatch, "agent_x")

        class _Pool:
            async def get_client(self) -> object:
                return object()

        monkeypatch.setattr(
            "src.core.als.infrastructure.redis_pool.RedisPoolManager", lambda: _Pool()
        )
        monkeypatch.setattr(
            "src.core.als.agents.organism_registry.get_organism_registry", lambda: object()
        )

        async def klaar(self: object) -> bool:
            return True

        monkeypatch.setattr(router_module.RouterService, "initialize", klaar)
        agent = router_module.AgentRouterAgent(tenant_id=TENANT, signal_bus=None)
        await agent.initialize()

        await agent._service._llm.generate_response("welke agent?")  # type: ignore[union-attr]

        _alleen_mistral(verkeer)


@pytest.mark.asyncio
class TestDeFocusGeneratorStuurtDeGebruikersvraagNietNaarDeepseek:
    async def test_de_node_gebruikt_de_keuze_van_de_klant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.domains.agentic.nodes.focus_generator import focus_generator_node

        graaf = json.dumps({"focus_flow": {"graph": {"nodes": [], "edges": []}}})
        verkeer = installeer_verkeer(monkeypatch, graaf)

        uitslag = await focus_generator_node(  # type: ignore[misc]
            {
                "input": "maak een flow",
                "chat_history": [],
                "intermediate_steps": [],
                "focus_flow": None,
                "tenant_id": TENANT,
            }
        )

        _alleen_mistral(verkeer)
        assert "focus_flow" in uitslag and klantmodel == [TENANT]

    async def test_zonder_tenant_in_de_state_is_het_een_fout_en_geen_platformmodel(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.domains.agentic.nodes.focus_generator import focus_generator_node

        verkeer = installeer_verkeer(monkeypatch)

        uitslag = await focus_generator_node(  # type: ignore[misc]
            {"input": "x", "chat_history": [], "intermediate_steps": [], "focus_flow": None}
        )

        assert (verkeer.hosts, "error" in uitslag["focus_flow"]) == ([], True)


@pytest.mark.asyncio
class TestDeWorkflowgeneratorKiestGeenEigenLeverancier:
    async def test_een_generatie_gaat_naar_de_keuze_van_de_klant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.services.workflow_generator_service import WorkflowGeneratorAgent

        verkeer = installeer_verkeer(monkeypatch, '{"nodes": [], "edges": []}')
        agent = WorkflowGeneratorAgent(tenant_id=TENANT)

        uitslag = await agent._call_llm("systeem", "gebruiker")

        _alleen_mistral(verkeer)
        assert uitslag == {"nodes": [], "edges": []}

    async def test_een_chirurgische_aanroep_gaat_ook_naar_de_keuze_van_de_klant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.services.workflow_generator_service import WorkflowGeneratorAgent

        verkeer = installeer_verkeer(monkeypatch, "klaar")
        agent = WorkflowGeneratorAgent(tenant_id=TENANT)

        await agent._call_llm_surgical("pas dit aan")

        _alleen_mistral(verkeer)

    async def test_een_onbekende_provider_valt_niet_terug_op_gemini_deepseek_qwen_of_mock(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.services.workflow_generator_service import WorkflowGeneratorAgent

        monkeypatch.setenv("LLM_PROVIDER", "mistral")
        agent = WorkflowGeneratorAgent(tenant_id=TENANT)

        assert agent.is_mock is False and not hasattr(agent, "genai_client")


@pytest.mark.asyncio
class TestDeFocussuggestiesGebruikenDeKeuzeVanDeKlant:
    async def test_suggesties_gaan_naar_de_keuze_van_de_klant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.services.focus_suggestion_service import (
            FocusSuggestionService,
            SuggestionRequest,
            WorkflowPhase,
        )

        verkeer = installeer_verkeer(monkeypatch, "[]")
        dienst = FocusSuggestionService(tenant_id=TENANT)

        await dienst.get_suggestions(
            SuggestionRequest(
                prompt="mail versturen", current_nodes=[], phase=WorkflowPhase.DISCOVER
            )
        )

        _alleen_mistral(verkeer)

    async def test_een_storing_geeft_regelgebaseerde_suggesties_die_zo_heten(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.focus_suggestion_service import (
            FocusSuggestionService,
            SuggestionRequest,
            WorkflowPhase,
        )
        from src.core.services.llm.service import LLMService

        async def kapot(tenant_id: int) -> object:
            raise RuntimeError("model weg")

        monkeypatch.setattr(LLMService, "for_tenant", staticmethod(kapot))
        verkeer = installeer_verkeer(monkeypatch)
        dienst = FocusSuggestionService(tenant_id=TENANT)

        antwoord = await dienst.get_suggestions(
            SuggestionRequest(
                prompt="mail versturen", current_nodes=[], phase=WorkflowPhase.DISCOVER
            )
        )

        assert (verkeer.hosts, antwoord.llm_provider) == ([], "regels")


@pytest.mark.asyncio
class TestDeAgenticFlowServiceGebruiktGeenStandaardDeepseek:
    async def test_een_analyse_gaat_naar_de_keuze_van_de_klant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.domains.flows.agentic_service import AgenticFlowService

        verkeer = installeer_verkeer(monkeypatch, "een plan")
        dienst = AgenticFlowService(tenant_id=TENANT)

        await dienst.start_interactive_session("verstuur een mail", "sessie-1")

        _alleen_mistral(verkeer)


@pytest.mark.asyncio
class TestDeLokaleClientValtNietStilTerugOpEenGehuurdModel:
    async def test_een_storing_in_het_lokale_model_is_een_fout_en_geen_deepseek_of_gemini(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        from src.core.shared.llm_client import (
            LLMConfig,
            LLMMessage,
            LLMModel,
            LLMProvider,
            LocalClient,
        )

        verkeer = Verkeer()

        async def lokaal_kapot(
            self: httpx.AsyncHTTPTransport, request: httpx.Request
        ) -> httpx.Response:
            verkeer.hosts.append(request.url.host)
            return httpx.Response(503, text="model weg")

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", lokaal_kapot)
        monkeypatch.setattr(
            "src.core.shared.config.get_settings",
            lambda: SimpleNamespace(
                LOCAL_LLM_URL="http://localhost:11434/v1",
                deepseek_api_key=ANDERE_SLEUTEL,
                google_api_key=ANDERE_SLEUTEL,
            ),
        )
        client = LocalClient(
            LLMConfig(provider=LLMProvider.LOCAL, model=LLMModel.LLAMA_3, api_key="local")
        )

        antwoord = await client.chat_completion([LLMMessage(role="user", content="hoi")])

        assert (antwoord.success, verkeer.verboden()) == (False, [])


@pytest.mark.asyncio
class TestDeFeedbackEnOrkestratieAgentsGebruikenDeKeuzeVanDeKlant:
    async def test_de_feedbackagent_gebruikt_de_keuze_van_de_klant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.agents.execution_feedback_agent import ExecutionFeedbackAgent

        verkeer = installeer_verkeer(monkeypatch, "[]")
        agent = ExecutionFeedbackAgent(tenant_id=TENANT)

        await agent._analyze_with_llm("context", "failed", "boom")

        _alleen_mistral(verkeer)

    async def test_de_orkestratieagent_gebruikt_de_keuze_van_de_klant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.agents.workflow_orchestrator_agent import WorkflowOrchestratorAgent

        verkeer = installeer_verkeer(monkeypatch, "[]")
        agent = WorkflowOrchestratorAgent(tenant_id=TENANT, user_id=1)

        await agent._generate_suggestions_with_llm("maak sneller", "context")

        _alleen_mistral(verkeer)

    async def test_een_afgeschafte_deepseekkeuze_in_de_constructor_bestaat_niet_meer(self) -> None:
        import inspect

        from src.core.agents.execution_feedback_agent import ExecutionFeedbackAgent
        from src.core.agents.workflow_orchestrator_agent import WorkflowOrchestratorAgent

        assert "llm_provider" not in inspect.signature(ExecutionFeedbackAgent).parameters
        assert "llm_provider" not in inspect.signature(WorkflowOrchestratorAgent).parameters


@pytest.mark.asyncio
class TestDeCvaChatGebruiktDeKeuzeVanDeKlant:
    async def test_de_dependency_vraagt_het_model_van_de_tenant_van_het_verzoek(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.api.v1.cva.dependencies import get_llm_service_dependency

        verkeer = installeer_verkeer(monkeypatch, "antwoord")

        dienst = await get_llm_service_dependency(current_user=SimpleNamespace(tenant_id=TENANT))  # type: ignore[arg-type]
        await dienst.generate([_bericht("hallo")])

        assert klantmodel == [TENANT]
        _alleen_mistral(verkeer)

    async def test_zonder_meegegeven_dienst_kiest_de_cva_service_het_model_van_de_tenant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from unittest.mock import AsyncMock

        from src.core.services.cva_service import CVAService

        verkeer = installeer_verkeer(monkeypatch, "antwoord")

        dienst = await CVAService(db_session=AsyncMock())._llm_voor(TENANT)
        await dienst.generate([_bericht("hallo")])

        assert klantmodel == [TENANT]
        _alleen_mistral(verkeer)


@pytest.mark.asyncio
class TestDeCopilotGebruiktDeKeuzeVanDeKlant:
    async def test_de_json_aanroep_van_de_handler_gaat_naar_het_model_van_de_tenant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.copilot.llm_handler import LLMHandler
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        verkeer = installeer_verkeer(monkeypatch, "{}")
        handler = LLMHandler(provider=TenantTaalmodel(TENANT))

        antwoord = await handler._provider.complete_json(  # type: ignore[attr-defined]
            [_bericht("doe iets")], dict
        )

        assert (antwoord.success, klantmodel) == (True, [TENANT])
        _alleen_mistral(verkeer)

    async def test_de_auditnaam_van_het_model_is_het_gekozen_model_en_niet_deepseek(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.copilot.llm_handler import LLMHandler
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        installeer_verkeer(monkeypatch, "{}")
        door = TenantTaalmodel(TENANT)
        handler = LLMHandler(provider=door)

        await door.complete_json([_bericht("doe iets")], dict)

        assert handler.model_id == "mistral:mistral-small-latest"


@pytest.mark.asyncio
class TestDeCragKnopenGebruikenDeKeuzeVanDeKlant:
    async def test_het_beoordelen_van_documenten_gaat_naar_het_model_van_de_tenant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.agents.crag_graph import grade_documents

        verkeer = installeer_verkeer(monkeypatch, "yes")

        uitslag = await grade_documents(
            {
                "query": "vraag",
                "documents": [{"id": 1, "content": "klantdocument"}],
                "web_search_needed": False,
                "generation": "",
                "tenant_id": TENANT,
                "metadata": {},
            }
        )

        assert (len(uitslag["documents"]), klantmodel) == (1, [TENANT])
        _alleen_mistral(verkeer)


    async def test_het_herschrijven_van_de_vraag_gaat_naar_het_model_van_de_tenant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.agents.crag_graph import transform_query

        verkeer = installeer_verkeer(monkeypatch, "betere vraag")

        uitslag = await transform_query(
            {
                "query": "vraag",
                "documents": [],
                "web_search_needed": True,
                "generation": "",
                "tenant_id": TENANT,
                "metadata": {},
            }
        )

        assert (uitslag["query"], klantmodel) == ("betere vraag", [TENANT])
        _alleen_mistral(verkeer)

    async def test_het_genereren_van_het_antwoord_gaat_naar_het_model_van_de_tenant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.agents.crag_graph import generate

        verkeer = installeer_verkeer(monkeypatch, "het antwoord")

        uitslag = await generate(
            {
                "query": "vraag",
                "documents": [{"id": 1, "content": "klantdocument"}],
                "web_search_needed": False,
                "generation": "",
                "tenant_id": TENANT,
                "metadata": {},
            }
        )

        assert (uitslag["generation"], klantmodel) == ("het antwoord", [TENANT])
        _alleen_mistral(verkeer)


@pytest.mark.asyncio
class TestHetGeheugenVanEenAgentGebruiktDeKeuzeVanDeKlant:
    async def test_het_samenvatten_van_signalen_gaat_naar_het_model_van_hun_tenant(
        self, monkeypatch: pytest.MonkeyPatch, klantmodel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.als.agents.memory import ContextCompressor
        from src.core.als.infrastructure.signal_bus import Signal, SignalTier

        verkeer = installeer_verkeer(monkeypatch, "samenvatting")
        signaal = Signal(
            tenant_id=TENANT,
            source_agent_id="a",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={"text": "klantgegeven"},
        )

        samenvatting = await ContextCompressor()._summarize_signals([signaal])

        assert (samenvatting, klantmodel) == ("samenvatting", [TENANT])
        _alleen_mistral(verkeer)


def _bericht(tekst: str) -> object:
    from src.core.services.llm.base import LLMMessage

    return LLMMessage(role="user", content=tekst)
