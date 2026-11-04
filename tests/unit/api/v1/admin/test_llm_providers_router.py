"""De routerlaag van het klantprovider-beheer: statuscodes, auditspoor en de body-grens.

**Waarom dit bestand bestaat.** Er was geen enkele test op deze laag, en precies dat liet de
zwaarste Gate 2-bevinding passeren: alle drie de `log_security_event`-aanroepen gaven geen `db`
mee, dus `audit_service.py:188-190` keerde meteen terug en er werd NOOIT een `AuditLog`-rij
geschreven -- terwijl de routerdocstring en de feature-spec allebei beweerden dat er een
auditspoor ontstond. Alles was groen. Dat is het patroon waar CLAUDE.md voor waarschuwt: code
die niets doet en er in elk dashboard uitziet als code die werkt.

De test die dat vangt is `test_elke_audit_aanroep_krijgt_de_database_mee`. Hij toetst het
ARGUMENT en niet of er "iets gelogd is" -- een assertie op "de mock is aangeroepen" zou ook
groen zijn gebleven bij de kapotte versie.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.admin import dependencies as facade
from src.core.api.v1.admin import llm_providers_router as router_module

from src.core.api.v1.admin.dependencies import LLM_PROVIDER_VOLGORDE_CONSTRAINT as CONSTRAINT

GEHEIM = "sk-" + "q" * 20
ADRES = "https://api.voorbeeld-leverancier.example/v1"


class _NepSessie:
    """Genoeg om als `db` door te geven, en hij TELT de commits.

    Die telling is geen bijvangst: de tweede Gate 2-ronde mat dat de auditregel wel werd
    geschreven maar daarna werd teruggedraaid, omdat `log_security_event` alleen flusht en
    `get_db` bij een `HTTPException` een rollback doet. Zonder een expliciete commit bestond
    het spoor van precies de twee weigeringen niet.
    """

    def __init__(self) -> None:
        self.commits = 0

    async def rollback(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


class _NepService:
    """Doet alsof; elke test zegt zelf welke uitkomst de servicelaag geeft."""

    def __init__(self, uitkomst: Any = 7) -> None:
        self.uitkomst = uitkomst
        self.aanroepen: list[dict[str, Any]] = []

    async def configureer(self, tenant_id: int, **velden: Any) -> int:
        self.aanroepen.append({"tenant_id": tenant_id, **velden})
        if isinstance(self.uitkomst, Exception):
            raise self.uitkomst
        return int(self.uitkomst)

    async def toon(self, _tenant_id: int) -> list[Any]:
        return list(self.uitkomst) if isinstance(self.uitkomst, list) else []


class _Overzicht:
    def __init__(self, heeft_sleutel: bool) -> None:
        self.id = 1
        self.volgorde = 1
        self.naam = "leverancier"
        self.base_url = ADRES
        self.model = "m"
        self.heeft_sleutel = heeft_sleutel
        self.actief = True


@pytest.fixture
def auditregels(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Vangt wat er NAAR de auditlaag gaat, inclusief het `db`-argument."""
    opgevangen: list[dict[str, Any]] = []

    async def _vang(**kwargs: Any) -> None:
        opgevangen.append(kwargs)

    # Op de FACADE gepatcht en niet op de router: de helper die `db` meegeeft woont daar, en
    # dat is precies het gedrag dat getoetst moet worden.
    monkeypatch.setattr(facade, "log_security_event", _vang)
    return opgevangen


def _client(
    monkeypatch: pytest.MonkeyPatch,
    service: Any,
    tenant_id: int = 42,
    sessie: _NepSessie | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router_module.router)
    sessie = sessie or _NepSessie()

    # Via SimpleNamespace en niet via een klasse in deze functie: een klasse-body ziet de
    # lokale variabelen van de omsluitende functie NIET (geen closure), dus `tenant_id`
    # zou daar naar zichzelf verwijzen en een NameError geven.
    gebruiker = SimpleNamespace(id=99, tenant_id=tenant_id)
    app.dependency_overrides[facade.require_admin_role] = lambda: gebruiker
    app.dependency_overrides[facade.get_db] = lambda: sessie
    monkeypatch.setattr(router_module, "bouw_llm_provider_service", lambda _db: service)
    monkeypatch.setattr(router_module, "_resolve_tenant_id", lambda _u: tenant_id)
    return TestClient(app)


def _body(**overschrijf: Any) -> dict[str, Any]:
    basis = {
        "volgorde": 1,
        "naam": "leverancier",
        "base_url": ADRES,
        "model": "m",
        "api_key": GEHEIM,
        "actief": True,
    }
    basis.update(overschrijf)
    return basis


# ------------------------------------------------------------------ het auditspoor


def test_elke_audit_aanroep_krijgt_de_database_mee(
    monkeypatch: pytest.MonkeyPatch, auditregels: list[dict[str, Any]]
) -> None:
    """Zonder `db` schrijft `log_security_event` NIETS weg -- alleen een logregel.

    Dit is de test die de zwaarste bevinding van Gate 2 vangt. Hij toetst het argument, niet
    dat er iets is aangeroepen.
    """
    client = _client(monkeypatch, _NepService(uitkomst=7))

    antwoord = client.post("/admin/llm-providers", json=_body())

    assert antwoord.status_code == 201
    assert auditregels, "er is helemaal geen auditregel geschreven"
    for regel in auditregels:
        assert regel.get("db") is not None, f"{regel.get('event_type')} kreeg geen database mee"


def test_de_auditregel_van_een_WEIGERING_wordt_VASTGELEGD(
    monkeypatch: pytest.MonkeyPatch, auditregels: list[dict[str, Any]]
) -> None:
    """Schrijven is niet hetzelfde als bewaren -- dat was de tweede Gate 2-bevinding.

    `AuditService.log_event` doet alleen `await db.flush()`, en `get_db` doet bij een
    uitzondering `await session.rollback()`. De router gooit op dit pad een `HTTPException`,
    dus de zojuist geschreven regel verdween weer. Uitgerekend op het slaagpad bleef hij wel
    staan (daar commit `get_db` gewoon), en dat verschil maakte het onzichtbaar.

    Deze test telt de commits op de sessie. Een assertie op "de auditfunctie is aangeroepen"
    zou ook groen zijn gebleven bij de kapotte versie -- dat was precies het probleem.
    """
    from src.core.services.tenant_llm_provider_service import ExterneProviderNietToegestaan

    sessie = _NepSessie()
    client = _client(
        monkeypatch, _NepService(uitkomst=ExterneProviderNietToegestaan("nee")), sessie=sessie
    )

    antwoord = client.post("/admin/llm-providers", json=_body())

    assert antwoord.status_code == 403
    assert auditregels, "geen auditregel geschreven"
    assert sessie.commits >= 1, (
        "de auditregel is wel geschreven maar nooit vastgelegd; de rollback van get_db "
        "gooit hem daarna weg"
    )


def test_het_auditpad_is_het_pad_waarop_de_router_echt_hangt(
    monkeypatch: pytest.MonkeyPatch, auditregels: list[dict[str, Any]]
) -> None:
    """De router wordt zonder `/api/v1`-voorvoegsel gemount.

    Een forensisch spoor met een niet-bestaand pad erin is minder waard dan geen spoor, want
    het leest als waarheid.
    """
    client = _client(monkeypatch, _NepService(uitkomst=7))

    client.post("/admin/llm-providers", json=_body())

    assert {regel["request_path"] for regel in auditregels} == {"/admin/llm-providers"}


def test_de_auditregel_bevat_de_sleutel_NIET(
    monkeypatch: pytest.MonkeyPatch, auditregels: list[dict[str, Any]]
) -> None:
    """Een auditregel is precies het soort plek waar een geheim onbedoeld belandt."""
    client = _client(monkeypatch, _NepService(uitkomst=7))

    client.post("/admin/llm-providers", json=_body())

    assert GEHEIM not in str(auditregels)


def test_een_weigering_wordt_geauditeerd_VOOR_het_antwoord(
    monkeypatch: pytest.MonkeyPatch, auditregels: list[dict[str, Any]]
) -> None:
    """Een beheerder die adressen aftast hoort een spoor achter te laten."""
    from src.core.services.tenant_llm_provider_service import ExterneProviderNietToegestaan

    client = _client(monkeypatch, _NepService(uitkomst=ExterneProviderNietToegestaan("nee")))

    antwoord = client.post("/admin/llm-providers", json=_body())

    assert antwoord.status_code == 403
    assert [r["event_type"] for r in auditregels] == ["LLM_PROVIDER_EXTERN_GEWEIGERD"]


def test_een_geweigerd_adres_wordt_geauditeerd(
    monkeypatch: pytest.MonkeyPatch, auditregels: list[dict[str, Any]]
) -> None:
    client = _client(monkeypatch, _NepService(uitkomst=ValueError("SSRF blocked: nee")))

    antwoord = client.post("/admin/llm-providers", json=_body())

    assert antwoord.status_code == 400
    assert [r["event_type"] for r in auditregels] == ["LLM_PROVIDER_ADRES_GEWEIGERD"]


# ------------------------------------------------------------------ statuscodes


def test_een_dubbele_volgorde_geeft_409_en_geen_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twee providers op dezelfde plek in de keten is een botsing, geen defect."""
    from sqlalchemy.exc import IntegrityError

    botsing = IntegrityError(
        "stmt", {}, Exception(f'duplicate key value violates unique constraint "{CONSTRAINT}"')
    )
    client = _client(monkeypatch, _NepService(uitkomst=botsing))

    antwoord = client.post("/admin/llm-providers", json=_body())

    assert antwoord.status_code == 409
    assert "volgorde" in antwoord.json()["detail"]


def test_een_ANDERE_integriteitsfout_wordt_GEEN_409(monkeypatch: pytest.MonkeyPatch) -> None:
    """De tegenrichting, en ze is belangrijker dan ze lijkt.

    Zonder deze test is "vang IntegrityError -> 409 volgorde al in gebruik" een geldige
    oplossing, en dan wordt elke verwijderde tenant, elke NOT NULL-schending en elke constraint
    die er in fase 2b bijkomt aan de aanvrager gemeld als een invoerfout die hij kan oplossen.
    Een defect als invoerfout wegschrijven is erger dan een 500, want er blijft niets van over.
    """
    from sqlalchemy.exc import IntegrityError

    anders = IntegrityError(
        "stmt", {}, Exception('insert violates foreign key constraint "fk_tenant"')
    )
    client = _client(
        monkeypatch,
        _NepService(uitkomst=anders),
    )

    with pytest.raises(IntegrityError):
        client.post("/admin/llm-providers", json=_body())


def test_zonder_hoofdsleutel_geeft_503_met_uitleg(monkeypatch: pytest.MonkeyPatch) -> None:
    """503 en niet 500: dit is een ontbrekende configuratie, geen defect."""
    from src.core.security.tenant_secret_encryption import HoofdsleutelOntbreekt

    def _weiger(_db: Any) -> Any:
        raise HoofdsleutelOntbreekt("niet gezet")

    client = _client(monkeypatch, _NepService())
    monkeypatch.setattr(router_module, "bouw_llm_provider_service", _weiger)

    antwoord = client.post("/admin/llm-providers", json=_body())

    assert antwoord.status_code == 503
    assert "MASTER_ENCRYPTION_KEY" in antwoord.json()["detail"]


def test_een_te_zwakke_hoofdsleutel_geeft_OOK_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """`HoofdsleutelTeZwak` erft van `HoofdsleutelOntbreekt`; die overerving is de rem.

    Zonder haar zou een zwakke sleutel een kale 500 geven waar een ontbrekende sleutel een
    nette 503 met uitleg geeft, terwijl het voor de beheerder dezelfde situatie is.
    """
    from src.core.security.tenant_secret_encryption import HoofdsleutelTeZwak

    def _weiger(_db: Any) -> Any:
        raise HoofdsleutelTeZwak("te kort")

    client = _client(monkeypatch, _NepService())
    monkeypatch.setattr(router_module, "bouw_llm_provider_service", _weiger)

    assert client.post("/admin/llm-providers", json=_body()).status_code == 503


# ------------------------------------------------------------------ de body-grens


def test_een_tenant_id_in_de_body_wordt_GEWEIGERD(monkeypatch: pytest.MonkeyPatch) -> None:
    """`extra="forbid"`: weigeren en niet stilzwijgend negeren.

    Stil negeren is veilig maar misleidend -- de aanvrager denkt dat hij een tenant koos. Dit
    is bovendien de verdediging die CVE-2026-59823 had voorkomen: daar kwam een genest
    configuratieveld langs de controle heen.
    """
    client = _client(monkeypatch, _NepService(uitkomst=7))

    antwoord = client.post("/admin/llm-providers", json=_body(tenant_id=1))

    assert antwoord.status_code == 422


def test_de_tenant_komt_uit_het_token_en_niet_uit_de_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backend-patterns regel 1, hier op het MECHANISME getoetst."""
    service = _NepService(uitkomst=7)
    client = _client(monkeypatch, service, tenant_id=4242)

    client.post("/admin/llm-providers", json=_body())

    assert service.aanroepen[0]["tenant_id"] == 4242


# ------------------------------------------------------------------ het leesendpoint


def test_het_leesantwoord_bevat_geen_sleutel_maar_wel_of_er_een_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """De sleutel is write-only; het antwoord zegt alleen OF er een staat."""
    client = _client(monkeypatch, _NepService(uitkomst=[_Overzicht(heeft_sleutel=True)]))

    antwoord = client.get("/admin/llm-providers")

    assert antwoord.status_code == 200
    rij = antwoord.json()["data"][0]
    assert rij["heeft_sleutel"] is True
    assert "api_key" not in rij
    assert "api_key_encrypted" not in rij


def test_het_leesendpoint_pagineert(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backend-patterns regel 5 vraagt limit/offset op elk list-endpoint."""
    rijen = [_Overzicht(heeft_sleutel=False) for _ in range(5)]
    client = _client(monkeypatch, _NepService(uitkomst=rijen))

    antwoord = client.get("/admin/llm-providers", params={"limit": 2, "offset": 1})

    lichaam = antwoord.json()
    assert len(lichaam["data"]) == 2
    assert lichaam["meta"] == {"total": 5, "limit": 2, "offset": 1}
