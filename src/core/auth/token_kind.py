"""Het soort JWT, gestempeld in de JOSE-header `typ` (OP-182).

Waarom de HEADER en niet een claim in de body: RFC 8725 par. 3.11 ("Use Explicit
Typing") beveelt de `typ`-header aan, en RFC 9068 par. 2.1 maakt het voor access
tokens dwingend -- "JWT access tokens MUST include this media type in the 'typ'
header parameter". Par. 4 van diezelfde RFC eist dat de resource server die waarde
controleert en elke andere weigert. De header valt onder de handtekening, dus hij is
authentiek zodra `decode` is geslaagd.

Waarom niet de bestaande body-claim `type`: die naam is een private claim zonder
registratie, hij botst in dit project met het OAuth2-responseveld `token_type`
("Bearer", 16 plekken in src), en de standaard wijst een ander mechanisme aan.

GEMETEN op 2026-09-11: noch python-jose 3.5.0 noch PyJWT 2.13.0 valideert `typ` bij
het decoderen -- `typ="GARBAGE"` wordt door beide geaccepteerd. De controle moet dus
door ons gebeuren, NA een geslaagde decode.

De waarden staan hier op EEN plek, zodat een typefout niet stil in een fail-open
verandert.
"""

from __future__ import annotations

from enum import Enum


class TokenKind(Enum):
    """Het soort token, zoals gestempeld in de JOSE-header `typ`."""

    ACCESS = "at+jwt"
    REFRESH = "refresh+jwt"

    @property
    def aanvaarde_headerwaarden(self) -> frozenset[str]:
        """Welke `typ`-waarden voor dit soort worden geaccepteerd.

        RFC 9068 par. 4 eist dat BEIDE spellingen worden aanvaard: "The resource
        server MUST verify that the 'typ' header value is 'at+jwt' or
        'application/at+jwt' and reject tokens carrying any other value." Een strikte
        vergelijking met alleen "at+jwt" zou dus een MOET-aanvaarde waarde weigeren.

        Voor REFRESH geldt geen RFC: `refresh+jwt` is een PRIVATE waarde van dit
        project. De `application/`-variant wordt symmetrisch aanvaard omdat een
        JOSE-bibliotheek het voorvoegsel mag toevoegen.
        """
        return frozenset({self.value, "application/" + self.value})


class TokenSoortFout(Enum):
    """De reden waarom een token op zijn soort is geweigerd.

    Apart geteld, want een guard die nooit vuurt ziet er van buiten identiek uit als
    een guard die iemand heeft verwijderd.
    """

    ONTBREEKT = "typ_missing"
    VERKEERD = "typ_mismatch"
