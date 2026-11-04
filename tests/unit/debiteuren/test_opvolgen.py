"""De opvolging van een debiteur -- Keten B dag 3: de actor `volg_debiteuren_op`.

Wat hier gemeten wordt, per vraag (techniek tussen haakjes):

1. `betaald` sluit de zaak: de opvolging raakt zo'n dossier niet aan (EP: klasse "betaald").
2. `herinnerd` en 14 dagen of meer na `herinnerd_op` wordt `geescaleerd`; erboven en eronder
   precies op de grens (BVA: 13 dagen, 14 dagen min 1 seconde, 14 dagen exact, 14 dagen plus 1
   seconde, 15 dagen). **De grens is `nu - herinnerd_op >= 14 dagen`**: op dag 14 zelf escaleert
   het dossier. Gekozen omdat de brief zegt "14 dagen na `herinnerd_op`: status `geescaleerd`";
   een bouwer die `>` neemt, laat het dossier een hele dag langer liggen en wordt rood op de
   rij "14 dagen exact".
3. Beslistabel status x datum (alleen de combinaties die iets beslissen): `open` en
   `geescaleerd` worden NOOIT aangeraakt, ook niet bij een oude aanmaakdatum.
4. `herinnerd` ZONDER `herinnerd_op` (een handmatig gezette status uit de tijd van voor dag 3):
   **gekozen regel: het aanmaakmoment (`created_at`) geldt dan als `herinnerd_op`.** Reden: een
   dossier dat stil wordt overgeslagen wordt nooit opgevolgd; escaleren verstuurt niets en legt
   alleen een beslissing bij een mens, dus de voorzichtige kant is dat het dossier meetelt.
5. Escaleren verstuurt NOOIT iets (ADR-039): geen nieuwe rij in `outgoing_messages` en geen
   SMTP-poging.
6. Logboek: een auditregel in de EIGEN tenant, eenmalig (een tweede run schrijft geen tweede
   regel), zonder persoonsgegevens van de debiteur.
7. Tenantisolatie: elke rij wordt in de tenantcontext van die rij verwerkt (de context op het
   moment van schrijven staat in `test_tenantcontext_rond_de_auditregel.py`).

**De klok is een parameter.** `nu` is een vaste, ver in de toekomst liggende datum (2099): een
implementatie die stiekem de echte klok leest, ziet dan een `herinnerd_op` in haar toekomst en
escaleert niets -- en de rij "15 dagen" wordt rood.

**Systeemgrens.** Alleen `aiosmtplib.send` is vervangen (`_smtp_dubbel.py`), om te kunnen meten
dat er NIETS verstuurd wordt. Database (echte SQLite-sessie met `create_all`), auditdienst en
actor lopen echt.

**Contract met de bouwer** (nog niet bestaand, dus de tests zijn rood), in
`src/core/tasks/debiteuren_tasks.py`:
- `ESCALATIE_NA_DAGEN = 14` (int, benoemde constante);
- `async def volg_debiteuren_op_async(sessie_fabriek=None, nu=None) -> ...`: de kern; `nu` is
  een tijdzone-bewuste `datetime` (UTC), `None` betekent de echte klok. De terugwaarde wordt
  niet getoetst;
- `volg_debiteuren_op`: de Dramatiq-actor, `actor_name="volg_debiteuren_op"`.

**Wat de opstelling uitzet, nagelopen.** Autouse in `tests/conftest.py`: `enforce_testing_env`
(TESTING=1), `_reset_global_state` (tenantfilter bewaren/herstellen), `ensure_main_thread_event_loop`,
`_seed_module_snapshot`. Geen daarvan raakt tijd, mail, de auditdienst of de rij. Geen conftest
in `tests/unit/debiteuren/`. Er is niets op de auditdienst of de repository gepatcht.

**Wat dit NIET meet.** (1) De hash-keten van het logboek (advisory lock bestaat alleen op
PostgreSQL). (2) Rijsloten bij twee gelijktijdige opvolgruns (alleen PostgreSQL). (3) RLS onder
een niet-eigenaarrol (OP-151). (4) Dat een kapotte auditschrijving de escalatie niet blokkeert:
`test_opvolgen_audit_faalt.py`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.models.outgoing_message_models import OutgoingMessage
from src.core.models.rbac_models import Tenant
from src.core.models.receivable_models import Receivable
from tests.unit.debiteuren._smtp_dubbel import SmtpDubbel, installeer_smtp_dubbel, zet_testmailbox

NU = datetime(2099, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
DAG = timedelta(days=1)

KLANT_NAAM = "Bakkerij De Korst"
KLANT_MAIL = "administratie@dekorst.example"


def _fabriek(sessie: AsyncSession) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    @asynccontextmanager
    async def _sessie() -> AsyncIterator[AsyncSession]:
        yield sessie

    return _sessie


async def _draai(sessie: AsyncSession, nu: datetime = NU) -> None:
    """Een run van de kern van de actor, op de testsessie, met een vaste klok."""
    from src.core.tasks.debiteuren_tasks import volg_debiteuren_op_async

    await volg_debiteuren_op_async(sessie_fabriek=_fabriek(sessie), nu=nu)


async def _zet_factuur(
    sessie: AsyncSession,
    tenant_id: int,
    *,
    rij_id: int,
    status: str = "herinnerd",
    herinnerd_op: datetime | None = None,
    betaald_op: datetime | None = None,
    created_at: datetime | None = None,
    met_verzonden_brief: bool = True,
) -> int:
    """Zet een rij DIRECT op een status en datum, zonder de overgangsregel te passeren.

    Een `herinnerd` dossier krijgt standaard de verzonden brief die het in het echt heeft
    (`met_verzonden_brief`); zonder die brief escaleert de opvolging niet (wfb-dag1 stap 2)."""
    sessie.add(
        Receivable(
            id=rij_id,
            tenant_id=tenant_id,
            customer_name=KLANT_NAAM,
            customer_email=KLANT_MAIL,
            invoice_number=f"F-{rij_id}",
            amount=Decimal("100.00"),
            currency="EUR",
            due_date=date(2099, 1, 1),
            status=status,
            source="handmatig",
            herinnerd_op=herinnerd_op,
            betaald_op=betaald_op,
            created_at=created_at or (NU - 60 * DAG),
        )
    )
    await sessie.flush()
    if status == "herinnerd" and met_verzonden_brief:
        sessie.add(_verzonden_brief(tenant_id, rij_id, herinnerd_op))
    await sessie.commit()
    return rij_id


def _verzonden_brief(tenant_id: int, rij_id: int, moment: datetime | None) -> OutgoingMessage:
    """De brief die een `herinnerd` dossier hoort te hebben: zonder verzonden brief escaleert de
    opvolging niet (wfb-dag1 stap 2, test_herinnerd_is_een_feit.py)."""
    return OutgoingMessage(
        tenant_id=tenant_id,
        receivable_id=rij_id,
        channel="email",
        kind="herinnering",
        recipient="klant@klant.example",
        subject="Herinnering",
        body="Tekst",
        status="verzonden",
        verzonden_op=moment,
        hitl_ticket_ref=f"hitl-verzonden-{tenant_id}-{rij_id}",
    )


async def _herlees(sessie: AsyncSession, rij_id: int) -> SimpleNamespace:
    """De rij zoals de database hem nu heeft, als momentopname."""
    sessie.expire_all()
    rij = await sessie.get(Receivable, rij_id)
    assert rij is not None
    return SimpleNamespace(
        status=rij.status, herinnerd_op=rij.herinnerd_op, betaald_op=rij.betaald_op
    )


async def _auditregels(sessie: AsyncSession, tenant_id: int | None = None) -> list[object]:
    from src.core.governance.models import AuditLog

    vraag = select(AuditLog).order_by(AuditLog.id)
    if tenant_id is not None:
        vraag = vraag.where(AuditLog.tenant_id == tenant_id)
    return list((await sessie.execute(vraag)).scalars().all())


def _tekst(regel: object) -> str:
    velden = ("event_type", "action", "resource", "description", "event_metadata", "details")
    return json.dumps({v: getattr(regel, v, None) for v in velden}, default=str).lower()


async def _aantal_berichten(sessie: AsyncSession) -> int:
    return int((await sessie.execute(select(func.count(OutgoingMessage.id)))).scalar_one())


@pytest_asyncio.fixture
async def stand(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> SmtpDubbel:
    """Twee tenants en een SMTP-dubbel op de systeemgrens (om te meten dat er niets uitgaat)."""
    db_session.add(Tenant(id=1, name="T1", slug="deb-opv-1"))
    db_session.add(Tenant(id=2, name="T2", slug="deb-opv-2"))
    await db_session.commit()
    zet_testmailbox(monkeypatch)
    return installeer_smtp_dubbel(monkeypatch)


@pytest.mark.unit
@pytest.mark.asyncio
class TestBetaaldSluitDeZaak:
    async def test_betaald_sluit_de_zaak(self, db_session: AsyncSession, stand: SmtpDubbel) -> None:
        rid = await _zet_factuur(
            db_session, 1, rij_id=1001, status="betaald", herinnerd_op=NU - 30 * DAG
        )

        await _draai(db_session)

        assert (await _herlees(db_session, rid)).status == "betaald"

    async def test_betaald_dossier_krijgt_geen_auditregel(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _zet_factuur(db_session, 1, rij_id=1001, status="betaald", herinnerd_op=NU - 30 * DAG)
        voor = len(await _auditregels(db_session))

        await _draai(db_session)

        assert len(await _auditregels(db_session)) == voor

    async def test_betaald_op_blijft_zoals_het_was(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        betaald_op = NU - 20 * DAG
        rid = await _zet_factuur(
            db_session,
            1,
            rij_id=1001,
            status="betaald",
            herinnerd_op=NU - 30 * DAG,
            betaald_op=betaald_op,
        )

        await _draai(db_session)

        gelezen = (await _herlees(db_session, rid)).betaald_op
        assert gelezen is not None and gelezen.replace(tzinfo=None) == betaald_op.replace(
            tzinfo=None
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestVeertienDagenNietBetaald:
    async def test_veertien_dagen_niet_betaald_escaleert(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """15 dagen na `herinnerd_op`, nog niet betaald."""
        rid = await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 15 * DAG)

        await _draai(db_session)

        assert (await _herlees(db_session, rid)).status == "geescaleerd"

    async def test_dertien_dagen_doet_niets(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        rid = await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 13 * DAG)

        await _draai(db_session)

        assert (await _herlees(db_session, rid)).status == "herinnerd"

    @pytest.mark.parametrize(
        ("leeftijd", "verwacht"),
        [
            (14 * DAG - timedelta(seconds=1), "herinnerd"),
            (14 * DAG, "geescaleerd"),
            (14 * DAG + timedelta(seconds=1), "geescaleerd"),
        ],
        ids=["14d_min_1s", "14d_exact", "14d_plus_1s"],
    )
    async def test_de_grens_ligt_precies_op_veertien_dagen(
        self,
        db_session: AsyncSession,
        stand: SmtpDubbel,
        leeftijd: timedelta,
        verwacht: str,
    ) -> None:
        """BVA: `nu - herinnerd_op >= 14 dagen` escaleert, een seconde minder niet."""
        rid = await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - leeftijd)

        await _draai(db_session)

        assert (await _herlees(db_session, rid)).status == verwacht

    async def test_de_termijn_is_een_benoemde_constante_van_veertien_dagen(self) -> None:
        from src.core.tasks.debiteuren_tasks import ESCALATIE_NA_DAGEN

        assert ESCALATIE_NA_DAGEN == 14

    async def test_een_jong_dossier_blijft_herinnerd_na_twee_runs(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Andere kant op: herhaald draaien rekent niets op bij een dossier dat nog niet toe is."""
        rid = await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 2 * DAG)

        await _draai(db_session)
        await _draai(db_session)

        assert (await _herlees(db_session, rid)).status == "herinnerd"


@pytest.mark.unit
@pytest.mark.asyncio
class TestHerinnerdZonderDatum:
    async def test_herinnerd_zonder_datum_wordt_niet_stil_overgeslagen(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Gekozen regel: `created_at` geldt als `herinnerd_op`; 20 dagen oud escaleert."""
        rid = await _zet_factuur(
            db_session, 1, rij_id=1001, herinnerd_op=None, created_at=NU - 20 * DAG
        )

        await _draai(db_session)

        assert (await _herlees(db_session, rid)).status == "geescaleerd"

    async def test_herinnerd_zonder_datum_en_een_jong_dossier_blijft_herinnerd(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Andere kant op: de terugvaldatum is geen vrijbrief om alles meteen te escaleren."""
        rid = await _zet_factuur(
            db_session, 1, rij_id=1001, herinnerd_op=None, created_at=NU - 5 * DAG
        )

        await _draai(db_session)

        assert (await _herlees(db_session, rid)).status == "herinnerd"

    async def test_een_echte_datum_gaat_voor_de_aanmaakdatum(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Andere kant op: oud dossier, maar pas 2 dagen geleden herinnerd: niet escaleren."""
        rid = await _zet_factuur(
            db_session, 1, rij_id=1001, herinnerd_op=NU - 2 * DAG, created_at=NU - 90 * DAG
        )

        await _draai(db_session)

        assert (await _herlees(db_session, rid)).status == "herinnerd"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAndereStatussenWordenNietAangeraakt:
    async def test_open_blijft_open_ook_bij_een_oud_dossier(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """`open -> geescaleerd` is geen toegestane overgang (dag 1)."""
        rid = await _zet_factuur(
            db_session, 1, rij_id=1001, status="open", herinnerd_op=None, created_at=NU - 90 * DAG
        )

        await _draai(db_session)

        assert (await _herlees(db_session, rid)).status == "open"

    async def test_een_geescaleerd_dossier_blijft_geescaleerd(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        rid = await _zet_factuur(
            db_session, 1, rij_id=1001, status="geescaleerd", herinnerd_op=NU - 40 * DAG
        )

        await _draai(db_session)

        assert (await _herlees(db_session, rid)).status == "geescaleerd"

    async def test_een_tweede_run_escaleert_niet_nog_een_keer(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """De auditregel is eenmalig: een al geescaleerd dossier telt niet opnieuw mee."""
        await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 15 * DAG)
        await _draai(db_session)
        na_eerste = len(await _auditregels(db_session))

        await _draai(db_session)

        assert len(await _auditregels(db_session)) == na_eerste

    async def test_een_run_zonder_werk_schrijft_niets(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        voor = len(await _auditregels(db_session))

        await _draai(db_session)

        assert len(await _auditregels(db_session)) == voor


@pytest.mark.unit
@pytest.mark.asyncio
class TestEscalerenVerstuurtNiets:
    async def test_escaleren_verstuurt_niets(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Geen nieuwe rij in `outgoing_messages`: een aanmaning loopt weer langs een mens."""
        await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 15 * DAG)
        voor = await _aantal_berichten(db_session)

        await _draai(db_session)

        assert await _aantal_berichten(db_session) == voor

    async def test_escaleren_doet_geen_smtp_poging(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 15 * DAG)

        await _draai(db_session)

        assert stand.pogingen == 0

    async def test_escaleren_laat_een_bestaand_klaar_bericht_ongemoeid(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Andere kant op: een eerder goedgekeurde, nog niet verzonden brief blijft `klaar`."""
        await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 15 * DAG)
        bericht = OutgoingMessage(
            tenant_id=1,
            receivable_id=1001,
            channel="email",
            kind="herinnering",
            recipient=KLANT_MAIL,
            subject="Herinnering",
            body="Tekst",
            status="klaar",
        )
        db_session.add(bericht)
        await db_session.flush()
        bericht_id = bericht.id
        await db_session.commit()

        await _draai(db_session)

        db_session.expire_all()
        gelezen = await db_session.get(OutgoingMessage, bericht_id)
        assert gelezen is not None and gelezen.status == "klaar"


@pytest.mark.unit
@pytest.mark.asyncio
class TestLogboek:
    async def test_escalatie_staat_in_het_logboek_van_de_eigen_tenant(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        rid = await _zet_factuur(db_session, 2, rij_id=2002, herinnerd_op=NU - 15 * DAG)
        voor = len(await _auditregels(db_session))

        await _draai(db_session)

        nieuw = (await _auditregels(db_session))[voor:]
        assert len(nieuw) == 1, f"verwacht precies een logboekregel erbij, kreeg {len(nieuw)}"
        assert nieuw[0].tenant_id == 2  # type: ignore[attr-defined]
        assert str(rid) in _tekst(nieuw[0]) and "geescaleerd" in _tekst(nieuw[0]), _tekst(nieuw[0])

    async def test_de_regel_noemt_geen_persoonsgegevens_van_de_debiteur(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 15 * DAG)
        voor = len(await _auditregels(db_session))

        await _draai(db_session)

        nieuw = (await _auditregels(db_session))[voor:]
        assert nieuw and all(
            KLANT_MAIL not in _tekst(r) and KLANT_NAAM.lower() not in _tekst(r) for r in nieuw
        )

    async def test_een_dossier_dat_niet_escaleert_geeft_geen_regel(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Andere kant op: 13 dagen is geen gebeurtenis voor het logboek."""
        await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 13 * DAG)
        voor = len(await _auditregels(db_session))

        await _draai(db_session)

        assert len(await _auditregels(db_session)) == voor

    async def test_de_escalatie_blijft_staan_naast_de_logboekregel(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """De primaire wijziging is gecommit; het logboek haalt hem niet terug."""
        rid = await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 15 * DAG)

        await _draai(db_session)

        assert (await _herlees(db_session, rid)).status == "geescaleerd"


@pytest.mark.unit
@pytest.mark.asyncio
class TestTenantIsolatie:
    async def test_beide_tenants_worden_opgevolgd(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        een = await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 15 * DAG)
        twee = await _zet_factuur(db_session, 2, rij_id=2002, herinnerd_op=NU - 15 * DAG)

        await _draai(db_session)

        assert (
            (await _herlees(db_session, een)).status,
            (await _herlees(db_session, twee)).status,
        ) == ("geescaleerd", "geescaleerd")

    async def test_elke_auditregel_staat_in_de_tenant_van_zijn_eigen_dossier(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 15 * DAG)
        await _zet_factuur(db_session, 2, rij_id=2002, herinnerd_op=NU - 15 * DAG)

        await _draai(db_session)

        van_een = [_tekst(r) for r in await _auditregels(db_session, 1)]
        van_twee = [_tekst(r) for r in await _auditregels(db_session, 2)]
        assert (
            len(van_een),
            len(van_twee),
            all("1001" in t and "2002" not in t for t in van_een),
            all("2002" in t and "1001" not in t for t in van_twee),
        ) == (1, 1, True, True)

    async def test_een_dossier_van_een_andere_tenant_dat_nog_niet_toe_is_blijft_staan(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        """Andere kant op: tenant 1 escaleert, het jonge dossier van tenant 2 verandert niet."""
        await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 15 * DAG)
        vreemd = await _zet_factuur(db_session, 2, rij_id=2002, herinnerd_op=NU - 3 * DAG)

        await _draai(db_session)

        assert (await _herlees(db_session, vreemd)).status == "herinnerd"

    async def test_een_betaald_dossier_van_tenant_2_blijft_betaald_terwijl_tenant_1_escaleert(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _zet_factuur(db_session, 1, rij_id=1001, herinnerd_op=NU - 15 * DAG)
        vreemd = await _zet_factuur(
            db_session, 2, rij_id=2002, status="betaald", herinnerd_op=NU - 30 * DAG
        )

        await _draai(db_session)

        assert (await _herlees(db_session, vreemd)).status == "betaald"


@pytest.mark.unit
class TestDeActor:
    def test_de_actor_heet_volg_debiteuren_op(self) -> None:
        import dramatiq

        from src.core.tasks.debiteuren_tasks import volg_debiteuren_op

        assert isinstance(volg_debiteuren_op, dramatiq.Actor)
        assert volg_debiteuren_op.actor_name == "volg_debiteuren_op"
