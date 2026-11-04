"""Docentenomgeving (BE-EP-055): rollen, eigen klassen, lessen per klas, leerlingprivacy.

Patroon van de andere foundation-unittests: de routefuncties direct aanroepen met een echte
tenant en gebruiker, de sessie gemockt. `public_tenant_scope` levert de tenant van de slug.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.api.v1.foundation import docent
from src.core.models.foundation_content import (
    EducationalRole,
    FoundationTeacherApplication,
    PortalRole,
    PortalUser,
    StudyCollection,
)
from src.core.models.rbac_models import Tenant
from src.core.services import foundation_klas, foundation_leerlingantwoorden as la

pytestmark = [pytest.mark.unit]

_NU = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def _tenant(tenant_id: int = 3) -> Tenant:
    return Tenant(
        id=tenant_id, slug="hetlevendmonument", name="Het Levend Monument", is_active=True
    )


def _gebruiker(
    tenant_id: int = 3, rol: PortalRole = PortalRole.TEACHER, user_id: int = 21
) -> PortalUser:
    return PortalUser(id=user_id, tenant_id=tenant_id, email="juf@school.nl", role=rol)


def _scope(tenant: Tenant) -> MagicMock:
    ctx = AsyncMock()
    ctx.__aenter__.return_value = tenant
    ctx.__aexit__.return_value = None
    return MagicMock(return_value=ctx)


def _uitslag(waarde: object = None, lijst: list[object] | None = None) -> MagicMock:
    resultaat = MagicMock()
    resultaat.scalar_one_or_none.return_value = waarde
    resultaat.scalar.return_value = waarde
    resultaat.scalars.return_value.all.return_value = lijst or []
    resultaat.scalars.return_value.first.return_value = (lijst or [None])[0]
    return resultaat


def _sql(stmt: object) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- rollen


@pytest.mark.asyncio
@pytest.mark.parametrize("rol", [PortalRole.VISITOR, PortalRole.STUDENT])
async def test_een_bezoeker_of_leerling_is_geen_docent(rol: PortalRole) -> None:
    with pytest.raises(HTTPException) as fout:
        await docent.require_docent(user=_gebruiker(rol=rol))
    assert fout.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("rol", [PortalRole.TEACHER, PortalRole.CURATOR, PortalRole.ADMIN])
async def test_docent_curator_en_beheerder_mogen_de_docentenomgeving_in(rol: PortalRole) -> None:
    gebruiker = _gebruiker(rol=rol)
    assert await docent.require_docent(user=gebruiker) is gebruiker


@pytest.mark.asyncio
async def test_een_docent_van_een_andere_tenant_ziet_geen_klassen() -> None:
    with patch.object(docent, "public_tenant_scope", _scope(_tenant(3))):
        with pytest.raises(HTTPException) as fout:
            await docent.mijn_klassen(
                tenantSlug="hetlevendmonument", user=_gebruiker(tenant_id=4), session=AsyncMock()
            )
    assert fout.value.status_code == 403


# --------------------------------------------------------------------------- eigen klassen


@pytest.mark.asyncio
async def test_een_klas_van_een_andere_docent_geeft_404_en_de_query_filtert_op_eigenaar() -> None:
    sessie = AsyncMock()
    sessie.execute.return_value = _uitslag(None)
    with pytest.raises(HTTPException) as fout:
        await docent._eigen_klas(sessie, 3, _gebruiker(user_id=21), klas_id=99)
    assert fout.value.status_code == 404
    sql = _sql(sessie.execute.call_args.args[0])
    assert "study_collections.owner_portal_user_id = 21" in sql
    assert "study_collections.tenant_id = 3" in sql


@pytest.mark.asyncio
async def test_feedback_op_een_antwoord_uit_een_andere_klas_wordt_geweigerd() -> None:
    antwoord = SimpleNamespace(id=5, study_collection_id=77, content_id=7)
    sessie = AsyncMock()
    sessie.execute.side_effect = [_uitslag(antwoord), _uitslag(None)]
    with patch.object(docent, "public_tenant_scope", _scope(_tenant())):
        with pytest.raises(HTTPException) as fout:
            await docent.geef_feedback(
                tenantSlug="hetlevendmonument",
                antwoord_id=5,
                data=docent.FeedbackRequest(feedback="Goed gedaan"),
                user=_gebruiker(),
                session=sessie,
            )
    assert fout.value.status_code == 404
    assert not hasattr(antwoord, "teacher_feedback")


# --------------------------------------------------------------------------- lessen per klas


@pytest.mark.asyncio
async def test_een_oude_klascode_zonder_docent_ziet_alles() -> None:
    sessie = AsyncMock()
    sessie.execute.return_value = _uitslag(lijst=[StudyCollection(id=1, owner_portal_user_id=None)])
    assert await foundation_klas.toegestane_les_ids(sessie, 3, 10) is None


@pytest.mark.asyncio
async def test_een_klas_van_een_docent_ziet_alleen_de_opengezette_lessen() -> None:
    sessie = AsyncMock()
    sessie.execute.side_effect = [
        _uitslag(lijst=[StudyCollection(id=8, owner_portal_user_id=21)]),
        _uitslag(lijst=[7, 9]),
    ]
    assert await foundation_klas.toegestane_les_ids(sessie, 3, 10) == {7, 9}


@pytest.mark.asyncio
async def test_een_klas_van_een_docent_zonder_lessen_ziet_niets_en_niet_alles() -> None:
    sessie = AsyncMock()
    sessie.execute.side_effect = [
        _uitslag(lijst=[StudyCollection(id=8, owner_portal_user_id=21)]),
        _uitslag(lijst=[]),
    ]
    assert await foundation_klas.toegestane_les_ids(sessie, 3, 10) == set()


@pytest.mark.asyncio
async def test_een_leerling_kan_een_dichte_les_niet_openen() -> None:
    ctx = SimpleNamespace(
        tenant=_tenant(), access=SimpleNamespace(id=10, role=EducationalRole.STUDENT)
    )
    with patch.object(docent, "toegestane_les_ids", AsyncMock(return_value={7})):
        with pytest.raises(HTTPException) as fout:
            await docent._werkblad_voor_klas(AsyncMock(), ctx, content_id=8)  # type: ignore[arg-type]
    assert fout.value.status_code == 404


@pytest.mark.asyncio
async def test_een_onbekend_werkblad_bij_lessen_zetten_is_een_fout() -> None:
    sessie = AsyncMock()
    sessie.execute.return_value = _uitslag(lijst=[7])
    with pytest.raises(HTTPException) as fout:
        await docent._geldige_les_ids(sessie, 3, [7, 1234])
    assert fout.value.status_code == 422
    sql = _sql(sessie.execute.call_args.args[0])
    assert "foundation_content.tenant_id = 3" in sql
    assert "'EDU'" in sql or "'edu'" in sql


# --------------------------------------------------------------------------- leerling


@pytest.mark.asyncio
async def test_alleen_een_leerlingcode_slaat_antwoorden_op() -> None:
    ctx = SimpleNamespace(
        tenant=_tenant(), access=SimpleNamespace(id=10, role=EducationalRole.TEACHER)
    )
    with pytest.raises(HTTPException) as fout:
        await docent.sla_antwoorden_op(
            tenantSlug="hetlevendmonument",
            content_id=7,
            data=docent.LeerlingAntwoordRequest(naam="Sam", antwoorden={}),
            x_leerling_token="a" * 32,
            ctx=ctx,  # type: ignore[arg-type]
            session=AsyncMock(),
        )
    assert fout.value.status_code == 403


def test_naam_alleen_voornaam_geen_email_en_niet_te_lang() -> None:
    assert la.schoon_naam("  Sam   de  Vries ") == "Sam de Vries"
    for fout in ["", "   ", "sam@school.nl", "x" * 41]:
        with pytest.raises(la.OngeldigAntwoord):
            la.schoon_naam(fout)


def test_alleen_antwoorden_op_vragen_van_het_werkblad() -> None:
    vragen = [{"sleutel": "vraag-1"}, {"sleutel": "denk-mee"}]
    assert la.schoon_antwoorden({"vraag-1": " Kwaku ", "denk-mee": ""}, vragen) == {
        "vraag-1": "Kwaku"
    }
    with pytest.raises(la.OngeldigAntwoord):
        la.schoon_antwoorden({"wachtwoord": "x"}, vragen)
    with pytest.raises(la.OngeldigAntwoord):
        la.schoon_antwoorden({"vraag-1": "x" * 2001}, vragen)


def test_het_token_wordt_alleen_als_hash_bewaard() -> None:
    token = "b" * 32
    assert la.hash_leerlingtoken(token) != token
    assert len(la.hash_leerlingtoken(token)) == 64


# --------------------------------------------------------------------------- 8 weken


@pytest.mark.asyncio
async def test_antwoorden_ouder_dan_acht_weken_worden_verwijderd() -> None:
    sessie = AsyncMock()
    sessie.execute.return_value = MagicMock(rowcount=2)
    assert await la.verwijder_verlopen_antwoorden(sessie, _NU, tenant_id=3) == 2
    stmt = sessie.execute.call_args.args[0]
    sql = _sql(stmt)
    assert sql.startswith("DELETE FROM foundation_student_answers")
    assert "foundation_student_answers.tenant_id = 3" in sql
    grens = stmt.compile().params
    assert (_NU - timedelta(weeks=8)) in grens.values()


def test_de_bewaartermijn_is_acht_weken() -> None:
    assert la.BEWAARTERMIJN == timedelta(weeks=8)


# --------------------------------------------------------------------------- beheer


@pytest.mark.asyncio
@pytest.mark.parametrize("rol", [PortalRole.ADMIN, PortalRole.CURATOR])
async def test_goedkeuren_verlaagt_nooit_een_hogere_rol(rol: PortalRole) -> None:
    aanvraag = FoundationTeacherApplication(
        id=4, tenant_id=3, email="juf@school.nl", name="Juf", school="De Vlinder", status="pending"
    )
    bestaand = PortalUser(id=21, tenant_id=3, email="juf@school.nl", role=rol)
    sessie = AsyncMock()
    sessie.add = MagicMock()
    sessie.execute.side_effect = [_uitslag(aanvraag), _uitslag(lijst=[bestaand])]
    with (
        patch.object(docent, "public_tenant_scope", _scope(_tenant())),
        patch.object(docent, "_mail", AsyncMock()),
        patch.object(docent, "_portal_url", MagicMock(return_value="https://hetlevendmonument.nl")),
    ):
        await docent.keur_aanvraag_goed(
            tenantSlug="hetlevendmonument",
            aanvraag_id=4,
            user=_gebruiker(rol=PortalRole.ADMIN, user_id=1),
            session=sessie,
        )
    assert bestaand.role == rol
    assert aanvraag.status == "approved"


@pytest.mark.asyncio
async def test_goedkeuren_maakt_een_bezoeker_docent_en_stuurt_een_inloglink() -> None:
    aanvraag = FoundationTeacherApplication(
        id=4, tenant_id=3, email="juf@school.nl", name="Juf", school="De Vlinder", status="pending"
    )
    bezoeker = PortalUser(id=21, tenant_id=3, email="juf@school.nl", role=PortalRole.VISITOR)
    sessie = AsyncMock()
    sessie.add = MagicMock()
    sessie.execute.side_effect = [_uitslag(aanvraag), _uitslag(lijst=[bezoeker])]
    mail = AsyncMock()
    with (
        patch.object(docent, "public_tenant_scope", _scope(_tenant())),
        patch.object(docent, "_mail", mail),
        patch.object(docent, "_portal_url", MagicMock(return_value="https://hetlevendmonument.nl")),
    ):
        await docent.keur_aanvraag_goed(
            tenantSlug="hetlevendmonument",
            aanvraag_id=4,
            user=_gebruiker(rol=PortalRole.ADMIN, user_id=1),
            session=sessie,
        )
    assert bezoeker.role == PortalRole.TEACHER
    assert "inloggen?token=" in " ".join(mail.call_args.args[2])


@pytest.mark.asyncio
async def test_een_afgehandelde_aanvraag_kan_niet_nog_eens() -> None:
    aanvraag = FoundationTeacherApplication(
        id=4, tenant_id=3, email="a@b.nl", name="A", school="S", status="approved"
    )
    sessie = AsyncMock()
    sessie.execute.return_value = _uitslag(aanvraag)
    with pytest.raises(HTTPException) as fout:
        await docent._aanvraag(sessie, 3, 4)
    assert fout.value.status_code == 409


def test_alle_beheerroutes_eisen_de_beheerdersrol() -> None:
    from fastapi.routing import APIRoute

    from src.core.api.v1.foundation.dependencies import require_admin

    beheer = [
        r for r in docent.router.routes if isinstance(r, APIRoute) and r.path.startswith("/admin/")
    ]
    assert len(beheer) == 5
    for route in beheer:
        assert any(d.call is require_admin for d in route.dependant.dependencies), route.path
