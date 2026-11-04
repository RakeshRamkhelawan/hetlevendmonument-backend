"""Een klantbeheerder raakt de platformrol niet aan, en een nieuw wachtwoord beeindigt oude sessies (2026-10-17).

Brief: docs/agent-briefs/generated/2026-10-17-sprint-dag-platformrol-en-sessies-na-herstel.md (bevindingen
1 en 3 uit Gate 2 van 2026-10-16).

Deel 1, de platformrol `system_admin` ontnemen. Uitdelen was sinds 33f1c78b dicht (`assign_role`); ontnemen
niet: een tenantbeheerder kon een platformbeheerder zijn rol afnemen via `revoke-role`, de bulkroute en door
weglating in `PUT /users/{id}`. Dezelfde regel als uitdelen: wie de rol zelf niet heeft, kan hem niet
toekennen EN niet ontnemen.

Deel 2, sessies na een nieuw wachtwoord. Gemeten vooraf: na een reset of een wijziging bleven al uitgegeven
toegangs- en verversingstokens werken. De blacklist (`token_blacklist`) kent alleen losse tokens op `jti`;
`revoke_all_user_tokens` zoekt Redis-sleutels met een patroon dat nooit bestond en trok dus niets in.

Echte app, echte JWT's, echte Postgres. Alleen `aiosmtplib.send` is vervangen (de mail met de herstellink).
"""

from __future__ import annotations

import asyncio
import re

import pytest
from httpx import AsyncClient, Response

from tests.integration.security._voordeur_hulp import (  # noqa: F401
    WACHTWOORD,
    bearer,
    client,
    een_waarde,
    limiters_leeg,
    registreer,
    rijen,
    unieke_email,
    voer_uit,
)
from tests.unit.debiteuren._smtp_dubbel import SmtpDubbel, installeer_smtp_dubbel, zet_testmailbox

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PLATFORMROL = "system_admin"
NIEUW = "NieuwGekozen#Wachtwoord9"  # nosec B105 - testwaarde


@pytest.fixture(autouse=True)
def _verse_redis_verbinding():  # type: ignore[no-untyped-def]
    """Een eigen Redis-verbinding per test (een pool uit een vorige test hangt aan een gesloten loop)."""
    from src.core.database.redis import reset_redis_pool

    reset_redis_pool()
    yield
    reset_redis_pool()


@pytest.fixture(autouse=True)
def mailbox(monkeypatch: pytest.MonkeyPatch) -> SmtpDubbel:
    zet_testmailbox(monkeypatch)
    return installeer_smtp_dubbel(monkeypatch)


# ---------------------------------------------------------------------------
# opstelling
# ---------------------------------------------------------------------------


async def _inloggen(
    client: AsyncClient, email: str, wachtwoord: str = WACHTWOORD
) -> dict[str, str]:
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": wachtwoord})
    assert r.status_code == 200, f"inloggen als {email} gaf {r.status_code}: {r.text}"
    return {
        "access_token": str(r.json()["access_token"]),
        "refresh_token": str(r.json()["refresh_token"]),
    }


async def _met_csrf(client: AsyncClient, access_token: str) -> dict[str, str]:
    kop = bearer(access_token)
    csrf = await client.get("/api/v1/auth/csrf-token", headers=kop)
    assert csrf.status_code == 200, csrf.text
    return {**kop, "X-CSRF-Token": str(csrf.json()["csrf_token"])}


async def _klant(client: AsyncClient) -> tuple[str, int, int]:
    """Een nieuwe klant met zijn beheerder: (e-mail, tenant, gebruikers-id). De platformrol bestaat als RIJ."""
    email = unieke_email("beheer")
    aangemeld = await registreer(client, email)
    assert aangemeld.status_code in (200, 201), aangemeld.text
    tenant = int(een_waarde("SELECT tenant_id FROM users WHERE email = :e", e=email))
    voer_uit(
        "INSERT INTO roles (name, tenant_id, is_active) VALUES (:n, :t, true)",
        n=PLATFORMROL,
        t=tenant,
    )
    return email, tenant, int(een_waarde("SELECT id FROM users WHERE email = :e", e=email))


def _geef_rol(email: str, tenant: int, rol: str) -> None:
    voer_uit(
        "INSERT INTO user_roles (user_id, role_id, tenant_id) "
        "SELECT u.id, r.id, :t FROM users u, roles r "
        "WHERE u.email = :e AND r.name = :n AND r.tenant_id = :t",
        e=email,
        n=rol,
        t=tenant,
    )


def _maak_gebruiker(email: str, tenant: int) -> int:
    voer_uit(
        "INSERT INTO users (email, hashed_password, is_active, is_superuser, tenant_id) "
        "VALUES (:e, 'x', true, false, :t)",
        e=email,
        t=tenant,
    )
    return int(een_waarde("SELECT id FROM users WHERE email = :e", e=email))


def _rollen_van(gebruiker_id: int) -> set[str]:
    return {
        r[0]
        for r in rijen(
            "SELECT r.name FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE ur.user_id = :u",
            u=gebruiker_id,
        )
    }


def _rol_id(tenant: int, naam: str) -> int:
    return int(
        een_waarde("SELECT id FROM roles WHERE name = :n AND tenant_id = :t", n=naam, t=tenant)
    )


async def _platform_opstelling(client: AsyncClient) -> dict[str, object]:
    """Een gewone tenantbeheerder (ingelogd) en een platformbeheerder (met de rol) in dezelfde tenant."""
    email, tenant, beheerder_id = await _klant(client)
    platform_email = unieke_email("platform")
    platform_id = _maak_gebruiker(platform_email, tenant)
    _geef_rol(platform_email, tenant, PLATFORMROL)
    tokens = await _inloggen(client, email)
    return {
        "kop": await _met_csrf(client, tokens["access_token"]),
        "email": email,
        "tenant": tenant,
        "beheerder_id": beheerder_id,
        "platform_id": platform_id,
    }


# ---------------------------------------------------------------------------
# deel 1: de platformrol ontnemen
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestEenKlantbeheerderOntneemtDePlatformrolNiet:
    async def test_revoke_role_geeft_403_en_de_rol_blijft(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)

        antwoord = await client.post(
            "/api/rbac/users/revoke-role",
            json={"user_id": o["platform_id"], "role_name": PLATFORMROL},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert PLATFORMROL in _rollen_van(int(o["platform_id"]))  # type: ignore[arg-type]

    async def test_de_bulkroute_geeft_403_en_de_rol_blijft(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)

        antwoord = await client.post(
            "/api/rbac/users/revoke-role/bulk",
            json={"user_ids": [o["platform_id"]], "role_name": PLATFORMROL},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert PLATFORMROL in _rollen_van(int(o["platform_id"]))  # type: ignore[arg-type]

    async def test_een_put_die_de_rol_weglaat_geeft_403_en_de_rol_blijft(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        gebruiker_rol = _rol_id(int(o["tenant"]), "user")  # type: ignore[arg-type]

        antwoord = await client.put(
            f"/api/v1/users/{o['platform_id']}",
            json={"role_ids": [gebruiker_rol]},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _rollen_van(int(o["platform_id"])) == {PLATFORMROL}  # type: ignore[arg-type]

    async def test_een_put_met_een_lege_set_geeft_403_en_de_platformrol_blijft(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)

        antwoord = await client.put(
            f"/api/v1/users/{o['platform_id']}",
            json={"role_ids": []},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _rollen_van(int(o["platform_id"])) == {PLATFORMROL}  # type: ignore[arg-type]

    async def test_een_gewone_rol_ontnemen_blijft_werken(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)
        medewerker = unieke_email("medewerker")
        medewerker_id = _maak_gebruiker(medewerker, int(o["tenant"]))  # type: ignore[arg-type]
        _geef_rol(medewerker, int(o["tenant"]), "editor")  # type: ignore[arg-type]

        antwoord = await client.post(
            "/api/rbac/users/revoke-role",
            json={"user_id": medewerker_id, "role_name": "editor"},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 200, antwoord.text
        assert "editor" not in _rollen_van(medewerker_id)

    async def test_een_put_zonder_platformrol_in_de_set_verandert_gewone_rollen_wel(
        self, client: AsyncClient
    ) -> None:
        """De regel beschermt ALLEEN de platformrol; de rest van de set wordt gewoon vervangen."""
        o = await _platform_opstelling(client)
        medewerker = unieke_email("medewerker")
        medewerker_id = _maak_gebruiker(medewerker, int(o["tenant"]))  # type: ignore[arg-type]
        _geef_rol(medewerker, int(o["tenant"]), "editor")  # type: ignore[arg-type]

        antwoord = await client.put(
            f"/api/v1/users/{medewerker_id}",
            json={"role_ids": [_rol_id(int(o["tenant"]), "user")]},  # type: ignore[arg-type]
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 200, antwoord.text
        assert _rollen_van(medewerker_id) == {"user"}


@pytest.mark.integration
class TestEenHouderVanDePlatformrolMagHemWelOntnemen:
    async def test_revoke_role_door_een_houder_werkt(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)
        _geef_rol(str(o["email"]), int(o["tenant"]), PLATFORMROL)  # type: ignore[arg-type]
        tokens = await _inloggen(client, str(o["email"]))
        kop = await _met_csrf(client, tokens["access_token"])

        antwoord = await client.post(
            "/api/rbac/users/revoke-role",
            json={"user_id": o["platform_id"], "role_name": PLATFORMROL},
            headers=kop,
        )

        assert antwoord.status_code == 200, antwoord.text
        assert PLATFORMROL not in _rollen_van(int(o["platform_id"]))  # type: ignore[arg-type]

    async def test_een_put_door_een_houder_mag_de_rol_wel_weglaten(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        _geef_rol(str(o["email"]), int(o["tenant"]), PLATFORMROL)  # type: ignore[arg-type]
        tokens = await _inloggen(client, str(o["email"]))
        kop = await _met_csrf(client, tokens["access_token"])

        antwoord = await client.put(
            f"/api/v1/users/{o['platform_id']}",
            json={"role_ids": [_rol_id(int(o["tenant"]), "user")]},  # type: ignore[arg-type]
            headers=kop,
        )

        assert antwoord.status_code == 200, antwoord.text
        assert _rollen_van(int(o["platform_id"])) == {"user"}  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# deel 1b: een platformbeheerder uitzetten, verwijderen of laten wissen
# ---------------------------------------------------------------------------


def _is_actief(gebruiker_id: int) -> bool:
    return bool(een_waarde("SELECT is_active FROM users WHERE id = :u", u=gebruiker_id))


def _weigeringen(actor_id: int) -> int:
    return int(
        een_waarde(
            "SELECT count(*) FROM audit_logs WHERE event_type = 'platform_user_disable_refused' "
            "AND user_id = :u",
            u=actor_id,
        )
    )


@pytest.mark.integration
class TestEenKlantbeheerderZetEenPlatformbeheerderNietUit:
    """Gate 2 (H2): uitzetten, verwijderen en laten wissen zijn dezelfde ontneming als de rol afnemen.
    De regel staat in de dienst (`mag_gebruiker_uitschakelen`); de drie routes erven hem."""

    async def test_uitzetten_via_put_geeft_403_en_de_gebruiker_blijft_actief(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)

        antwoord = await client.put(
            f"/api/v1/users/{o['platform_id']}",
            json={"is_active": False},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _is_actief(int(o["platform_id"]))  # type: ignore[arg-type]

    async def test_verwijderen_geeft_403_en_de_gebruiker_blijft_actief(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)

        antwoord = await client.delete(
            f"/api/v1/users/{o['platform_id']}",
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _is_actief(int(o["platform_id"]))  # type: ignore[arg-type]

    async def test_laten_wissen_geeft_403_en_de_gebruiker_blijft_actief(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)

        antwoord = await client.post(
            f"/api/gdpr/users/{o['platform_id']}/erase",
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _is_actief(int(o["platform_id"]))  # type: ignore[arg-type]

    async def test_de_weigering_is_in_het_nederlands(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)

        antwoord = await client.delete(
            f"/api/v1/users/{o['platform_id']}",
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert "platformbeheerder" in antwoord.text, antwoord.text
        assert "alleen" in antwoord.text.lower(), antwoord.text

    async def test_de_weigering_laat_een_auditregel_achter(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)

        await client.delete(
            f"/api/v1/users/{o['platform_id']}",
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert _weigeringen(int(o["beheerder_id"])) == 1  # type: ignore[arg-type]

    async def test_een_geweigerde_put_legt_geen_halve_wijziging_vast(
        self, client: AsyncClient
    ) -> None:
        """Gate 2 (B1): `update_user` zette het e-mailadres VOOR de controle; de commit die de auditregel
        bewaart legde die wijziging vast terwijl de aanvrager een 403 kreeg."""
        o = await _platform_opstelling(client)
        voor = een_waarde("SELECT email FROM users WHERE id = :u", u=o["platform_id"])

        antwoord = await client.put(
            f"/api/v1/users/{o['platform_id']}",
            json={"email": unieke_email("aanvaller"), "is_active": False},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert een_waarde("SELECT email FROM users WHERE id = :u", u=o["platform_id"]) == voor
        assert _is_actief(int(o["platform_id"]))  # type: ignore[arg-type]

    async def test_een_geweigerde_uitnodiging_met_de_platformrol_laat_een_auditregel_achter(
        self, client: AsyncClient
    ) -> None:
        """Dezelfde valkuil bij de eerdere weigering (31c506fb): flush zonder commit voor de 403 en de
        auditregel verdwijnt met de teruggedraaide transactie."""
        o = await _platform_opstelling(client)

        antwoord = await client.post(
            "/api/v1/admin/create_user",
            json={"email": unieke_email("nieuw"), "role": PLATFORMROL},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert (
            int(
                een_waarde(
                    "SELECT count(*) FROM audit_logs WHERE event_type = 'ADMIN_USER_CREATE_REFUSED' "
                    "AND user_id = :u",
                    u=o["beheerder_id"],
                )
            )
            == 1
        )

    async def test_een_gewone_gebruiker_van_de_eigen_tenant_blijft_uit_te_zetten(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        tenant = int(o["tenant"])  # type: ignore[arg-type]
        uit_put = _maak_gebruiker(unieke_email("medewerker"), tenant)
        uit_delete = _maak_gebruiker(unieke_email("medewerker"), tenant)
        uit_erase = _maak_gebruiker(unieke_email("medewerker"), tenant)
        kop = o["kop"]  # type: ignore[assignment]

        via_put = await client.put(
            f"/api/v1/users/{uit_put}", json={"is_active": False}, headers=kop
        )  # type: ignore[arg-type]
        via_delete = await client.delete(f"/api/v1/users/{uit_delete}", headers=kop)  # type: ignore[arg-type]
        via_erase = await client.post(f"/api/gdpr/users/{uit_erase}/erase", headers=kop)  # type: ignore[arg-type]

        assert (via_put.status_code, via_delete.status_code, via_erase.status_code) == (
            200,
            204,
            200,
        ), (via_put.text, via_delete.text, via_erase.text)
        assert not _is_actief(uit_put) and not _is_actief(uit_delete) and not _is_actief(uit_erase)


@pytest.mark.integration
class TestEenHouderVanDePlatformrolMagEenPlatformbeheerderWelUitzetten:
    async def test_uitzetten_verwijderen_en_laten_wissen_werken_voor_een_houder(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        tenant = int(o["tenant"])  # type: ignore[arg-type]
        _geef_rol(str(o["email"]), tenant, PLATFORMROL)
        tokens = await _inloggen(client, str(o["email"]))
        kop = await _met_csrf(client, tokens["access_token"])
        ander_put = _maak_gebruiker(unieke_email("platform"), tenant)
        ander_delete = _maak_gebruiker(unieke_email("platform"), tenant)
        ander_erase = _maak_gebruiker(unieke_email("platform"), tenant)
        for gebruiker_id in (ander_put, ander_delete, ander_erase):
            voer_uit(
                "INSERT INTO user_roles (user_id, role_id, tenant_id) "
                "SELECT :u, r.id, :t FROM roles r WHERE r.name = :n AND r.tenant_id = :t",
                u=gebruiker_id,
                n=PLATFORMROL,
                t=tenant,
            )

        via_put = await client.put(
            f"/api/v1/users/{ander_put}", json={"is_active": False}, headers=kop
        )
        via_delete = await client.delete(f"/api/v1/users/{ander_delete}", headers=kop)
        via_erase = await client.post(f"/api/gdpr/users/{ander_erase}/erase", headers=kop)

        assert (via_put.status_code, via_delete.status_code, via_erase.status_code) == (
            200,
            204,
            200,
        ), (via_put.text, via_delete.text, via_erase.text)


# ---------------------------------------------------------------------------
# deel 2: sessies na een reset of een wijziging
# ---------------------------------------------------------------------------


async def _reset(client: AsyncClient, mailbox: SmtpDubbel, email: str, nieuw: str = NIEUW) -> None:
    aantal = len(mailbox.ontvangen)
    gevraagd = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert gevraagd.status_code == 200, gevraagd.text
    assert len(mailbox.ontvangen) == aantal + 1, "er is geen herstelmail verstuurd"
    token = re.search(r"/reset-password\?token=([\w\-]+)", mailbox.ontvangen[-1].alle_delen)
    assert token, mailbox.ontvangen[-1].alle_delen[:300]
    gekozen = await client.post(
        "/api/v1/auth/reset-password", json={"token": token.group(1), "new_password": nieuw}
    )
    assert gekozen.status_code == 200, gekozen.text


def _auditregels(event_type: str, gebruiker_id: int) -> int:
    """Auditregels van dit type voor deze gebruiker waarin de intrekking van alle sessies staat."""
    return int(
        een_waarde(
            "SELECT count(*) FROM audit_logs WHERE event_type = :e AND user_id = :u "
            "AND CAST(event_metadata AS text) LIKE '%sessions_revoked%'",
            e=event_type,
            u=gebruiker_id,
        )
    )


async def _me(client: AsyncClient, access_token: str) -> Response:
    return await client.get("/api/v1/auth/me", headers=bearer(access_token))


async def _ververs(client: AsyncClient, refresh_token: str) -> Response:
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})


@pytest.mark.integration
class TestNaEenResetZijnOudeSessiesWeg:
    async def test_het_oude_toegangstoken_werkt_voor_de_reset(self, client: AsyncClient) -> None:
        """Controle op de opstelling: zonder reset blijft het token gewoon werken."""
        email, _tenant, _ = await _klant(client)
        oud = await _inloggen(client, email)

        assert (await _me(client, oud["access_token"])).status_code == 200

    async def test_het_oude_toegangstoken_geeft_401_na_een_reset(
        self, client: AsyncClient, mailbox: SmtpDubbel
    ) -> None:
        email, _tenant, _ = await _klant(client)
        oud = await _inloggen(client, email)

        await _reset(client, mailbox, email)

        assert (await _me(client, oud["access_token"])).status_code == 401

    async def test_het_oude_verversingstoken_werkt_niet_meer_na_een_reset(
        self, client: AsyncClient, mailbox: SmtpDubbel
    ) -> None:
        email, _tenant, _ = await _klant(client)
        oud = await _inloggen(client, email)

        await _reset(client, mailbox, email)

        assert (await _ververs(client, oud["refresh_token"])).status_code == 401

    async def test_het_nieuwe_wachtwoord_geeft_een_werkend_token_en_verversingstoken(
        self, client: AsyncClient, mailbox: SmtpDubbel
    ) -> None:
        email, _tenant, _ = await _klant(client)
        await _inloggen(client, email)
        await _reset(client, mailbox, email)
        # Tokens dragen `iat` in hele seconden: een token uit dezelfde seconde als de reset telt als oud
        # (gesloten kant). Een mens logt niet binnen een seconde na het kiezen in; de test wacht dus.
        await asyncio.sleep(1.1)

        nieuw = await _inloggen(client, email, NIEUW)

        assert (await _me(client, nieuw["access_token"])).status_code == 200
        assert (await _ververs(client, nieuw["refresh_token"])).status_code == 200

    async def test_de_reset_laat_een_auditregel_achter_met_de_intrekking(
        self, client: AsyncClient, mailbox: SmtpDubbel
    ) -> None:
        email, _tenant, gebruiker_id = await _klant(client)

        await _reset(client, mailbox, email)

        assert _auditregels("PASSWORD_RESET_COMPLETED", gebruiker_id) == 1

    async def test_het_oude_wachtwoord_werkt_niet_meer(
        self, client: AsyncClient, mailbox: SmtpDubbel
    ) -> None:
        email, _tenant, _ = await _klant(client)
        await _reset(client, mailbox, email)

        r = await client.post(
            "/api/v1/auth/login", data={"username": email, "password": WACHTWOORD}
        )

        assert r.status_code == 401, r.text

    async def test_de_sessie_van_een_ander_blijft_staan(
        self, client: AsyncClient, mailbox: SmtpDubbel
    ) -> None:
        email, _tenant, _ = await _klant(client)
        ander_email, _t2, _ = await _klant(client)
        ander = await _inloggen(client, ander_email)

        await _reset(client, mailbox, email)

        assert (await _me(client, ander["access_token"])).status_code == 200
        assert (await _ververs(client, ander["refresh_token"])).status_code == 200


@pytest.mark.integration
class TestNaEenWijzigingZijnOudeSessiesWeg:
    async def _wijzig(self, client: AsyncClient, email: str) -> dict[str, str]:
        oud = await _inloggen(client, email)
        kop = await _met_csrf(client, oud["access_token"])
        antwoord = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": WACHTWOORD, "new_password": NIEUW},
            headers=kop,
        )
        assert antwoord.status_code == 200, antwoord.text
        return oud

    async def test_het_oude_toegangstoken_geeft_401_na_een_wijziging(
        self, client: AsyncClient
    ) -> None:
        email, _tenant, _ = await _klant(client)

        oud = await self._wijzig(client, email)

        assert (await _me(client, oud["access_token"])).status_code == 401

    async def test_het_oude_verversingstoken_werkt_niet_meer_na_een_wijziging(
        self, client: AsyncClient
    ) -> None:
        email, _tenant, _ = await _klant(client)

        oud = await self._wijzig(client, email)

        assert (await _ververs(client, oud["refresh_token"])).status_code == 401

    async def test_de_wijziging_laat_een_auditregel_achter_met_de_intrekking(
        self, client: AsyncClient
    ) -> None:
        email, _tenant, gebruiker_id = await _klant(client)

        await self._wijzig(client, email)

        assert _auditregels("PASSWORD_CHANGED", gebruiker_id) == 1

    async def test_het_nieuwe_wachtwoord_geeft_een_werkend_token(self, client: AsyncClient) -> None:
        email, _tenant, _ = await _klant(client)
        await self._wijzig(client, email)
        await asyncio.sleep(1.1)

        nieuw = await _inloggen(client, email, NIEUW)

        assert (await _me(client, nieuw["access_token"])).status_code == 200


@pytest.mark.integration
class TestDeOverigeWebSocketIngangenWeigerenOudeTokensOok:
    """Gate 2 (2026-10-18): alleen `get_current_user_ws` (de copilot) las de grens; `WebSocketAuthenticator`
    en de andere ingangen (terminal, workflowbouwer, sync, canvas, ...) stellen allemaal EEN vraag:
    `token_mag_op_een_websocket`. Daar hoort de intrekking dus te staan, zodat elke ingang haar erft."""

    class _NepSocket:
        def __init__(self, token: str) -> None:
            self.cookies: dict[str, str] = {"access_token": token}
            self.headers: dict[str, str] = {}
            self.query_params: dict[str, str] = {}
            self.sluitcodes: list[int] = []

        async def close(self, code: int = 1000, reason: str = "") -> None:
            self.sluitcodes.append(code)

        async def accept(self) -> None:
            return None

    async def test_de_gedeelde_vraag_weigert_een_oud_token_en_laat_een_nieuw_toe(
        self,
        client: AsyncClient,
        mailbox: SmtpDubbel,
        postgres_session,  # type: ignore[no-untyped-def]
    ) -> None:
        from src.core.auth.jwt_handler import jwt_handler
        from src.core.auth.websocket_auth import token_mag_op_een_websocket

        email, _tenant, _ = await _klant(client)
        oud = await _inloggen(client, email)
        await _reset(client, mailbox, email)
        await asyncio.sleep(1.1)
        nieuw = await _inloggen(client, email, NIEUW)

        oud_payload = jwt_handler.verify_token(oud["access_token"])
        nieuw_payload = jwt_handler.verify_token(nieuw["access_token"])

        assert oud_payload and nieuw_payload
        assert await token_mag_op_een_websocket(oud_payload) is False  # type: ignore[arg-type]
        assert await token_mag_op_een_websocket(nieuw_payload) is True  # type: ignore[arg-type]

    async def test_de_authenticator_sluit_een_oud_token_af(
        self,
        client: AsyncClient,
        mailbox: SmtpDubbel,
        postgres_session,  # type: ignore[no-untyped-def]
    ) -> None:
        from src.core.auth.websocket_auth import WebSocketAuthenticator

        email, _tenant, _ = await _klant(client)
        oud = await _inloggen(client, email)
        await _reset(client, mailbox, email)
        socket = self._NepSocket(oud["access_token"])

        gebruiker = await WebSocketAuthenticator().authenticate_connected_user(socket)  # type: ignore[arg-type]

        assert gebruiker is None
        assert socket.sluitcodes == [4005]

    async def test_een_ingetrokken_jti_wordt_ook_op_een_websocket_geweigerd(
        self,
        client: AsyncClient,
        postgres_session,  # type: ignore[no-untyped-def]
    ) -> None:
        """De losse intrekking (uitloggen) stond ook niet op deze ingangen; dezelfde vraag dekt beide."""
        from src.core.auth.jwt_handler import jwt_handler
        from src.core.auth.websocket_auth import token_mag_op_een_websocket

        email, _tenant, _ = await _klant(client)
        tokens = await _inloggen(client, email)
        kop = await _met_csrf(client, tokens["access_token"])
        uitgelogd = await client.post("/api/v1/auth/logout", headers=kop)
        assert uitgelogd.status_code == 200, uitgelogd.text

        payload = jwt_handler.verify_token(tokens["access_token"])

        assert payload
        assert await token_mag_op_een_websocket(payload) is False  # type: ignore[arg-type]


@pytest.mark.integration
class TestDeIntrekkingsvraagFaaltGesloten:
    async def test_een_onbereikbare_database_geeft_ingetrokken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.auth import account_status

        class _KapotteMaker:
            def __call__(self) -> object:
                raise OSError("database weg")

        monkeypatch.setattr(account_status, "_sessiemaker", lambda: _KapotteMaker())

        assert await account_status.token_is_ingetrokken({"sub": "7", "jti": "x", "iat": 1}) is True

    async def test_een_token_zonder_jti_geeft_ingetrokken(self) -> None:
        from src.core.auth.account_status import token_is_ingetrokken

        assert await token_is_ingetrokken({"sub": "7", "iat": 1}) is True


@pytest.mark.integration
class TestDeGrensRijOverleeftHetLangstLevendeToken:
    """Gate 2 (2026-10-18): `create_refresh_token` zet `exp` altijd op 7 dagen, wat de configuratie ook zegt;
    de grensrij mag dus niet korter leven dan 7 dagen."""

    async def test_de_grensrij_verloopt_niet_voor_het_verversingstoken(
        self, client: AsyncClient, mailbox: SmtpDubbel, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.auth.oauth2_service import oauth2_service

        # Een configuratie van MINDER dan 7 dagen: het verversingstoken leeft toch 7 dagen (jwt_handler).
        monkeypatch.setattr(oauth2_service, "refresh_token_expire_days", 1)
        email, _tenant, gebruiker_id = await _klant(client)
        await _reset(client, mailbox, email)

        verloopt_over_seconden = float(
            een_waarde(
                "SELECT extract(epoch FROM (expires_at - now())) FROM token_blacklist "
                "WHERE user_id = :u AND jti LIKE 'user-all:%'",
                u=gebruiker_id,
            )
        )

        assert verloopt_over_seconden > 7 * 24 * 3600 - 120


@pytest.mark.integration
class TestOokDeWebSocketIngangWeigertOudeTokens:
    """`get_current_user_ws` deelt `_get_user_from_token` met de HTTP-ingang: een deur, dezelfde regel."""

    class _NepSocket:
        def __init__(self, token: str) -> None:
            self.cookies: dict[str, str] = {}
            self.headers: dict[str, str] = {"authorization": f"Bearer {token}"}

    async def test_een_oud_token_wordt_geweigerd_en_een_nieuw_toegelaten(
        self,
        client: AsyncClient,
        mailbox: SmtpDubbel,
        postgres_session,  # type: ignore[no-untyped-def]
    ) -> None:
        from fastapi import HTTPException

        from src.core.auth.dependencies import get_current_user_ws

        email, _tenant, _ = await _klant(client)
        oud = await _inloggen(client, email)
        await _reset(client, mailbox, email)
        await asyncio.sleep(1.1)
        nieuw = await _inloggen(client, email, NIEUW)

        with pytest.raises(HTTPException) as fout:
            await get_current_user_ws(self._NepSocket(oud["access_token"]), db=postgres_session)  # type: ignore[arg-type]
        gebruiker = await get_current_user_ws(
            self._NepSocket(nieuw["access_token"]),
            db=postgres_session,  # type: ignore[arg-type]
        )

        assert fout.value.status_code == 401
        assert gebruiker.email == email
