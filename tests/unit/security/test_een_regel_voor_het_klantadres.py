"""Een regel voor het adres van de klant: limiet, beveiliging en auditlog lezen hetzelfde adres.

Brief 2026-10-28. Drie plekken bepaalden het adres elk op hun eigen manier (limietsleutel:
rechtse niet-vertrouwde waarde; SecurityMiddleware: N-de van rechts; AuditLoggingMiddleware: de
EERSTE waarde, door de client zelf gekozen). Nu is er een functie, `afzender_adres`, en de twee
middlewares roepen die aan.

Mutatiebewijs: zie de commitboodschap van de commit die dit bestand toevoegt.
"""

from __future__ import annotations

import asyncio
import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.types import Message, Receive, Scope, Send

from src.core.middleware.audit_middleware import AuditLoggingMiddleware
from src.core.shared.limiet_sleutel import afzender_adres, client_adres
from tests.helpers.limiet_request import echte_request

pytestmark = [pytest.mark.unit, pytest.mark.security]

#: Documentatiebereiken zijn GEEN vertrouwde proxy, dus een geloofwaardige "echte klant".
KLANT = "203.0.113.9"
VERZONNEN = "6.6.6.6"
PROXY = "10.0.0.5"
INGRESS = "100.64.0.7"

SRC = Path(__file__).resolve().parents[3] / "src"


@pytest.fixture(autouse=True)
def _geen_instelling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUSTED_PROXY_NETWORKS", raising=False)


def _audit_adres(headers: dict[str, str], peer: str) -> str:
    """Het adres dat de auditmiddleware voor dit verzoek in de auditregel zet."""
    opgeslagen: list[dict[str, object]] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def verstuur(message: Message) -> None:
        return None

    async def ontvang() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/iets",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 1234),
        "state": {},
    }
    middleware = AuditLoggingMiddleware(app)

    async def vang(entry: dict[str, object]) -> None:
        opgeslagen.append(entry)

    with patch.object(middleware, "_write_to_db", AsyncMock(side_effect=vang)):
        asyncio.run(middleware(scope, ontvang, verstuur))
    assert len(opgeslagen) == 1
    return str(opgeslagen[0]["ip_address"])


class TestAuditlogSlaatGeenVervalstAdresOp:
    def test_vervalste_eerste_waarde_komt_niet_in_het_auditlog(self) -> None:
        adres = _audit_adres({"X-Forwarded-For": f"{VERZONNEN}, {KLANT}"}, peer=PROXY)

        assert adres == KLANT

    def test_vervalste_waarde_van_een_openbare_afzender_telt_niet(self) -> None:
        adres = _audit_adres({"X-Forwarded-For": VERZONNEN}, peer=KLANT)

        assert adres == KLANT

    def test_zonder_header_is_het_de_verbinding(self) -> None:
        assert _audit_adres({}, peer=KLANT) == KLANT


class TestEenAdresVoorAlleDrie:
    CASES: list[tuple[dict[str, str], str]] = [
        ({"X-Forwarded-For": f"{VERZONNEN}, {KLANT}"}, PROXY),
        ({"X-Forwarded-For": VERZONNEN}, KLANT),
        ({"X-Forwarded-For": f"{KLANT}, 10.0.0.9"}, PROXY),
        ({}, KLANT),
    ]

    @pytest.mark.parametrize(("headers", "peer"), CASES)
    def test_audit_en_limiet_geven_hetzelfde_adres(
        self, headers: dict[str, str], peer: str
    ) -> None:
        verzoek = echte_request(headers=headers, client_host=peer)

        assert _audit_adres(headers, peer) == afzender_adres(verzoek)

    @pytest.mark.parametrize(("headers", "peer"), CASES)
    def test_limietsleutel_is_dit_adres(self, headers: dict[str, str], peer: str) -> None:
        verzoek = echte_request(headers=headers, client_host=peer)

        assert client_adres(verzoek) == afzender_adres(verzoek)

    def test_beveiligingsmiddleware_heeft_geen_eigen_regel(self) -> None:
        """De middleware roept `afzender_adres` aan en bepaalt het adres niet zelf."""
        boom = ast.parse((SRC / "core/security/security_middleware.py").read_text("utf-8"))
        eigen = [
            n.name
            for n in ast.walk(boom)
            if isinstance(n, ast.FunctionDef)
            and n.name in ("_get_client_ip", "_trusted_proxy_count")
        ]
        aanroepen = [
            n
            for n in ast.walk(boom)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "afzender_adres"
        ]

        assert eigen == [] and len(aanroepen) >= 1

    def test_auditmiddleware_heeft_geen_eigen_regel(self) -> None:
        boom = ast.parse((SRC / "core/middleware/audit_middleware.py").read_text("utf-8"))
        eigen = [
            n.name
            for n in ast.walk(boom)
            if isinstance(n, ast.FunctionDef) and n.name == "_get_client_ip"
        ]

        assert eigen == []


class TestAchterEenVertrouwdeProxy:
    def test_het_door_de_proxy_waargenomen_adres_wint_van_het_proxyadres(self) -> None:
        verzoek = echte_request(headers={"X-Forwarded-For": KLANT}, client_host=PROXY)

        assert afzender_adres(verzoek) == KLANT

    def test_van_rechts_gelezen_met_een_keten_van_proxys(self) -> None:
        verzoek = echte_request(
            headers={"X-Forwarded-For": f"{VERZONNEN}, {KLANT}, 10.0.0.9"}, client_host=PROXY
        )

        assert afzender_adres(verzoek) == KLANT

    def test_een_onbekende_afzender_mag_de_header_niet_sturen(self) -> None:
        verzoek = echte_request(headers={"X-Forwarded-For": VERZONNEN}, client_host=KLANT)

        assert afzender_adres(verzoek) == KLANT

    def test_zonder_client_is_het_unknown(self) -> None:
        verzoek = echte_request()
        verzoek.scope["client"] = None

        assert afzender_adres(verzoek) == "unknown"


class TestDeInstellingVoorVertrouwdeProxys:
    def test_een_ingress_buiten_de_standaardlijst_telt_pas_na_de_instelling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        verzoek = echte_request(headers={"X-Forwarded-For": KLANT}, client_host=INGRESS)
        assert afzender_adres(verzoek) == INGRESS

        monkeypatch.setenv("TRUSTED_PROXY_NETWORKS", "100.64.0.0/10")

        assert afzender_adres(verzoek) == KLANT

    def test_de_standaard_vertrouwt_niets_wat_de_klant_meestuurt(self) -> None:
        verzoek = echte_request(headers={"X-Forwarded-For": VERZONNEN}, client_host=KLANT)

        assert afzender_adres(verzoek) == KLANT

    def test_een_onleesbare_instelling_valt_terug_op_de_standaard_niet_op_alles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TRUSTED_PROXY_NETWORKS", "geen-netwerk")
        verzoek = echte_request(headers={"X-Forwarded-For": VERZONNEN}, client_host=KLANT)

        assert afzender_adres(verzoek) == KLANT

    def test_een_geldig_netwerk_naast_een_ongeldig_telt_wel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TRUSTED_PROXY_NETWORKS", "kapot, 100.64.0.0/10")
        verzoek = echte_request(headers={"X-Forwarded-For": KLANT}, client_host=INGRESS)

        assert afzender_adres(verzoek) == KLANT

    @pytest.mark.parametrize("alles", ["0.0.0.0/0", "::/0", "0.0.0.0/0, ::/0", "128.0.0.0/1"])
    def test_een_netwerk_dat_praktisch_alles_dekt_wordt_geweigerd(
        self, monkeypatch: pytest.MonkeyPatch, alles: str
    ) -> None:
        """Een afzender die tot proxy wordt verklaard laat de client zijn eigen adres kiezen."""
        monkeypatch.setenv("TRUSTED_PROXY_NETWORKS", alles)
        verzoek = echte_request(headers={"X-Forwarded-For": VERZONNEN}, client_host=KLANT)

        assert afzender_adres(verzoek) == KLANT
