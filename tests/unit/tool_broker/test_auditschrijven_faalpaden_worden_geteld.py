"""Elk faalpad van het schrijven van een auditregel wordt geteld en lekt niet naar de aanroeper.

Gate 2 F7: `async with factory() as sessie` stond BUITEN `best_effort`. Een fout bij het openen
van de sessie, bij de commit/sluiting na de yield, of bij het terugzetten van de RLS-context
viel in de buitenste `except` die alleen waarschuwde: een stil verloren auditregel zonder
telling in `tool_audit_write_failures_total`. Hetzelfde voor het oude pad (`audit_repository`)
zonder bruikbare `tenant_id`: dat schreef zonder klantcontrole in plaats van te weigeren.

Beide routes: de achtergrondregel van een uitgevoerde tool en de synchrone regel van een
geweigerde poging. Wat er met de toolaanroep gebeurt, verandert niet (best effort).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.metrics import TOOL_AUDIT_WRITE_FAILURES
from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id
from src.core.tool_broker import service as service_module
from src.core.tool_broker.audit_repository import ToolAuditRepository
from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.local_registry import LocalToolRegistry
from src.core.tool_broker.service import ToolBrokerService


class OpenFout(Exception):
    """Het openen van de auditsessie mislukt (pool vol, database weg)."""


class SluitFout(Exception):
    """De commit of het sluiten van de auditsessie mislukt."""


class TerugzetFout(Exception):
    """Het terugzetten van de RLS-context mislukt."""


class _UnusedClient:
    async def call(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
        raise AssertionError(f"externe client onverwacht aangeroepen voor {tool_name}")


class _Repo:
    """Vervangt ToolAuditRepository: legt vast wat er geschreven wordt, geen database."""

    geschreven: list[int] = []

    def __init__(self, sessie: object, tenant_id: int) -> None:
        self.tenant_id = tenant_id

    async def log_execution(self, **kwargs: object) -> None:
        _Repo.geschreven.append(self.tenant_id)


@pytest.fixture(autouse=True)
def _schoon() -> Iterator[None]:
    set_tenant_id(None)
    _Repo.geschreven = []
    yield
    set_tenant_id(None)


def _teller(fout: str) -> float:
    return float(TOOL_AUDIT_WRITE_FAILURES.labels(error_type=fout)._value.get())


@asynccontextmanager
async def _gezonde_sessie() -> AsyncGenerator[AsyncMock, None]:
    yield AsyncMock()


@asynccontextmanager
async def _open_faalt() -> AsyncGenerator[AsyncMock, None]:
    raise OpenFout("pool vol")
    yield AsyncMock()  # pragma: no cover


@asynccontextmanager
async def _sluit_faalt() -> AsyncGenerator[AsyncMock, None]:
    yield AsyncMock()
    raise SluitFout("commit mislukt")


def _service(
    *,
    factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
    repo: object | None = None,
    toegestaan: bool = True,
) -> ToolBrokerService:
    permission_manager = AsyncMock()
    permission_manager.is_tool_allowed = lambda *_a, **_k: toegestaan
    return ToolBrokerService(
        serena_client=_UnusedClient(),
        seq_thinking_client=_UnusedClient(),
        local_registry=LocalToolRegistry(),
        event_publisher=AsyncMock(),
        enable_resilience=False,
        audit_session_factory=factory,
        audit_repository=cast(ToolAuditRepository | None, repo),
        db_session=AsyncMock() if repo is not None else None,
        permission_manager=permission_manager,
    )


async def _uitgevoerd(service: ToolBrokerService) -> None:
    """Route 1: de tool slaagt, de regel wordt op de achtergrond geschreven."""
    await service.execute_tool(
        "test__echo", {"message": "hallo"}, agent_id="agent-1", context={"tenant_id": 7}
    )
    await asyncio.sleep(0.1)


async def _geweigerd(service: ToolBrokerService) -> None:
    """Route 2: de poging wordt geweigerd, de regel wordt synchroon geschreven."""
    with pytest.raises(ToolExecutionException):
        await service.execute_tool(
            "test__echo", {"message": "hallo"}, agent_id="agent-1", context={"tenant_id": 7}
        )


def _route(naam: str) -> Callable[[ToolBrokerService], Awaitable[None]]:
    return _uitgevoerd if naam == "uitgevoerd" else _geweigerd


ROUTES = ["uitgevoerd", "geweigerd"]


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
class TestElkFaalpadWordtGeteld:
    async def test_een_fabriek_die_bij_het_openen_gooit_wordt_geteld(self, route: str) -> None:
        voor = _teller("OpenFout")
        service = _service(factory=_open_faalt, toegestaan=route == "uitgevoerd")

        with patch.object(service_module, "ToolAuditRepository", _Repo):
            await _route(route)(service)

        assert _teller("OpenFout") == voor + 1
        assert _Repo.geschreven == []

    async def test_een_fabriek_die_bij_het_verlaten_gooit_wordt_geteld(self, route: str) -> None:
        voor = _teller("SluitFout")
        service = _service(factory=_sluit_faalt, toegestaan=route == "uitgevoerd")

        with patch.object(service_module, "ToolAuditRepository", _Repo):
            await _route(route)(service)

        assert _teller("SluitFout") == voor + 1

    async def test_een_mislukt_terugzetten_van_de_context_wordt_geteld(self, route: str) -> None:
        voor = _teller("TerugzetFout")
        service = _service(factory=_gezonde_sessie, toegestaan=route == "uitgevoerd")
        aanroepen: list[object] = []

        def _set(waarde: object) -> None:
            aanroepen.append(waarde)
            if len(aanroepen) == 2:
                raise TerugzetFout("context")

        with (
            patch.object(service_module, "ToolAuditRepository", _Repo),
            patch("src.core.middleware.tenant_context.set_tenant_id", _set),
        ):
            await _route(route)(service)

        assert aanroepen == [7, None], "het terugzetten is niet geprobeerd"
        assert _teller("TerugzetFout") == voor + 1

    async def test_een_repository_zonder_tenant_id_schrijft_niet_en_wordt_geteld(
        self, route: str
    ) -> None:
        class _ZonderKlant:
            log_execution = AsyncMock()

        repo = _ZonderKlant()
        voor = _teller("RuntimeError")
        service = _service(repo=repo, toegestaan=route == "uitgevoerd")

        await _route(route)(service)

        repo.log_execution.assert_not_awaited()
        assert _teller("RuntimeError") == voor + 1

    async def test_een_repository_met_een_tenant_id_van_het_verkeerde_type_schrijft_niet(
        self, route: str
    ) -> None:
        repo = MagicMock()
        repo.tenant_id = "7"
        repo.log_execution = AsyncMock()
        voor = _teller("RuntimeError")
        service = _service(repo=repo, toegestaan=route == "uitgevoerd")

        await _route(route)(service)

        repo.log_execution.assert_not_awaited()
        assert _teller("RuntimeError") == voor + 1


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
class TestHetGezondePadBlijftOngemoeid:
    async def test_een_gezonde_fabriek_schrijft_voor_de_juiste_klant_zonder_telling(
        self, route: str
    ) -> None:
        voor = {n: _teller(n) for n in ("OpenFout", "SluitFout", "TerugzetFout", "RuntimeError")}
        service = _service(factory=_gezonde_sessie, toegestaan=route == "uitgevoerd")

        with patch.object(service_module, "ToolAuditRepository", _Repo):
            await _route(route)(service)

        assert _Repo.geschreven == [7]
        assert get_tenant_id() is None, "de context is niet teruggezet"
        assert {n: _teller(n) for n in voor} == voor

    async def test_een_repository_van_dezelfde_klant_schrijft_nog_steeds(self, route: str) -> None:
        repo = MagicMock()
        repo.tenant_id = 7
        repo.log_execution = AsyncMock()
        service = _service(repo=repo, toegestaan=route == "uitgevoerd")

        await _route(route)(service)

        repo.log_execution.assert_awaited_once()


class RedactieFout(Exception):
    """De redactie van een payload of resultaat mislukt (bijvoorbeeld: sleutel ontbreekt)."""


class DigestFout(Exception):
    """De digest van een waarde mislukt."""


def _gooit_vanaf_aanroep(
    echt: Callable[..., object], fout: type[Exception], vanaf: int
) -> Callable[..., object]:
    """Een vervanger die vanaf de `vanaf`-de aanroep gooit en daarvoor het echte werk doet.

    `safe_digest_result` wordt in het hoofdpad van `execute_tool` een keer aangeroepen (voor de
    event bus) voordat de auditregel hem aanroept; dat hoofdpad moet gewoon blijven werken. De
    plaats van de aanroep (in de `finally` of in de achtergrondtaak) staat hier bewust NIET vast:
    de test eist alleen dat een fout in de auditroute geteld wordt, waar die code ook staat.
    """
    aanroepen = 0

    def _vervanger(*args: object, **kwargs: object) -> object:
        nonlocal aanroepen
        aanroepen += 1
        if aanroepen >= vanaf:
            raise fout("stuk in de auditroute")
        return echt(*args, **kwargs)

    return _vervanger


#: (route, naam in service-module, foutklasse, vanaf welke aanroep gooit hij). Per route alleen wat die route in de
#: auditregel zelf aanroept: de uitgevoerde regel redigeert het resultaat en digest de fout, de
#: geweigerde regel redigeert de payload en digest de fout.
REDACTIE_EN_DIGEST = [
    ("uitgevoerd", "safe_digest_result", RedactieFout, 2),
    ("uitgevoerd", "safe_value_digest", DigestFout, 1),
    ("geweigerd", "redact_for_publication", RedactieFout, 1),
    ("geweigerd", "safe_value_digest", DigestFout, 1),
]


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(("route", "naam", "fout", "vanaf"), REDACTIE_EN_DIGEST)
class TestEenFoutInRedactieOfDigestWordtGeteld:
    """S1 (Gate 2): redactie en digest stonden binnen `best_effort` of in de `finally` zelf."""

    async def test_de_fout_wordt_geteld_en_de_toolactie_blijft_zoals_hij_was(
        self, route: str, naam: str, fout: type[Exception], vanaf: int
    ) -> None:
        voor = _teller(fout.__name__)
        service = _service(factory=_gezonde_sessie, toegestaan=route == "uitgevoerd")
        echt = getattr(service_module, naam)

        with (
            patch.object(service_module, "ToolAuditRepository", _Repo),
            patch.object(service_module, naam, _gooit_vanaf_aanroep(echt, fout, vanaf)),
        ):
            if route == "uitgevoerd":
                uitkomst = await service.execute_tool(
                    "test__echo",
                    {"message": "hallo"},
                    agent_id="agent-1",
                    context={"tenant_id": 7},
                )
                await asyncio.sleep(0.1)
                assert uitkomst is not None
            else:
                with pytest.raises(ToolExecutionException) as weigering:
                    await service.execute_tool(
                        "test__echo",
                        {"message": "hallo"},
                        agent_id="agent-1",
                        context={"tenant_id": 7},
                    )
                assert not isinstance(weigering.value.__cause__, fout)

        assert _teller(fout.__name__) == voor + 1
        assert _Repo.geschreven == [], "er is toch een regel geschreven met een stuk veld"


class _HangendeRepo(_Repo):
    """Een repository die nooit klaar komt: de achtergrondtaak is dan te annuleren."""

    bezig: asyncio.Event

    async def log_execution(self, **kwargs: object) -> None:
        _HangendeRepo.bezig.set()
        await asyncio.Event().wait()


@pytest.mark.unit
@pytest.mark.asyncio
class TestEenGeannuleerdeAuditregelWordtGeteld:
    """S5 (Gate 2): `except Exception` vangt `CancelledError` niet; de regel ging ongeteld verloren."""

    async def test_een_geannuleerde_taak_wordt_geteld_en_blijft_geannuleerd(
        self, audittaken_vooraf: None
    ) -> None:
        _HangendeRepo.bezig = asyncio.Event()
        voor = _teller("CancelledError")
        service = _service(factory=_gezonde_sessie)
        # Gate 2 F7: alleen naar de eigen taak kijken; `_AUDIT_TASKS` is gedeeld op moduleniveau.
        vooraf = set(service_module._AUDIT_TASKS)

        with patch.object(service_module, "ToolAuditRepository", _HangendeRepo):
            await service.execute_tool(
                "test__echo", {"message": "hallo"}, agent_id="agent-1", context={"tenant_id": 7}
            )
            await asyncio.wait_for(_HangendeRepo.bezig.wait(), timeout=5)
            taken = [t for t in set(service_module._AUDIT_TASKS) - vooraf if not t.done()]
            assert len(taken) == 1
            taken[0].cancel()
            with pytest.raises(asyncio.CancelledError):
                await taken[0]

        assert taken[0].cancelled(), "de annulering is ingeslikt in plaats van opnieuw opgegooid"
        assert _teller("CancelledError") == voor + 1
        assert get_tenant_id() is None, "de context is niet teruggezet na de annulering"


class _GeweigerdHangendeRepo(_HangendeRepo):
    """Hetzelfde, een eigen klasse zodat `bezig` niet gedeeld wordt met de test hierboven."""

    bezig: asyncio.Event


@pytest.mark.unit
@pytest.mark.asyncio
class TestEenGeannuleerdeWeigeringsregelWordtGeteld:
    """N5 (Gate 2 ronde 3): `_audit_blocked_attempt` telde een annulering niet (zie S5)."""

    async def test_een_geannuleerde_weigering_wordt_geteld_en_blijft_geannuleerd(self) -> None:
        _GeweigerdHangendeRepo.bezig = asyncio.Event()
        voor = _teller("CancelledError")
        service = _service(factory=_gezonde_sessie, toegestaan=False)

        class _Hangt(_Repo):
            async def log_execution(self, **kwargs: object) -> None:
                _GeweigerdHangendeRepo.bezig.set()
                await asyncio.Event().wait()

        with patch.object(service_module, "ToolAuditRepository", _Hangt):
            taak = asyncio.create_task(
                service.execute_tool(
                    "test__echo",
                    {"message": "hallo"},
                    agent_id="agent-1",
                    context={"tenant_id": 7},
                )
            )
            await asyncio.wait_for(_GeweigerdHangendeRepo.bezig.wait(), timeout=5)
            taak.cancel()
            with pytest.raises(asyncio.CancelledError):
                await taak

        assert taak.cancelled(), "de annulering is ingeslikt in plaats van opnieuw opgegooid"
        assert _teller("CancelledError") == voor + 1
        assert get_tenant_id() is None, "de context is niet teruggezet na de annulering"


class _VangRepo(_Repo):
    """Legt vast wat er als `tool_output` wordt geschreven."""

    uitvoer: list[object] = []

    async def log_execution(self, **kwargs: object) -> None:
        _VangRepo.uitvoer.append(kwargs.get("tool_output"))
        await super().log_execution(**kwargs)


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeDigestIsVanHetResultaatZoalsDeToolHetGaf:
    """N6 (Gate 2 ronde 3): de digest werd pas in de achtergrondtaak berekend."""

    async def test_een_mutatie_na_de_aanroep_komt_niet_in_het_logboek(self) -> None:
        _VangRepo.uitvoer = []
        service = _service(factory=_gezonde_sessie)

        with patch.object(service_module, "ToolAuditRepository", _VangRepo):
            uitkomst = await service.execute_tool(
                "test__echo", {"message": "hallo"}, agent_id="agent-1", context={"tenant_id": 7}
            )
            assert isinstance(uitkomst, dict)
            origineel = service_module.safe_digest_result(dict(uitkomst), tenant_id=7)
            # De aanroeper muteert het resultaat direct na de aanroep, voor de achtergrondtaak.
            uitkomst["message"] = "GEMUTEERD DOOR DE AANROEPER"
            uitkomst["extra"] = "erbij"
            await asyncio.sleep(0.1)

        assert _VangRepo.uitvoer == [origineel], "de digest hoort bij het origineel"
        gemuteerd = service_module.safe_digest_result(dict(uitkomst), tenant_id=7)
        assert origineel != gemuteerd, "de test bewijst niets: de mutatie verandert de digest niet"

    async def test_een_digestfout_wordt_geteld_en_lekt_niet_naar_de_aanroeper(self) -> None:
        _VangRepo.uitvoer = []
        voor = _teller("DigestFout")
        service = _service(factory=_gezonde_sessie)
        echt = service_module.safe_value_digest

        with (
            patch.object(service_module, "ToolAuditRepository", _VangRepo),
            patch.object(
                service_module, "safe_value_digest", _gooit_vanaf_aanroep(echt, DigestFout, 1)
            ),
        ):
            uitkomst = await service.execute_tool(
                "test__echo", {"message": "hallo"}, agent_id="agent-1", context={"tenant_id": 7}
            )
            await asyncio.sleep(0.1)

        assert uitkomst is not None
        assert _teller("DigestFout") == voor + 1
        assert _VangRepo.uitvoer == [], "er is toch een regel geschreven zonder digest"
