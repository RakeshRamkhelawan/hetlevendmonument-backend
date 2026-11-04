"""Het verschil tussen wat de client BEWEERT en wat de ingress heeft WAARGENOMEN.

ADR-036 OP-111 nazorg. Gemeten op staging 2026-08-29: een kale aanroep van
`/health/ready` gaf 403, en exact dezelfde aanroep met `X-Forwarded-For: 10.0.0.1`
gaf 200. Oorzaak: `_get_client_ip` nam het EERSTE element van `X-Forwarded-For`, en
dat element stuurt de client zelf mee. De Azure Container Apps-ingress voegt het IP
dat hij zelf waarnam er RECHTS aan toe.

Dat ene punt voedt vijf controles in `security_middleware.py`: de IP-allowlist
(regel 116), `blocked_ips` (131), de rate limiter (147), threat detection (163) en
het IP dat in de security-events belandt (233). Een spoofbaar client-IP maakt die
alle vijf omzeilbaar en zet bovendien een door de aanvaller gekozen adres in de
auditregels, waar ADR-019 juist op leunt.

Waarom dit maandenlang onzichtbaar bleef: geen enkele test draaide de ECHTE
`ProductionSecurityManager` met een publiek IP. De bestaande tests toetsen de
brontekst of mocken de manager weg.

Deze tests zijn ROOD geschreven, voor de fix.
"""

from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from src.core.security.security_manager import ProductionSecurityManager
from src.core.security.security_middleware import SecurityMiddleware
from src.core.shared.limiet_sleutel import afzender_adres

# Het adres dat de ingress waarnam tijdens de meting op 2026-08-29.
WAARGENOMEN_IP = "83.84.32.81"
# Wat een aanvaller er links voor plakt om binnen te komen.
VERZONNEN_IP = "10.0.0.1"


@pytest.fixture(autouse=True)
def _ingress_is_een_vertrouwde_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """De directe afzender hieronder (100.64.0.7) is de ingress: een vertrouwde proxy via de instelling."""
    monkeypatch.setenv("TRUSTED_PROXY_NETWORKS", "100.64.0.0/10")


def _verzoek(headers: dict[str, str]) -> Request:
    """Een minimaal HTTP-verzoek met de meegegeven headers."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/health/ready",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("100.64.0.7", 443),
        }
    )


def _middleware() -> SecurityMiddleware:
    return SecurityMiddleware(MagicMock(), enable_security=True)


class TestClientIpBepaling:
    def test_een_verzonnen_eerste_hop_wordt_niet_het_client_ip(self) -> None:
        """De aanvaller schrijft links bij; de ingress voegt rechts toe. Rechts wint.

        Dit is de test die de gemeten 403-naar-200-omzeiling vastlegt.
        """
        verzoek = _verzoek({"X-Forwarded-For": f"{VERZONNEN_IP}, {WAARGENOMEN_IP}"})

        assert afzender_adres(verzoek) == WAARGENOMEN_IP

    def test_meerdere_verzonnen_hops_veranderen_niets(self) -> None:
        """Ook een hele keten verzonnen adressen mag het oordeel niet verschuiven."""
        keten = f"1.2.3.4, {VERZONNEN_IP}, 192.168.1.1, {WAARGENOMEN_IP}"
        verzoek = _verzoek({"X-Forwarded-For": keten})

        assert afzender_adres(verzoek) == WAARGENOMEN_IP

    def test_een_enkele_hop_is_het_waargenomen_ip(self) -> None:
        """Zonder client-header staat er precies een adres, en dat is het echte."""
        verzoek = _verzoek({"X-Forwarded-For": WAARGENOMEN_IP})

        assert afzender_adres(verzoek) == WAARGENOMEN_IP

    def test_zonder_forwarded_header_valt_hij_terug_op_de_verbinding(self) -> None:
        """Geen header betekent direct verkeer: het adres van de verbinding zelf."""
        assert afzender_adres(_verzoek({})) == "100.64.0.7"


class TestAllowlistIsOptIn:
    def test_een_ongezette_allowlist_sluit_geen_publiek_verkeer_buiten(
        self, monkeypatch
    ) -> None:
        """Niets ingesteld hoort 'de ingress bewaakt dit' te betekenen, niet 'iedereen eruit'.

        De oude default (loopback + RFC1918) maakte van 'vergeten in te stellen' een
        stille muur: staging gaf op elk pad 403 en productie zou bij oplevering meteen
        onbereikbaar zijn geweest.
        """
        monkeypatch.delenv("ALLOWED_IP_RANGES", raising=False)

        assert ProductionSecurityManager().is_ip_allowed(WAARGENOMEN_IP) is True

    def test_een_expliciete_allowlist_wordt_wel_gehandhaafd(self, monkeypatch) -> None:
        """Opt-in blijft werken: wie hem invult, krijgt precies wat hij invulde."""
        monkeypatch.setenv("ALLOWED_IP_RANGES", "203.0.113.0/24")
        manager = ProductionSecurityManager()

        assert manager.is_ip_allowed("203.0.113.9") is True
        assert manager.is_ip_allowed(WAARGENOMEN_IP) is False


def _verzoek_met_lijst(headers: list[tuple[str, str]]) -> Request:
    """Zoals `_verzoek`, maar met herhaalbare headers."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/health/ready",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
            "client": ("100.64.0.7", 443),
        }
    )


class TestMeerdereHeadersEnXRealIp:
    """Plan nazorg, deel I punt b: twee gaten in de bepaling van het client-IP (2026-10-08)."""

    def test_alle_x_forwarded_for_headers_worden_samengevoegd(self) -> None:
        """De client stuurt een eigen header; de ingress voegt een TWEEDE header toe.

        Alleen de eerste lezen gaf het verzonnen adres terug. MDN: "It is insufficient to use
        only one of multiple X-Forwarded-For headers".
        """
        verzoek = _verzoek_met_lijst(
            [("X-Forwarded-For", VERZONNEN_IP), ("X-Forwarded-For", WAARGENOMEN_IP)]
        )
        assert afzender_adres(verzoek) == WAARGENOMEN_IP

    def test_x_real_ip_is_geen_terugval(self) -> None:
        """Zonder X-Forwarded-For telt de verbinding, niet een header die de client zet."""
        verzoek = _verzoek_met_lijst([("X-Real-IP", VERZONNEN_IP)])
        assert afzender_adres(verzoek) == "100.64.0.7"
