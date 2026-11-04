"""De actors `verstuur_klare_berichten` en `volg_debiteuren_op` slagen bij ELKE run.

Keten B dag 4, defect 1 uit de acceptatie. De workerlog gaf om de andere run `RuntimeError ...
attached to a different loop` en `Event loop is closed`, vanuit `asyncio.run(...)` in de actor.
De dag 2- en dag 3-tests riepen de async-kern aan op de testloop, NIET de actor zoals de worker
hem draait: elke run een nieuwe `asyncio.run`, dus een nieuwe event loop, op dezelfde
processen-brede `db_manager` met een echte connectiepool.

**Opstelling = de worker.** `DatabaseInitMiddleware.after_process_boot` (de echte hook uit
`src/workers/workflow_worker.py`) zet `db_manager` op zoals een workerproces; daarna roept de
test de onderliggende functie van de actor (`.fn`) synchroon TWEE keer aan, in dezelfde thread,
precies wat Dramatiq doet. De sessiefabriek is de standaard (`get_db_session`): er wordt dus
niets geinjecteerd.

**Wat de opstelling uitzet, nagelopen en omzeild.** De autouse-fixture `setup_db_manager`
(tests/integration/conftest.py) zet `db_manager` op een engine met `NullPool`, en dan bestaat
het defect niet (er is geen pool die een verbinding aan een oude loop kan teruggeven). Die
fixture raakt dus wat hier gemeten wordt. De test bewaart daarom de staat van `db_manager`,
bouwt hem opnieuw op via de echte workerhook (gepoolde engine uit `config`) en herstelt hem
in `finally`; een assertie in de fixture controleert dat de pool er niet `NullPool` is. Andere
autouse-fixtures (`reset_db_per_module`, `reset_cache_singleton`, `reset_rate_limiter`,
`enforce_testing_env`, `ensure_main_thread_event_loop`) raken mail, rijen of loops van de actor
niet.

**Alleen PostgreSQL.** Het defect zit in asyncpg-verbindingen die aan een loop gebonden zijn;
SQLite (aiosqlite) kent dat niet. Vandaar `@pytest.mark.integration`.

**Dag 5: een ANDERE actor op dezelfde pool (tweede reparatie).** De dag 4-fix (`dispose()` na
elke debiteurenrun) hield de acceptatie niet stand: de workerlog gaf nog steeds `attached to a
different loop`. Oorzaak (gemeten, de worker draait ook andere actors): een actor die een KALE
`asyncio.run(...)` doet op de gedeelde `db_manager` zonder `dispose()` -- zoals
`src/core/tasks/audit_tasks.py:92` (`write_audit_log_task`) -- laat een verbinding in de pool
achter die aan zijn gesloten loop hangt; de eerstvolgende debiteurenrun trekt hem eruit. Twee
varianten, allebei over de echte actor van de debiteuren: (1) een kale run TUSSEN twee
debiteurenruns (zelfde thread, na elkaar); (2) een kale run en een debiteurenrun in twee threads
tegelijk (de worker draait meerdere threads op een proces). De kale run is een stand-in
(`select 1` op `get_db_session`); een derde test gebruikt de ECHTE producent
`write_audit_log_task.fn`.

**Mutatie die dit moet betrappen.** Productiecode die `db_manager`/`get_db_session` blijft
delen over `asyncio.run`-aanroepen (de stand van 455e400b) is rood; een actor die per run zijn
eigen engine maakt en na afloop `dispose()`t wordt groen.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.database.database import db_manager
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.models.outgoing_message_models import OutgoingMessage
from src.core.models.receivable_models import Receivable
from tests.integration.conftest import TEST_DB_URL
from tests.unit.debiteuren._smtp_dubbel import installeer_smtp_dubbel, zet_testmailbox

TENANT_ID = 1
DOSSIER_ID_BASIS = 940_000


def _eigen_sessies() -> async_sessionmaker:  # type: ignore[type-arg]
    # NullPool-wegwerpengine: alleen om te zaaien en te lezen, nooit voor de actor zelf.
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False)


def _zaai_bericht(nummer: int) -> int:
    async def _doe() -> int:
        async with _eigen_sessies()() as sessie:
            rij = OutgoingMessage(
                tenant_id=TENANT_ID,
                channel="email",
                kind="herinnering",
                recipient=f"loop{nummer}@klant.example",
                subject=f"Herinnering {nummer}",
                body=f"Tekst {nummer}",
                status="klaar",
            )
            sessie.add(rij)
            await sessie.commit()
            return int(rij.id)

    return asyncio.run(_doe())


def _zaai_dossier(rij_id: int) -> int:
    oud = datetime.now(timezone.utc) - timedelta(days=30)

    async def _doe() -> int:
        async with _eigen_sessies()() as sessie:
            sessie.add(
                Receivable(
                    id=rij_id,
                    tenant_id=TENANT_ID,
                    customer_name="Bakkerij De Korst",
                    customer_email="administratie@dekorst.example",
                    invoice_number=f"LOOP-{rij_id}",
                    amount=Decimal("100.00"),
                    currency="EUR",
                    due_date=date(2026, 1, 1),
                    status="herinnerd",
                    source="handmatig",
                    herinnerd_op=oud,
                )
            )
            await sessie.flush()
            # Zonder verzonden brief escaleert de opvolging niet (wfb-dag1 stap 2).
            sessie.add(
                OutgoingMessage(
                    tenant_id=TENANT_ID,
                    receivable_id=rij_id,
                    channel="email",
                    kind="herinnering",
                    recipient="administratie@dekorst.example",
                    subject="Herinnering",
                    body="Tekst",
                    status="verzonden",
                    verzonden_op=oud,
                    hitl_ticket_ref=f"hitl-loop-dossier-{rij_id}",
                )
            )
            await sessie.commit()
            return rij_id

    return asyncio.run(_doe())


def _lees_status(model: type, rij_id: int) -> str:
    async def _doe() -> str:
        async with _eigen_sessies()() as sessie:
            with TenantFilterBypass():  # de testlezer heeft geen tenantcontext
                res = await sessie.execute(
                    select(model.status).where(model.id == rij_id)  # type: ignore[attr-defined]
                )
            return str(res.scalar_one())

    return asyncio.run(_doe())


def _ruim_op(model: type, *ids: int) -> None:
    async def _doe() -> None:
        async with _eigen_sessies()() as sessie:
            with TenantFilterBypass():
                if model is Receivable:
                    # De verzonden brief uit `_zaai_dossier` hoort bij het dossier.
                    await sessie.execute(
                        delete(OutgoingMessage).where(OutgoingMessage.receivable_id.in_(ids))
                    )
                await sessie.execute(delete(model).where(model.id.in_(ids)))  # type: ignore[attr-defined]
            await sessie.commit()

    asyncio.run(_doe())


@pytest.fixture
def workerdatabase() -> Iterator[None]:
    """`db_manager` zoals een workerproces hem krijgt: via de echte `after_process_boot`."""
    from src.workers.workflow_worker import DatabaseInitMiddleware

    bewaard = (db_manager.engine, db_manager.async_session_maker, db_manager._initialized)
    db_manager.engine = None
    db_manager.async_session_maker = None
    db_manager._initialized = False
    try:
        DatabaseInitMiddleware().after_process_boot(None)
        assert db_manager.engine is not None
        assert not isinstance(db_manager.engine.pool, NullPool), (
            "opstelling: de workerhook moet een gepoolde engine geven, anders meet de test niets"
        )
        yield
    finally:
        eigen = db_manager.engine
        if eigen is not None:
            asyncio.run(eigen.dispose())
        db_manager.engine, db_manager.async_session_maker, db_manager._initialized = bewaard


@pytest.mark.integration
class TestVerstuurKlareBerichtenActor:
    def test_twee_runs_na_elkaar_versturen_allebei(
        self, workerdatabase: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten

        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        eerste = _zaai_bericht(1)
        tweede = 0
        try:
            verstuur_klare_berichten.fn()
            na_eerste = _lees_status(OutgoingMessage, eerste)
            tweede = _zaai_bericht(2)
            verstuur_klare_berichten.fn()
            na_tweede = _lees_status(OutgoingMessage, tweede)
        finally:
            _ruim_op(OutgoingMessage, eerste, tweede)

        assert (na_eerste, na_tweede, len(dubbel.ontvangen)) == ("verzonden", "verzonden", 2)

    def test_een_enkele_run_verstuurt_wel(
        self, workerdatabase: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Andere kant op: de eerste run slaagt; alleen de herhaling is het defect."""
        from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten

        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        rij_id = _zaai_bericht(3)
        try:
            verstuur_klare_berichten.fn()
            status = _lees_status(OutgoingMessage, rij_id)
        finally:
            _ruim_op(OutgoingMessage, rij_id)

        assert (status, len(dubbel.ontvangen)) == ("verzonden", 1)


@pytest.mark.integration
class TestVolgDebiteurenOpActor:
    def test_twee_runs_na_elkaar_escaleren_allebei(self, workerdatabase: None) -> None:
        from src.core.tasks.debiteuren_tasks import volg_debiteuren_op

        eerste = _zaai_dossier(DOSSIER_ID_BASIS)
        tweede = DOSSIER_ID_BASIS + 1
        try:
            volg_debiteuren_op.fn()
            na_eerste = _lees_status(Receivable, eerste)
            _zaai_dossier(tweede)
            volg_debiteuren_op.fn()
            na_tweede = _lees_status(Receivable, tweede)
        finally:
            _ruim_op(Receivable, eerste, tweede)

        assert (na_eerste, na_tweede) == ("geescaleerd", "geescaleerd")

    def test_een_enkele_run_escaleert_wel(self, workerdatabase: None) -> None:
        """Andere kant op: de eerste run slaagt; alleen de herhaling is het defect."""
        from src.core.tasks.debiteuren_tasks import volg_debiteuren_op

        rij_id = _zaai_dossier(DOSSIER_ID_BASIS + 2)
        try:
            volg_debiteuren_op.fn()
            status = _lees_status(Receivable, rij_id)
        finally:
            _ruim_op(Receivable, rij_id)

        assert status == "geescaleerd"


def _kale_run() -> None:
    """Wat `audit_tasks.py:92` doet: `asyncio.run` op de gedeelde `db_manager`, geen `dispose()`."""
    from sqlalchemy import text

    from src.core.database.session import get_db_session

    async def _doe() -> None:
        async with get_db_session() as sessie:
            await sessie.execute(text("SELECT 1"))

    asyncio.run(_doe())


@pytest.mark.integration
class TestEenAndereActorOpDezelfdePool:
    def test_een_kale_run_tussen_twee_debiteurenruns_laat_de_tweede_slagen(
        self, workerdatabase: None
    ) -> None:
        from src.core.tasks.debiteuren_tasks import volg_debiteuren_op

        eerste = _zaai_dossier(DOSSIER_ID_BASIS + 10)
        tweede = DOSSIER_ID_BASIS + 11
        try:
            volg_debiteuren_op.fn()
            na_eerste = _lees_status(Receivable, eerste)
            _kale_run()
            _zaai_dossier(tweede)
            volg_debiteuren_op.fn()
            na_tweede = _lees_status(Receivable, tweede)
        finally:
            _ruim_op(Receivable, eerste, tweede)

        assert (na_eerste, na_tweede) == ("geescaleerd", "geescaleerd")

    def test_de_echte_auditactor_tussen_twee_debiteurenruns_laat_de_tweede_slagen(
        self, workerdatabase: None
    ) -> None:
        """Over de ECHTE producent van de kale `asyncio.run`: `write_audit_log_task`."""
        from src.core.tasks.audit_tasks import write_audit_log_task
        from src.core.tasks.debiteuren_tasks import volg_debiteuren_op

        eerste = _zaai_dossier(DOSSIER_ID_BASIS + 20)
        tweede = DOSSIER_ID_BASIS + 21
        try:
            volg_debiteuren_op.fn()
            na_eerste = _lees_status(Receivable, eerste)
            write_audit_log_task.fn(
                tenant_id=TENANT_ID, action="loop_test", resource="loop_test", user_id=None
            )
            _zaai_dossier(tweede)
            volg_debiteuren_op.fn()
            na_tweede = _lees_status(Receivable, tweede)
        finally:
            _ruim_op(Receivable, eerste, tweede)

        assert (na_eerste, na_tweede) == ("geescaleerd", "geescaleerd")

    def test_een_kale_run_en_een_debiteurenrun_in_twee_threads_tegelijk(
        self, workerdatabase: None
    ) -> None:
        import threading

        from src.core.tasks.debiteuren_tasks import volg_debiteuren_op

        ronden = 6
        start = threading.Barrier(2)
        klaar = threading.Event()
        uitkomsten: list[str] = []
        ids = [DOSSIER_ID_BASIS + 30 + i for i in range(ronden)]

        def kale_thread() -> None:
            start.wait()
            while not klaar.is_set():
                try:
                    _kale_run()
                except Exception:  # noqa: BLE001 -- de kale run mag falen; het gaat om de ander
                    pass

        def debiteuren_thread() -> None:
            start.wait()
            for rij_id in ids:
                try:
                    _zaai_dossier(rij_id)
                    volg_debiteuren_op.fn()
                    uitkomsten.append(_lees_status(Receivable, rij_id))
                except Exception as fout:  # noqa: BLE001 -- de uitkomst is wat we meten
                    uitkomsten.append(f"{type(fout).__name__}: {fout}")
            klaar.set()

        draden = [threading.Thread(target=kale_thread), threading.Thread(target=debiteuren_thread)]
        try:
            for draad in draden:
                draad.start()
            for draad in draden:
                draad.join(timeout=120)
        finally:
            klaar.set()
            _ruim_op(Receivable, *ids)

        assert uitkomsten == ["geescaleerd"] * ronden
