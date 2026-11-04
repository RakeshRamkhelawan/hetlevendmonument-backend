"""`audit_logs` heeft een leesregel per klant en houdt het schrijven open (ADR-036 OP-246, migratie 20261024_audit_leesregel).

**Wat dit meet, als NIET-eigenaar.** De sessie draait als `sanskritisetu_app` met de tenantcontext uit de ContextVar, het
pad dat een klant in productie neemt. Vooraf gemeten (stap 0, zonder policy, 6 rijen: klant A 3, klant B 2, zonder klant 1):
zonder klantcontext zag de applicatierol 6 rijen, klant A zag er 6 en klant B zag er 6.

1. **Lezen per klant.** Zonder klantcontext nul rijen; klant A ziet alleen A, klant B alleen B; de rij zonder klant is voor
   niemand zichtbaar; ook na een commit midden in het verzoek.
2. **Schrijven blijft open.** Een auditregel voor een andere klant of zonder klant lukt nog, via ruwe SQL en via de ORM
   (`AuditService.log_event`, die een `AuditLog` toevoegt). De ORM leest de sleutel niet terug via `RETURNING`
   (`implicit_returning=False`): Postgres toetst bij `RETURNING` de nieuwe rij ook tegen de leesregel.
3. **De hashketen werkt per klant.** Schrijven en verifieren onder de eigen klantcontext geeft een geldige keten; een andere
   klant ziet de rijen niet.
4. **Bijwerken en verwijderen raken alleen de eigen klant**: een UPDATE of DELETE op een rij van een andere klant raakt nul
   rijen (dit is ook wat `avg_auditlog._ANONIMISEER_ELDERS` bij het opheffen van een tenant onder de applicatierol zou
   meemaken, zie het rapport bij OP-151).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, connection as PgConnection
from sqlalchemy import text
from tests.integration.security.test_the_application_role_is_confined_to_its_tenant import (
    _SCRATCH_DB,
    _bouw_verse_database,
    _dsn,
    _postgres_bereikbaar,
)
from tests.integration.test_rls_als_niet_eigenaar import _applicatiesessie

from src.core.governance.audit import AuditService as GovernanceAuditService
from src.core.governance.hash_chain import HashChainVerifier
from src.core.governance.services.audit_service import AuditService

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

_INSERT_RAUW = (
    "INSERT INTO audit_logs (tenant_id, event_type, threat_level, client_ip, endpoint, description, "
    "event_metadata, details) VALUES (:t, 'LEESREGEL_TEST', 'low', '127.0.0.1', '/test', :d, '{}', '{}')"
)


@dataclass(frozen=True)
class Klanten:
    a: int
    b: int
    c: int
    d: int
    e: int
    f: int
    g: int


@pytest.fixture(scope="module")
def db() -> Iterator[PgConnection]:
    _bouw_verse_database()
    conn = psycopg2.connect(_dsn(_SCRATCH_DB))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def klanten(db: PgConnection) -> Klanten:
    """Vier klanten. A (3 rijen) en B (2 rijen) en een rij zonder klant voor de leestests; C en D blijven leeg voor de keten."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) VALUES "
            "('Log A', 'log-a', true, 10, 50, 5), ('Log B', 'log-b', true, 10, 50, 5), "
            "('Log C', 'log-c', true, 10, 50, 5), ('Log D', 'log-d', true, 10, 50, 5), "
            "('Log E', 'log-e', true, 10, 50, 5), ('Log F', 'log-f', true, 10, 50, 5), ('Log G', 'log-g', true, 10, 50, 5)"
        )
        cur.execute("SELECT slug, id FROM tenants WHERE slug LIKE 'log-%'")
        t = dict(cur.fetchall())
        zaad = [(t["log-a"], 3), (t["log-b"], 2), (None, 1)]
        for tenant, aantal in zaad:
            for nummer in range(aantal):
                cur.execute(
                    "INSERT INTO audit_logs (tenant_id, event_type, threat_level, client_ip, endpoint, "
                    "description, event_metadata, details) VALUES (%s, 'ZAAD', 'low', '127.0.0.1', "
                    "'/zaad', %s, '{}', '{}')",
                    (tenant, f"zaad-{tenant}-{nummer}"),
                )
    return Klanten(
        a=t["log-a"],
        b=t["log-b"],
        c=t["log-c"],
        d=t["log-d"],
        e=t["log-e"],
        f=t["log-f"],
        g=t["log-g"],
    )


def _tel(db: PgConnection, where: str, params: tuple[object, ...] = ()) -> int:
    """Telt als EIGENAAR (de eigenaar omzeilt RLS niet geforceerd): de waarheid over wat er staat."""
    with db.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM audit_logs WHERE {where}", params)  # nosec B608 - vaste tekst
        rij = cur.fetchone()
    assert rij is not None
    return int(rij[0])


async def _zichtbaar(tenant: int | None, extra: str = "") -> list[int | None]:
    """De tenant-ids van de rijen die de applicatierol onder deze klantcontext ziet."""
    async with _applicatiesessie(tenant) as sessie:
        uitkomst = await sessie.execute(text(f"SELECT tenant_id FROM audit_logs {extra}"))  # nosec B608 - vaste tekst
        return [rij[0] for rij in uitkomst.all()]


class TestLezenPerKlant:
    async def test_zonder_klantcontext_ziet_de_applicatierol_niets(self, klanten: Klanten) -> None:
        assert await _zichtbaar(None) == []

    async def test_klant_a_ziet_alleen_de_eigen_drie_rijen(self, klanten: Klanten) -> None:
        assert await _zichtbaar(klanten.a, "WHERE event_type = 'ZAAD'") == [klanten.a] * 3

    async def test_klant_b_ziet_alleen_de_eigen_twee_rijen(self, klanten: Klanten) -> None:
        assert await _zichtbaar(klanten.b, "WHERE event_type = 'ZAAD'") == [klanten.b] * 2

    async def test_de_rij_zonder_klant_is_voor_niemand_zichtbaar(self, klanten: Klanten) -> None:
        voor_a = await _zichtbaar(klanten.a, "WHERE tenant_id IS NULL")
        voor_b = await _zichtbaar(klanten.b, "WHERE tenant_id IS NULL")
        zonder = await _zichtbaar(None, "WHERE tenant_id IS NULL")

        assert (voor_a, voor_b, zonder) == ([], [], [])

    async def test_de_zaadrijen_staan_er_echt_als_eigenaar(
        self, db: PgConnection, klanten: Klanten
    ) -> None:
        """Vacuumval: een lege uitkomst hierboven telt alleen als de rijen er WEL zijn."""
        assert (
            _tel(db, "tenant_id = %s AND event_type = 'ZAAD'", (klanten.a,)),
            _tel(db, "tenant_id = %s AND event_type = 'ZAAD'", (klanten.b,)),
            _tel(db, "tenant_id IS NULL AND event_type = 'ZAAD'"),
        ) == (3, 2, 1)

    async def test_na_een_commit_midden_in_het_verzoek_blijft_de_scheiding(
        self, klanten: Klanten
    ) -> None:
        async with _applicatiesessie(klanten.a) as sessie:
            voor = (await sessie.execute(text("SELECT DISTINCT tenant_id FROM audit_logs"))).all()
            await sessie.commit()
            na = (await sessie.execute(text("SELECT DISTINCT tenant_id FROM audit_logs"))).all()

        assert ({r[0] for r in voor}, {r[0] for r in na}) == ({klanten.a}, {klanten.a})


class TestSchrijvenBlijftOpen:
    async def test_een_ruwe_regel_voor_een_andere_klant_lukt(
        self, db: PgConnection, klanten: Klanten
    ) -> None:
        marker = f"vreemd-{uuid.uuid4().hex[:8]}"
        async with _applicatiesessie(klanten.a) as sessie:
            await sessie.execute(text(_INSERT_RAUW), {"t": klanten.b, "d": marker})
            await sessie.commit()

        assert _tel(db, "description = %s AND tenant_id = %s", (marker, klanten.b)) == 1

    async def test_een_ruwe_regel_zonder_klantcontext_en_zonder_klant_lukt(
        self, db: PgConnection, klanten: Klanten
    ) -> None:
        marker = f"zonder-{uuid.uuid4().hex[:8]}"
        async with _applicatiesessie(None) as sessie:
            await sessie.execute(text(_INSERT_RAUW), {"t": None, "d": marker})
            await sessie.commit()

        assert _tel(db, "description = %s AND tenant_id IS NULL", (marker,)) == 1

    async def test_de_orm_schrijft_voor_een_andere_klant(
        self, db: PgConnection, klanten: Klanten
    ) -> None:
        """`log_event` voegt een `AuditLog` toe; zonder `implicit_returning=False` faalt dit onder de leesregel."""
        marker = f"orm-vreemd-{uuid.uuid4().hex[:8]}"
        async with _applicatiesessie(klanten.a) as sessie:
            gelukt = await AuditService.log_event(
                db=sessie,
                event_type="LEESREGEL_TEST",
                severity="low",
                source_ip="127.0.0.1",
                endpoint="/test",
                description=marker,
                tenant_id=klanten.b,
            )
            await sessie.commit()

        assert (gelukt, _tel(db, "description = %s AND tenant_id = %s", (marker, klanten.b))) == (
            True,
            1,
        )

    async def test_de_orm_schrijft_zonder_klantcontext_en_zonder_klant(
        self, db: PgConnection, klanten: Klanten
    ) -> None:
        marker = f"orm-zonder-{uuid.uuid4().hex[:8]}"
        async with _applicatiesessie(None) as sessie:
            gelukt = await AuditService.log_event(
                db=sessie,
                event_type="LEESREGEL_TEST",
                severity="low",
                source_ip="127.0.0.1",
                endpoint="/test",
                description=marker,
                tenant_id=None,
            )
            await sessie.commit()

        assert (gelukt, _tel(db, "description = %s AND tenant_id IS NULL", (marker,))) == (True, 1)


class TestBijwerkenEnVerwijderenRakenDeEigenKlant:
    async def test_een_update_op_een_rij_van_een_andere_klant_raakt_niets(
        self, db: PgConnection, klanten: Klanten
    ) -> None:
        async with _applicatiesessie(klanten.a) as sessie:
            resultaat = await sessie.execute(
                text("UPDATE audit_logs SET description = 'gewijzigd' WHERE tenant_id = :t"),
                {"t": klanten.b},
            )
            await sessie.commit()
            geraakt = resultaat.rowcount

        assert (geraakt, _tel(db, "description = 'gewijzigd'")) == (0, 0)

    async def test_een_delete_op_een_rij_van_een_andere_klant_raakt_niets(
        self, db: PgConnection, klanten: Klanten
    ) -> None:
        voor = _tel(db, "tenant_id = %s", (klanten.b,))
        async with _applicatiesessie(klanten.a) as sessie:
            resultaat = await sessie.execute(
                text("DELETE FROM audit_logs WHERE tenant_id = :t"), {"t": klanten.b}
            )
            await sessie.commit()
            geraakt = resultaat.rowcount

        assert (geraakt, _tel(db, "tenant_id = %s", (klanten.b,)), voor > 0) == (0, voor, True)


class TestDeHashketenWerktPerKlant:
    async def _schrijf(self, tenant: int, aantal: int) -> None:
        async with _applicatiesessie(tenant) as sessie:
            for nummer in range(aantal):
                gelukt = await AuditService.log_event(
                    db=sessie,
                    event_type="KETEN_TEST",
                    severity="low",
                    source_ip="127.0.0.1",
                    endpoint="/keten",
                    description=f"keten-{tenant}-{nummer}",
                    tenant_id=tenant,
                )
                assert gelukt is True
                await sessie.commit()

    async def test_schrijven_en_verifieren_onder_de_eigen_klantcontext(
        self, klanten: Klanten
    ) -> None:
        await self._schrijf(klanten.c, 3)
        async with _applicatiesessie(klanten.c) as sessie:
            uitkomst = await HashChainVerifier(db_session=sessie).verify_chain(tenant_id=klanten.c)

        assert (uitkomst.is_valid, uitkomst.total_entries) == (True, 3)

    async def test_een_andere_klant_ziet_de_rijen_van_deze_keten_niet(
        self, klanten: Klanten
    ) -> None:
        await self._schrijf(klanten.d, 2)
        async with _applicatiesessie(klanten.d) as sessie:
            eigen = await HashChainVerifier(db_session=sessie).verify_chain(tenant_id=klanten.d)
            vreemd = await HashChainVerifier(db_session=sessie).verify_chain(tenant_id=klanten.c)

        assert (eigen.total_entries, vreemd.total_entries) == (2, 0)


def _keten(db: PgConnection, tenant: int) -> list[tuple[int, str | None, str | None]]:
    """(id, previous_hash, audit_hash) van een klant, als eigenaar, op volgorde van schrijven."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, previous_hash, audit_hash FROM audit_logs WHERE tenant_id = %s ORDER BY id",
            (tenant,),
        )
        return [(int(r[0]), r[1], r[2]) for r in cur.fetchall()]


def _is_een_aaneengesloten_keten(rijen: list[tuple[int, str | None, str | None]]) -> bool:
    """Elke rij heeft een hash en wijst naar de hash van de vorige; de eerste wijst nergens naar."""
    if not rijen or any(r[2] is None for r in rijen):
        return False
    return rijen[0][1] is None and all(rijen[i][1] == rijen[i - 1][2] for i in range(1, len(rijen)))


class TestDeKetenBijEenAndereKlantcontext:
    """Gate 2 F1: de ketenlookup draait onder de context van de klant VOOR WIE geschreven wordt.

    Zonder dat ziet de lookup onder de leesregel de keten van die klant niet en wordt elke regel
    `previous_hash = NULL`, terwijl `log_event` toch True geeft.
    """

    async def _schrijf_event(self, context: int | None, voor: int | None, aantal: int) -> None:
        async with _applicatiesessie(context) as sessie:
            for nummer in range(aantal):
                gelukt = await AuditService.log_event(
                    db=sessie,
                    event_type="KRUIS_TEST",
                    severity="low",
                    source_ip="127.0.0.1",
                    endpoint="/kruis",
                    description=f"kruis-{voor}-{nummer}",
                    tenant_id=voor,
                )
                assert gelukt is True
                await sessie.commit()

    async def test_log_event_onder_de_context_van_een_andere_klant(
        self, db: PgConnection, klanten: Klanten
    ) -> None:
        await self._schrijf_event(klanten.a, klanten.e, 3)
        async with _applicatiesessie(klanten.e) as sessie:
            uitkomst = await HashChainVerifier(db_session=sessie).verify_chain(tenant_id=klanten.e)

        assert (
            _is_een_aaneengesloten_keten(_keten(db, klanten.e)),
            uitkomst.is_valid,
            uitkomst.total_entries,
        ) == (
            True,
            True,
            3,
        )

    async def test_log_event_zonder_klantcontext(self, db: PgConnection, klanten: Klanten) -> None:
        await self._schrijf_event(None, klanten.f, 3)
        async with _applicatiesessie(klanten.f) as sessie:
            uitkomst = await HashChainVerifier(db_session=sessie).verify_chain(tenant_id=klanten.f)

        assert (
            _is_een_aaneengesloten_keten(_keten(db, klanten.f)),
            uitkomst.is_valid,
            uitkomst.total_entries,
        ) == (
            True,
            True,
            3,
        )

    async def test_log_action_onder_de_context_van_een_andere_klant(
        self, db: PgConnection, klanten: Klanten
    ) -> None:
        async with _applicatiesessie(klanten.a) as sessie:
            for nummer in range(3):
                regel = await GovernanceAuditService.log_action(
                    tenant_id=klanten.g, action="KRUIS", resource=f"kruis:{nummer}", session=sessie
                )
                assert regel is not None
                await sessie.commit()
        async with _applicatiesessie(klanten.g) as sessie:
            uitkomst = await HashChainVerifier(db_session=sessie).verify_chain(tenant_id=klanten.g)

        assert (
            _is_een_aaneengesloten_keten(_keten(db, klanten.g)),
            uitkomst.is_valid,
            uitkomst.total_entries,
        ) == (
            True,
            True,
            3,
        )

    async def test_de_eigen_context_van_de_schrijver_is_na_afloop_teruggezet(
        self, klanten: Klanten
    ) -> None:
        async with _applicatiesessie(klanten.a) as sessie:
            await AuditService.log_event(
                db=sessie,
                event_type="KRUIS_TEST",
                severity="low",
                source_ip="127.0.0.1",
                endpoint="/kruis",
                description="herstel",
                tenant_id=klanten.e,
            )
            nu = (
                await sessie.execute(text("SELECT current_setting('app.current_tenant', true)"))
            ).scalar_one()

        assert nu == str(klanten.a)

    async def test_een_regel_zonder_klant_hoort_in_geen_keten(
        self, db: PgConnection, klanten: Klanten
    ) -> None:
        """Gemeten: `log_event` ketent alleen als er een klant is; een regel zonder klant is bewust ongeketend."""
        marker = f"geenketen-{uuid.uuid4().hex[:8]}"
        async with _applicatiesessie(None) as sessie:
            await AuditService.log_event(
                db=sessie,
                event_type="KRUIS_TEST",
                severity="low",
                source_ip="127.0.0.1",
                endpoint="/kruis",
                description=marker,
                tenant_id=None,
            )
            await sessie.commit()
        with db.cursor() as cur:
            cur.execute(
                "SELECT audit_hash, previous_hash FROM audit_logs WHERE description = %s", (marker,)
            )
            rij = cur.fetchone()

        assert rij == (None, None)
