"""Een ingetrokken token wordt op het verzoekpad geweigerd (ADR-036 OP-188).

**De bevinding.** `jwt_handler.verify_token_with_blacklist` bestond, maar NIETS op het
verzoekpad riep hem aan: `tenant_middleware`, `auth/dependencies` en `scope_validator`
gebruikten alle drie de gewone `verify_token`. Uitloggen maakte een access-token dus niet
ongeldig, en tijdens een incident was er geen knop om een gecompromitteerd token te doden --
het bleef geldig tot het verliep (default 60 minuten).

**Waarom het zo lang onopgemerkt bleef.** Er zijn TWEE `TokenBlacklist`-klassen: een
Redis-variant (`auth/token_blacklist.py`, nul productie-aanroepers) en een databasemodel
(`auth/oauth2_service.py:27`, wel gebruikt). De refresh-flow controleert die tweede WEL, dus
het mechanisme leek te bestaan.

**Waarom dit nu pas zin heeft.** De rij zei zelf dat intrekken tweede orde was zolang de ROL
in de database blijft staan -- een aanvaller logt dan gewoon opnieuw in. Met OP-186, OP-187
en OP-191 dicht is de rollenkant op orde en heeft intrekken betekenis.

**Vier richtingen, met opzet.** Zonder de tegentests zou "weiger alles" hier slagen, en dan
kan niemand meer inloggen.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.auth.dependencies import _get_user_from_token, get_current_user_id


def _payload(jti: str | None = "jti-1234") -> dict[str, object]:
    inhoud: dict[str, object] = {"sub": "7", "email": "iemand@example.com"}
    if jti is not None:
        inhoud["jti"] = jti
    return inhoud


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeBlacklistWordtOpHetVerzoekpadGelezen:
    async def test_een_ingetrokken_token_wordt_geweigerd(self) -> None:
        """De kern: intrekken moet effect hebben op het verzoekpad."""
        db = AsyncMock()
        with patch("src.core.auth.dependencies.jwt_handler.verify_token", return_value=_payload()):
            with patch(
                "src.core.auth.oauth2_service.oauth2_service.is_jti_revoked",
                new=AsyncMock(return_value=True),
            ):
                with pytest.raises(HTTPException) as fout:
                    await _get_user_from_token("token", db)

        assert fout.value.status_code == 401, (
            "Een ingetrokken token kwam er doorheen. Uitloggen maakt een access-token dan "
            "niet ongeldig en er is tijdens een incident geen knop om hem te doden "
            "(ADR-036 OP-188)."
        )

    async def test_een_token_zonder_jti_wordt_geweigerd(self) -> None:
        """Fail-secure: zonder jti is intrekken per definitie onmogelijk.

        `create_access_token` zet altijd een jti en elke uitgifteplek loopt via die functie,
        dus dit kan uit deze codebase niet ontstaan. Doorlaten zou een tokensoort opleveren
        die niet in te trekken is -- een sentinel-achtige omweg, en die lijn volgt dit
        project niet.
        """
        db = AsyncMock()
        blacklist = AsyncMock(return_value=False)
        with patch(
            "src.core.auth.dependencies.jwt_handler.verify_token",
            return_value=_payload(jti=None),
        ):
            with patch("src.core.auth.oauth2_service.oauth2_service.is_jti_revoked", new=blacklist):
                with pytest.raises(HTTPException) as fout:
                    await _get_user_from_token("token", db)

        assert fout.value.status_code == 401
        # De blacklist mag NIET zijn geraadpleegd: we horen te weigeren VOORDAT we hem
        # bevragen. Zonder deze assertie is de test hol -- een mutatie die de jti-controle
        # uitzet leverde ook een 401 op, maar dan uit een andere oorzaak (de AsyncMock gaf
        # een waarheidswaardige uitkomst terug). Gemeten 2026-09-15: die mutatie werd NIET
        # betrapt tot deze regel erbij kwam.
        assert blacklist.await_count == 0, (
            "Een token zonder jti werd alsnog tegen de blacklist gehouden. Dan hangt de "
            "weigering af van wat die controle toevallig antwoordt, en niet van de "
            "fail-secure regel."
        )

    async def test_de_blacklist_wordt_daadwerkelijk_geraadpleegd(self) -> None:
        """Vangnet: een controle die nooit wordt aangeroepen bewaakt niets."""
        db = AsyncMock()
        controle = AsyncMock(return_value=False)
        with patch("src.core.auth.dependencies.jwt_handler.verify_token", return_value=_payload()):
            with patch("src.core.auth.oauth2_service.oauth2_service.is_jti_revoked", new=controle):
                with patch(
                    "src.core.auth.dependencies.auth_service.get_user_by_email",
                    new=AsyncMock(return_value=None),
                ):
                    with pytest.raises(HTTPException):
                        await _get_user_from_token("token", db)

        controle.assert_awaited_once()
        assert controle.await_args is not None
        assert controle.await_args.args[0] == "jti-1234", (
            "De blacklist is met een andere jti bevraagd dan die in het token staat."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestEenGeldigTokenBlijftWerken:
    async def test_een_niet_ingetrokken_token_komt_voorbij_de_blacklist(self) -> None:
        """De andere richting -- zonder deze zou 'weiger alles' de tests hierboven halen.

        De gebruiker wordt hier bewust NIET gevonden, zodat de test uitsluitend over de
        blacklistcontrole gaat: hij komt daar voorbij en valt pas op de gebruikerslookup.
        Zou de blacklist hem tegenhouden, dan was de opgeroepen lookup nooit gebeurd.
        """
        db = AsyncMock()
        lookup = AsyncMock(return_value=None)
        with patch("src.core.auth.dependencies.jwt_handler.verify_token", return_value=_payload()):
            with patch(
                "src.core.auth.oauth2_service.oauth2_service.is_jti_revoked",
                new=AsyncMock(return_value=False),
            ), patch(
                # De grens "alle sessies ingetrokken" leest ook de database; hier is er geen grens.
                "src.core.auth.oauth2_service.oauth2_service.is_uitgegeven_voor_intrekking",
                new=AsyncMock(return_value=False),
            ):
                with patch("src.core.auth.dependencies.auth_service.get_user_by_email", new=lookup):
                    with pytest.raises(HTTPException):
                        await _get_user_from_token("token", db)

        assert lookup.await_count == 1, (
            "Een geldig token kwam niet voorbij de blacklistcontrole. Dan is de reparatie "
            "een storing en geen beveiliging."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeTweedeIngangLeestDeBlacklistOok:
    """`get_current_user_id` is de TWEEDE authenticatie-ingang (ADR-036 OP-260).

    Waarom deze klasse bestaat: de blokkerende poort is `tests/unit tests/architecture
    tests/core tests/contracts` -- `tests/integration/` valt daarbuiten en draait alleen met
    een handmatig opgestarte PostgreSQL. Gemeten 2026-09-19: met de aanroep van
    `_weiger_als_ingetrokken` uit `get_current_user_id` verwijderd bleven 436 unittests
    GROEN. De fix had dus geen enkele bewaker in de poort die hem moet bewaken.

    **Waarom elke assertie de DETAILTEKST toetst en niet alleen de 401.** De eerste versie
    van deze klasse deed dat wel en was daardoor HOL: met de mutatie erin kwam er nog steeds
    een 401, maar uit de brede `except Exception` onderaan `get_current_user_id`
    ("Authentication failed"), omdat de gemockte sessie daarna een coroutine teruggaf. Vier
    tests bleven groen terwijl de fix eruit was. De intrekkingstak geeft
    `_credentials_exception()` met "Could not validate credentials"; dat onderscheidt de
    twee. Daarnaast is de sessie nu zo opgezet dat het verzoek ZONDER de controle zou
    SLAGEN, zodat de mutatie een geslaagde aanroep oplevert in plaats van een toevallige 401.
    """

    @staticmethod
    def _sessie_die_gebruiker_7_vindt() -> AsyncMock:
        gebruiker = MagicMock()
        gebruiker.id = 7
        resultaat = MagicMock()
        resultaat.scalar_one_or_none.return_value = gebruiker
        sessie = AsyncMock()
        sessie.execute.return_value = resultaat
        return sessie

    async def test_een_ingetrokken_token_wordt_ook_op_deze_ingang_geweigerd(self) -> None:
        sessie = self._sessie_die_gebruiker_7_vindt()
        with patch(
            "src.core.auth.dependencies.jwt_handler.verify_token",
            return_value={"sub": "7", "user_id": 7, "jti": "jti-1234"},
        ):
            with patch(
                "src.core.auth.oauth2_service.oauth2_service.is_jti_revoked",
                new=AsyncMock(return_value=True),
            ):
                with pytest.raises(HTTPException) as fout:
                    await get_current_user_id("token", sessie)

        assert fout.value.status_code == 401
        assert fout.value.detail == "Could not validate credentials", (
            "De 401 kwam NIET uit de intrekkingstak maar uit een andere (detail: %r). Zonder "
            "deze assertie is de test hol: zonder de controle levert deze opzet een geslaagde "
            "aanroep op, en elke andere 401 zou hem ten onrechte groen houden."
            % fout.value.detail
        )

    async def test_een_token_zonder_jti_wordt_ook_op_deze_ingang_geweigerd(self) -> None:
        """Fail-secure, net als op de andere ingang: zonder jti kan niets ingetrokken."""
        sessie = self._sessie_die_gebruiker_7_vindt()
        blacklist = AsyncMock(return_value=False)
        with patch(
            "src.core.auth.dependencies.jwt_handler.verify_token",
            return_value={"sub": "7", "user_id": 7},
        ):
            with patch(
                "src.core.auth.oauth2_service.oauth2_service.is_jti_revoked", new=blacklist
            ):
                with pytest.raises(HTTPException) as fout:
                    await get_current_user_id("token", sessie)

        assert fout.value.status_code == 401
        assert fout.value.detail == "Could not validate credentials"
        assert blacklist.await_count == 0, (
            "Er is een token ZONDER jti tegen de blacklist gehouden. Dan hangt de weigering "
            "af van wat de database toevallig teruggeeft in plaats van van de fail-secure tak."
        )

    async def test_een_geldig_token_komt_er_op_deze_ingang_WEL_door(self) -> None:
        """Tegenrichting. Zonder deze test is "weiger alles" een geldige oplossing."""
        sessie = self._sessie_die_gebruiker_7_vindt()
        with patch(
            "src.core.auth.dependencies.jwt_handler.verify_token",
            return_value={"sub": "7", "user_id": 7, "jti": "jti-1234"},
        ):
            with patch(
                "src.core.auth.oauth2_service.oauth2_service.is_jti_revoked",
                new=AsyncMock(return_value=False),
            ), patch(
                # De grens "alle sessies ingetrokken" leest ook de database; hier is er geen grens.
                "src.core.auth.oauth2_service.oauth2_service.is_uitgegeven_voor_intrekking",
                new=AsyncMock(return_value=False),
            ):
                assert await get_current_user_id("token", sessie) == 7

    async def test_een_databasefout_in_de_blacklist_geeft_geen_toegang(self) -> None:
        """Fail-secure bij een storing (Gate 2 LOW-4, 2026-09-19).

        De drie auth-paden zijn vandaag dicht, maar dat rust op een brede `except Exception`
        die daar om een andere reden staat. Wie die ooit versmalt, zet de deur open zonder
        het te merken. Deze test legt het GEDRAG vast, niet de implementatie. De detailtekst
        is hier bewust "Authentication failed": dat IS de brede tak, en dat is precies wat
        deze test bewaakt -- zolang hij maar geen toegang geeft.
        """
        sessie = self._sessie_die_gebruiker_7_vindt()
        with patch(
            "src.core.auth.dependencies.jwt_handler.verify_token",
            return_value={"sub": "7", "user_id": 7, "jti": "jti-1234"},
        ):
            with patch(
                "src.core.auth.oauth2_service.oauth2_service.is_jti_revoked",
                new=AsyncMock(side_effect=RuntimeError("database weg")),
            ):
                with pytest.raises(HTTPException) as fout:
                    await get_current_user_id("token", sessie)

        assert fout.value.status_code == 401, (
            "Een storing in de blacklistcontrole gaf TOEGANG in plaats van een weigering. "
            "Een deny-list die bij een fout wordt overgeslagen, is geen deny-list."
        )


def test_de_intrekkingscontrole_is_in_dit_bestand_niet_gepatcht() -> None:
    """Vangnet: draait deze module onder een patch, dan zegt de rest hierboven niets.

    Drie andere testbestanden hebben sinds OP-188 een autouse-fixture die
    `is_jti_revoked` uitzet -- nodig, want zij mocken de database los en krijgen anders een
    401 die niets met hun onderwerp te maken heeft. Niets houdt tegen dat iemand die
    fixture OOK naar dit bestand kopieert zodra een test hier een 401 geeft. Dan zijn de
    asserties hierboven stil betekenisloos.

    Dat is geen theorie: in dit project is een autouse-fixture die uitzette wat een andere
    test mat 1538 tests lang onopgemerkt gebleven. Zelfde patroon als
    `tests/unit/tool_broker/test_the_executing_identity_has_permission.py::test_the_permission_check_is_not_patched_here`,
    op aanbeveling van de Gate-2-reviewer (org-46).
    """
    from unittest.mock import Mock

    from src.core.auth.oauth2_service import OAuth2Service, oauth2_service

    methode = type(oauth2_service).is_jti_revoked
    assert not isinstance(methode, Mock), (
        "`is_jti_revoked` is in deze testomgeving gepatcht. Dan kan geen enkele assertie in "
        "dit bestand nog aantonen dat een ingetrokken token wordt geweigerd (ADR-036 OP-188)."
    )
    assert methode is OAuth2Service.is_jti_revoked, (
        "`is_jti_revoked` is vervangen door iets anders dan de echte methode."
    )
