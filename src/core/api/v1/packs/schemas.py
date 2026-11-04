"""Pydantic-schemas voor het `packs`-domein (pakket aanzetten, dag 1; ADR-033)."""

from pydantic import BaseModel, ConfigDict

#: Lengtegrens van een catalogus-id (`pack_id`). Gelijk aan de kolomlengte in
#: `tenant_pack_activation_models.PACK_ID_MAX_LENGTE`; een unit-test houdt die twee gelijk. Hier
#: gedefinieerd en niet geimporteerd uit het model, zodat de API-laag geen paar naar de
#: modellaag erbij krijgt in de fan-out-meting van `core_api` (ADR-033).
PACK_ID_MAX_LENGTE = 100


class PackActivationRequest(BaseModel):
    """Een pakket aan- of uitzetten. De klant komt uit de JWT, NOOIT uit deze body.

    `extra="forbid"`: een `tenant_id` (of ander veld) in de body wordt niet stilzwijgend genegeerd
    maar geweigerd (422), zodat niemand denkt dat hij een andere klant kan kiezen.
    """

    model_config = ConfigDict(extra="forbid")

    is_enabled: bool
