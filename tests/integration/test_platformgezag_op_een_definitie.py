"""Platformgezag op EEN definitie: rol OF vlag, in elke schrijfwijze (2026-10-19).

Brief: docs/agent-briefs/generated/2026-10-19-sprint-dag-platformgezag-op-een-definitie.md.

Gemeten vooraf (324147da): de platformregels herkenden een platformbeheerder alleen aan de ROL
`system_admin` in de tenant van het doel. Een account met alleen de vlag `is_superuser` (en dat zijn in de
ontwikkel- en testdatabase de enige twee platformaccounts) was door geen enkele regel beschermd, en
`delete-all` kende de platformrol helemaal niet. De auditregel van een weigering had een vaste methode (POST)
en een vast pad.

De regel (`telt_als_platformbeheerder`, gebruikt door uitzetten, verwijderen, wissen, profiel wijzigen,
rollen wijzigen en de tenantbrede wissing): een DOEL is platformbeheerder bij de vlag OF een platformrol, in
welke tenant of schrijfwijze ook. Het GEZAG van de aanvrager blijft de ROL (OP-189).

Echte app, echte JWT's, echte Postgres.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.security._voordeur_hulp import (  # noqa: F401
    client,
    een_waarde,
    limiters_leeg,
    rijen,
    unieke_email,
    voer_uit,
)
from tests.integration.test_platformrol_en_sessies_na_herstel import (
    PLATFORMROL,
    _geef_rol,
    _inloggen,
    _klant,
    _maak_gebruiker,
    _met_csrf,
    _platform_opstelling,
    _rol_id,
    _rollen_van,
    _verse_redis_verbinding,  # noqa: F401
    mailbox,  # noqa: F401
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

NIEUW_WACHTWOORD = "NieuwGekozen#Wachtwoord9"  # nosec B105 - testwaarde


def _maak_platformbeheerder_met_alleen_de_vlag(tenant: int) -> int:
    gebruiker = _maak_gebruiker(unieke_email("vlag"), tenant)
    voer_uit("UPDATE users SET is_superuser = true WHERE id = :u", u=gebruiker)
    return gebruiker


def _geef_gewone_rol(gebruiker_id: int, tenant: int, rol: str) -> None:
    voer_uit(
        "INSERT INTO user_roles (user_id, role_id, tenant_id) "
        "SELECT :u, r.id, :t FROM roles r WHERE r.name = :n AND r.tenant_id = :t",
        u=gebruiker_id,
        n=rol,
        t=tenant,
    )


def _is_actief(gebruiker_id: int) -> bool:
    return bool(een_waarde("SELECT is_active FROM users WHERE id = :u", u=gebruiker_id))


def _e_mail_van(gebruiker_id: int) -> str:
    return str(een_waarde("SELECT email FROM users WHERE id = :u", u=gebruiker_id))


def _hash_van(gebruiker_id: int) -> str:
    return str(een_waarde("SELECT hashed_password FROM users WHERE id = :u", u=gebruiker_id))


def _weigeringen(event_type: str, actor_id: int) -> int:
    return int(
        een_waarde(
            "SELECT count(*) FROM audit_logs WHERE event_type = :e AND user_id = :u",
            e=event_type,
            u=actor_id,
        )
    )


async def _als_rolhouder(client: AsyncClient, o: dict[str, object]) -> dict[str, str]:
    """De beheerder uit de opstelling krijgt zelf de platformrol; daarna opnieuw inloggen."""
    _geef_rol(str(o["email"]), int(o["tenant"]), PLATFORMROL)  # type: ignore[arg-type]
    tokens = await _inloggen(client, str(o["email"]))
    return await _met_csrf(client, tokens["access_token"])


@pytest.mark.integration
class TestEenDoelMetAlleenDeVlagIsBeschermd:
    """Een tenantbeheerder raakt een platformbeheerder met alleen de vlag net zo min aan als een rolhouder."""

    async def test_uitzetten_geeft_403_en_hij_blijft_actief(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)
        doel = _maak_platformbeheerder_met_alleen_de_vlag(int(o["tenant"]))  # type: ignore[arg-type]

        antwoord = await client.put(
            f"/api/v1/users/{doel}",
            json={"is_active": False},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _is_actief(doel)

    async def test_verwijderen_geeft_403_en_hij_blijft_actief(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)
        doel = _maak_platformbeheerder_met_alleen_de_vlag(int(o["tenant"]))  # type: ignore[arg-type]

        antwoord = await client.delete(
            f"/api/v1/users/{doel}",
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _is_actief(doel)

    async def test_laten_wissen_geeft_403_en_hij_blijft_actief(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)
        doel = _maak_platformbeheerder_met_alleen_de_vlag(int(o["tenant"]))  # type: ignore[arg-type]

        antwoord = await client.post(
            f"/api/gdpr/users/{doel}/erase",
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _is_actief(doel)

    async def test_het_adres_wijzigen_geeft_403_en_het_adres_blijft(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        doel = _maak_platformbeheerder_met_alleen_de_vlag(int(o["tenant"]))  # type: ignore[arg-type]
        voor = _e_mail_van(doel)

        antwoord = await client.put(
            f"/api/v1/users/{doel}",
            json={"email": unieke_email("overname")},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _e_mail_van(doel) == voor

    async def test_het_wachtwoord_zetten_geeft_403_en_het_wachtwoord_blijft(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        doel = _maak_platformbeheerder_met_alleen_de_vlag(int(o["tenant"]))  # type: ignore[arg-type]
        voor = _hash_van(doel)

        antwoord = await client.put(
            f"/api/v1/users/{doel}/password",
            json={"current_password": "x", "new_password": NIEUW_WACHTWOORD},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _hash_van(doel) == voor

    async def test_een_rol_ontnemen_geeft_403_en_de_rol_blijft(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)
        doel = _maak_platformbeheerder_met_alleen_de_vlag(int(o["tenant"]))  # type: ignore[arg-type]
        _geef_gewone_rol(doel, int(o["tenant"]), "user")  # type: ignore[arg-type]

        antwoord = await client.post(
            "/api/rbac/users/revoke-role",
            json={"user_id": doel, "role_name": "user"},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _rollen_van(doel) == {"user"}

    async def test_een_rol_ontnemen_via_de_bulkroute_geeft_403_en_de_rol_blijft(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        doel = _maak_platformbeheerder_met_alleen_de_vlag(int(o["tenant"]))  # type: ignore[arg-type]
        _geef_gewone_rol(doel, int(o["tenant"]), "user")  # type: ignore[arg-type]

        antwoord = await client.post(
            "/api/rbac/users/revoke-role/bulk",
            json={"user_ids": [doel], "role_name": "user"},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _rollen_van(doel) == {"user"}

    async def test_een_bulkroute_met_een_platformbeheerder_op_plek_twee_trekt_niemand_in(
        self, client: AsyncClient
    ) -> None:
        """`revoke_role` commit per gebruiker: zonder voorafgaande toets was gebruiker 1 al ingetrokken."""
        o = await _platform_opstelling(client)
        tenant = int(o["tenant"])  # type: ignore[arg-type]
        gewoon = _maak_gebruiker(unieke_email("gewoon"), tenant)
        _geef_gewone_rol(gewoon, tenant, "user")
        vlag = _maak_platformbeheerder_met_alleen_de_vlag(tenant)
        _geef_gewone_rol(vlag, tenant, "user")

        antwoord = await client.post(
            "/api/rbac/users/revoke-role/bulk",
            json={"user_ids": [gewoon, vlag], "role_name": "user"},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert (_rollen_van(gewoon), _rollen_van(vlag)) == ({"user"}, {"user"})

    async def test_een_vervangende_rollenset_geeft_403_en_de_rollen_blijven(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        doel = _maak_platformbeheerder_met_alleen_de_vlag(int(o["tenant"]))  # type: ignore[arg-type]
        _geef_gewone_rol(doel, int(o["tenant"]), "user")  # type: ignore[arg-type]

        antwoord = await client.put(
            f"/api/v1/users/{doel}",
            json={"role_ids": [_rol_id(int(o["tenant"]), "editor")]},  # type: ignore[arg-type]
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _rollen_van(doel) == {"user"}


@pytest.mark.integration
class TestEenAndereSchrijfwijzeVanDePlatformrolTeltOok:
    async def test_een_rolnaam_met_hoofdletters_beschermt_net_zo(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)
        tenant = int(o["tenant"])  # type: ignore[arg-type]
        voer_uit(
            "INSERT INTO roles (name, tenant_id, is_active) VALUES ('System_Admin', :t, true)",
            t=tenant,
        )
        doel = _maak_gebruiker(unieke_email("hoofdletters"), tenant)
        _geef_gewone_rol(doel, tenant, "System_Admin")
        voor = _e_mail_van(doel)

        antwoord = await client.put(
            f"/api/v1/users/{doel}",
            json={"email": unieke_email("overname")},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _e_mail_van(doel) == voor


@pytest.mark.integration
class TestGekruisteRolrijenKunnenNietBestaan:
    """Gemeten: `user_roles` heeft twee samengestelde vreemde sleutels (rol+tenant en gebruiker+tenant).
    Een rij die een gebruiker aan een rol van een ANDERE tenant koppelt, wordt door de database geweigerd;
    de definitie hoeft er dus geen rekening mee te houden, en een poging gaat niet ongemerkt."""

    async def test_een_gebruiker_aan_een_rol_van_een_andere_tenant_koppelen_mislukt(
        self, client: AsyncClient
    ) -> None:
        _, tenant_a, _ = await _klant(client)
        _, tenant_b, _ = await _klant(client)
        gebruiker = _maak_gebruiker(unieke_email("gekruist"), tenant_a)

        with pytest.raises(Exception):  # noqa: B017, PT011 - elke databasefout telt
            voer_uit(
                "INSERT INTO user_roles (user_id, role_id, tenant_id) "
                "SELECT :u, r.id, :t FROM roles r WHERE r.name = :n AND r.tenant_id = :t",
                u=gebruiker,
                n=PLATFORMROL,
                t=tenant_b,
            )


@pytest.mark.integration
class TestEenTenantbredeWissingRaaktEenPlatformbeheerderNiet:
    @staticmethod
    def _wissing(tenant: int) -> dict[str, object]:
        return {"delete_type": "soft", "confirmation_code": str(tenant), "reason": "test"}

    async def test_een_tenant_met_een_rolhouder_wordt_niet_gewist(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        tenant = int(o["tenant"])  # type: ignore[arg-type]

        antwoord = await client.post(
            "/api/gdpr/delete-all",
            json=self._wissing(tenant),
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _is_actief(int(o["platform_id"]))  # type: ignore[arg-type]

    async def test_een_tenant_met_alleen_een_vlagaccount_wordt_niet_gewist(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        tenant = int(o["tenant"])  # type: ignore[arg-type]
        vlag = _maak_platformbeheerder_met_alleen_de_vlag(tenant)

        antwoord = await client.post(
            "/api/gdpr/delete-all",
            json=self._wissing(tenant),
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _is_actief(vlag)

    async def test_een_harde_wissing_wordt_ook_geweigerd(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)

        antwoord = await client.post(
            "/api/gdpr/delete-all",
            json={
                "delete_type": "hard",
                "confirmation_code": str(o["tenant"]),
                "reason": "test",
            },
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text
        assert _is_actief(int(o["platform_id"]))  # type: ignore[arg-type]

    async def test_de_weigering_laat_een_auditregel_achter(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)
        voor = _weigeringen("platform_tenant_wipe_refused", int(o["beheerder_id"]))  # type: ignore[arg-type]

        await client.post(
            "/api/gdpr/delete-all",
            json=self._wissing(int(o["tenant"])),  # type: ignore[arg-type]
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert _weigeringen("platform_tenant_wipe_refused", int(o["beheerder_id"])) == voor + 1  # type: ignore[arg-type]

    async def test_een_tenant_zonder_platformbeheerder_wordt_wel_gewist(
        self, client: AsyncClient
    ) -> None:
        email, tenant, _beheerder = await _klant(client)
        kop = await _met_csrf(client, (await _inloggen(client, email))["access_token"])
        medewerker = _maak_gebruiker(unieke_email("medewerker"), tenant)

        antwoord = await client.post(
            "/api/gdpr/delete-all", json=self._wissing(tenant), headers=kop
        )

        assert antwoord.status_code == 200, antwoord.text
        assert not _is_actief(medewerker)

    async def test_een_houder_van_de_platformrol_mag_de_tenant_wel_wissen(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        kop = await _als_rolhouder(client, o)

        antwoord = await client.post(
            "/api/gdpr/delete-all",
            json=self._wissing(int(o["tenant"])),  # type: ignore[arg-type]
            headers=kop,
        )

        assert antwoord.status_code == 200, antwoord.text


@pytest.mark.integration
class TestDeAuditregelNoemtHetEchteVerzoek:
    @staticmethod
    def _regel(event_type: str, actor_id: int) -> tuple[str, str, str]:
        rij = rijen(
            "SELECT endpoint, client_ip, CAST(event_metadata AS text) FROM audit_logs "
            "WHERE event_type = :e AND user_id = :u ORDER BY id DESC LIMIT 1",
            e=event_type,
            u=actor_id,
        )[0]
        return str(rij[0]), str(rij[1]), str(rij[2])

    async def test_een_weigerde_put_noemt_het_pad_de_methode_en_het_ip(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)

        await client.put(
            f"/api/v1/users/{o['platform_id']}",
            json={"email": unieke_email("overname")},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        pad, ip, metadata = self._regel(
            "platform_user_profile_change_refused",
            int(o["beheerder_id"]),  # type: ignore[arg-type]
        )
        assert (pad, "PUT" in metadata, ip != "unknown") == (
            f"/api/v1/users/{o['platform_id']}",
            True,
            True,
        )

    async def test_een_weigerde_delete_noemt_de_methode_delete(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)

        await client.delete(
            f"/api/v1/users/{o['platform_id']}",
            headers=o["kop"],  # type: ignore[arg-type]
        )

        pad, _ip, metadata = self._regel(
            "platform_user_disable_refused",
            int(o["beheerder_id"]),  # type: ignore[arg-type]
        )
        assert (pad, "DELETE" in metadata) == (f"/api/v1/users/{o['platform_id']}", True)


@pytest.mark.integration
class TestDeTegenrichtingBlijftWerken:
    async def test_een_gewone_gebruiker_blijft_beheerbaar(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)
        tenant = int(o["tenant"])  # type: ignore[arg-type]
        gewoon = _maak_gebruiker(unieke_email("gewoon"), tenant)
        nieuw = unieke_email("nieuwadres")

        via_adres = await client.put(
            f"/api/v1/users/{gewoon}",
            json={"email": nieuw},
            headers=o["kop"],  # type: ignore[arg-type]
        )
        via_rollen = await client.put(
            f"/api/v1/users/{gewoon}",
            json={"role_ids": [_rol_id(tenant, "editor")]},
            headers=o["kop"],  # type: ignore[arg-type]
        )
        via_uitzetten = await client.put(
            f"/api/v1/users/{gewoon}",
            json={"is_active": False},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert (via_adres.status_code, via_rollen.status_code, via_uitzetten.status_code) == (
            200,
            200,
            200,
        ), (via_adres.text, via_rollen.text, via_uitzetten.text)
        assert (_e_mail_van(gewoon), _rollen_van(gewoon), _is_actief(gewoon)) == (
            nieuw,
            {"editor"},
            False,
        )

    async def test_een_rolhouder_wijzigt_het_adres_van_een_vlagaccount(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        kop = await _als_rolhouder(client, o)
        doel = _maak_platformbeheerder_met_alleen_de_vlag(int(o["tenant"]))  # type: ignore[arg-type]
        nieuw = unieke_email("nieuwadres")

        antwoord = await client.put(f"/api/v1/users/{doel}", json={"email": nieuw}, headers=kop)

        assert antwoord.status_code == 200, antwoord.text
        assert _e_mail_van(doel) == nieuw

    async def test_een_rolhouder_wijzigt_de_rollen_van_een_platformbeheerder(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        kop = await _als_rolhouder(client, o)

        antwoord = await client.put(
            f"/api/v1/users/{o['platform_id']}",
            json={"role_ids": [_rol_id(int(o["tenant"]), "user")]},  # type: ignore[arg-type]
            headers=kop,
        )

        assert antwoord.status_code == 200, antwoord.text
        assert _rollen_van(int(o["platform_id"])) == {"user"}  # type: ignore[arg-type]

    async def test_een_platformbeheerder_wijzigt_zijn_eigen_adres(
        self, client: AsyncClient
    ) -> None:
        email, _tenant, beheerder = await _klant(client)
        voer_uit("UPDATE users SET is_superuser = true WHERE id = :u", u=beheerder)
        kop = await _met_csrf(client, (await _inloggen(client, email))["access_token"])
        nieuw = unieke_email("nieuwadres")

        antwoord = await client.put(
            f"/api/v1/users/{beheerder}", json={"email": nieuw}, headers=kop
        )

        assert antwoord.status_code == 200, antwoord.text
        assert _e_mail_van(beheerder) == nieuw


@pytest.mark.integration
class TestWatDeGezaaideBeheerderMetAlleenDeVlagKan:
    """De stand van de ontwikkeldatabase (account 1 en 101): vlag, rol `admin`, GEEN rol `system_admin`.

    Het gezag om een platformrol uit te delen is de ROL (OP-189). Dit legt vast wat zo'n account wel en niet
    kan, zodat niemand het per ongeluk aanneemt."""

    async def _vlagbeheerder(self, client: AsyncClient) -> tuple[dict[str, str], int]:
        email, tenant, beheerder = await _klant(client)
        voer_uit("UPDATE users SET is_superuser = true WHERE id = :u", u=beheerder)
        kop = await _met_csrf(client, (await _inloggen(client, email))["access_token"])
        return kop, tenant

    async def test_hij_deelt_de_platformrol_niet_uit(self, client: AsyncClient) -> None:
        kop, tenant = await self._vlagbeheerder(client)
        ander = _maak_gebruiker(unieke_email("ander"), tenant)

        antwoord = await client.post(
            "/api/rbac/users/assign-role",
            json={"user_id": ander, "role_name": PLATFORMROL},
            headers=kop,
        )

        assert antwoord.status_code == 403, antwoord.text
        assert PLATFORMROL not in _rollen_van(ander)

    async def test_hij_deelt_een_gewone_rol_wel_uit(self, client: AsyncClient) -> None:
        kop, tenant = await self._vlagbeheerder(client)
        ander = _maak_gebruiker(unieke_email("ander"), tenant)

        antwoord = await client.post(
            "/api/rbac/users/assign-role",
            json={"user_id": ander, "role_name": "editor"},
            headers=kop,
        )

        assert antwoord.status_code == 200, antwoord.text
        assert "editor" in _rollen_van(ander)

    async def test_met_ook_de_rol_deelt_hij_de_platformrol_wel_uit(
        self, client: AsyncClient
    ) -> None:
        email, tenant, beheerder = await _klant(client)
        voer_uit("UPDATE users SET is_superuser = true WHERE id = :u", u=beheerder)
        _geef_rol(email, tenant, PLATFORMROL)
        kop = await _met_csrf(client, (await _inloggen(client, email))["access_token"])
        ander = _maak_gebruiker(unieke_email("ander"), tenant)

        antwoord = await client.post(
            "/api/rbac/users/assign-role",
            json={"user_id": ander, "role_name": PLATFORMROL},
            headers=kop,
        )

        assert antwoord.status_code == 200, antwoord.text
        assert PLATFORMROL in _rollen_van(ander)
