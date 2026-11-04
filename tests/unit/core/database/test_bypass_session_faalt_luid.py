"""De aparte bypass-verbinding faalt LUID, nooit stil (ADR-036 OP-154).

**Waarom deze tests bestaan.** `src/core/database/bypass_session.py` belooft in zijn
docstring dat er nooit stil wordt teruggevallen op de gewone sessie. Die belofte stond bij
de eerste versie uitsluitend in proza -- er was geen enkele test die hem vastlegde, en de
Gate 2-review op 2026-09-15 heeft dat (terecht) als blocker teruggegeven.

Waarom het uitmaakt: onder de rol `sanskritisetu_app` geeft een pre-authenticatie-lookup
nul rijen ZONDER foutmelding. "Geen gebruiker gevonden" en "geen werkende verbinding" zijn
dan niet te onderscheiden, en inloggen zou stil weigeren in plaats van luid te falen. Een
volgende sessie die "even een terugval inbouwt zodat de tests niet skippen" moet hierop
stuklopen.

Deze module raakt GEEN database: alle gevallen hieronder falen voordat er een verbinding
tot stand komt. Daarom kan hij in de blokkerende poort draaien.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.core.database import bypass_session as bs


@pytest.fixture(autouse=True)
def _schone_modulestand(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Zet de moduleglobals terug, zodat de tests elkaar niet beinvloeden.

    De module houdt engine en sessionmaker op moduleniveau vast (dat is de bedoeling: een
    pool hoort gedeeld te zijn). Zonder deze fixture lekt de toestand van de ene test naar
    de andere en meet de tweede iets anders dan hij denkt.
    """
    monkeypatch.setattr(bs, "_engine", None, raising=False)
    monkeypatch.setattr(bs, "_session_maker", None, raising=False)
    monkeypatch.setattr(bs, "_slot", None, raising=False)
    yield
    bs._engine = None
    bs._session_maker = None
    bs._slot = None


def test_geen_enkele_fixture_zet_de_bypass_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vangnet: meet ik wel wat ik denk te meten?

    In dit project is een keer 1538 tests lang niets gemeten doordat een autouse-fixture
    precies de functie patchte die de assertie toetste
    (`valkuil_autouse_fixture_zet_uit_wat_je_meet`). Hier is het equivalent: zou een
    conftest ergens `BYPASS_DATABASE_URL` zetten, dan zouden de "niet geconfigureerd"-tests
    hieronder stil het verkeerde pad nemen.
    """
    monkeypatch.delenv(bs.BYPASS_DSN_ENV, raising=False)
    assert bs.bypass_is_configured() is False, (
        f"{bs.BYPASS_DSN_ENV} is gezet terwijl deze test hem net heeft weggehaald. "
        "Een fixture zet hem dus terug, en de tests hieronder meten niet wat ze beweren."
    )


class TestZonderConfiguratieBlijftAllesZoalsHetWas:
    """Zonder DSN is dit pad UIT -- dat is wat stap 1 onzichtbaar maakt voor productie."""

    def test_bypass_is_configured_is_onwaar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(bs.BYPASS_DSN_ENV, raising=False)
        assert bs.bypass_is_configured() is False

    def test_een_lege_of_witruimte_waarde_telt_als_niet_gezet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Anders zou een lege regel in een .env als 'geconfigureerd' gelden."""
        monkeypatch.setenv(bs.BYPASS_DSN_ENV, "   ")
        assert bs.bypass_is_configured() is False

    def test_initialiseren_doet_niets_en_werpt_niet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Het opstarten mag niet omvallen omdat dit pad uit staat."""
        monkeypatch.delenv(bs.BYPASS_DSN_ENV, raising=False)
        asyncio.run(bs.initialize_bypass_engine())
        assert bs._engine is None
        assert bs._session_maker is None

    def test_een_sessie_vragen_WERPT_in_plaats_van_stil_de_gewone_sessie_te_geven(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De kern van de fail-secure-belofte.

        Geeft dit ooit een sessie terug, dan is dat de GEWONE sessie, en die levert onder
        de applicatierol nul rijen op het inlogpad -- stil.
        """
        monkeypatch.delenv(bs.BYPASS_DSN_ENV, raising=False)

        async def probeer() -> None:
            async with bs.bypass_session():
                pytest.fail(
                    "bypass_session() leverde een sessie terwijl er geen aparte verbinding "
                    "is geconfigureerd. Dat is precies de stille terugval die ADR-036 "
                    "OP-154 verbiedt."
                )

        with pytest.raises(bs.BypassNietBeschikbaar):
            asyncio.run(probeer())


class TestEenKapotteConfiguratieFaaltLuid:
    def test_een_onleesbare_dsn_geeft_bypassnietbeschikbaar(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Niet de ruwe `ArgumentError` van SQLAlchemy: het contract is een eigen fout."""
        monkeypatch.setenv(bs.BYPASS_DSN_ENV, "dit-is-geen-verbindingsreeks")
        with pytest.raises(bs.BypassNietBeschikbaar):
            asyncio.run(bs.initialize_bypass_engine())
        assert bs._session_maker is None, "Na een fout mag er geen sessionmaker klaarstaan."

    def test_de_foutmelding_lekt_de_verbindingsreeks_niet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Die reeks bevat een wachtwoord; hij hoort niet in een melding of een log."""
        geheim = "sUpErGeHeIm123"
        monkeypatch.setenv(bs.BYPASS_DSN_ENV, f"kapot://gebruiker:{geheim}@host/db")
        with pytest.raises(bs.BypassNietBeschikbaar) as fout:
            asyncio.run(bs.initialize_bypass_engine())
        assert geheim not in str(fout.value)


class TestDeRolToetsLaatGeenVerkeerdeIdentiteitDoor:
    """`SELECT 1` slaagt ook op de VERKEERDE rol -- daarom toetst de module de identiteit.

    Zonder deze toets passeren de twee misconfiguraties die er echt toe doen: een DSN naar
    de eigenaar/superuser (ongelimiteerde toegang) en een DSN naar `sanskritisetu_app`
    (nul rijen, stil). Beide zijn een copy-paste van `DATABASE_URL` verwijderd.
    """

    @staticmethod
    def _verbinding(rol: str, bypassrls: bool, superuser: bool) -> Any:
        """Minimale dubbel die precies teruggeeft wat `_toets_de_rol` opvraagt."""

        class _Resultaat:
            def first(self) -> tuple[str, bool, bool]:
                return (rol, bypassrls, superuser)

        class _Verbinding:
            async def execute(self, *_: object, **__: object) -> _Resultaat:
                return _Resultaat()

        return _Verbinding()

    def test_de_echte_bypass_rol_komt_erdoor(self) -> None:
        verbinding = self._verbinding("sanskritisetu_bypass", bypassrls=True, superuser=False)
        asyncio.run(bs._toets_de_rol(verbinding))  # mag niet werpen

    def test_een_rol_zonder_bypassrls_wordt_geweigerd(self) -> None:
        """Dit is de `sanskritisetu_app`-copy-paste: hij zou nul rijen geven, stil."""
        verbinding = self._verbinding("sanskritisetu_app", bypassrls=False, superuser=False)
        with pytest.raises(bs.BypassNietBeschikbaar, match="ZONDER BYPASSRLS"):
            asyncio.run(bs._toets_de_rol(verbinding))

    def test_een_superuser_wordt_geweigerd(self) -> None:
        """Een superuser omzeilt alles; de smalle rechtenset is dan betekenisloos."""
        verbinding = self._verbinding("postgres", bypassrls=True, superuser=True)
        with pytest.raises(bs.BypassNietBeschikbaar, match="SUPERUSER"):
            asyncio.run(bs._toets_de_rol(verbinding))


class TestOpruimenIsIdempotent:
    def test_sluiten_zonder_engine_werpt_niet(self) -> None:
        asyncio.run(bs.close_bypass_engine())
        asyncio.run(bs.close_bypass_engine())
        assert bs._engine is None
        assert bs._session_maker is None


class TestPreAuthLookupKiestDeJuisteSessie:
    """`pre_auth_lookup` mag NOOIT stil iets anders opleveren dan wat de configuratie zegt."""

    def test_zonder_aparte_verbinding_krijgt_de_aanroeper_zijn_eigen_sessie(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dat is het huidige gedrag, en dat hoort ongewijzigd te blijven."""
        monkeypatch.delenv(bs.BYPASS_DSN_ENV, raising=False)
        eigen = object()

        async def probeer() -> object:
            async with bs.pre_auth_lookup(eigen) as sessie:  # type: ignore[arg-type]
                return sessie

        assert asyncio.run(probeer()) is eigen

    def test_de_tenantfilter_staat_UIT_binnen_het_blok(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Zonder de bypass geeft de fail-secure filter `WHERE false` -- ook op een
        vreemde sessie, want de hook hangt op de KLASSE `Session` met `propagate=True`.

        Deze test is de reden dat `pre_auth_lookup` de bypass zelf opent in plaats van dat
        aan de aanroeper over te laten.
        """
        from src.core.database import tenant_query_filter as tqf

        monkeypatch.delenv(bs.BYPASS_DSN_ENV, raising=False)
        binnen: list[bool] = []

        async def probeer() -> None:
            async with bs.pre_auth_lookup(object()):  # type: ignore[arg-type]
                binnen.append(tqf._bypass_tenant_filter.get())

        assert tqf._bypass_tenant_filter.get() is False, "voorwaarde: filter staat AAN"
        asyncio.run(probeer())
        assert binnen == [True], "de tenantfilter stond NIET uit binnen pre_auth_lookup"
        assert tqf._bypass_tenant_filter.get() is False, "de bypass lekt buiten het blok"


class TestAdoptTenantZetTerugWatHijVond:
    """De tenant mag NOOIT buiten het blok blijven staan.

    Het inlogpad loopt via de publieke doorlaat van de middleware, en die heeft GEEN
    opruiming aan het eind (`tenant_middleware.py:366-367`). Blijft de tenant staan, dan
    kan hij meeliften naar een volgend verzoek op dezelfde verbinding.
    """

    @staticmethod
    def _db(dialect: str = "postgresql") -> Any:
        """Minimale dubbel met een `bind.dialect.name`.

        Dat veld is niet decoratief: `adopt_tenant` zet de instelling op de transactie
        ALLEEN op PostgreSQL. SQLite kent `set_config` niet, en zonder die controle werpt
        elke unittest die dit pad raakt een OperationalError die in `login` als een 500
        naar buiten komt -- gemeten 2026-09-15.
        """

        class _Dialect:
            name = dialect

        class _Bind:
            dialect = _Dialect()

        class _Db:
            bind = _Bind()

            def __init__(self) -> None:
                self.statements: list[Any] = []

            async def execute(self, statement: Any, params: Any = None) -> None:
                self.statements.append((statement, params))

        return _Db()

    def test_binnen_het_blok_staat_de_tenant_en_erbuiten_niet(self) -> None:
        """De controle NA het blok staat BINNEN dezelfde coroutine, en dat is essentieel.

        `asyncio.run()` draait zijn coroutine in een nieuwe Task met een KOPIE van de
        context. Een ContextVar die daarbinnen wordt gezet, is buiten `asyncio.run()` per
        definitie onzichtbaar. Een eerdere versie van deze test controleerde daar, en was
        daardoor hol: het mutatiebewijs toonde op 2026-09-15 aan dat het weghalen van de
        hele terugzet-`finally` deze test GROEN liet. Meten moet dus in dezelfde context
        waarin gezet is.
        """
        from src.core.middleware.tenant_context import clear_tenant_context, get_tenant_id

        clear_tenant_context()
        db = self._db()
        waarnemingen: dict[str, int | None] = {}

        async def probeer() -> None:
            async with bs.adopt_tenant(db, 42):
                waarnemingen["binnen"] = get_tenant_id()
            waarnemingen["erna"] = get_tenant_id()

        asyncio.run(probeer())
        assert waarnemingen["binnen"] == 42
        assert waarnemingen["erna"] is None, "de tenant bleef staan NA het blok"

    def test_de_lopende_transactie_krijgt_de_tenant_ook(self) -> None:
        """Alleen de ContextVar is niet genoeg: de AL LOPENDE transactie heeft de
        listener al gehad en zou zonder dit met een lege tenant blijven draaien."""
        from src.core.middleware.tenant_context import clear_tenant_context

        clear_tenant_context()
        db = self._db()

        async def probeer() -> None:
            async with bs.adopt_tenant(db, 7):
                pass

        asyncio.run(probeer())
        assert db.statements, "er is geen set_config op de lopende transactie gedaan"
        _, params = db.statements[0]
        assert params == {"t": "7"}, f"verkeerde tenant meegegeven: {params}"

    def test_een_al_gezette_tenant_wordt_HERSTELD_en_niet_gewist(self) -> None:
        """Op een geauthenticeerd pad (`change_password`) heeft de middleware al een
        tenant gezet. Die hoort na het blok te blijven staan -- `clear_tenant_context()`
        zou hem wissen en de rest van het verzoek zonder context laten draaien."""
        from src.core.middleware.tenant_context import (
            clear_tenant_context,
            get_tenant_id,
            set_tenant_id,
        )

        set_tenant_id(9)
        db = self._db()
        hersteld: dict[str, int | None] = {}

        async def probeer() -> None:
            async with bs.adopt_tenant(db, 42):
                pass
            # Binnen dezelfde coroutine meten -- zie de toelichting hierboven.
            hersteld["waarde"] = get_tenant_id()

        try:
            asyncio.run(probeer())
            assert hersteld["waarde"] == 9, "de oorspronkelijke tenant is niet hersteld"
        finally:
            clear_tenant_context()

    def test_ook_bij_een_fout_wordt_teruggezet(self) -> None:
        """Zonder deze helft zou een 401 of een 500 de tenant laten staan."""
        from src.core.middleware.tenant_context import clear_tenant_context, get_tenant_id

        clear_tenant_context()
        db = self._db()

        async def probeer() -> None:
            async with bs.adopt_tenant(db, 42):
                raise RuntimeError("iets ging mis binnen het blok")

        na_fout: dict[str, int | None] = {}

        async def probeer_en_meet() -> None:
            try:
                await probeer()
            except RuntimeError:
                # In dezelfde coroutine meten, niet buiten `asyncio.run()`.
                na_fout["waarde"] = get_tenant_id()
                raise

        with pytest.raises(RuntimeError):
            asyncio.run(probeer_en_meet())
        assert na_fout["waarde"] is None, "na een fout bleef de tenant staan"


    def test_op_sqlite_wordt_er_GEEN_set_config_gedaan(self) -> None:
        """SQLite kent `set_config` niet. Zonder deze uitzondering werpt elke unittest die
        dit pad raakt, en in `login` wordt dat een 500 -- gemeten 2026-09-15:
        `test_failed_attempts_accumulate_on_one_record` vond nul lockout-records."""
        from src.core.middleware.tenant_context import clear_tenant_context, get_tenant_id

        clear_tenant_context()
        db = self._db(dialect="sqlite")

        async def probeer() -> None:
            async with bs.adopt_tenant(db, 7):
                # De ContextVar wordt WEL gezet: die is dialect-onafhankelijk en is op
                # SQLite het hele verhaal (geen RLS).
                assert get_tenant_id() == 7

        asyncio.run(probeer())
        assert db.statements == [], "op SQLite mag er geen set_config worden uitgevoerd"
