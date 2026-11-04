"""Tests for Digital Twin background workers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.learning.consent.consent_manager import TwinConsentManager
from src.core.learning.worker import _run_hard_delete


@pytest.fixture(autouse=True)
def _no_real_redis():
    """Nooit een echte Redis-verbinding openen in deze unit-tests.

    `_run_hard_delete` doet `await get_redis_client()`, en die client wordt in een
    module-globale singleton gecachet. Zonder deze mock opent de test een echte
    verbinding naar localhost:6380 die daarna in de event-loop van een VOLGENDE test
    wordt hergebruikt -- met "got Future attached to a different loop" tot gevolg in een
    heel ander bestand (test_workflow_real_routing.py).

    Dat bleef tot 2026-08-01 onzichtbaar omdat deze tests door een vergiftigde REDIS_URL
    (comment in de string, tests/unit/test_middleware_order_sprint33.py) al bij import
    stukliepen en dus nooit draaiden. Een unit-test hoort sowieso geen netwerkverbinding
    te openen.
    """
    with patch("src.core.database.redis.get_redis_client", new_callable=AsyncMock) as mock:
        yield mock


class TestRunHardDelete:
    """Tests for the _run_hard_delete helper (core logic without Dramatiq)."""

    @pytest.mark.asyncio
    async def test_calls_hard_delete_on_consent_manager(self):
        """The helper should call TwinConsentManager.hard_delete with correct args."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_consent_mgr = AsyncMock(spec=TwinConsentManager)
        mock_consent_mgr.hard_delete = AsyncMock(
            return_value={"observations": -1, "profiles": -1, "consent": -1}
        )

        with (
            patch(
                "src.core.learning.worker._get_session_maker",
                return_value=MagicMock(return_value=mock_session),
            ),
            patch(
                "src.core.learning.worker.TwinConsentManager",
                return_value=mock_consent_mgr,
            ),
        ):
            result = await _run_hard_delete("user_123", 42)

        assert result["user_id"] == "user_123"
        assert result["tenant_id"] == 42
        assert result["deleted"]["observations"] == -1
        mock_consent_mgr.hard_delete.assert_awaited_once_with(user_id="user_123", tenant_id=42)

    @pytest.mark.asyncio
    async def test_raises_when_database_url_is_missing(self):
        """Zonder DATABASE_URL moet de helper hard falen, niet stil doorgaan.

        Deze test controleerde `worker.async_session_maker is None` met de melding
        "Database session maker not initialized". Die modulevariabele en die melding
        bestaan niet meer: de worker maakt de sessionmaker nu lazy aan via
        `_get_session_maker()` -> `_get_engine()` -> `_get_database_url()`, en die laatste
        gooit `RuntimeError("DATABASE_URL environment variable is required")`. De test is
        meegetrokken naar dat contract (gevonden OP-11, 2026-07-31).
        """
        import src.core.learning.worker as worker_mod

        # Alleen DATABASE_URL weghalen, niet de HELE omgeving: `clear=True` sloopte
        # variabelen die pytest-xdist-workers nodig hebben (8 ERRORs onder -n 8,
        # "Port could not be..."), terwijl de tests los wel slaagden.
        with (
            patch.dict("os.environ", {"DATABASE_URL": ""}),
            patch.object(worker_mod, "_DATABASE_URL", None),
            patch.object(worker_mod, "_engine", None),
            patch.object(worker_mod, "_async_session_maker", None),
            patch("src.core.database.redis.get_redis_client", new_callable=AsyncMock),
        ):
            with pytest.raises(RuntimeError, match="DATABASE_URL"):
                await _run_hard_delete("user_123", 42)

    @pytest.mark.asyncio
    async def test_reraises_on_hard_delete_failure(self):
        """The helper should re-raise exceptions from hard_delete."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_consent_mgr = AsyncMock(spec=TwinConsentManager)
        mock_consent_mgr.hard_delete = AsyncMock(side_effect=Exception("DB error"))

        with (
            patch(
                "src.core.learning.worker._get_session_maker",
                return_value=MagicMock(return_value=mock_session),
            ),
            patch(
                "src.core.learning.worker.TwinConsentManager",
                return_value=mock_consent_mgr,
            ),
        ):
            with pytest.raises(Exception, match="DB error"):
                await _run_hard_delete("user_123", 42)


class TestTwinHardDeleteAsyncActor:
    """Tests for the dramatiq actor wrapper (thin layer)."""

    def test_actor_is_registered(self):
        """The actor should be a valid dramatiq actor."""
        from src.core.learning.worker import twin_hard_delete_async

        assert hasattr(twin_hard_delete_async, "send")
        assert twin_hard_delete_async.options["max_retries"] == 3
        assert twin_hard_delete_async.options["time_limit"] == 60000


class TestRunObservationCleanup:
    """Tests for the _run_observation_cleanup helper."""

    @staticmethod
    def _sessie_met_twee_klanten(rijen_per_klant: int) -> AsyncMock:
        """Een sessie die eerst de klantenlijst geeft en daarna per klant een DELETE.

        Die vorm is geen detail van de test maar van de productiecode: sinds ADR-036
        OP-155 loopt `_verwijder_per_tenant` eerst `select(Tenant.id)` en daarna per klant
        een DELETE met de klantcontext aangenomen. Een mock die alleen een `rowcount`
        teruggeeft, meet die lus niet -- en gaf met een MagicMock stilzwijgend een LEGE
        klantenlijst, dus nul rondes en een test die 0 zag waar 42 werd verwacht.
        """
        sessie = AsyncMock()
        sessie.__aenter__ = AsyncMock(return_value=sessie)
        sessie.__aexit__ = AsyncMock(return_value=None)

        klantenlijst = MagicMock()
        klantenlijst.all = MagicMock(return_value=[(7,), (9,)])

        verwijderresultaat = MagicMock()
        verwijderresultaat.rowcount = rijen_per_klant

        sessie.execute = AsyncMock(
            side_effect=[klantenlijst, verwijderresultaat, verwijderresultaat]
        )
        return sessie

    @pytest.mark.asyncio
    async def test_deletes_expired_observations(self):
        """Should delete observations where expires_at is in the past, per tenant."""
        mock_session = self._sessie_met_twee_klanten(rijen_per_klant=21)

        with patch(
            "src.core.learning.worker._get_session_maker",
            return_value=MagicMock(return_value=mock_session),
        ):
            from src.core.learning.worker import _run_observation_cleanup

            result = await _run_observation_cleanup()

        # 21 per klant, twee klanten: het totaal wordt over de rondes OPGETELD.
        assert result["observations"] == 42
        # Een lezing voor de klantenlijst plus een DELETE per klant.
        assert mock_session.execute.await_count == 3
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deletes_only_expired_records(self):
        """Should only delete records where expires_at < now().

        Zelfde opzet als hierboven, met nul geraakte rijen per klant. Deze test stond tot
        2026-09-16 met een simpele mock die TOEVALLIG groen was: de klantenlijst kwam leeg
        terug, de lus draaide nul rondes, en de uitkomst was dus ook 0 -- om de verkeerde
        reden. Nu draait hij de rondes echt.
        """
        mock_session = self._sessie_met_twee_klanten(rijen_per_klant=0)

        with patch(
            "src.core.learning.worker._get_session_maker",
            return_value=MagicMock(return_value=mock_session),
        ):
            from src.core.learning.worker import _run_observation_cleanup

            result = await _run_observation_cleanup()

        assert result["observations"] == 0

    @pytest.mark.asyncio
    async def test_raises_when_database_url_is_missing(self):
        """Zonder DATABASE_URL moet de cleanup hard falen -- zie de gelijknamige test hierboven."""
        import src.core.learning.worker as worker_mod

        # Alleen DATABASE_URL weghalen, niet de HELE omgeving: `clear=True` sloopte
        # variabelen die pytest-xdist-workers nodig hebben (8 ERRORs onder -n 8,
        # "Port could not be..."), terwijl de tests los wel slaagden.
        with (
            patch.dict("os.environ", {"DATABASE_URL": ""}),
            patch.object(worker_mod, "_DATABASE_URL", None),
            patch.object(worker_mod, "_engine", None),
            patch.object(worker_mod, "_async_session_maker", None),
        ):
            from src.core.learning.worker import _run_observation_cleanup

            with pytest.raises(RuntimeError, match="DATABASE_URL"):
                await _run_observation_cleanup()


class TestCleanupExpiredObservationsActor:
    """Tests for the dramatiq actor wrapper."""

    def test_actor_is_registered(self):
        """The actor should be a valid dramatiq actor."""
        from src.core.learning.worker import cleanup_expired_observations

        assert hasattr(cleanup_expired_observations, "send")
        assert cleanup_expired_observations.options["max_retries"] == 2
        assert cleanup_expired_observations.options["time_limit"] == 120000
