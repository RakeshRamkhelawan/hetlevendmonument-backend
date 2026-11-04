"""ActivePieces tenant utilities -- AP project ID lookup for a given tenant."""

from __future__ import annotations

from src.core.activepieces.verbinding import ap_verbinding_voor


async def get_tenant_ap_project(tenant_id: int) -> str:
    """Return the ActivePieces project ID of the given tenant.

    Komt uit de verbinding van die tenant (`ap_verbinding_voor`). Een tenant zonder verbinding of
    project krijgt een `ApVerbindingOntbreektError`: er is GEEN terugval op `str(tenant_id)`, het
    eerste project van de server of een algemene standaard (ADR-040 B4).
    """
    return (await ap_verbinding_voor(tenant_id)).project_id


AP_TIMEOUT = 3.0


async def fetch_live_connections(tenant_id: int) -> list[dict[str, object]]:
    """De app-verbindingen in het ActivePieces-project van DEZE tenant.

    Gaat via `ActivePiecesClient` met de verbinding van de tenant (ADR-040 B6: een toegangsweg).
    Faalt LUID: een tenant zonder verbinding geeft `ApVerbindingOntbreektError`, en een
    onbereikbare server of een time-out van 3 s geeft de fout zelf. De aanroeper beslist wat
    "geen antwoord" betekent -- deze functie verzint geen lege lijst, want die is niet te
    onderscheiden van "deze klant heeft geen enkele verbinding".
    """
    import asyncio

    from src.core.activepieces.client import ap_client_voor

    client = await ap_client_voor(tenant_id)
    return await asyncio.wait_for(client.list_app_connections(), timeout=AP_TIMEOUT)
