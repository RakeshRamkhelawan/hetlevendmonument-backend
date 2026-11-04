"""De workflowgenerator stelt alleen agents voor die een stap echt kan uitvoeren (agentstap dag 2, Keten G).

Een voorstel met een andere agent (een koppeling, een catalogusagent zonder uitvoering) wordt niet stil overgenomen: de klant
krijgt een Nederlandse melding en er komt geen stap met die agent. Is er voor de klant geen enkele agent te kiezen (het
pakket staat uit), dan wordt het taalmodel niet eens gebeld en leest de klant wat de beheerder moet aanzetten.

De lijst zelf komt uit `workflow_stap.uitvoerbare_agents_voor_klant`; die wordt hier vervangen (de pakketschakelaar en de
catalogus hebben eigen tests in `tests/integration/test_agentstap_de_gekozen_agent_draait.py`).

**Mutatiebewijs (2026-10-25):** zie de eindmelding van de sessie.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.services.workflow_generator_service import WorkflowGeneratorAgent

LIJST = [
    {
        "agent_id": "dunning",
        "name": "Debiteurenagent",
        "naam": "Debiteurenagent",
        "omschrijving": "Volgt openstaande facturen op.",
    },
    {
        "agent_id": "vatcompliance",
        "name": "Btw-overzicht",
        "naam": "Btw-overzicht",
        "omschrijving": "Maakt een btw-overzicht.",
    },
]


def _voorstel(agent: str) -> dict[str, object]:
    return {
        "name": "voorstel",
        "description": "d",
        "nodes": [
            {
                "id": "n1",
                "agent_name": agent,
                "label": "Facturen nalopen",
                "config": {},
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }


def _verzoek() -> object:
    from starlette.requests import Request

    verzoek = Request(
        {"type": "http", "method": "GET", "path": "/api/v1/vibe/agents/uitvoerbaar", "headers": [], "query_string": b""}
    )
    verzoek.state.user = SimpleNamespace(id=1, tenant_id=1)
    return verzoek


def _generator() -> WorkflowGeneratorAgent:
    generator = WorkflowGeneratorAgent(tenant_id=1, correlation_id="t")
    generator.max_retries = 1
    generator.retry_base_delay = 0
    return generator


def _lijst(lijst: list[dict[str, str]]) -> AbstractContextManager[AsyncMock]:
    return patch(
        "src.core.als.agents.workflow_stap.uitvoerbare_agents_voor_klant",
        AsyncMock(return_value=lijst),
    )


@pytest.mark.asyncio
class TestDeGeneratorBiedtAlleenUitvoerbareAgentsAan:
    async def test_de_aangeboden_agents_zijn_de_uitvoerbare_lijst_met_nederlandse_tekst(
        self,
    ) -> None:
        with _lijst(LIJST):
            agents = await _generator().get_uitvoerbare_agents()

        assert [a["name"] for a in agents] == ["dunning", "vatcompliance"]
        assert "Debiteurenagent" in str(agents[0]["description"])

    async def test_een_voorstel_met_een_niet_uitvoerbare_agent_geeft_een_melding_en_geen_stap(
        self,
    ) -> None:
        generator = _generator()
        with (
            _lijst(LIJST),
            patch.object(generator, "_call_llm", AsyncMock(return_value=_voorstel("email_agent"))),
        ):
            succes, workflow, fout = await generator.generate_workflow("stuur een mail")

        assert (succes, workflow) == (False, None)
        assert fout is not None and "kan nog niet in een workflow draaien" in fout
        assert "dunning" in fout and "vatcompliance" in fout

    async def test_een_voorstel_met_een_uitvoerbare_agent_wordt_gewoon_overgenomen(self) -> None:
        generator = _generator()
        with (
            _lijst(LIJST),
            patch.object(generator, "_call_llm", AsyncMock(return_value=_voorstel("dunning"))),
        ):
            succes, workflow, fout = await generator.generate_workflow("volg facturen op")

        assert succes is True and fout is None
        assert workflow is not None and [n.agent_name for n in workflow.nodes] == ["dunning"]

    async def test_zonder_enige_uitvoerbare_agent_wordt_het_taalmodel_niet_gebeld(self) -> None:
        generator = _generator()
        llm = AsyncMock(return_value=_voorstel("dunning"))
        with _lijst([]), patch.object(generator, "_call_llm", llm):
            succes, workflow, fout = await generator.generate_workflow("volg facturen op")

        assert (succes, workflow) == (False, None)
        assert fout is not None and "pakket" in fout and "aan te zetten" in fout
        assert llm.await_count == 0

    async def test_een_voorgestelde_stap_draagt_de_agent_en_de_opdracht_voor_de_engine(
        self,
    ) -> None:
        generator = _generator()
        gebeurtenissen: list[dict[str, object]] = []

        async def vang(gebeurtenis: dict[str, object]) -> None:
            gebeurtenissen.append(gebeurtenis)

        with (
            _lijst(LIJST),
            patch.object(generator, "_call_llm", AsyncMock(return_value=_voorstel("dunning"))),
        ):
            await generator.generate_workflow("volg facturen op", stream_callback=vang)

        stap = next(g for g in gebeurtenissen if g.get("type") == "node_proposed")["node"]
        assert stap["data"]["agent_id"] == "dunning"  # type: ignore[index]
        assert stap["data"]["instruction"] == "Facturen nalopen"  # type: ignore[index]


@pytest.mark.asyncio
class TestHetVoorstelWordtGevalideerdMetNederlandseMeldingen:
    async def test_een_voorstel_met_een_cyclus_geeft_een_melding_geen_typefout(self) -> None:
        voorstel = _voorstel("dunning")
        voorstel["nodes"] = [
            {"id": "a", "agent_name": "dunning", "label": "A", "config": {}, "position": {"x": 0, "y": 0}},
            {"id": "b", "agent_name": "dunning", "label": "B", "config": {}, "position": {"x": 1, "y": 0}},
        ]
        voorstel["edges"] = [
            {"id": "e1", "source": "a", "target": "b"},
            {"id": "e2", "source": "b", "target": "a"},
        ]
        generator = _generator()
        with _lijst(LIJST), patch.object(generator, "_call_llm", AsyncMock(return_value=voorstel)):
            succes, workflow, fout = await generator.generate_workflow("volg facturen op")

        assert (succes, workflow) == (False, None)
        assert fout is not None and "TypeError" not in fout and "__new__" not in fout

    async def test_een_losse_knoop_geeft_een_melding_geen_typefout(self) -> None:
        voorstel = _voorstel("dunning")
        voorstel["nodes"] = [
            {"id": "a", "agent_name": "dunning", "label": "A", "config": {}, "position": {"x": 0, "y": 0}},
            {"id": "b", "agent_name": "dunning", "label": "B", "config": {}, "position": {"x": 1, "y": 0}},
        ]
        voorstel["edges"] = []
        generator = _generator()
        with _lijst(LIJST), patch.object(generator, "_call_llm", AsyncMock(return_value=voorstel)):
            succes, workflow, fout = await generator.generate_workflow("volg facturen op")

        assert (succes, workflow) == (False, None)
        assert fout is not None and "TypeError" not in fout and "__new__" not in fout

    async def test_de_config_van_het_taalmodel_overschrijft_de_gekozen_agent_niet(self) -> None:
        voorstel = _voorstel("dunning")
        voorstel["nodes"][0]["config"] = {"agent_id": "email_agent", "instruction": 5}  # type: ignore[index]
        generator = _generator()
        gebeurtenissen: list[dict[str, object]] = []

        async def vang(gebeurtenis: dict[str, object]) -> None:
            gebeurtenissen.append(gebeurtenis)

        with _lijst(LIJST), patch.object(generator, "_call_llm", AsyncMock(return_value=voorstel)):
            await generator.generate_workflow("volg facturen op", stream_callback=vang)

        stap = next(g for g in gebeurtenissen if g.get("type") == "node_proposed")["node"]
        assert stap["data"]["agent_id"] == "dunning"  # type: ignore[index]
        assert isinstance(stap["data"]["instruction"], str)  # type: ignore[index]


@pytest.mark.asyncio
class TestDeLijstVoorDeBouwer:
    async def test_een_lege_lijst_krijgt_een_nederlandse_uitleg(self) -> None:
        from src.core.api.v1.workflow.workflow_generation_router import list_executable_agents

        with _lijst([]):
            antwoord = await list_executable_agents(
                request=_verzoek(),  # type: ignore[arg-type]
                current_user=SimpleNamespace(tenant_id=1),  # type: ignore[arg-type]
            )

        assert antwoord["agents"] == [] and "pakket" in str(antwoord["uitleg"])

    async def test_een_gevulde_lijst_heeft_geen_uitleg_en_draagt_naam_en_omschrijving(self) -> None:
        from src.core.api.v1.workflow.workflow_generation_router import list_executable_agents

        with _lijst(LIJST):
            antwoord = await list_executable_agents(
                request=_verzoek(),  # type: ignore[arg-type]
                current_user=SimpleNamespace(tenant_id=1),  # type: ignore[arg-type]
            )

        assert antwoord["uitleg"] is None
        assert antwoord["agents"][0]["naam"] == "Debiteurenagent"  # type: ignore[index]
        assert antwoord["agents"][0]["omschrijving"]  # type: ignore[index]
