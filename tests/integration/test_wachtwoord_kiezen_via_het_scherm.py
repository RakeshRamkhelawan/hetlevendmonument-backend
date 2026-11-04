"""Een medewerker kiest zijn wachtwoord via het scherm; een beheerder kan geen platformrol uitdelen (2026-10-16).

Brief: docs/agent-briefs/generated/2026-10-16-sprint-dag-wachtwoord-kiezen-via-het-scherm.md.

Stap 0: de rolkeuze bij uitnodigen toonde `system_admin`. `system_admin` is een platformrol
(`RESERVED_ROLE_NAMES`); twee endpoints laten er cross-tenant toegang op volgen. Een klant mag de rol
niet AANMAKEN (422), maar de rij bestaat in de tenant van het platform (geseed), en de routes die rollen
uitdelen controleerden alleen dat de rol bestaat.

Wat gemeten wordt (echte app, echte JWT's, echte Postgres; de rol wordt als rij gezet zoals de seed dat
doet, de rest loopt over de echte routes):

(a) een beheerder zonder die rol krijgt 403 bij uitnodigen met `system_admin`, en er ontstaat geen gebruiker;
(b) idem bij `assign-role` (de andere deur die de rolkeuze in het scherm gebruikt);
(c) de rollenlijst toont de platformrol alleen aan wie hem zelf heeft;
(d) tegenrichting: een houder van de platformrol mag hem wel uitdelen, en gewone rollen blijven werken.
"""

from __future__ import annotations

import re

import pytest
from httpx import AsyncClient, Response

from tests.integration.security._voordeur_hulp import (  # noqa: F401
    WACHTWOORD,
    bearer,
    client,
    een_waarde,
    limiters_leeg,
    log_in,
    registreer,
    unieke_email,
    voer_uit,
)
from tests.unit.debiteuren._smtp_dubbel import SmtpDubbel, installeer_smtp_dubbel, zet_testmailbox

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PLATFORMROL = "system_admin"


@pytest.fixture(autouse=True)
def _verse_redis_verbinding():  # type: ignore[no-untyped-def]
    """Een eigen Redis-verbinding per test (een pool uit een vorige test hangt aan een gesloten loop)."""
    from src.core.database.redis import reset_redis_pool

    reset_redis_pool()
    yield
    reset_redis_pool()


@pytest.fixture(autouse=True)
def mailbox(monkeypatch: pytest.MonkeyPatch) -> SmtpDubbel:
    """Geen echte mail: de brieven komen in dit dubbel terecht."""
    zet_testmailbox(monkeypatch)
    return installeer_smtp_dubbel(monkeypatch)


async def _beheerder(client: AsyncClient) -> tuple[dict[str, str], int, str]:
    """Een nieuwe klant met zijn beheerder, echt ingelogd, met de platformrol als RIJ in zijn tenant."""
    email = unieke_email("beheer")
    aangemeld = await registreer(client, email)
    assert aangemeld.status_code in (200, 201), aangemeld.text
    kop = bearer(await log_in(client, email))
    ik = await client.get("/api/v1/auth/me", headers=kop)
    assert ik.status_code == 200, ik.text
    csrf = await client.get("/api/v1/auth/csrf-token", headers=kop)
    assert csrf.status_code == 200, csrf.text
    tenant = int(ik.json()["tenant_id"])
    # Zoals de seed van het platform: de rij bestaat, de beheerder heeft hem NIET.
    voer_uit(
        "INSERT INTO roles (name, tenant_id, is_active) VALUES (:n, :t, true)",
        n=PLATFORMROL,
        t=tenant,
    )
    return {**kop, "X-CSRF-Token": str(csrf.json()["csrf_token"])}, tenant, email


def _geef_de_platformrol(email: str, tenant: int) -> None:
    voer_uit(
        "INSERT INTO user_roles (user_id, role_id, tenant_id) "
        "SELECT u.id, r.id, :t FROM users u, roles r "
        "WHERE u.email = :e AND r.name = :n AND r.tenant_id = :t",
        e=email,
        n=PLATFORMROL,
        t=tenant,
    )


def _aantal_gebruikers(email: str) -> int:
    return int(een_waarde("SELECT count(*) FROM users WHERE email = :e", e=email))


async def _nodig_uit(client: AsyncClient, kop: dict[str, str], email: str, rol: str) -> Response:
    return await client.post(
        "/api/v1/admin/create_user", json={"email": email, "role": rol}, headers=kop
    )


@pytest.mark.integration
class TestEenBeheerderDeeltGeenPlatformrolUit:
    async def test_uitnodigen_met_de_platformrol_geeft_403(self, client: AsyncClient) -> None:
        kop, _tenant, _ = await _beheerder(client)

        antwoord = await _nodig_uit(client, kop, unieke_email("nieuw"), PLATFORMROL)

        assert antwoord.status_code == 403, antwoord.text

    async def test_er_ontstaat_dan_geen_gebruiker(self, client: AsyncClient) -> None:
        kop, _tenant, _ = await _beheerder(client)
        medewerker = unieke_email("nieuw")

        await _nodig_uit(client, kop, medewerker, PLATFORMROL)

        assert _aantal_gebruikers(medewerker) == 0

    async def test_assign_role_met_de_platformrol_geeft_403(self, client: AsyncClient) -> None:
        kop, _tenant, _ = await _beheerder(client)
        medewerker = unieke_email("nieuw")
        gemaakt = await _nodig_uit(client, kop, medewerker, "user")
        assert gemaakt.status_code == 201, gemaakt.text
        gebruiker_id = int(een_waarde("SELECT id FROM users WHERE email = :e", e=medewerker))

        antwoord = await client.post(
            "/api/rbac/users/assign-role",
            json={"user_id": gebruiker_id, "role_name": PLATFORMROL},
            headers=kop,
        )

        assert antwoord.status_code == 403, antwoord.text

    async def test_de_rollenlijst_toont_de_platformrol_niet_aan_een_gewone_beheerder(
        self, client: AsyncClient
    ) -> None:
        kop, _tenant, _ = await _beheerder(client)

        antwoord = await client.get("/api/rbac/roles", headers=kop)

        assert antwoord.status_code == 200, antwoord.text
        namen = {r["name"] for r in antwoord.json()}
        assert PLATFORMROL not in namen
        assert {"admin", "user"} <= namen

    async def test_een_gewone_rol_uitdelen_blijft_werken(self, client: AsyncClient) -> None:
        kop, _tenant, _ = await _beheerder(client)

        antwoord = await _nodig_uit(client, kop, unieke_email("nieuw"), "editor")

        assert antwoord.status_code == 201, antwoord.text


async def _uitgenodigde_met_token(client: AsyncClient, mailbox: SmtpDubbel) -> tuple[str, str]:
    """Een beheerder nodigt een medewerker uit; terug komt (e-mailadres, token uit de mail)."""
    kop, _, _ = await _beheerder(client)
    medewerker = unieke_email("nieuw")
    gemaakt = await _nodig_uit(client, kop, medewerker, "user")
    assert gemaakt.status_code == 201, gemaakt.text
    assert mailbox.ontvangen, "er is geen mail verstuurd"
    gevonden = re.search(r"/reset-password\?token=([\w\-]+)", mailbox.ontvangen[-1].alle_delen)
    assert gevonden, mailbox.ontvangen[-1].alle_delen[:300]
    return medewerker, gevonden.group(1)


async def _kies(client: AsyncClient, token: str, wachtwoord: str) -> Response:
    return await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": wachtwoord}
    )


async def _log_in_met(client: AsyncClient, email: str, wachtwoord: str) -> Response:
    return await client.post("/api/v1/auth/login", data={"username": email, "password": wachtwoord})


@pytest.mark.integration
class TestWatJeMagKiezenKanJeGebruiken:
    """Een bron voor kiezen, herstellen en inloggen (brief, besluit 4).

    Gemeten vooraf: kiezen met `#` gaf 200, inloggen daarna 400 "password contains invalid
    characters": de inlogroute hield het wachtwoord tegen een SQL-injectielijst (`#`, `'`, `--`, `=`
    gevolgd door `'` of `;`), terwijl een wachtwoord nooit in een query komt maar alleen gehasht wordt
    vergeleken. En herstellen kende alleen een minimumlengte, geen sterkteregels.
    """

    @pytest.mark.parametrize(
        "wachtwoord",
        [
            "Gekozen#Wachtwoord9",
            "Gekozen'Wachtwoord9",
            "Gekozen--Wachtwoord9",
            "Gekozen=Wachtwoord9;x",
        ],
    )
    async def test_een_gekozen_teken_kan_je_ook_gebruiken_om_in_te_loggen(
        self, client: AsyncClient, mailbox: SmtpDubbel, wachtwoord: str
    ) -> None:
        medewerker, token = await _uitgenodigde_met_token(client, mailbox)

        gekozen = await _kies(client, token, wachtwoord)
        ingelogd = await _log_in_met(client, medewerker, wachtwoord)

        assert gekozen.status_code == 200, gekozen.text
        assert ingelogd.status_code == 200, ingelogd.text

    async def test_een_fout_wachtwoord_met_zo_n_teken_is_gewoon_401(
        self, client: AsyncClient, mailbox: SmtpDubbel
    ) -> None:
        medewerker, token = await _uitgenodigde_met_token(client, mailbox)
        await _kies(client, token, "Gekozen#Wachtwoord9")

        ingelogd = await _log_in_met(client, medewerker, "Fout#Wachtwoord9")

        assert ingelogd.status_code == 401, ingelogd.text

    async def test_een_te_zwak_wachtwoord_wordt_bij_kiezen_geweigerd(
        self, client: AsyncClient, mailbox: SmtpDubbel
    ) -> None:
        _medewerker, token = await _uitgenodigde_met_token(client, mailbox)

        antwoord = await _kies(client, token, "allemaalkleineletters")

        assert antwoord.status_code == 422, antwoord.text

    @pytest.mark.parametrize(
        "wachtwoord",
        [
            "Kort1a",  # te kort
            "allemaalkleiner9",  # geen hoofdletter, wel een cijfer
            "ALLEMAALGROOT9",  # geen kleine letter, wel een cijfer
            "GeenCijferHierWel",  # geen cijfer
            "GekozenéWachtwoord9",  # een accent
        ],
    )
    async def test_elke_regel_wordt_apart_afgedwongen_bij_kiezen(
        self, client: AsyncClient, mailbox: SmtpDubbel, wachtwoord: str
    ) -> None:
        _medewerker, token = await _uitgenodigde_met_token(client, mailbox)

        antwoord = await _kies(client, token, wachtwoord)

        assert antwoord.status_code == 422, antwoord.text

    async def test_na_een_geweigerd_wachtwoord_werkt_dezelfde_link_nog(
        self, client: AsyncClient, mailbox: SmtpDubbel
    ) -> None:
        medewerker, token = await _uitgenodigde_met_token(client, mailbox)
        await _kies(client, token, "allemaalkleineletters")

        opnieuw = await _kies(client, token, "Gekozen#Wachtwoord9")

        assert opnieuw.status_code == 200, opnieuw.text

    async def test_een_speciaal_teken_is_geen_eis(
        self, client: AsyncClient, mailbox: SmtpDubbel
    ) -> None:
        medewerker, token = await _uitgenodigde_met_token(client, mailbox)

        gekozen = await _kies(client, token, "GewoonEenWachtwoord9")
        ingelogd = await _log_in_met(client, medewerker, "GewoonEenWachtwoord9")

        assert gekozen.status_code == 200, gekozen.text
        assert ingelogd.status_code == 200, ingelogd.text

    async def test_wijzigen_weigert_een_te_zwak_wachtwoord(self, client: AsyncClient) -> None:
        kop, _tenant, _ = await _beheerder(client)

        antwoord = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": WACHTWOORD, "new_password": "allemaalkleineletters"},
            headers=kop,
        )

        assert antwoord.status_code == 422, antwoord.text

    async def test_na_wijzigen_met_een_teken_kan_je_inloggen(self, client: AsyncClient) -> None:
        kop, _tenant, email = await _beheerder(client)

        gewijzigd = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": WACHTWOORD, "new_password": "Gewijzigd#Wachtwoord9"},
            headers=kop,
        )
        ingelogd = await _log_in_met(client, email, "Gewijzigd#Wachtwoord9")

        assert gewijzigd.status_code == 200, gewijzigd.text
        assert ingelogd.status_code == 200, ingelogd.text

    @pytest.mark.parametrize("wachtwoord", ["GekozenéWachtwoord9", "Aa1" + "b" * 200])
    async def test_ook_de_beheerroute_voor_gebruikers_gebruikt_dezelfde_regels(
        self, client: AsyncClient, wachtwoord: str
    ) -> None:
        kop, tenant, _ = await _beheerder(client)

        antwoord = await client.post(
            "/api/v1/users/",
            params={"target_tenant_id": tenant},
            json={"email": unieke_email("nieuw"), "password": wachtwoord},
            headers=kop,
        )

        assert antwoord.status_code == 422, antwoord.text

    async def test_een_te_lang_wachtwoord_wordt_bij_inloggen_geweigerd(
        self, client: AsyncClient, mailbox: SmtpDubbel
    ) -> None:
        medewerker, _token = await _uitgenodigde_met_token(client, mailbox)

        ingelogd = await _log_in_met(client, medewerker, "A1" + "b" * 200)

        assert ingelogd.status_code == 400, ingelogd.text


def _platformrol_id(tenant: int) -> int:
    return int(
        een_waarde(
            "SELECT id FROM roles WHERE name = :n AND tenant_id = :t", n=PLATFORMROL, t=tenant
        )
    )


@pytest.mark.integration
class TestOokDeAndereDeurenDelenDePlatformrolNietUit:
    """Gate 2 (security-review 2026-10-16): de gate stond maar op uitnodigen en assign-role.

    Nagemeten welke routes rollen schrijven EN gemount zijn: `POST /api/v1/admin/assign_role/{id}`,
    `POST /api/v1/users/` en `PUT /api/v1/users/{id}` (beide met `role_ids`). `user_management/crud_router`
    is niet gemount.
    """

    async def test_admin_assign_role_met_de_platformrol_geeft_403(
        self, client: AsyncClient
    ) -> None:
        kop, _tenant, email = await _beheerder(client)
        eigen_id = int(een_waarde("SELECT id FROM users WHERE email = :e", e=email))

        antwoord = await client.post(
            f"/api/v1/admin/assign_role/{eigen_id}", json={"role": PLATFORMROL}, headers=kop
        )

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_gebruiker_aanmaken_met_role_ids_van_de_platformrol_geeft_403(
        self, client: AsyncClient
    ) -> None:
        kop, tenant, _ = await _beheerder(client)
        medewerker = unieke_email("nieuw")

        antwoord = await client.post(
            "/api/v1/users/",
            params={"target_tenant_id": tenant},
            json={"email": medewerker, "role_ids": [_platformrol_id(tenant)]},
            headers=kop,
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _aantal_gebruikers(medewerker) == 0

    async def test_een_gebruiker_wijzigen_met_role_ids_van_de_platformrol_geeft_403(
        self, client: AsyncClient
    ) -> None:
        kop, tenant, email = await _beheerder(client)
        eigen_id = int(een_waarde("SELECT id FROM users WHERE email = :e", e=email))

        antwoord = await client.put(
            f"/api/v1/users/{eigen_id}", json={"role_ids": [_platformrol_id(tenant)]}, headers=kop
        )

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_gewone_rol_via_role_ids_blijft_werken(self, client: AsyncClient) -> None:
        kop, tenant, _ = await _beheerder(client)
        editor_id = int(
            een_waarde("SELECT id FROM roles WHERE name = 'editor' AND tenant_id = :t", t=tenant)
        )

        antwoord = await client.post(
            "/api/v1/users/",
            params={"target_tenant_id": tenant},
            json={"email": unieke_email("nieuw"), "role_ids": [editor_id]},
            headers=kop,
        )

        assert antwoord.status_code == 201, antwoord.text

    async def test_een_houder_mag_de_platformrol_via_role_ids_wel_uitdelen(
        self, client: AsyncClient
    ) -> None:
        kop, tenant, email = await _beheerder(client)
        _geef_de_platformrol(email, tenant)

        antwoord = await client.post(
            "/api/v1/users/",
            params={"target_tenant_id": tenant},
            json={"email": unieke_email("nieuw"), "role_ids": [_platformrol_id(tenant)]},
            headers=kop,
        )

        assert antwoord.status_code == 201, antwoord.text

    async def test_wijzigen_van_een_platformbeheerder_wordt_geweigerd_ook_met_een_ongewijzigde_set(
        self, client: AsyncClient
    ) -> None:
        """Fail-secure (f9971f04, 2026-10-19; besluit regie 2026-10-26): een beheerder zonder de platformrol
        raakt de rollen van een platformbeheerder NIET aan, ook niet als de meegegeven set gelijk lijkt.

        Hier stond de verwachting dat zo'n PUT slaagde (200) zolang de rol niet NIEUW werd toegekend. Dat is
        bewust veranderd; de tak die de rol liet staan (`platformrollen_die_blijven`) is daarmee onbereikbaar
        en staat in een opruimbrief. De platformrol moet na de weigering nog bij de gebruiker staan."""
        kop, tenant, _ = await _beheerder(client)
        platform_email = unieke_email("platform")
        voer_uit(
            "INSERT INTO users (email, hashed_password, is_active, is_superuser, tenant_id) "
            "VALUES (:e, 'x', true, false, :t)",
            e=platform_email,
            t=tenant,
        )
        _geef_de_platformrol(platform_email, tenant)
        platform_id = int(een_waarde("SELECT id FROM users WHERE email = :e", e=platform_email))

        antwoord = await client.put(
            f"/api/v1/users/{platform_id}",
            json={"role_ids": [_platformrol_id(tenant)]},
            headers=kop,
        )

        nog_aanwezig = int(
            een_waarde(
                "SELECT count(*) FROM user_roles WHERE user_id = :u AND role_id = :r",
                u=platform_id,
                r=_platformrol_id(tenant),
            )
        )
        assert (antwoord.status_code, nog_aanwezig) == (403, 1), antwoord.text
        assert "platformbeheerder" in antwoord.text


@pytest.mark.integration
class TestEenHouderVanDePlatformrolMagHemWelUitdelen:
    async def test_uitnodigen_met_de_platformrol_door_een_houder_geeft_201(
        self, client: AsyncClient
    ) -> None:
        kop, tenant, email = await _beheerder(client)
        _geef_de_platformrol(email, tenant)

        antwoord = await _nodig_uit(client, kop, unieke_email("nieuw"), PLATFORMROL)

        assert antwoord.status_code == 201, antwoord.text

    async def test_de_rollenlijst_toont_de_platformrol_aan_een_houder(
        self, client: AsyncClient
    ) -> None:
        kop, tenant, email = await _beheerder(client)
        _geef_de_platformrol(email, tenant)

        antwoord = await client.get("/api/rbac/roles", headers=kop)

        assert PLATFORMROL in {r["name"] for r in antwoord.json()}
