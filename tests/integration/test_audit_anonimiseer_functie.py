"""Het wissen van een klant onder de applicatierol, met de smalle anonimiseerfunctie (Gate 2 F2, ADR-036 OP-246).

`audit_logs_anonimiseer_gebruikers` (migratie 20261025_audit_anonimiseer_functie) is de enige weg waarlangs de wissende klant
personen in auditregels van een ANDERE klant of zonder klant kan anonimiseren. Zonder die weg raakt de oude UPDATE onder de
leesregel 0 rijen en faalt `DELETE FROM users` op `audit_logs_user_id_fkey` (de hele wissing draait terug, 500).

Gemeten als `sanskritisetu_app`: de volledige keten anonimiseren en de gebruikers verwijderen slaagt, ook als een persoon in
een auditregel van een andere klant of zonder klant staat; de persoonsvelden daar zijn daarna leeg en de hashvelden ongewijzigd;
een klant kan via de functie geen gebruikers van een andere klant anonimiseren; de bypass-rol heeft geen `EXECUTE`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, connection as PgConnection
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.integration.security.test_the_application_role_is_confined_to_its_tenant import (
    _SCRATCH_DB,
    _bouw_verse_database,
    _dsn,
    _postgres_bereikbaar,
)
from tests.integration.test_rls_als_niet_eigenaar import _applicatiesessie

from src.core.governance import avg_auditlog
from src.core.governance.avg_auditlog import anonimiseer_auditlog_van_tenant

pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    # De verse database uit de hele migratieketen kost minuten; de standaardgrens is daar te krap voor.
    pytest.mark.timeout(900),
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op de netwerkpoort uit SANSKRITISETU_TEST_DATABASE_URL",
    ),
]

_HASHVELDEN = "tenant_id, action, resource, timestamp, audit_hash, previous_hash"
_PERSOON = "user_id, client_ip, description, details::text, event_metadata::text"


@dataclass(frozen=True)
class Opstelling:
    x: int
    y: int
    z: int
    gebruiker_x: int
    gebruiker_y: int
    gebruiker_z: int
    regel_bij_y: int
    regel_zonder_klant: int
    regel_van_y_zelf: int
    hitl_regel: int


@pytest.fixture(scope="module")
def db() -> Iterator[PgConnection]:
    _bouw_verse_database()
    conn = psycopg2.connect(_dsn(_SCRATCH_DB))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    yield conn
    conn.close()


def _nieuw(cur: psycopg2.extensions.cursor) -> int:
    rij = cur.fetchone()
    assert rij is not None
    return int(rij[0])


def _regel(
    cur: psycopg2.extensions.cursor, tenant: int | None, user: int | None, resource: str
) -> int:
    cur.execute(
        "INSERT INTO audit_logs (tenant_id, user_id, action, resource, event_type, threat_level, client_ip, "
        "endpoint, description, event_metadata, details, audit_hash, previous_hash) VALUES "
        "(%s, %s, 'ACTIE', %s, 'FUNCTIE_TEST', 'low', '203.0.113.9', '/x', 'Triggered by jan@example.com', "
        '\'{"user_agent": "Firefox"}\', \'{"email": "jan@example.com"}\', %s, NULL) RETURNING id',
        (tenant, user, resource, uuid.uuid4().hex),
    )
    return _nieuw(cur)


@pytest.fixture(scope="module")
def opstelling(db: PgConnection) -> Opstelling:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) VALUES "
            "('Wis X', 'wis-x', true, 10, 50, 5), ('Wis Y', 'wis-y', true, 10, 50, 5), "
            "('Wis Z', 'wis-z', true, 10, 50, 5)"
        )
        cur.execute("SELECT slug, id FROM tenants WHERE slug IN ('wis-x', 'wis-y', 'wis-z')")
        t = dict(cur.fetchall())
        gebruikers = {}
        for slug in ("wis-x", "wis-y", "wis-z"):
            cur.execute(
                "INSERT INTO users (tenant_id, email) VALUES (%s, %s) RETURNING id",
                (t[slug], f"{uuid.uuid4().hex[:8]}@wis.example.com"),
            )
            gebruikers[slug] = _nieuw(cur)
        return Opstelling(
            x=t["wis-x"],
            y=t["wis-y"],
            z=t["wis-z"],
            gebruiker_x=gebruikers["wis-x"],
            gebruiker_y=gebruikers["wis-y"],
            gebruiker_z=gebruikers["wis-z"],
            regel_bij_y=_regel(cur, t["wis-y"], gebruikers["wis-x"], "doel:1"),
            regel_zonder_klant=_regel(cur, None, gebruikers["wis-x"], "doel:2"),
            regel_van_y_zelf=_regel(cur, t["wis-y"], gebruikers["wis-y"], "doel:3"),
            hitl_regel=_regel(cur, t["wis-y"], gebruikers["wis-z"], "hitl_ticket:77"),
        )


def _rij(db: PgConnection, kolommen: str, regel: int) -> tuple[object, ...]:
    with db.cursor() as cur:
        cur.execute(f"SELECT {kolommen} FROM audit_logs WHERE id = %s", (regel,))  # nosec B608 - vaste tekst
        rij = cur.fetchone()
    assert rij is not None
    return tuple(rij)


async def _roep_functie(context: int | None, tenant: int, gebruikers: list[int]) -> int:
    async with _applicatiesessie(context) as sessie:
        uitkomst = await sessie.execute(
            text("SELECT audit_logs_anonimiseer_gebruikers(:t, CAST(:g AS integer[]))"),
            {"t": tenant, "g": gebruikers},
        )
        await sessie.commit()
        return int(uitkomst.scalar_one())


class TestDeFunctieWeigertWatNietVanDeKlantIs:
    """Een klant kan via de functie geen gebruikers van een andere klant anonimiseren."""

    async def test_een_andere_klant_als_tenant_wordt_geweigerd(
        self, opstelling: Opstelling
    ) -> None:
        with pytest.raises(DBAPIError, match="alleen de klant zelf"):
            await _roep_functie(opstelling.y, opstelling.x, [opstelling.gebruiker_x])

    async def test_zonder_klantcontext_wordt_geweigerd(self, opstelling: Opstelling) -> None:
        with pytest.raises(DBAPIError, match="alleen de klant zelf"):
            await _roep_functie(None, opstelling.x, [opstelling.gebruiker_x])

    async def test_gebruikers_van_een_andere_klant_worden_geweigerd(
        self, opstelling: Opstelling
    ) -> None:
        with pytest.raises(DBAPIError, match="horen niet allemaal bij deze klant"):
            await _roep_functie(opstelling.x, opstelling.x, [opstelling.gebruiker_y])

    async def test_een_gemengde_lijst_wordt_helemaal_geweigerd(
        self, db: PgConnection, opstelling: Opstelling
    ) -> None:
        voor = _rij(db, _PERSOON, opstelling.regel_bij_y)
        with pytest.raises(DBAPIError, match="horen niet allemaal bij deze klant"):
            await _roep_functie(
                opstelling.x, opstelling.x, [opstelling.gebruiker_x, opstelling.gebruiker_y]
            )

        assert _rij(db, _PERSOON, opstelling.regel_bij_y) == voor

    async def test_de_bypass_rol_en_publiek_hebben_geen_execute(self, db: PgConnection) -> None:
        with db.cursor() as cur:
            cur.execute(
                "SELECT has_function_privilege('sanskritisetu_bypass', "
                "'audit_logs_anonimiseer_gebruikers(integer, integer[])', 'EXECUTE'), "
                "has_function_privilege('sanskritisetu_app', "
                "'audit_logs_anonimiseer_gebruikers(integer, integer[])', 'EXECUTE')"
            )
            rij = cur.fetchone()

        assert rij == (False, True)


class TestDeVolledigeWissingOnderDeApplicatierol:
    async def test_anonimiseren_en_gebruikers_verwijderen_slaagt(
        self, db: PgConnection, opstelling: Opstelling
    ) -> None:
        async with _applicatiesessie(opstelling.x) as sessie:
            await anonimiseer_auditlog_van_tenant(sessie, opstelling.x)
            await sessie.execute(
                text("DELETE FROM users WHERE tenant_id = :t"), {"t": opstelling.x}
            )
            await sessie.commit()
        with db.cursor() as cur:
            cur.execute("SELECT count(*) FROM users WHERE tenant_id = %s", (opstelling.x,))
            rij = cur.fetchone()

        assert rij == (0,)

    async def test_de_persoonsvelden_in_regels_van_een_andere_klant_zijn_leeg(
        self, db: PgConnection, opstelling: Opstelling
    ) -> None:
        for regel in (opstelling.regel_bij_y, opstelling.regel_zonder_klant):
            kolommen = _rij(db, _PERSOON, regel)
            assert kolommen[:3] == (None, "geanonimiseerd", "ACTIE")
            assert "jan@example.com" not in str(kolommen) and "Firefox" not in str(kolommen)

    async def test_de_hashvelden_zijn_niet_geraakt(
        self, db: PgConnection, opstelling: Opstelling
    ) -> None:
        with db.cursor() as cur:
            cur.execute(
                f"SELECT {_HASHVELDEN} FROM audit_logs WHERE id = %s", (opstelling.regel_bij_y,)
            )  # nosec B608
            rij = cur.fetchone()

        assert (
            rij is not None
            and (rij[0], rij[1], rij[2]) == (opstelling.y, "ACTIE", "doel:1")
            and rij[3] is not None
        )

    async def test_regels_van_een_andere_gebruiker_blijven_staan(
        self, db: PgConnection, opstelling: Opstelling
    ) -> None:
        eigen = _rij(db, "user_id, client_ip", opstelling.regel_van_y_zelf)

        assert eigen == (opstelling.gebruiker_y, "203.0.113.9")


class TestHitlRegelsBlijvenBuitenSchot:
    async def test_een_hitl_gebonden_regel_wordt_niet_geanonimiseerd(
        self, db: PgConnection, opstelling: Opstelling
    ) -> None:
        geraakt = await _roep_functie(opstelling.z, opstelling.z, [opstelling.gebruiker_z])

        assert (geraakt, _rij(db, "user_id", opstelling.hitl_regel)) == (
            0,
            (opstelling.gebruiker_z,),
        )


def _gebruikers(monkeypatch: pytest.MonkeyPatch, gebruiker: int) -> None:
    """Laat `anonimiseer_auditlog_van_tenant` met een vaste gebruiker door de functie lopen (RLS op users kan hem verbergen)."""
    monkeypatch.setattr(avg_auditlog, "_EIGEN_GEBRUIKERS", text(f"SELECT {int(gebruiker)}"))  # nosec B608


# Een stand-in voor de directe UPDATE die luid faalt: komt een test hier uit, dan viel de code ten onrechte terug.
_TERUGVAL_FAALT = text("SELECT CAST('terugval gebruikt' AS integer)")
_TERUGVAL_MERKT = text("SELECT set_config('test.terugval', 'ja', true)")
_FUNCTIE_WEG = text(
    "SELECT audit_logs_anonimiseer_gebruikers_bestaat_niet(:tenant_id, CAST(:gebruikers AS integer[]))"
)


class TestDeTerugvalIsSmal:
    """Gate 2 G2F-1: alleen een ONTBREKENDE functie (42883) in een testomgeving valt terug; weigeringen gaan omhoog."""

    async def test_een_weigering_van_de_functie_komt_als_fout_door(
        self, opstelling: Opstelling, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _gebruikers(monkeypatch, opstelling.gebruiker_x)
        monkeypatch.setattr(avg_auditlog, "_ANONIMISEER_ELDERS_DIRECT", _TERUGVAL_FAALT)

        with pytest.raises(DBAPIError, match="alleen de klant zelf"):
            async with _applicatiesessie(opstelling.y) as sessie:
                await anonimiseer_auditlog_van_tenant(sessie, opstelling.x)

    async def test_null_voor_de_klant_komt_als_fout_door(
        self, opstelling: Opstelling, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _gebruikers(monkeypatch, opstelling.gebruiker_x)
        monkeypatch.setattr(avg_auditlog, "_ANONIMISEER_ELDERS_DIRECT", _TERUGVAL_FAALT)

        with pytest.raises(DBAPIError, match="tenant en gebruikers zijn verplicht"):
            async with _applicatiesessie(opstelling.x) as sessie:
                await anonimiseer_auditlog_van_tenant(sessie, None)  # type: ignore[arg-type]

    async def test_een_ontbrekende_functie_in_de_testomgeving_gebruikt_de_terugval(
        self, opstelling: Opstelling, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "test")
        _gebruikers(monkeypatch, opstelling.gebruiker_x)
        monkeypatch.setattr(avg_auditlog, "_ANONIMISEER_ELDERS", _FUNCTIE_WEG)
        monkeypatch.setattr(avg_auditlog, "_ANONIMISEER_ELDERS_DIRECT", _TERUGVAL_MERKT)

        async with _applicatiesessie(opstelling.x) as sessie:
            await anonimiseer_auditlog_van_tenant(sessie, opstelling.x)
            merk = (
                await sessie.execute(text("SELECT current_setting('test.terugval', true)"))
            ).scalar_one()

        assert merk == "ja"

    @pytest.mark.parametrize("omgeving", ["production", "staging", "blue", ""])
    async def test_een_ontbrekende_functie_buiten_de_testomgeving_is_een_luide_fout(
        self, opstelling: Opstelling, monkeypatch: pytest.MonkeyPatch, omgeving: str
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", omgeving)
        _gebruikers(monkeypatch, opstelling.gebruiker_x)
        monkeypatch.setattr(avg_auditlog, "_ANONIMISEER_ELDERS", _FUNCTIE_WEG)
        monkeypatch.setattr(avg_auditlog, "_ANONIMISEER_ELDERS_DIRECT", _TERUGVAL_MERKT)

        with pytest.raises(
            RuntimeError, match="migratie 20261025_audit_anonimiseer_functie ontbreekt"
        ):
            async with _applicatiesessie(opstelling.x) as sessie:
                await anonimiseer_auditlog_van_tenant(sessie, opstelling.x)
