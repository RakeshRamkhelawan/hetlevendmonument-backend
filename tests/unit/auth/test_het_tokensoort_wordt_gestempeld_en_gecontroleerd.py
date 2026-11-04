"""Het soort JWT wordt gestempeld bij uitgifte en gecontroleerd bij verificatie (OP-182).

Gemeten gat voor deze fix: niets controleerde het soort token, dus een refresh-token --
levensduur zeven dagen, en bij uitloggen niet ingetrokken -- was bruikbaar op elk endpoint
dat een access-token verwacht.

Deze toetsen draaien tegen de ECHTE fabriek en de ECHTE verifier, op een echte sleutel.
Niets wordt gemockt. Dat is de les van `src/core/auth/token_refresh.py:91`: dat pad maakt
een token zonder de verplichte `tenant_id` -- per constructie ongeldig -- en de toetsen
bleven jarenlang groen omdat precies `verify_token` en `create_access_token` waren
vervangen door dubbels.

Mutatiebewijs in BEIDE richtingen: de weigerende kant EN de legitieme kant, zodat
"weiger alles" geen geldige oplossing is.
"""

from __future__ import annotations

import inspect

import pytest
from jose import jwt as jose_jwt

from src.core.auth.jwt_handler import JWTHandler
from src.core.auth.token_kind import TokenKind, TokenSoortFout

GELDIGE_LADING = {"sub": "iemand@example.com", "tenant_id": 1}


@pytest.fixture
def handler() -> JWTHandler:
    return JWTHandler()


class TestDeStempel:
    def test_een_access_token_draagt_at_jwt(self, handler: JWTHandler) -> None:
        """RFC 9068 par. 2.1: een access token MOET dit mediatype in `typ` dragen."""
        token = handler.create_access_token(dict(GELDIGE_LADING))
        assert jose_jwt.get_unverified_header(token)["typ"] == "at+jwt"

    def test_een_refresh_token_draagt_refresh_jwt(self, handler: JWTHandler) -> None:
        """Private waarde: RFC 9068 zegt niets over refresh tokens."""
        token = handler.create_refresh_token(dict(GELDIGE_LADING))
        assert jose_jwt.get_unverified_header(token)["typ"] == "refresh+jwt"

    def test_de_stempel_zit_in_de_HEADER_en_niet_in_de_body(self, handler: JWTHandler) -> None:
        """De header valt onder de handtekening; een body-claim zou een tweede,
        concurrerend mechanisme zijn (RFC 8725 par. 3.12)."""
        token = handler.create_refresh_token(dict(GELDIGE_LADING))
        lading = jose_jwt.get_unverified_claims(token)
        assert "typ" not in lading
        assert "type" not in lading
        assert "token_type" not in lading


class TestDeControle:
    def test_een_access_token_komt_door_het_access_pad(self, handler: JWTHandler) -> None:
        """De legitieme richting. Zonder deze toets is 'weiger alles' een oplossing."""
        token = handler.create_access_token(dict(GELDIGE_LADING))
        assert handler.verify_token(token) is not None

    def test_een_refresh_token_komt_door_het_refresh_pad(self, handler: JWTHandler) -> None:
        """De legitieme richting van de andere kant."""
        token = handler.create_refresh_token(dict(GELDIGE_LADING))
        assert handler.verify_token(token, expected_kind=TokenKind.REFRESH) is not None

    def test_een_refresh_token_wordt_op_het_access_pad_GEWEIGERD(
        self, handler: JWTHandler
    ) -> None:
        """Dit is het gat dat OP-182 beschrijft."""
        token = handler.create_refresh_token(dict(GELDIGE_LADING))
        assert handler.verify_token(token) is None
        assert handler.soortfouten.get(TokenSoortFout.VERKEERD) == 1

    def test_een_access_token_wordt_op_het_refresh_pad_GEWEIGERD(
        self, handler: JWTHandler
    ) -> None:
        """De omgekeerde richting: RFC 8725 par. 3.12 eist dat de regels elkaar
        WEDERZIJDS uitsluiten, niet alleen in een richting."""
        token = handler.create_access_token(dict(GELDIGE_LADING))
        assert handler.verify_token(token, expected_kind=TokenKind.REFRESH) is None

    def test_een_token_zonder_typ_wordt_geweigerd(self, handler: JWTHandler) -> None:
        """Fail-secure, zonder terugvalvenster: er is geen productiedata en er zijn geen
        klanten, dus de kosten van de harde knip zijn een keer opnieuw inloggen."""
        kaal = jose_jwt.encode(
            {**GELDIGE_LADING, "exp": 9999999999},
            handler.secret_key,
            algorithm=handler.algorithm,
            headers={"typ": None},
        )
        assert handler.verify_token(kaal) is None
        assert handler.soortfouten.get(TokenSoortFout.ONTBREEKT) == 1

    def test_een_token_met_een_onzin_typ_wordt_geweigerd(self, handler: JWTHandler) -> None:
        """GEMETEN op 2026-09-11: python-jose 3.5.0 en PyJWT 2.13.0 accepteren
        `typ="GARBAGE"` bij het decoderen. Deze controle is dus van ons, niet van de
        bibliotheek."""
        rommel = jose_jwt.encode(
            {**GELDIGE_LADING, "exp": 9999999999},
            handler.secret_key,
            algorithm=handler.algorithm,
            headers={"typ": "GARBAGE"},
        )
        assert handler.verify_token(rommel) is None

    def test_de_application_spelling_wordt_AANVAARD(self, handler: JWTHandler) -> None:
        """RFC 9068 par. 4: de resource server MOET `at+jwt` EN `application/at+jwt`
        aanvaarden. Een strikte vergelijking met alleen de korte vorm zou een
        MOET-aanvaarde waarde weigeren."""
        lang = jose_jwt.encode(
            {**GELDIGE_LADING, "exp": 9999999999},
            handler.secret_key,
            algorithm=handler.algorithm,
            headers={"typ": "application/at+jwt"},
        )
        assert handler.verify_token(lang) is not None


class TestDeVormVanDeApi:
    """De vorm zelf is dragend: een default op de verkeerde plek IS het gat."""

    def test_de_fabriek_heeft_GEEN_soort_parameter(self) -> None:
        """Twee fabrieken in plaats van een parameter met een default. Een parameter kan
        een aanroeper vergeten; een tweede functienaam niet."""
        parameters = inspect.signature(JWTHandler.create_access_token).parameters
        assert "kind" not in parameters
        assert "token_kind" not in parameters
        assert "soort" not in parameters
        assert "create_refresh_token" in dir(JWTHandler)

    def test_expected_kind_is_keyword_only_en_staat_standaard_op_ACCESS(self) -> None:
        """De default moet ACCESS zijn, niet iets permissiefs. Vergeet een aanroeper op
        het refresh-pad hem, dan wordt een refresh-token daar GEWEIGERD -- luid, en in de
        veilige richting. Deze toets pint dat vast zodat niemand er later een
        doorlaat-waarde van maakt."""
        parameter = inspect.signature(JWTHandler.verify_token).parameters["expected_kind"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is TokenKind.ACCESS

    def test_er_zijn_precies_twee_soorten(self) -> None:
        """Groeit dit, dan hoort daar een bewuste wijziging bij en niet een stille."""
        assert {k.value for k in TokenKind} == {"at+jwt", "refresh+jwt"}


class TestDeTenantInHetRefreshToken:
    """De tweede helft van OP-182: elk refresh-token zette de gebruiker in tenant 1.

    `_create_refresh_token` had `tenant_id: int = 1` als default en werd aangeroepen
    ZONDER tenant. Een gebruiker van organisatie 7 kreeg dus een refresh-token dat zei
    dat hij bij organisatie 1 hoorde -- en `verify_token` leest die claim en gebruikt
    hem.
    """

    def test_de_fabriek_heeft_geen_stille_tenant_default(self) -> None:
        """Een default op een tenant is een stille aanname over bij wie iemand hoort."""
        from src.core.auth.oauth2_service import OAuth2Service

        parameter = inspect.signature(OAuth2Service._create_refresh_token).parameters[
            "tenant_id"
        ]
        assert parameter.default is inspect.Parameter.empty

    @pytest.mark.asyncio
    async def test_het_refresh_token_draagt_de_tenant_van_de_gebruiker(self) -> None:
        """De legitieme richting, tegen de echte fabriek: geen mock van de tokenmaker."""
        from src.core.auth.oauth2_service import OAuth2Service

        dienst = OAuth2Service()
        tokens = await dienst.create_tokens(
            user_id=42, email="iemand@example.com", tenant_id=7
        )

        lading = jose_jwt.get_unverified_claims(tokens["refresh_token"])
        assert lading["tenant_id"] == 7, lading
        assert jose_jwt.get_unverified_header(tokens["refresh_token"])["typ"] == "refresh+jwt"

    @pytest.mark.asyncio
    async def test_het_access_token_uit_dezelfde_uitgifte_is_een_ACCESS_token(self) -> None:
        """Beide tokens komen uit een aanroep; ze mogen niet hetzelfde soort dragen."""
        from src.core.auth.oauth2_service import OAuth2Service

        tokens = await OAuth2Service().create_tokens(
            user_id=42, email="iemand@example.com", tenant_id=7
        )

        assert jose_jwt.get_unverified_header(tokens["access_token"])["typ"] == "at+jwt"
        assert jose_jwt.get_unverified_header(tokens["refresh_token"])["typ"] == "refresh+jwt"
