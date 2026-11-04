"""De brief gaat echt -- Keten B dag 2: de actor `verstuur_klare_berichten` (outbox-patroon).

Wat hier gemeten wordt, per vraag (techniek tussen haakjes):

1. Een rij `klaar` wordt `verzonden`, met `verzonden_op`, en de SMTP-kant ontving PRECIES die
   brief (EP: een klasse "klaar"; beslis-tabel status x pogingen hieronder).
2. Een SMTP-fout geeft `mislukt` + `foutreden` (zonder geheimen) + `pogingen` +1; na 3 pogingen
   geen nieuwe poging (BVA: pogingen 2 -> nog een poging, 3 -> geen).
3. Een tweede run verstuurt hetzelfde bericht niet nog eens (sequentieel hier; gelijktijdig in
   `tests/integration/test_debiteuren_verzenden_gelijktijdig.py`, want rijsloten bestaan alleen op
   PostgreSQL).
4. Tenantisolatie: beide tenants worden verwerkt, elke rij met de eigen tenantcontext, en een
   fout bij de een raakt de rij van de ander niet.
5. Logboek: verzonden en mislukt geven elk een auditregel in de EIGEN tenant.

**Systeemgrens.** Alleen `aiosmtplib.send` is vervangen (`_smtp_dubbel.py`). `SMTPEmailService`,
`get_email_service()`, de actor en de databasesessie (echte SQLite-sessie met `create_all`) lopen
echt. De tests kiezen de mailservice dus NIET: de actor haalt hem zelf op, en `SMTP_HOST`
bepaalt dat het SMTP wordt.

**Het contract met de bouwer** (nog niet bestaand, dus de tests zijn rood):
`src/core/tasks/debiteuren_tasks.py` met
- `async def verstuur_klare_berichten_async(sessie_fabriek=None) -> ...`: de kern. `sessie_fabriek`
  is een aanroepbaar object dat een async contextmanager met een `AsyncSession` geeft (standaard
  `get_db_session`). Dit is de seam: zonder hem is de actor niet buiten de worker te meten.
- `verstuur_klare_berichten`: de Dramatiq-actor (`actor_name="verstuur_klare_berichten"`) die de
  kern draait.
- `MAX_POGINGEN = 3`.

**Wat de opstelling uitzet, nagelopen.** Autouse in `tests/conftest.py`: `enforce_testing_env`
(TESTING=1), `_reset_global_state` (tenantfilter bewaren/herstellen), `ensure_main_thread_event_loop`,
`_seed_module_snapshot`. Geen daarvan raakt mail, de auditdienst, de tenantcontext of het
bericht. Geen conftest in `tests/unit/debiteuren/`. Er is niets op de auditdienst gepatcht: de
auditregels worden teruggelezen uit `audit_logs`.

**Wat dit NIET meet.** (1) De hash-keten van het logboek (advisory lock bestaat alleen op
PostgreSQL; zie `test_logboek_bij_wijzigen.py`). (2) Dat een mislukte AUDITschrijving de
verzending niet blokkeert (`best_effort`): dat vraagt een patch op de auditdienst, en de naam
van de aanroep is een keuze van de bouwer. (3) Echte Mailpit-aflevering: dat is taak van de
acceptant. (4) De RLS-policy op de nieuwe kolommen (PostgreSQL).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.models.outgoing_message_models import OutgoingMessage
from src.core.models.rbac_models import Tenant
from tests.unit.debiteuren._smtp_dubbel import SmtpDubbel, installeer_smtp_dubbel, zet_testmailbox

WACHTWOORD = "geheim-ww-Zx81"
DEBITEUR_1 = "administratie@dekorst.example"
DEBITEUR_2 = "boekhouding@anderbedrijf.example"
ONDERWERP = "Betalingsherinnering factuur F-2026-001"
TEKST = "Geachte heer, mevrouw,\n\nWij hebben nog geen betaling ontvangen voor factuur F-2026-001."


def _fabriek(sessie: AsyncSession) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    @asynccontextmanager
    async def _sessie() -> AsyncIterator[AsyncSession]:
        yield sessie

    return _sessie


async def _draai(sessie: AsyncSession) -> None:
    """Een run van de kern van de actor, op de testsessie."""
    from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten_async

    await verstuur_klare_berichten_async(sessie_fabriek=_fabriek(sessie))


async def _zet_bericht(
    sessie: AsyncSession,
    tenant_id: int,
    ontvanger: str = DEBITEUR_1,
    *,
    status: str = "klaar",
    pogingen: int = 0,
    onderwerp: str = ONDERWERP,
    tekst: str = TEKST,
) -> int:
    rij = OutgoingMessage(
        tenant_id=tenant_id,
        channel="email",
        kind="herinnering",
        recipient=ontvanger,
        subject=onderwerp,
        body=tekst,
        status=status,
        pogingen=pogingen,
    )
    sessie.add(rij)
    await sessie.commit()
    return rij.id


async def _herlees(sessie: AsyncSession, bericht_id: int) -> SimpleNamespace:
    """De rij zoals de database hem nu heeft, als momentopname (blijft geldig na een volgende lees)."""
    sessie.expire_all()
    rij = await sessie.get(OutgoingMessage, bericht_id)
    assert rij is not None
    return SimpleNamespace(
        status=rij.status,
        pogingen=rij.pogingen,
        foutreden=rij.foutreden,
        verzonden_op=rij.verzonden_op,
    )


def _utc(moment: datetime) -> datetime:
    """SQLite geeft tijdzone-loze waarden terug; de kolom is `timezone=True`, dus UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


async def _auditregels(sessie: AsyncSession, tenant_id: int | None = None) -> list[object]:
    from src.core.governance.models import AuditLog

    vraag = select(AuditLog).order_by(AuditLog.id)
    if tenant_id is not None:
        vraag = vraag.where(AuditLog.tenant_id == tenant_id)
    return list((await sessie.execute(vraag)).scalars().all())


def _tekst(regel: object) -> str:
    velden = ("event_type", "action", "resource", "description", "event_metadata", "details")
    return json.dumps({v: getattr(regel, v, None) for v in velden}, default=str).lower()


@pytest_asyncio.fixture
async def stand(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> SmtpDubbel:
    """Twee tenants, een testmailbox met inlog, en de SMTP-dubbel op de systeemgrens."""
    db_session.add(Tenant(id=1, name="T1", slug="deb-verz-1"))
    db_session.add(Tenant(id=2, name="T2", slug="deb-verz-2"))
    await db_session.commit()
    zet_testmailbox(monkeypatch, wachtwoord=WACHTWOORD)
    return installeer_smtp_dubbel(monkeypatch)


@pytest.mark.unit
@pytest.mark.asyncio
class TestKlaarBerichtWordtVerzonden:
    async def test_klaar_bericht_wordt_verzonden(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        bid = await _zet_bericht(db_session, 1)

        await _draai(db_session)

        assert (await _herlees(db_session, bid)).status == "verzonden"

    async def test_verzonden_op_is_het_moment_van_verzenden(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        bid = await _zet_bericht(db_session, 1)
        voor = datetime.now(timezone.utc)

        await _draai(db_session)

        na = datetime.now(timezone.utc)
        verzonden_op = (await _herlees(db_session, bid)).verzonden_op
        assert verzonden_op is not None and voor <= _utc(verzonden_op) <= na

    async def test_de_smtp_kant_ontving_precies_een_brief(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _zet_bericht(db_session, 1)

        await _draai(db_session)

        assert len(stand.ontvangen) == 1

    async def test_de_afzender_is_het_noreply_adres_en_niet_de_inlognaam(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _zet_bericht(db_session, 1)

        await _draai(db_session)

        assert [b.afzender for b in stand.ontvangen] == ["noreply@sanskritisetu.org"]

    async def test_de_brief_gaat_naar_de_debiteur(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _zet_bericht(db_session, 1, DEBITEUR_1)

        await _draai(db_session)

        assert [b.ontvanger for b in stand.ontvangen] == [DEBITEUR_1]

    async def test_onderwerp_en_tekst_zijn_gelijk_aan_de_rij(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """De mens heeft precies deze tekst goedgekeurd (ADR-039): geen woord erbij of eraf."""
        await _zet_bericht(db_session, 1)

        await _draai(db_session)

        brief = stand.ontvangen[0]
        assert (brief.onderwerp, brief.tekst) == (ONDERWERP, TEKST)

    async def test_een_geslaagde_verzending_laat_geen_foutreden_achter(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        bid = await _zet_bericht(db_session, 1)

        await _draai(db_session)

        assert (await _herlees(db_session, bid)).foutreden is None

    async def test_een_bericht_dat_al_verzonden_is_gaat_niet_nog_eens(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Andere kant op: alleen `klaar` (en een mislukte met ruimte) wordt opgepakt."""
        await _zet_bericht(db_session, 1, status="verzonden")

        await _draai(db_session)

        assert stand.ontvangen == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestBerichtNietTweeKeerVerzonden:
    async def test_bericht_niet_twee_keer_verzonden(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Twee runs achter elkaar: een verzending. Gelijktijdig: de integratietest."""
        await _zet_bericht(db_session, 1)

        await _draai(db_session)
        await _draai(db_session)

        assert len(stand.ontvangen) == 1

    async def test_een_run_zonder_klare_berichten_verstuurt_niets(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _draai(db_session)

        assert stand.pogingen == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestMislukteVerzendingBlijftZichtbaar:
    async def test_een_smtp_fout_zet_het_bericht_op_mislukt(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        stand.weiger_alles = True
        bid = await _zet_bericht(db_session, 1)

        await _draai(db_session)

        assert (await _herlees(db_session, bid)).status == "mislukt"

    async def test_mislukte_verzending_blijft_zichtbaar_met_een_foutreden(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        stand.weiger_alles = True
        bid = await _zet_bericht(db_session, 1)

        await _draai(db_session)

        reden = (await _herlees(db_session, bid)).foutreden
        assert reden is not None and reden.strip() != ""

    async def test_de_foutreden_bevat_geen_geheimen(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Een serverfout die het wachtwoord noemt mag niet in een zichtbare kolom belanden."""
        stand.weiger_alles = True
        stand.foutboodschap = f"auth failed for inlog@smtp.example password={WACHTWOORD}"
        bid = await _zet_bericht(db_session, 1)

        await _draai(db_session)

        reden = (await _herlees(db_session, bid)).foutreden or ""
        assert WACHTWOORD not in reden

    async def test_een_mislukte_poging_telt_een_poging(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        stand.weiger_alles = True
        bid = await _zet_bericht(db_session, 1)

        await _draai(db_session)

        assert (await _herlees(db_session, bid)).pogingen == 1

    async def test_na_drie_pogingen_geen_nieuwe_poging_meer(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        stand.weiger_alles = True
        bid = await _zet_bericht(db_session, 1)

        for _ in range(5):
            await _draai(db_session)

        assert (stand.pogingen, (await _herlees(db_session, bid)).pogingen) == (3, 3)

    async def test_na_drie_pogingen_blijft_het_bericht_zichtbaar_op_mislukt(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        stand.weiger_alles = True
        bid = await _zet_bericht(db_session, 1)

        for _ in range(5):
            await _draai(db_session)

        assert (await _herlees(db_session, bid)).status == "mislukt"

    async def test_grens_twee_pogingen_krijgt_nog_een_kans(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """BVA, net onder de grens: `mislukt` met pogingen=2 wordt opnieuw geprobeerd."""
        bid = await _zet_bericht(db_session, 1, status="mislukt", pogingen=2)

        await _draai(db_session)

        assert (len(stand.ontvangen), (await _herlees(db_session, bid)).status) == (
            1,
            "verzonden",
        )

    async def test_grens_drie_pogingen_krijgt_geen_kans_meer(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """BVA, op de grens: `mislukt` met pogingen=3 blijft liggen."""
        bid = await _zet_bericht(db_session, 1, status="mislukt", pogingen=3)

        await _draai(db_session)

        assert (stand.pogingen, (await _herlees(db_session, bid)).status) == (0, "mislukt")

    async def test_een_geslaagde_nieuwe_poging_haalt_een_mislukt_bericht_op(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Andere kant op: `mislukt` is geen eindstation zolang er pogingen over zijn."""
        stand.weiger_alles = True
        bid = await _zet_bericht(db_session, 1)
        await _draai(db_session)
        stand.weiger_alles = False

        await _draai(db_session)

        rij = await _herlees(db_session, bid)
        assert (rij.status, rij.verzonden_op is not None) == ("verzonden", True)

    async def test_een_mislukt_bericht_houdt_een_ander_bericht_niet_tegen(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        stand.weiger_voor = {DEBITEUR_1}
        slecht = await _zet_bericht(db_session, 1, DEBITEUR_1)
        goed = await _zet_bericht(db_session, 1, DEBITEUR_2)

        await _draai(db_session)

        assert (
            (await _herlees(db_session, slecht)).status,
            (await _herlees(db_session, goed)).status,
        ) == ("mislukt", "verzonden")


@pytest.mark.unit
@pytest.mark.asyncio
class TestTenantIsolatie:
    async def test_beide_tenants_worden_verwerkt(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        een = await _zet_bericht(db_session, 1, DEBITEUR_1)
        twee = await _zet_bericht(db_session, 2, DEBITEUR_2)

        await _draai(db_session)

        assert (
            (await _herlees(db_session, een)).status,
            (await _herlees(db_session, twee)).status,
        ) == ("verzonden", "verzonden")

    async def test_elke_brief_gaat_naar_de_debiteur_van_zijn_eigen_tenant(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _zet_bericht(db_session, 1, DEBITEUR_1, onderwerp="Voor tenant 1")
        await _zet_bericht(db_session, 2, DEBITEUR_2, onderwerp="Voor tenant 2")

        await _draai(db_session)

        assert sorted((b.onderwerp, b.ontvanger) for b in stand.ontvangen) == [
            ("Voor tenant 1", DEBITEUR_1),
            ("Voor tenant 2", DEBITEUR_2),
        ]

    async def test_een_bericht_wordt_verstuurd_met_de_tenantcontext_van_zijn_eigen_tenant(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Nooit met de context van een ander: de context staat op het moment van verzenden goed."""
        await _zet_bericht(db_session, 1, DEBITEUR_1)
        await _zet_bericht(db_session, 2, DEBITEUR_2)

        await _draai(db_session)

        per_ontvanger = {
            b.ontvanger: ctx
            for b, ctx in zip(stand.ontvangen, stand.tenantcontext_per_verzending, strict=True)
        }
        assert per_ontvanger == {DEBITEUR_1: 1, DEBITEUR_2: 2}

    async def test_de_tenantcontext_is_na_de_run_weer_zoals_ervoor(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        from src.core.middleware.tenant_context import get_current_tenant_id

        await _zet_bericht(db_session, 2, DEBITEUR_2)

        await _draai(db_session)

        assert get_current_tenant_id() is None

    async def test_een_fout_bij_tenant_2_raakt_de_rij_van_tenant_1_niet(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        stand.weiger_voor = {DEBITEUR_2}
        een = await _zet_bericht(db_session, 1, DEBITEUR_1)
        twee = await _zet_bericht(db_session, 2, DEBITEUR_2)

        await _draai(db_session)

        rij_een, rij_twee = await _herlees(db_session, een), await _herlees(db_session, twee)
        assert (rij_een.status, rij_een.foutreden) == ("verzonden", None)
        assert (rij_twee.status, rij_twee.pogingen) == ("mislukt", 1)

    async def test_de_rij_van_een_andere_tenant_blijft_staan_als_alleen_de_andere_klaar_is(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Andere kant op: een `verzonden` rij van tenant 2 verandert niet door een run voor 1."""
        await _zet_bericht(db_session, 1, DEBITEUR_1)
        vreemd = await _zet_bericht(db_session, 2, DEBITEUR_2, status="verzonden")

        await _draai(db_session)

        rij = await _herlees(db_session, vreemd)
        assert (rij.status, rij.verzonden_op, rij.pogingen) == ("verzonden", None, 0)


@pytest.mark.unit
@pytest.mark.asyncio
class TestLogboek:
    async def test_een_verzonden_bericht_geeft_een_auditregel_in_zijn_tenant(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        bid = await _zet_bericht(db_session, 2, DEBITEUR_2)
        voor = len(await _auditregels(db_session))

        await _draai(db_session)

        nieuw = (await _auditregels(db_session))[voor:]
        assert len(nieuw) == 1, f"verwacht een auditregel, kreeg {len(nieuw)}"
        assert nieuw[0].tenant_id == 2  # type: ignore[attr-defined]
        assert str(bid) in _tekst(nieuw[0]) and "verzonden" in _tekst(nieuw[0]), _tekst(nieuw[0])

    async def test_een_mislukt_bericht_geeft_een_auditregel_in_zijn_tenant(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        stand.weiger_alles = True
        bid = await _zet_bericht(db_session, 2, DEBITEUR_2)
        voor = len(await _auditregels(db_session))

        await _draai(db_session)

        nieuw = (await _auditregels(db_session))[voor:]
        assert len(nieuw) == 1, f"verwacht een auditregel, kreeg {len(nieuw)}"
        assert nieuw[0].tenant_id == 2  # type: ignore[attr-defined]
        assert str(bid) in _tekst(nieuw[0]) and "mislukt" in _tekst(nieuw[0]), _tekst(nieuw[0])

    async def test_de_auditregel_van_een_mislukt_bericht_bevat_geen_geheimen(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        stand.weiger_alles = True
        stand.foutboodschap = f"auth failed password={WACHTWOORD}"
        await _zet_bericht(db_session, 1)
        voor = len(await _auditregels(db_session))

        await _draai(db_session)

        nieuw = (await _auditregels(db_session))[voor:]
        assert nieuw and all(WACHTWOORD.lower() not in _tekst(r) for r in nieuw)

    async def test_de_auditregel_bevat_de_tekst_van_de_brief_niet(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Het logboek zegt DAT er verstuurd is, niet wat erin stond (persoonsgegevens)."""
        await _zet_bericht(db_session, 1)
        voor = len(await _auditregels(db_session))

        await _draai(db_session)

        nieuw = (await _auditregels(db_session))[voor:]
        assert nieuw and all(
            DEBITEUR_1 not in _tekst(r) and "F-2026-001" not in _tekst(r) for r in nieuw
        )

    async def test_een_run_zonder_werk_schrijft_geen_auditregel(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Andere kant op: alleen een echte verzending of mislukking komt in het logboek."""
        voor = len(await _auditregels(db_session))

        await _draai(db_session)

        assert len(await _auditregels(db_session)) == voor

    async def test_een_overgeslagen_bericht_schrijft_geen_auditregel(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Andere kant op: `mislukt` met pogingen=3 wordt niet aangeraakt en dus niet gelogd."""
        await _zet_bericht(db_session, 1, status="mislukt", pogingen=3)
        voor = len(await _auditregels(db_session))

        await _draai(db_session)

        assert len(await _auditregels(db_session)) == voor


@pytest.mark.unit
class TestDeActor:
    def test_de_actor_heet_verstuur_klare_berichten(self) -> None:
        import dramatiq

        from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten

        assert isinstance(verstuur_klare_berichten, dramatiq.Actor)
        assert verstuur_klare_berichten.actor_name == "verstuur_klare_berichten"

    def test_het_maximum_aantal_pogingen_is_drie(self) -> None:
        from src.core.tasks.debiteuren_tasks import MAX_POGINGEN

        assert MAX_POGINGEN == 3
