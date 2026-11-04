"""De controle van de noodstop weigert bij alles wat niet "zeker niet stil" is (ADR-036 OP-03).

`eis_klant_actief` is de ene functie die elke deur aanroept. Dit bestand meet hem op de GRENS: de
lezer van de stand (de database) is vervangen door een dubbel, al het andere draait echt. Elke test
dekt een weigerroute; samen zijn dat alle manieren waarop een deur NIET open mag gaan.

Wat dit NIET meet: de echte database (zie `tests/integration/test_noodstop_per_klant.py`).
"""

from __future__ import annotations

import asyncio

import pytest

from src.core.noodstop import guard
from src.core.noodstop.guard import (
    MELDING_ONBEKEND,
    MELDING_STIL,
    KlantStilgezet,
    eis_klant_actief,
    klant_staat_stil,
)

pytestmark = [pytest.mark.unit, pytest.mark.noodstop_echt]


def _lezer(stil: set[int]):
    async def _lees(tenant_id: int) -> bool:
        return tenant_id in stil

    return _lees


@pytest.mark.asyncio
class TestEenStilgezetteKlant:
    async def test_wordt_geweigerd_met_de_nederlandse_melding(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(guard, "_lees_stand", _lezer({1}))

        with pytest.raises(KlantStilgezet) as fout:
            await eis_klant_actief(1)

        assert fout.value.bericht == MELDING_STIL

    async def test_is_een_besluit_en_geen_storing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guard, "_lees_stand", _lezer({1}))

        with pytest.raises(KlantStilgezet) as fout:
            await eis_klant_actief(1)

        assert fout.value.onbekend is False

    async def test_een_andere_klant_wordt_toegelaten(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guard, "_lees_stand", _lezer({1}))

        assert await eis_klant_actief(2) is None

    async def test_een_klant_als_tekst_met_cijfers_wordt_als_getal_gelezen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gezien: list[int] = []

        async def _lees(tenant_id: int) -> bool:
            gezien.append(tenant_id)
            return False

        monkeypatch.setattr(guard, "_lees_stand", _lees)

        await eis_klant_actief(" 7 ")

        assert gezien == [7]


@pytest.mark.asyncio
class TestFailClosed:
    async def test_een_lezer_die_faalt_weigert(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _kapot(tenant_id: int) -> bool:
            raise ConnectionError("database weg")

        monkeypatch.setattr(guard, "_lees_stand", _kapot)

        with pytest.raises(KlantStilgezet):
            await eis_klant_actief(1)

    async def test_een_lezer_die_faalt_meldt_dat_de_stand_onbekend_is(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _kapot(tenant_id: int) -> bool:
            raise ConnectionError("database weg")

        monkeypatch.setattr(guard, "_lees_stand", _kapot)

        with pytest.raises(KlantStilgezet) as fout:
            await eis_klant_actief(1)

        assert (fout.value.onbekend, fout.value.bericht) == (True, MELDING_ONBEKEND)

    @pytest.mark.parametrize("antwoord", [None, 0, 1, "", "nee", "False", [], object()])
    async def test_alleen_een_expliciet_false_laat_door(
        self, monkeypatch: pytest.MonkeyPatch, antwoord: object
    ) -> None:
        async def _lees(tenant_id: int) -> object:
            return antwoord

        monkeypatch.setattr(guard, "_lees_stand", _lees)

        with pytest.raises(KlantStilgezet):
            await eis_klant_actief(1)

    @pytest.mark.parametrize("klant", [None, "", "abc", "1.5", "-3", 0, -3, True, 1.5, [1], {}])
    async def test_een_onbekende_of_ongeldige_klant_weigert_zonder_de_lezer_te_vragen(
        self, monkeypatch: pytest.MonkeyPatch, klant: object
    ) -> None:
        async def _lees(tenant_id: int) -> bool:
            raise AssertionError("de lezer mag niet worden gevraagd voor een ongeldige klant")

        monkeypatch.setattr(guard, "_lees_stand", _lees)

        with pytest.raises(KlantStilgezet):
            await eis_klant_actief(klant)

    async def test_een_geannuleerde_taak_wordt_niet_ingeslikt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _geannuleerd(tenant_id: int) -> bool:
            raise asyncio.CancelledError()

        monkeypatch.setattr(guard, "_lees_stand", _geannuleerd)

        with pytest.raises(asyncio.CancelledError):
            await eis_klant_actief(1)


@pytest.mark.asyncio
class TestKlantStaatStil:
    async def test_is_waar_voor_een_stilgezette_klant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(guard, "_lees_stand", _lezer({1}))

        assert await klant_staat_stil(1) is True

    async def test_is_onwaar_voor_een_actieve_klant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guard, "_lees_stand", _lezer({1}))

        assert await klant_staat_stil(2) is False

    async def test_is_waar_als_de_stand_niet_te_lezen_is(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _kapot(tenant_id: int) -> bool:
            raise ConnectionError("database weg")

        monkeypatch.setattr(guard, "_lees_stand", _kapot)

        assert await klant_staat_stil(1) is True


class TestDeStandaardlezer:
    def test_is_de_database_en_geen_overgebleven_dubbel(self) -> None:
        """Een `noodstop_echt`-test krijgt de echte lezer; een achtergebleven stub zou alles verbergen."""
        assert guard._lees_stand is guard._lees_uit_database
