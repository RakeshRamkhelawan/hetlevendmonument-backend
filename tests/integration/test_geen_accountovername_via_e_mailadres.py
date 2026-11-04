"""Een klantbeheerder wijzigt geen profielgegevens van een platformbeheerder (2026-10-19).

Brief: docs/agent-briefs/generated/2026-10-19-sprint-dag-geen-accountovername-via-e-mailadres.md.

Gemeten vooraf (bfe04360): een tenantbeheerder zette via `PUT /api/v1/users/{id}` het e-mailadres van een
gebruiker met `system_admin` om. "Wachtwoord vergeten" stuurt de herstellink naar dat NIEUWE adres: een
accountovername. Direct nog korter was `PUT /api/v1/users/{id}/password`: een beheerder zet daar zonder
herstelmail het wachtwoord van elke gebruiker in zijn tenant.

De regel (een plek, `RBACService.controleer_profiel_wijzigen`): wie zelf geen platformrol heeft, wijzigt bij
een gebruiker MET die rol geen e-mailadres en geen wachtwoord. Dezelfde regel als uitdelen, ontnemen en
uitzetten (`mag_rol_uitdelen`). Een houder van de rol mag het wel; een gewone gebruiker blijft te wijzigen.

Echte app, echte JWT's, echte Postgres.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.security._voordeur_hulp import (  # noqa: F401
    client,
    een_waarde,
    limiters_leeg,
    unieke_email,
)
from tests.integration.test_platformrol_en_sessies_na_herstel import (
    PLATFORMROL,
    _geef_rol,
    _inloggen,
    _maak_gebruiker,
    _met_csrf,
    _platform_opstelling,
    _verse_redis_verbinding,  # noqa: F401
    mailbox,  # noqa: F401
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

NIEUW_WACHTWOORD = "NieuwGekozen#Wachtwoord9"  # nosec B105 - testwaarde
EVENT = "platform_user_profile_change_refused"


def _e_mail_van(gebruiker_id: int) -> str:
    return str(een_waarde("SELECT email FROM users WHERE id = :u", u=gebruiker_id))


def _hash_van(gebruiker_id: int) -> str:
    return str(een_waarde("SELECT hashed_password FROM users WHERE id = :u", u=gebruiker_id))


def _weigeringen(actor_id: int) -> int:
    return int(
        een_waarde(
            "SELECT count(*) FROM audit_logs WHERE event_type = :e AND user_id = :u",
            e=EVENT,
            u=actor_id,
        )
    )


async def _houder(client: AsyncClient, o: dict[str, object]) -> dict[str, str]:
    """De beheerder uit de opstelling krijgt zelf de platformrol; daarna opnieuw inloggen."""
    _geef_rol(str(o["email"]), int(o["tenant"]), PLATFORMROL)  # type: ignore[arg-type]
    tokens = await _inloggen(client, str(o["email"]))
    return await _met_csrf(client, tokens["access_token"])


@pytest.mark.integration
class TestEenKlantbeheerderWijzigtHetEmailadresVanEenPlatformbeheerderNiet:
    async def test_put_geeft_403(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)

        antwoord = await client.put(
            f"/api/v1/users/{o['platform_id']}",
            json={"email": unieke_email("overname")},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text

    async def test_het_adres_staat_daarna_nog_ongewijzigd_in_de_database(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        voor = _e_mail_van(int(o["platform_id"]))  # type: ignore[arg-type]

        await client.put(
            f"/api/v1/users/{o['platform_id']}",
            json={"email": unieke_email("overname")},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert _e_mail_van(int(o["platform_id"])) == voor  # type: ignore[arg-type]

    async def test_een_put_met_meer_velden_legt_ook_het_andere_veld_niet_vast(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)

        await client.put(
            f"/api/v1/users/{o['platform_id']}",
            json={"email": unieke_email("overname"), "is_active": True, "role_ids": []},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert _e_mail_van(int(o["platform_id"])).startswith("platform")  # type: ignore[arg-type]

    async def test_de_weigering_is_in_het_nederlands(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)

        antwoord = await client.put(
            f"/api/v1/users/{o['platform_id']}",
            json={"email": unieke_email("overname")},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert "platformrol" in antwoord.json()["detail"]

    async def test_de_weigering_laat_een_auditregel_achter(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)
        voor = _weigeringen(int(o["beheerder_id"]))  # type: ignore[arg-type]

        await client.put(
            f"/api/v1/users/{o['platform_id']}",
            json={"email": unieke_email("overname")},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert _weigeringen(int(o["beheerder_id"])) == voor + 1  # type: ignore[arg-type]


@pytest.mark.integration
class TestEenKlantbeheerderZetHetWachtwoordVanEenPlatformbeheerderNiet:
    async def test_put_wachtwoord_geeft_403(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)

        antwoord = await client.put(
            f"/api/v1/users/{o['platform_id']}/password",
            json={"current_password": "x", "new_password": NIEUW_WACHTWOORD},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 403, antwoord.text

    async def test_het_wachtwoord_staat_daarna_nog_ongewijzigd_in_de_database(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        voor = _hash_van(int(o["platform_id"]))  # type: ignore[arg-type]

        await client.put(
            f"/api/v1/users/{o['platform_id']}/password",
            json={"current_password": "x", "new_password": NIEUW_WACHTWOORD},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert _hash_van(int(o["platform_id"])) == voor  # type: ignore[arg-type]

    async def test_de_weigering_laat_een_auditregel_achter(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)
        voor = _weigeringen(int(o["beheerder_id"]))  # type: ignore[arg-type]

        await client.put(
            f"/api/v1/users/{o['platform_id']}/password",
            json={"current_password": "x", "new_password": NIEUW_WACHTWOORD},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert _weigeringen(int(o["beheerder_id"])) == voor + 1  # type: ignore[arg-type]


@pytest.mark.integration
class TestDeTegenrichtingBlijftWerken:
    async def test_een_houder_van_de_platformrol_wijzigt_het_adres_van_een_platformbeheerder(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        kop = await _houder(client, o)
        nieuw = unieke_email("nieuwadres")

        antwoord = await client.put(
            f"/api/v1/users/{o['platform_id']}", json={"email": nieuw}, headers=kop
        )

        assert antwoord.status_code == 200, antwoord.text
        assert _e_mail_van(int(o["platform_id"])) == nieuw  # type: ignore[arg-type]

    async def test_een_houder_zet_het_wachtwoord_van_een_platformbeheerder(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        kop = await _houder(client, o)
        voor = _hash_van(int(o["platform_id"]))  # type: ignore[arg-type]

        antwoord = await client.put(
            f"/api/v1/users/{o['platform_id']}/password",
            json={"current_password": "x", "new_password": NIEUW_WACHTWOORD},
            headers=kop,
        )

        assert antwoord.status_code == 200, antwoord.text
        assert _hash_van(int(o["platform_id"])) != voor  # type: ignore[arg-type]

    async def test_een_klantbeheerder_wijzigt_het_adres_van_een_gewone_gebruiker(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        gewoon = _maak_gebruiker(unieke_email("gewoon"), int(o["tenant"]))  # type: ignore[arg-type]
        nieuw = unieke_email("nieuwadres")

        antwoord = await client.put(
            f"/api/v1/users/{gewoon}",
            json={"email": nieuw},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 200, antwoord.text
        assert _e_mail_van(gewoon) == nieuw

    async def test_een_klantbeheerder_zet_het_wachtwoord_van_een_gewone_gebruiker(
        self, client: AsyncClient
    ) -> None:
        o = await _platform_opstelling(client)
        gewoon = _maak_gebruiker(unieke_email("gewoon"), int(o["tenant"]))  # type: ignore[arg-type]
        voor = _hash_van(gewoon)

        antwoord = await client.put(
            f"/api/v1/users/{gewoon}/password",
            json={"current_password": "x", "new_password": NIEUW_WACHTWOORD},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 200, antwoord.text
        assert _hash_van(gewoon) != voor

    async def test_een_klantbeheerder_wijzigt_zijn_eigen_adres(self, client: AsyncClient) -> None:
        o = await _platform_opstelling(client)
        nieuw = unieke_email("nieuwadres")

        antwoord = await client.put(
            f"/api/v1/users/{o['beheerder_id']}",
            json={"email": nieuw},
            headers=o["kop"],  # type: ignore[arg-type]
        )

        assert antwoord.status_code == 200, antwoord.text
        assert _e_mail_van(int(o["beheerder_id"])) == nieuw  # type: ignore[arg-type]
