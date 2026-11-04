"""Startcontrole: de applicatie weigert te starten met een databaserol die RLS omzeilt (brief 2026-10-21).

Row Level Security beschermt pas als de applicatie NIET als eigenaar van de tabellen, als superuser of met
BYPASSRLS verbindt (ADR-036 OP-151). Zonder deze controle merkt niemand een verkeerde `DATABASE_URL`: elke test
en elke pagina werkt, en de scheiding tussen klanten rust stilletjes alleen nog op de applicatiecode.

In productie en staging is dat een weigering om te starten (fail-closed); in ontwikkeling een waarschuwing. In
`single_tenant` (een klant, een installatie) is er geen andere klant om te lekken: daar een waarschuwing.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.database.applicatierol_controle import (
    ApplicatieRolFout,
    RolMeting,
    controleer_applicatierol,
    meet_rol,
)

GOEDE_ROL = RolMeting(
    rol="sanskritisetu_app", rolsuper=False, heeft_bypassrls=False, eigen_rls_tabellen=0
)


def _conn(meting: RolMeting, dialect: str = "postgresql") -> MagicMock:
    """Een async verbinding die precies een meetrij teruggeeft."""
    resultaat = MagicMock()
    resultaat.first.return_value = (
        meting.rol,
        meting.rolsuper,
        meting.heeft_bypassrls,
        meting.eigen_rls_tabellen,
    )
    conn = MagicMock()
    conn.dialect.name = dialect
    conn.execute = AsyncMock(return_value=resultaat)
    return conn


@pytest.mark.asyncio
class TestDeMeting:
    async def test_de_rij_uit_postgresql_wordt_een_rolmeting(self) -> None:
        eigenaar = RolMeting("postgres", True, True, 180)

        assert await meet_rol(_conn(eigenaar)) == eigenaar


@pytest.mark.asyncio
class TestWeigeringInProductieEnStaging:
    @pytest.mark.parametrize("omgeving", ["production", "staging"])
    async def test_de_eigenaar_van_de_tabellen_weigert_te_starten(self, omgeving: str) -> None:
        meting = RolMeting("migratie", False, False, 180)

        with pytest.raises(ApplicatieRolFout, match="eigenaar"):
            await controleer_applicatierol(_conn(meting), omgeving=omgeving, single_tenant=False)

    @pytest.mark.parametrize("omgeving", ["production", "staging"])
    async def test_een_superuser_weigert_te_starten(self, omgeving: str) -> None:
        meting = RolMeting("postgres", True, True, 0)

        with pytest.raises(ApplicatieRolFout, match="superuser"):
            await controleer_applicatierol(_conn(meting), omgeving=omgeving, single_tenant=False)

    @pytest.mark.parametrize("omgeving", ["production", "staging"])
    async def test_bypassrls_weigert_te_starten(self, omgeving: str) -> None:
        meting = RolMeting("beheer", False, True, 0)

        with pytest.raises(ApplicatieRolFout, match="BYPASSRLS"):
            await controleer_applicatierol(_conn(meting), omgeving=omgeving, single_tenant=False)

    @pytest.mark.parametrize("omgeving", ["prod", "live", "uat", "", " production ", "PRODUCTION"])
    async def test_een_onbekende_of_verkeerd_gespelde_omgeving_is_streng(
        self, omgeving: str
    ) -> None:
        meting = RolMeting("postgres", True, True, 180)

        with pytest.raises(ApplicatieRolFout):
            await controleer_applicatierol(_conn(meting), omgeving=omgeving, single_tenant=False)

    @pytest.mark.parametrize("omgeving", ["production", "staging", "development"])
    async def test_de_goede_rol_start_overal(self, omgeving: str) -> None:
        await controleer_applicatierol(_conn(GOEDE_ROL), omgeving=omgeving, single_tenant=False)

    async def test_de_melding_noemt_alle_problemen_en_de_rol(self) -> None:
        meting = RolMeting("postgres", True, True, 180)

        with pytest.raises(ApplicatieRolFout) as fout:
            await controleer_applicatierol(
                _conn(meting), omgeving="production", single_tenant=False
            )

        tekst = str(fout.value)
        assert all(woord in tekst for woord in ("eigenaar", "superuser", "BYPASSRLS", "postgres"))


@pytest.mark.asyncio
class TestWaarschuwingZonderWeigering:
    async def test_in_ontwikkeling_is_het_een_waarschuwing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        meting = RolMeting("postgres", True, True, 180)

        with caplog.at_level(logging.WARNING):
            await controleer_applicatierol(
                _conn(meting), omgeving="development", single_tenant=False
            )

        assert "RLS" in caplog.text

    async def test_in_single_tenant_is_het_een_waarschuwing_ook_in_productie(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        meting = RolMeting("postgres", True, True, 180)

        with caplog.at_level(logging.WARNING):
            await controleer_applicatierol(_conn(meting), omgeving="production", single_tenant=True)

        assert "RLS" in caplog.text

    async def test_single_tenant_in_productie_meldt_op_critical_niveau(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        meting = RolMeting("postgres", True, True, 180)

        with caplog.at_level(logging.WARNING):
            await controleer_applicatierol(_conn(meting), omgeving="production", single_tenant=True)

        assert [r.levelno for r in caplog.records if "single_tenant" in r.getMessage()] == [
            logging.CRITICAL
        ]

    @pytest.mark.parametrize("omgeving", ["development", "dev", "local", "test", "testing"])
    async def test_de_zachte_omgevingen_waarschuwen_alleen(self, omgeving: str) -> None:
        await controleer_applicatierol(
            _conn(RolMeting("postgres", True, True, 180)), omgeving=omgeving, single_tenant=False
        )

    async def test_sqlite_kent_geen_rollen_en_wordt_overgeslagen(self) -> None:
        conn = _conn(RolMeting("x", True, True, 1), dialect="sqlite")

        await controleer_applicatierol(conn, omgeving="production", single_tenant=False)

        conn.execute.assert_not_awaited()


class _Engine:
    """Een engine waarvan `connect()` een async contextmanager met een vaste verbinding is."""

    def __init__(self, conn: MagicMock) -> None:
        self._conn = conn

    def connect(self) -> "_Engine":
        return self

    async def __aenter__(self) -> MagicMock:
        return self._conn

    async def __aexit__(self, *_rest: object) -> None:
        return None


@pytest.mark.asyncio
class TestDeOpstartWeigertDeApplicatie:
    """`app_lifespan._init_database` is de plek waar de controle echt de start tegenhoudt."""

    def _opstart(self, monkeypatch: pytest.MonkeyPatch, meting: RolMeting, omgeving: str) -> object:
        import src.config as config
        from src.core import app_lifespan

        monkeypatch.setattr(app_lifespan, "initialize_database", AsyncMock(return_value=True))
        monkeypatch.setattr(app_lifespan.db_manager, "engine", _Engine(_conn(meting)))
        monkeypatch.setattr(app_lifespan, "ENVIRONMENT", omgeving)
        monkeypatch.setattr(config, "DEPLOYMENT_MODE", "saas")
        return app_lifespan._init_database()

    async def test_productie_met_een_eigenaarsrol_start_niet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gestart = await self._opstart(
            monkeypatch, RolMeting("postgres", True, True, 180), "production"
        )  # type: ignore[misc]

        assert gestart is False

    async def test_staging_met_een_eigenaarsrol_start_niet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gestart = await self._opstart(
            monkeypatch, RolMeting("migratie", False, False, 180), "staging"
        )  # type: ignore[misc]

        assert gestart is False

    async def test_productie_met_de_applicatierol_start_wel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gestart = await self._opstart(monkeypatch, GOEDE_ROL, "production")  # type: ignore[misc]

        assert gestart is True

    async def test_zonder_databaseverbinding_start_de_applicatie_niet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.config as config
        from src.core import app_lifespan

        monkeypatch.setattr(app_lifespan, "initialize_database", AsyncMock(return_value=True))
        monkeypatch.setattr(app_lifespan.db_manager, "engine", None)
        monkeypatch.setattr(app_lifespan, "ENVIRONMENT", "development")
        monkeypatch.setattr(config, "DEPLOYMENT_MODE", "saas")

        assert await app_lifespan._init_database() is False

    async def test_ontwikkeling_met_een_eigenaarsrol_start_wel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gestart = await self._opstart(
            monkeypatch, RolMeting("postgres", True, True, 180), "development"
        )  # type: ignore[misc]

        assert gestart is True
