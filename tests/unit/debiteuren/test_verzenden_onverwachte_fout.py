"""Een onverwachte fout bij een bericht stopt de verzendrun niet -- Keten B dag 3 (dag-2-bevinding).

Dag-2-bevinding (`debiteuren_tasks.py`): "een andere uitzondering dan `SQLAlchemyError` breekt de
hele run af; de rij blijft `klaar` vooraan staan. Per bericht afvangen." En: "de tak
`FOUTREDEN_ONVERWACHT` is ongetest en met de echte service onbereikbaar".

**Hoe de fout erin komt.** Met de echte `SMTPEmailService` komt een onverwachte uitzondering niet
voort uit `aiosmtplib` (de dubbel werpt alleen `SMTPConnectError`). Daarom is hier, op de
systeemgrens, de mailservice zelf vervangen door een stub die voor een bepaalde ontvanger een
uitzondering werpt: `get_email_service` in de module van de actor. Dat is de enige koppeling met
de bouwer-keuze; staat die naam er niet meer, dan faalt de test luid (`raising=True`).

**Gekozen regel (documenteer in de code):** een onverwachte uitzondering telt als een mislukte
poging: het bericht wordt `mislukt` met `pogingen` +1 en een vaste, geheimvrije `foutreden`. Een
bericht dat na zo'n fout gewoon `klaar` bleef zou elke minuut opnieuw proberen zonder dat
`pogingen` de grens van 3 bewaakt.

Techniek: EP (klasse "verwachte" fout versus "onverwachte" fout), twee representanten
(`RuntimeError` zit in de huidige afhandeling, `KeyError` niet).

**Wat de opstelling uitzet, nagelopen.** Autouse in `tests/conftest.py` (TESTING=1, tenantfilter,
event loop, seed-snapshot): geen daarvan raakt mail of de actor. De stub staat alleen in deze
module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.models.outgoing_message_models import OutgoingMessage
from src.core.models.rbac_models import Tenant
from src.core.services.email import EmailMessage

SLECHT = "slecht@klant.example"
GOED = "goed@klant.example"
GEHEIM = "geheim-sleutel-Qw93"


class _Dienst:
    """Mailservice-stub: werpt `fout` voor SLECHT, anders `True`."""

    def __init__(self, fout: Exception) -> None:
        self.fout = fout
        self.verstuurd: list[str] = []

    async def send(self, bericht: EmailMessage) -> bool:
        if bericht.to == SLECHT:
            raise self.fout
        self.verstuurd.append(bericht.to)
        return True


def _fabriek(sessie: AsyncSession) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    @asynccontextmanager
    async def _sessie() -> AsyncIterator[AsyncSession]:
        yield sessie

    return _sessie


async def _bericht(sessie: AsyncSession, ontvanger: str) -> int:
    rij = OutgoingMessage(
        tenant_id=1,
        channel="email",
        kind="herinnering",
        recipient=ontvanger,
        subject="Herinnering",
        body="Tekst",
        status="klaar",
    )
    sessie.add(rij)
    await sessie.commit()
    return rij.id


async def _lees(sessie: AsyncSession, bericht_id: int) -> SimpleNamespace:
    sessie.expire_all()
    rij = await sessie.get(OutgoingMessage, bericht_id)
    assert rij is not None
    return SimpleNamespace(status=rij.status, pogingen=rij.pogingen, foutreden=rij.foutreden)


@pytest_asyncio.fixture
async def tenant(db_session: AsyncSession) -> None:
    db_session.add(Tenant(id=1, name="T1", slug="deb-onverwacht"))
    await db_session.commit()


def _installeer(monkeypatch: pytest.MonkeyPatch, fout: Exception) -> _Dienst:
    dienst = _Dienst(fout)
    monkeypatch.setattr(
        "src.core.tasks.debiteuren_tasks.get_email_service", lambda: dienst, raising=True
    )
    return dienst


FOUTEN = [RuntimeError(GEHEIM), KeyError(GEHEIM)]
FOUT_IDS = ["RuntimeError_verwacht", "KeyError_onverwacht"]


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("fout", FOUTEN, ids=FOUT_IDS)
class TestOnverwachteFoutBijEenBericht:
    async def test_het_volgende_bericht_wordt_nog_verstuurd(
        self,
        db_session: AsyncSession,
        tenant: None,
        monkeypatch: pytest.MonkeyPatch,
        fout: Exception,
    ) -> None:
        from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten_async

        dienst = _installeer(monkeypatch, fout)
        await _bericht(db_session, SLECHT)
        goed = await _bericht(db_session, GOED)

        await verstuur_klare_berichten_async(sessie_fabriek=_fabriek(db_session))

        assert ((await _lees(db_session, goed)).status, dienst.verstuurd) == ("verzonden", [GOED])

    async def test_het_foute_bericht_telt_als_een_mislukte_poging(
        self,
        db_session: AsyncSession,
        tenant: None,
        monkeypatch: pytest.MonkeyPatch,
        fout: Exception,
    ) -> None:
        from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten_async

        _installeer(monkeypatch, fout)
        slecht = await _bericht(db_session, SLECHT)
        await _bericht(db_session, GOED)

        await verstuur_klare_berichten_async(sessie_fabriek=_fabriek(db_session))

        rij = await _lees(db_session, slecht)
        assert (rij.status, rij.pogingen) == ("mislukt", 1)

    async def test_de_foutreden_is_gevuld_en_zonder_de_tekst_van_de_fout(
        self,
        db_session: AsyncSession,
        tenant: None,
        monkeypatch: pytest.MonkeyPatch,
        fout: Exception,
    ) -> None:
        from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten_async

        _installeer(monkeypatch, fout)
        slecht = await _bericht(db_session, SLECHT)

        await verstuur_klare_berichten_async(sessie_fabriek=_fabriek(db_session))

        reden = (await _lees(db_session, slecht)).foutreden or ""
        assert reden.strip() != "" and GEHEIM not in reden

    async def test_na_drie_runs_is_er_geen_vierde_poging(
        self,
        db_session: AsyncSession,
        tenant: None,
        monkeypatch: pytest.MonkeyPatch,
        fout: Exception,
    ) -> None:
        """Het foute bericht blijft niet eindeloos vooraan staan: `pogingen` bewaakt de grens."""
        from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten_async

        _installeer(monkeypatch, fout)
        slecht = await _bericht(db_session, SLECHT)

        for _ in range(5):
            await verstuur_klare_berichten_async(sessie_fabriek=_fabriek(db_session))

        assert (await _lees(db_session, slecht)).pogingen == 3
