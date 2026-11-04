"""Schemas van het `bonnen`-domein (bonlezer dag 4)."""

from pydantic import BaseModel, ConfigDict


class BevestigingInvoer(BaseModel):
    """De (gecorrigeerde) velden van een bon. Bewust GEEN `tenant_id`: die komt uit de JWT.

    `extra="forbid"`: een onbekend veld (ook `tenant_id`) in de body is een 422 in plaats van stil negeren.
    De inhoud van `velden` wordt door `BonBevestiging` aan een vast schema getoetst.
    """

    model_config = ConfigDict(extra="forbid")

    velden: dict[str, object]
