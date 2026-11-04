"""AVG-inzage en -export vinden rolwijzigingen OVER een persoon (ADR-039 vervolg).

De auditregel `role_assigned`/`role_revoked` heeft sinds ADR-039 als `user_id` de ACTOR (wie gaf of
nam de rol) en als `resource` de DOELGEBRUIKER (het gewone gebruikersnummer, zo schrijft
`event_handlers._handle_security_audit` het weg). De lezers van `audit_logs` filterden op
`user_id` alleen, dus een persoon die inzage vroeg zag niet dat iemand hem een rol gaf.

Wat gemeten wordt, tegen echte Postgres (netwerkpoort 5455) met de echte lezers:
- A geeft B een rol: B ziet de regel in zijn inzage (audit-trail) EN in zijn export (DSAR);
  A ziet zijn eigen handeling ook.
- Een regel van een andere tenant komt er nooit in, ook niet met dezelfde id's.
- Een ONGERELATEERDE regel waarvan `resource` toevallig dezelfde id draagt (een andere actie)
  telt niet mee: alleen de rolactions.

Wat NIET gemeten wordt: de portabiliteitsroute zelf (`/api/gdpr/export`); die gebruikt dezelfde
filter, bewaakt door `tests/architecture/test_gdpr_inzage_gebruikt_de_gedeelde_auditfilter.py`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text

TENANT = 1
ANDERE_TENANT = 2
ACTOR = 1
DOEL = 101


async def _sql(query: str, **params: Any) -> Any:
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        result = await session.execute(text(query), params)
        await session.commit()
        return result


async def _schrijf(tenant: int, action: str, resource: str, user_id: int) -> int:
    """Een auditregel zoals `_handle_security_audit` hem schrijft (zelfde velden)."""
    from src.core.database.bypass_session import adopt_tenant
    from src.core.database.database import db_manager
    from src.core.governance.audit import AuditService

    async with db_manager.get_session() as session:
        async with adopt_tenant(session, tenant):
            rij = await AuditService.log_action(
                tenant_id=tenant,
                action=action,
                resource=resource,
                user_id=user_id,
                details={"role_name": "goedkeurder", "action": action},
                session=session,
                threat_level="MEDIUM",
                endpoint="SECURITY",
            )
            await session.commit()
            assert rij is not None
            return int(rij.id)


@pytest_asyncio.fixture
async def regels() -> AsyncGenerator[dict[str, int], None]:
    ids = {
        # A (1) geeft B (101) in tenant 1 een rol
        "toewijzing": await _schrijf(TENANT, "role_assigned", str(DOEL), ACTOR),
        # dezelfde vorm in een ANDERE tenant, zelfde id's
        "andere_tenant": await _schrijf(ANDERE_TENANT, "role_assigned", str(DOEL), ACTOR),
        # ongerelateerd: andere actie, resource draagt toevallig hetzelfde nummer
        "ongerelateerd": await _schrijf(TENANT, "workflow_updated", str(DOEL), ACTOR),
    }
    yield ids
    for rij_id in ids.values():
        await _sql("DELETE FROM audit_logs WHERE id = :i", i=rij_id)


async def _inzage(user_id: int) -> set[int]:
    """De audit-trail-inzage (GDPR art. 15) van deze gebruiker in tenant 1."""
    from src.core.api.v1.gdpr_compliance.access_router import _build_audit_query
    from src.core.api.v1.gdpr_compliance.schemas import AuditTrailRequest
    from src.core.database.bypass_session import adopt_tenant
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        async with adopt_tenant(session, TENANT):
            query = _build_audit_query(TENANT, AuditTrailRequest(), user_id)  # type: ignore[arg-type]
            return {int(r.id) for r in (await session.execute(query)).scalars().all()}


async def _export(user_id: int) -> set[int]:
    """De DSAR-export (GDPR art. 20) van deze gebruiker in tenant 1."""
    from src.core.database.bypass_session import adopt_tenant
    from src.core.database.database import db_manager
    from src.core.governance.dsar_service import DSARService

    async with db_manager.get_session() as session:
        async with adopt_tenant(session, TENANT):
            resultaat = await DSARService(session).export_user_data(
                str(user_id), TENANT, requested_by_user_id=str(user_id)
            )
    return {int(r["id"]) for r in resultaat.data["audit_logs"]}


@pytest.mark.integration
@pytest.mark.asyncio
class TestInzageVindtRolwijzigingenOverDePersoon:
    async def test_the_person_who_received_the_role_sees_it_in_the_access_request(
        self, regels: dict[str, int]
    ) -> None:
        assert regels["toewijzing"] in await _inzage(DOEL)

    async def test_the_person_who_gave_the_role_still_sees_their_own_action(
        self, regels: dict[str, int]
    ) -> None:
        assert regels["toewijzing"] in await _inzage(ACTOR)

    async def test_a_line_of_another_tenant_never_appears(self, regels: dict[str, int]) -> None:
        assert regels["andere_tenant"] not in await _inzage(DOEL) | await _inzage(ACTOR)

    async def test_an_unrelated_line_with_the_same_number_in_resource_is_not_about_the_person(
        self, regels: dict[str, int]
    ) -> None:
        assert regels["ongerelateerd"] not in await _inzage(DOEL)


@pytest.mark.integration
@pytest.mark.asyncio
class TestExportVindtRolwijzigingenOverDePersoon:
    async def test_the_person_who_received_the_role_sees_it_in_the_export(
        self, regels: dict[str, int]
    ) -> None:
        assert regels["toewijzing"] in await _export(DOEL)

    async def test_the_person_who_gave_the_role_still_sees_their_own_action_in_the_export(
        self, regels: dict[str, int]
    ) -> None:
        assert regels["toewijzing"] in await _export(ACTOR)

    async def test_a_line_of_another_tenant_never_appears_in_the_export(
        self, regels: dict[str, int]
    ) -> None:
        assert regels["andere_tenant"] not in await _export(DOEL) | await _export(ACTOR)

    async def test_an_unrelated_line_is_not_in_the_export_of_the_person(
        self, regels: dict[str, int]
    ) -> None:
        assert regels["ongerelateerd"] not in await _export(DOEL)
