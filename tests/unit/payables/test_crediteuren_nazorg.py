"""Crediteuren nazorg (brief 2026-10-27-sprint-dag-crediteuren-nazorg): het deel zonder database.

Punt 1: een mislukte uitvoering na goedkeuren krijgt een VASTE Nederlandse zin (een code uit de tool, een zin uit een tabel), nooit de
ruwe tekst van de tool. Punt 3: een ticket voorbij zijn termijn telt als verlopen op het moment van LEZEN, ook als de uurlijkse job
niet draait. De tests met een echte database staan in `tests/integration/test_crediteuren_nazorg.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.api.v1.tool_broker.hitl_router import _voer_goedgekeurde_actie_uit
from src.core.tool_broker.hitl_store import _ticket_to_dict
from src.core.tool_broker.uitvoerredenen import UITVOERREDENEN, zin_voor


class TestDeVasteZinnen:
    def test_every_code_has_a_dutch_sentence_without_placeholders(self) -> None:
        for code, zin in UITVOERREDENEN.items():
            assert zin.endswith("."), code
            assert "{" not in zin and "}" not in zin, code
            assert zin.isascii(), code

    def test_a_changed_iban_is_explained_and_the_next_step_is_named(self) -> None:
        zin = zin_voor("iban_gewijzigd")

        assert zin is not None
        assert "rekeningnummer" in zin and "opnieuw worden voorgelegd" in zin

    def test_an_iban_clash_has_its_own_sentence(self) -> None:
        zin = zin_voor("iban_al_in_gebruik")

        assert zin is not None and "IBAN" in zin and "andere leverancier" in zin

    def test_an_unknown_code_gives_no_sentence(self) -> None:
        assert zin_voor("iets_dat_niet_bestaat") is None

    def test_none_gives_no_sentence(self) -> None:
        assert zin_voor(None) is None


class _Broker:
    def __init__(self, resultaat: object) -> None:
        self._resultaat = resultaat

    async def execute_tool(self, **_: Any) -> object:
        return self._resultaat


async def _voer_uit(resultaat: object) -> tuple[bool, str | None]:
    return await _voer_goedgekeurde_actie_uit(
        _Broker(resultaat),
        ticket_ref="hitl_x",
        tool_name="propose_payment_run",
        parameters={},
        tenant_id=1,
        aangevraagd_door=1,
    )


@pytest.mark.asyncio
class TestDeUitvoerCodeGaatMee:
    async def test_a_known_reason_code_travels_with_the_failure_kind(self) -> None:
        uitkomst = await _voer_uit(
            {"success": False, "error": "ruwe tekst", "reden_code": "iban_gewijzigd"}
        )

        assert uitkomst == (False, "tool_failure:iban_gewijzigd")

    async def test_an_unknown_reason_code_is_dropped(self) -> None:
        uitkomst = await _voer_uit(
            {"success": False, "error": "ruwe tekst", "reden_code": "<script>"}
        )

        assert uitkomst == (False, "tool_failure")

    async def test_a_failure_without_a_code_stays_a_plain_tool_failure(self) -> None:
        assert await _voer_uit({"success": False, "error": "ruwe tekst"}) == (False, "tool_failure")

    async def test_a_success_has_no_failure_kind(self) -> None:
        assert await _voer_uit({"success": True}) == (True, None)


def _ticket(status: str, verloopt_over: timedelta) -> SimpleNamespace:
    nu = datetime.now(timezone.utc)
    return SimpleNamespace(
        ticket_ref="hitl_1",
        tenant_id=1,
        status=status,
        tool_name="propose_payment_run",
        created_at=nu - timedelta(hours=5),
        risk_level="HIGH",
        payload={"_requested_by": "1"},
        resolved_by=None,
        resolved_at=None,
        resolution_note=None,
        expires_at=nu + verloopt_over,
    )


class TestVerlopenTeltBijHetLezen:
    def test_a_pending_ticket_past_its_term_is_shown_as_expired_without_the_job(self) -> None:
        uit = _ticket_to_dict(_ticket("pending", timedelta(hours=-1)), None)

        assert uit["status"] == "expired"

    def test_a_pending_ticket_within_its_term_stays_pending(self) -> None:
        assert _ticket_to_dict(_ticket("pending", timedelta(hours=1)), None)["status"] == "pending"

    def test_an_approved_ticket_past_its_term_stays_approved(self) -> None:
        uit = _ticket_to_dict(_ticket("approved", timedelta(hours=-1)), None)

        assert uit["status"] == "approved"
