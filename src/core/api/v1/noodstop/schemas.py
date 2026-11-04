"""Pydantic-schemas voor het `noodstop`-domein (noodstop per klant; ADR-033)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

#: Lengtegrens van de reden. Gelijk aan `tenant_noodstop_models.REDEN_MAX_LENGTE`; een unit-test
#: houdt die twee gelijk. Hier gedefinieerd en niet geimporteerd uit het model, zodat de API-laag
#: geen paar naar de modellaag erbij krijgt in de fan-out-meting van `core_api` (ADR-033).
REDEN_MAX_LENGTE = 500

Reden = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class NoodstopRequest(BaseModel):
    """De noodstop zetten of opheffen. De klant komt uit de JWT, NOOIT uit deze body.

    `extra="forbid"`: een `tenant_id` (of ander veld) in de body wordt niet stilzwijgend genegeerd
    maar geweigerd (422), zodat niemand denkt dat hij een andere klant kan kiezen. De `reden` is
    verplicht, ook bij opheffen: het logboek legt vast wie, wanneer en waarom.
    """

    model_config = ConfigDict(extra="forbid")

    is_stilgezet: bool
    reden: Reden
