"""Het toolregister is per klant: een klant kan de tool van een andere klant niet overschrijven, zien of schakelen.

Brief 2026-10-24 (toolregister per klant). Gemeten in de code: `POST /api/v1/tools/` zette een tool onder de kale
naam in het proces-brede woordenboek `available_tools`. Bestond die naam al, ook bij een ANDERE klant, dan werd die
overschreven en kreeg hij de `tenant_id` van de nieuwe aanroeper; `/tools/list`, `/{naam}/status`, `enable`,
`disable` en `execute` zochten allemaal op de naam alleen en zagen dus elkaars tools.

De sleutel is nu `(tenant_id, naam)`; de vijf meegeleverde tools hebben `tenant_id` `None` en zijn voor iedereen
leesbaar. Verwijderen bestaat niet als route, dus daar valt niets te toetsen.

MUTATIEBEWIJS (2026-10-27, productiecode gemuteerd, kopie als terugweg; basis 13 groen):
    sleutel terug naar alleen de naam (geen klant)          -> ROOD (9)
    zoek_tool: elke klant vindt elke tool op naam           -> ROOD (4)
    volledige lijst toont de tools van alle klanten         -> ROOD
    uitvoeren zoekt op naam over klanten                    -> ROOD
    alles terug                                             -> GROEN (13)
BEWUST NIET GEWIJZIGD (bevinding voor de regie): `enable` en `disable` werken op een MEEGELEVERDE tool (zoals
`serena`) voor ELKE klant tegelijk; een bestaande test schakelt hem. Of een klantbeheerder dat mag is een besluit.
"""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.api.v1.tool_broker.crud_router import list_tools_filtered, register_tool
from src.core.api.v1.tool_broker.execution_router import execute_tool
from src.core.api.v1.tool_broker.management_router import (
    disable_tool,
    enable_tool,
    get_tool_status,
    list_tools_all,
)
from src.core.api.v1.tool_broker_shared import (
    ToolCreate,
    ToolExecutionRequest,
    available_tools,
    meegeleverd_gebruik,
)
from src.core.auth.api_deps import UserResponse

KLANT_A = 7101
KLANT_B = 7102
NAAM = "factuurlezer"


def _gebruiker(tenant_id: int) -> UserResponse:
    gebruiker = MagicMock(spec=UserResponse)
    gebruiker.tenant_id = tenant_id
    gebruiker.id = tenant_id * 10
    return gebruiker


def _tool(beschrijving: str, naam: str = NAAM) -> ToolCreate:
    return ToolCreate(
        name=naam, category="finance", capabilities=["lezen"], description=beschrijving
    )


@pytest.fixture(autouse=True)
def _register_terugzetten() -> Iterator[None]:
    voor = {sleutel: dict(waarde) for sleutel, waarde in available_tools.items()}
    meegeleverd_gebruik.clear()
    yield
    available_tools.clear()
    available_tools.update(voor)
    meegeleverd_gebruik.clear()


async def _registreer(tenant_id: int, beschrijving: str, naam: str = NAAM) -> None:
    await register_tool(
        tool_data=_tool(beschrijving, naam), current_user=_gebruiker(tenant_id), _=1
    )


@pytest.mark.asyncio
async def test_klant_b_overschrijft_de_tool_van_klant_a_niet() -> None:
    await _registreer(KLANT_A, "van A")
    await _registreer(KLANT_B, "van B")

    van_a = await list_tools_filtered(current_user=_gebruiker(KLANT_A))

    assert [(t.description, t.tenant_id) for t in van_a] == [("van A", KLANT_A)]


@pytest.mark.asyncio
async def test_klant_b_krijgt_zijn_eigen_tool_onder_dezelfde_naam() -> None:
    await _registreer(KLANT_A, "van A")
    await _registreer(KLANT_B, "van B")

    van_b = await list_tools_filtered(current_user=_gebruiker(KLANT_B))

    assert [(t.description, t.tenant_id) for t in van_b] == [("van B", KLANT_B)]


@pytest.mark.asyncio
async def test_klant_a_houdt_zijn_tool_id_als_klant_b_dezelfde_naam_registreert() -> None:
    await _registreer(KLANT_A, "van A")
    id_voor = (await list_tools_filtered(current_user=_gebruiker(KLANT_A)))[0].id

    await _registreer(KLANT_B, "van B")

    assert (await list_tools_filtered(current_user=_gebruiker(KLANT_A)))[0].id == id_voor


@pytest.mark.asyncio
async def test_klant_a_kan_zijn_eigen_tool_wel_opnieuw_registreren() -> None:
    await _registreer(KLANT_A, "eerste")
    await _registreer(KLANT_A, "tweede")

    van_a = await list_tools_filtered(current_user=_gebruiker(KLANT_A))

    assert [t.description for t in van_a] == ["tweede"]


@pytest.mark.asyncio
async def test_klant_b_kan_de_status_van_de_tool_van_klant_a_niet_ophalen() -> None:
    await _registreer(KLANT_A, "van A")

    with pytest.raises(HTTPException) as fout:
        await get_tool_status(tool_name=NAAM, current_user=_gebruiker(KLANT_B), _=1)

    assert fout.value.status_code == 404


@pytest.mark.asyncio
async def test_klant_a_kan_de_status_van_zijn_eigen_tool_ophalen() -> None:
    await _registreer(KLANT_A, "van A")

    status = await get_tool_status(tool_name=NAAM, current_user=_gebruiker(KLANT_A), _=1)

    assert status.tool_name == NAAM


@pytest.mark.asyncio
async def test_klant_b_kan_de_tool_van_klant_a_niet_uitzetten() -> None:
    await _registreer(KLANT_A, "van A")

    with pytest.raises(HTTPException):
        await disable_tool(tool_name=NAAM, current_user=_gebruiker(KLANT_B), _=1)

    assert available_tools[(KLANT_A, NAAM)]["available"] is True


@pytest.mark.asyncio
async def test_klant_b_kan_de_tool_van_klant_a_niet_aanzetten() -> None:
    await _registreer(KLANT_A, "van A")
    available_tools[(KLANT_A, NAAM)]["available"] = False

    with pytest.raises(HTTPException):
        await enable_tool(tool_name=NAAM, current_user=_gebruiker(KLANT_B), _=1)

    assert available_tools[(KLANT_A, NAAM)]["available"] is False


@pytest.mark.asyncio
async def test_klant_a_kan_zijn_eigen_tool_uitzetten() -> None:
    await _registreer(KLANT_A, "van A")

    await disable_tool(tool_name=NAAM, current_user=_gebruiker(KLANT_A), _=1)

    assert available_tools[(KLANT_A, NAAM)]["available"] is False


@pytest.mark.asyncio
async def test_de_volledige_lijst_toont_de_tool_van_een_andere_klant_niet() -> None:
    await _registreer(KLANT_A, "van A", naam="alleen_van_a")

    lijst = await list_tools_all(current_user=_gebruiker(KLANT_B), _=1)

    assert "alleen_van_a" not in [t.tool_name for t in lijst.tools]


@pytest.mark.asyncio
async def test_de_volledige_lijst_toont_de_meegeleverde_tools_nog_wel() -> None:
    lijst = await list_tools_all(current_user=_gebruiker(KLANT_B), _=1)

    assert "serena" in [t.tool_name for t in lijst.tools]


@pytest.mark.asyncio
async def test_een_klant_die_een_meegeleverde_naam_registreert_overschrijft_hem_niet() -> None:
    await _registreer(KLANT_A, "eigen versie", naam="serena")

    meegeleverd = available_tools[(None, "serena")]

    assert (meegeleverd["description"], meegeleverd.get("tenant_id")) == ("Serena Agent", None)


@pytest.mark.asyncio
async def test_klant_b_kan_de_tool_van_klant_a_niet_uitvoeren() -> None:
    await _registreer(KLANT_A, "van A")
    service = MagicMock()
    service.execute_tool = AsyncMock(return_value={"ok": True})

    with pytest.raises(HTTPException) as fout:
        await execute_tool(
            request=ToolExecutionRequest(tool_name=NAAM, payload={}),
            service=service,
            current_user=_gebruiker(KLANT_B),
            _=1,
        )

    assert (fout.value.status_code, service.execute_tool.await_count) == (400, 0)


@pytest.mark.asyncio
async def test_het_gebruik_van_een_meegeleverde_tool_door_klant_b_is_voor_klant_a_onzichtbaar() -> None:
    """Gate 2 (security-reviewer, 2026-10-27): `execute` verhoogde `execution_count` en `last_used` op het GEDEELDE
    meegeleverde object, dus klant A zag hoe vaak en wanneer klant B `serena` gebruikte."""
    service = MagicMock()
    service.execute_tool = AsyncMock(return_value={"ok": True})
    await execute_tool(
        request=ToolExecutionRequest(tool_name="serena", payload={}),
        service=service,
        current_user=_gebruiker(KLANT_B),
        _=1,
    )

    status_a = await get_tool_status(tool_name="serena", current_user=_gebruiker(KLANT_A), _=1)
    status_b = await get_tool_status(tool_name="serena", current_user=_gebruiker(KLANT_B), _=1)

    assert (status_a.execution_count, status_a.last_used, status_b.execution_count) == (0, None, 1)


@pytest.mark.asyncio
async def test_de_volledige_lijst_toont_het_gebruik_van_de_eigen_klant_en_niet_dat_van_anderen() -> None:
    service = MagicMock()
    service.execute_tool = AsyncMock(return_value={"ok": True})
    await execute_tool(
        request=ToolExecutionRequest(tool_name="serena", payload={}),
        service=service,
        current_user=_gebruiker(KLANT_B),
        _=1,
    )

    lijst_a = await list_tools_all(current_user=_gebruiker(KLANT_A), _=1)

    assert {t.tool_name: t.execution_count for t in lijst_a.tools}["serena"] == 0
