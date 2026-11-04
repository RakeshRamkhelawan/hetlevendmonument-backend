"""Vier bewezen lekken in de payload-pseudonimisering (BE-AGT-045 ronde 2, ADR-036 OP-27).

Deze tests horen ROOD te zijn op commit `72cec596` en groen na de fix. Ze zijn opzettelijk op
GEDRAGSNIVEAU geschreven -- via `ToolBrokerService.execute_tool` en de gepubliceerde event-data,
niet via `redact_for_publication` rechtstreeks. Reden: de fix wijzigt de signatuur van die
functie, en een test die de oude signatuur aanroept zou daarna een `TypeError` geven in plaats
van de eigenschap te toetsen. Op gedragsniveau blijft dezelfde testtekst geldig voor EN na.

De vier lekken (alle drie de eerste zijn door de Gate 2-reviewers aangetoond door code te
draaien, niet door te lezen):

1. **Scope gedeeld tussen tenants.** Zonder `context` viel de scope terug op
   `payload["tenant_id"]`, en zonder die sleutel op de constante `"unscoped"`. Twee aanroepers
   geven geen context (`tool_broker/router.py`, `knowledge/sops/sop_executor.py`), dus daar
   deelden ALLE tenants een scope en was de tenant-scheiding een claim zonder dekking.
2. **De payload koos zijn eigen scope.** De payload is de `json.loads` van een
   `TOOL_CALL`-directive en dus modeloutput. Zolang de scope daaruit kwam, kon het model zijn
   eigen scope kiezen -- exact de fout die een dag eerder in `hr_registry.py` was gesloten.
3. **Naamgedreven allowlist.** `ALWAYS_PUBLISHABLE` bevatte acht namen; de broker zet er in dit
   pad twee. De overige zes waren gewoon namen die het model zelf mocht kiezen, en
   `_requested_by` is elders letterlijk `current_user.email`.
4. **Idempotentie zonder vormcheck.** `_is_already_pseudonymised` controleerde of een dict
   precies de sleutel `hmac` had, zonder naar de waarde te kijken. `{"hmac": "<e-mailadres>"}`
   passeerde daardoor verbatim naar alle drie de bewarende sinks.

Assertie ALTIJD op `event.data["payload"]` en nooit op de hele event: `test__echo` echoot de
payload in zijn `result`, en dat resultaat is OP-29 (nog niet gefilterd). Een assertie op de
hele event zou dus om de verkeerde reden falen.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.middleware.tenant_context import set_tenant_id
from src.core.tool_broker.local_registry import LocalToolRegistry
from src.core.tool_broker.service import ToolBrokerService

PERSONAL_VALUE = "jan.jansen@acme.nl"


class _UnusedClient:
    """Stub voor de externe clients: dit pad raakt alleen lokale tools."""

    async def call(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
        raise AssertionError(f"externe client onverwacht aangeroepen voor {tool_name}")


@pytest.fixture(autouse=True)
def _allow_all_tools() -> Iterator[None]:
    """De permissielaag is elders getoetst; hier gaat het om de payload-behandeling."""
    with patch(
        "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
        return_value=True,
    ):
        yield


@pytest.fixture(autouse=True)
def _clean_tenant_context() -> Iterator[None]:
    """De tenant-ContextVar opruimen voor EN na.

    Zonder dit lekt een gezette tenant naar elke latere test in dezelfde xdist-worker -- het
    patroon dat OP-20 blootlegde.
    """
    set_tenant_id(None)
    yield
    set_tenant_id(None)


async def _published_payload(
    payload: dict[str, Any],
    context: dict[str, object] | None = None,
) -> dict[str, Any]:
    """De payload zoals hij op de event bus belandt."""
    publisher = AsyncMock()
    service = ToolBrokerService(
        serena_client=_UnusedClient(),
        seq_thinking_client=_UnusedClient(),
        local_registry=LocalToolRegistry(),
        event_publisher=publisher,
        enable_resilience=False,
    )

    await service.execute_tool("test__echo", payload, agent_id="agent-1", context=context)
    await asyncio.sleep(0)

    event = publisher.publish.await_args.args[0]
    return dict(event.data["payload"])


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheScopeIsNeverShared:
    async def test_two_tenants_without_a_call_context_do_not_share_one_scope(self) -> None:
        """Dezelfde persoon in twee tenants mag nooit dezelfde digest krijgen.

        Twee aanroepers van `execute_tool` geven geen `context` mee. Zolang de scope uit de
        payload kwam, vielen die allebei terug op de constante `"unscoped"`; dezelfde waarde gaf
        dan in elke tenant dezelfde digest en kon dus over de tenantgrens gecorreleerd worden.
        De tenant hoort uit de ADR-003 ContextVar te komen als de aanroeper geen context
        meegeeft.
        """
        set_tenant_id(1)
        first = await _published_payload({"message": PERSONAL_VALUE})

        set_tenant_id(2)
        second = await _published_payload({"message": PERSONAL_VALUE})

        # Op de WAARDEN en niet op een sleutelnaam: sinds ronde 4 is ook de sleutelnaam een
        # pseudonym als hij niet bij het vocabulaire van de tool hoort, en `test__echo` echoot de
        # hele payload zonder een benoemde sleutel te lezen -- zijn vocabulaire is dus leeg.
        assert list(first.values()) != list(second.values()), (
            "Dezelfde waarde geeft in tenant 1 en tenant 2 dezelfde digest. Iemand met "
            "leesrechten op twee tenants kan personen dus over die grens correleren -- in "
            "strijd met de isolatie die ADR-003/004/005 afdwingen."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheModelCannotChooseItsOwnScope:
    async def test_a_payload_tenant_id_does_not_change_the_scope(self) -> None:
        """De scope komt uit de executiecontext, niet uit de modeloutput.

        Kon het model de scope kiezen, dan kon het zijn digests in de scope van een andere
        tenant laten vallen (en daarmee correleerbaar maken met die tenant) of ze per aanroep
        onvergelijkbaar maken. Dit is dezelfde fout die in `hr_registry.py` bij BE-AGT-044
        HIGH-4 is gesloten.
        """
        set_tenant_id(1)

        # Dezelfde VORM in beide aanroepen, alleen een andere payload-tenant. Als die de scope
        # had bepaald, zou geen enkel (sleutel, waarde)-paar overeenkomen; nu moet het paar van
        # `message` in beide gelijk zijn. Op paren en niet op een sleutelnaam, want sinds ronde 4
        # is ook de sleutelnaam een pseudonym.
        spoofed = await _published_payload({"tenant_id": 9, "message": PERSONAL_VALUE})
        honest = await _published_payload({"tenant_id": 1, "message": PERSONAL_VALUE})

        # Geen `set()`: de waarden zijn dicts en dus niet hashbaar. `in` op `.items()` werkt
        # wel, dat vergelijkt op gelijkheid.
        shared = [pair for pair in spoofed.items() if pair in honest.items()]

        assert shared, (
            "Geen enkel sleutel/waarde-paar komt overeen, dus een `tenant_id` in de payload "
            "verandert de digest. De payload is modeloutput, dus het model kiest daarmee zijn "
            "eigen pseudonimiseringsscope."
        )

    async def test_a_payload_tenant_id_is_not_published_as_broker_context(self) -> None:
        """Een tenant die het model zelf schreef mag niet als contextveld doorgaan.

        `tenant_id` stond op de altijd-leesbaar-lijst met als reden "de broker zet dit uit de
        executiecontext". Dat geldt alleen als er een context IS: `service.py` injecteert de
        sleutel uitsluitend dan. Zonder context bleef staan wat het model had geschreven, met
        de leesbaarheid van een contextveld.
        """
        set_tenant_id(1)

        published = await _published_payload({"tenant_id": 9, "message": PERSONAL_VALUE})

        assert "tenant_id" not in published
        assert 9 not in published.values(), (
            "De door het model geschreven `tenant_id` staat leesbaar in het log alsof de broker "
            "hem uit de context had gezet."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheAllowlistIsWiringDrivenNotNameDriven:
    @pytest.mark.parametrize(
        "key",
        ["_requested_by", "_reason", "_task_id", "_agent_id", "_requested_at"],
    )
    async def test_a_context_looking_key_from_the_model_is_still_pseudonymised(
        self, key: str
    ) -> None:
        """Vijf van de acht namen op de altijd-leesbaar-lijst zet de broker nooit.

        Wat leesbaar mag blijven hoort te volgen uit de WIRING (welke sleutels heeft de broker
        zelf uit de context geinjecteerd) en niet uit een NAAM die het model ook zelf kan
        kiezen. `_requested_by` is elders letterlijk `current_user.email`, dus deze lijst had
        een e-mailveld altijd-leesbaar verklaard binnen een PII-filter.
        """
        set_tenant_id(1)

        published = await _published_payload({key: PERSONAL_VALUE})

        assert PERSONAL_VALUE not in str(published), (
            f"`{key}` staat leesbaar in het log omdat de NAAM op de allowlist staat, terwijl de "
            "broker die sleutel in dit pad nooit zet. Het model kan de naam dus zelf kiezen."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestAModelWrittenDigestShapeIsNotTrusted:
    async def test_a_payload_that_mimics_a_digest_is_still_pseudonymised(self) -> None:
        """De idempotentiecheck was een vormcheck zonder vorm.

        `_is_already_pseudonymised` keek of een dict precies de sleutel `hmac` had en niet naar
        de waarde. Een model dat zijn argument zo inpakt schreef daarmee leesbare tekst naar de
        event bus, de leeropslag en de onuitwisbare auditketen.
        """
        set_tenant_id(1)

        published = await _published_payload({"message": {"hmac": PERSONAL_VALUE}})

        assert PERSONAL_VALUE not in str(published), (
            "Een payload in de vorm {'hmac': <waarde>} passeert verbatim. De check controleert "
            "de sleutelnaam maar niet of de waarde een digest IS."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestAnUnknownTenantFailsClosed:
    async def test_execution_without_any_resolvable_tenant_is_refused(self) -> None:
        """Geen tenant, geen uitvoering.

        Een terugval op een gedeelde constante is precies het lek uit
        `test_two_tenants_without_a_call_context_do_not_share_one_scope`, en een terugval op een
        per-proces willekeurige scope zou stil de koppelbaarheid slopen waarop het
        art.-12(2)-argument rust -- exact de reden waarom de SLEUTEL buiten development ook
        hard faalt. Dus hard falen, luid en vindbaar.
        """
        from src.core.tool_broker.exceptions import ToolExecutionException

        with pytest.raises(ToolExecutionException, match="tenant"):
            await _published_payload({"message": PERSONAL_VALUE})


@pytest.mark.unit
@pytest.mark.asyncio
class TestAMissingKeyAbortsTheExecution:
    async def test_no_pseudonymisation_key_means_no_execution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Zonder sleutel gaat de tool niet af, en gaat er niets onbeschermd naar een sink.

        `service.py` bepaalt de te publiceren payload BINNEN de `try`, juist zodat een
        ontbrekende sleutel als tool-fout wordt geclassificeerd, gepubliceerd en geaudit in
        plaats van als rauwe `RuntimeError` langs beide except-takken te glippen. Die wiring had
        geen eigen test; dit is hem.
        """
        from src.core.tool_broker import redaction
        from src.core.tool_broker.exceptions import ToolExecutionException

        monkeypatch.setattr(redaction, "_configured_key", lambda: None)
        monkeypatch.setattr(redaction, "_allows_ephemeral_key", lambda: False)
        redaction.reset_key_cache()
        set_tenant_id(1)

        publisher = AsyncMock()
        service = ToolBrokerService(
            serena_client=_UnusedClient(),
            seq_thinking_client=_UnusedClient(),
            local_registry=LocalToolRegistry(),
            event_publisher=publisher,
            enable_resilience=False,
        )

        with pytest.raises(ToolExecutionException):
            await service.execute_tool(
                "test__echo", {"message": PERSONAL_VALUE}, agent_id="agent-1"
            )
        await asyncio.sleep(0)

        published = str(publisher.publish.await_args.args[0].data["payload"])
        assert PERSONAL_VALUE not in published, (
            "Zonder sleutel is de payload alsnog onbeschermd gepubliceerd. Dan is de "
            "fail-closed een formaliteit: de uitvoering stopt wel, maar het lek gebeurt."
        )
