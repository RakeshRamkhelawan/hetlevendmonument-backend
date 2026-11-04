"""Bewijs van scheiding met TWEE ECHTE ActivePieces-containers (ADR-040 B3, brief dag 2).

Twee tenants, elk met een eigen AP-container (de lokale image 0.92.1, ingebouwde database,
geheugenwachtrij, willekeurige geheimen per run, alleen op 127.0.0.1). Elke tenant krijgt via
`ApVerbindingBeheer` zijn eigen verbinding in de database, en de echte `ActivePiecesClient` praat
met zijn eigen container. Gemeten wordt wat een klant kan zien en raken:

- tenant A ziet alleen de flows van A, tenant B alleen die van B;
- het flow-id van B via de verbinding van A geeft 404 (dat id bestaat daar niet);
- het project-id van B in een verzoek van A geeft 403 en er wordt niets aangemaakt;
- tenant A kan in de container van B niets lezen of raken.

Dit is lokaal en niets wordt uitgerold (interlock 2). Wordt overgeslagen zonder werkende docker.
Vereist ook de testdatabase op poort 5455 (`postgres_session`).
"""

from __future__ import annotations

import secrets
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import jwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.activepieces.client import ap_client_voor
from src.core.activepieces.verbinding import (
    ApProjectIsNietVanDezeKlantError,
    ApRessourceNietGevondenError,
)
from src.core.activepieces.verbinding_beheer import ApVerbindingBeheer
from src.core.models.rbac_models import Tenant
from src.core.repositories.tenant_ap_verbinding_repository import TenantAPVerbindingRepository
from src.core.security.tenant_secret_encryption import TenantSecretEncryption

pytestmark = pytest.mark.integration

_IMAGE = "ghcr.io/activepieces/activepieces:0.92.1"
_SLEUTEL = "Zq3vK8mWp2Xr9TnL5bYc7HfA1dGeJ4sUoI6xNzMwQvE"
_WACHTWOORD = "Wachtwoord-Test-1!"


@dataclass(frozen=True)
class _Ap:
    naam: str
    url: str
    email: str
    project_id: str
    flow_id: str


def _docker_werkt() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _vrije_poort() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _start(letter: str, run: str) -> tuple[str, int]:
    poort = _vrije_poort()
    naam = f"ap-scheiding-{run}-{letter}"
    jwt_geheim = secrets.token_hex(24)
    worker = jwt.encode(
        {"type": "WORKER", "id": secrets.token_hex(8), "iss": "activepieces"},
        jwt_geheim,
        algorithm="HS256",
    )
    subprocess.run(
        [
            "docker", "run", "-d", "--name", naam, "-p", f"127.0.0.1:{poort}:80",
            "-e", "AP_DB_TYPE=PGLITE", "-e", "AP_QUEUE_MODE=MEMORY",
            "-e", f"AP_ENCRYPTION_KEY={secrets.token_hex(16)}",
            "-e", f"AP_JWT_SECRET={jwt_geheim}", "-e", f"AP_WORKER_TOKEN={worker}",
            "-e", "AP_EXECUTION_MODE=UNSANDBOXED", "-e", "AP_TELEMETRY_ENABLED=false",
            "-e", "AP_ENVIRONMENT=prod",
            "-e", f"AP_FRONTEND_URL=http://localhost:{poort}",
            "-e", f"AP_API_URL=http://localhost:{poort}/api",
            _IMAGE,
        ],
        capture_output=True,
        check=True,
        timeout=120,
    )  # fmt: skip
    return naam, poort


def _wacht_tot_klaar(poort: int, naam: str) -> None:
    einde = time.monotonic() + 300
    while time.monotonic() < einde:
        try:
            if httpx.get(f"http://127.0.0.1:{poort}/api/v1/flags", timeout=3).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        if not subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={naam}"], capture_output=True
        ).stdout:
            raise RuntimeError(f"container {naam} is gestopt voor hij antwoordde")
        time.sleep(3)
    raise TimeoutError(f"container {naam} antwoordde niet binnen 5 minuten")


def _richt_in(letter: str, poort: int) -> _Ap:
    basis = f"http://127.0.0.1:{poort}/api/v1"
    email = f"{letter}-{uuid.uuid4().hex[:6]}@example.test"
    aanmelding = httpx.post(
        f"{basis}/authentication/sign-up",
        json={
            "email": email,
            "password": _WACHTWOORD,
            "firstName": letter,
            "lastName": "Test",
            "trackEvents": False,
            "newsLetter": False,
        },
        timeout=60,
    )
    aanmelding.raise_for_status()
    gegevens = aanmelding.json()
    flow = httpx.post(
        f"{basis}/flows",
        json={"displayName": f"flow-van-{letter}", "projectId": gegevens["projectId"]},
        headers={"Authorization": f"Bearer {gegevens['token']}"},
        timeout=60,
    )
    flow.raise_for_status()
    return _Ap(
        naam=letter,
        url=basis,
        email=email,
        project_id=gegevens["projectId"],
        flow_id=flow.json()["id"],
    )


@pytest.fixture(scope="module")
def twee_ap() -> Iterator[tuple[_Ap, _Ap]]:
    if not _docker_werkt():
        pytest.skip("docker is niet beschikbaar")
    run = uuid.uuid4().hex[:6]
    namen: list[str] = []
    try:
        gestart = []
        for letter in ("a", "b"):
            naam, poort = _start(letter, run)
            namen.append(naam)
            gestart.append((letter, naam, poort))
        for _, naam, poort in gestart:
            _wacht_tot_klaar(poort, naam)
        a, b = (_richt_in(letter, poort) for letter, _, poort in gestart)
        yield a, b
    finally:
        for naam in namen:
            subprocess.run(["docker", "rm", "-f", naam], capture_output=True, timeout=120)


@pytest.fixture(autouse=True)
def _hoofdsleutel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", _SLEUTEL)


async def _tenant_met_verbinding(db: AsyncSession, ap: _Ap) -> int:
    kenmerk = uuid.uuid4().hex[:12]
    tenant = Tenant(name=f"scheiding-{kenmerk}", slug=f"scheiding-{kenmerk}")
    db.add(tenant)
    await db.flush()
    tenant_id = int(tenant.id)
    await ApVerbindingBeheer(
        opslag=TenantAPVerbindingRepository(db), encryptie=TenantSecretEncryption()
    ).leg_vast(
        tenant_id,
        base_url=ap.url,
        email=ap.email,
        wachtwoord=_WACHTWOORD,
        project_id=ap.project_id,
    )
    return tenant_id


@pytest.mark.asyncio
async def test_tenant_a_ziet_alleen_de_flows_van_a(
    twee_ap: tuple[_Ap, _Ap], postgres_session: AsyncSession
) -> None:
    a, b = twee_ap
    tenant_a = await _tenant_met_verbinding(postgres_session, a)
    await _tenant_met_verbinding(postgres_session, b)

    client = await ap_client_voor(tenant_a, postgres_session)
    flows = await client.list_project_flows(a.project_id)

    assert [f["id"] for f in flows] == [a.flow_id]


@pytest.mark.asyncio
async def test_tenant_b_ziet_alleen_de_flows_van_b(
    twee_ap: tuple[_Ap, _Ap], postgres_session: AsyncSession
) -> None:
    a, b = twee_ap
    await _tenant_met_verbinding(postgres_session, a)
    tenant_b = await _tenant_met_verbinding(postgres_session, b)

    client = await ap_client_voor(tenant_b, postgres_session)
    flows = await client.list_project_flows(b.project_id)

    assert [f["id"] for f in flows] == [b.flow_id]


@pytest.mark.asyncio
async def test_het_flow_id_van_b_via_de_verbinding_van_a_geeft_404(
    twee_ap: tuple[_Ap, _Ap], postgres_session: AsyncSession
) -> None:
    a, b = twee_ap
    tenant_a = await _tenant_met_verbinding(postgres_session, a)

    client = await ap_client_voor(tenant_a, postgres_session)

    with pytest.raises(ApRessourceNietGevondenError):
        await client.get_flow(b.flow_id)


@pytest.mark.asyncio
async def test_een_vreemd_flow_id_verwijderen_via_a_geeft_404_en_de_flow_van_b_blijft(
    twee_ap: tuple[_Ap, _Ap], postgres_session: AsyncSession
) -> None:
    a, b = twee_ap
    tenant_a = await _tenant_met_verbinding(postgres_session, a)
    tenant_b = await _tenant_met_verbinding(postgres_session, b)

    client_a = await ap_client_voor(tenant_a, postgres_session)
    with pytest.raises(ApRessourceNietGevondenError):
        await client_a.delete_flow(b.flow_id)

    client_b = await ap_client_voor(tenant_b, postgres_session)
    assert (await client_b.get_flow(b.flow_id))["id"] == b.flow_id


@pytest.mark.asyncio
async def test_het_project_van_b_in_een_verzoek_van_a_geeft_403(
    twee_ap: tuple[_Ap, _Ap], postgres_session: AsyncSession
) -> None:
    a, b = twee_ap
    tenant_a = await _tenant_met_verbinding(postgres_session, a)

    client = await ap_client_voor(tenant_a, postgres_session)

    with pytest.raises(ApProjectIsNietVanDezeKlantError):
        await client.create_flow(b.project_id, {"displayName": "binnengedrongen"})


@pytest.mark.asyncio
async def test_na_een_poging_van_a_staat_er_geen_extra_flow_in_de_container_van_b(
    twee_ap: tuple[_Ap, _Ap], postgres_session: AsyncSession
) -> None:
    a, b = twee_ap
    tenant_a = await _tenant_met_verbinding(postgres_session, a)
    tenant_b = await _tenant_met_verbinding(postgres_session, b)
    client_a = await ap_client_voor(tenant_a, postgres_session)
    with pytest.raises(ApProjectIsNietVanDezeKlantError):
        await client_a.create_flow(b.project_id, {"displayName": "binnengedrongen"})

    client_b = await ap_client_voor(tenant_b, postgres_session)
    flows = await client_b.list_project_flows(b.project_id)

    assert [f["id"] for f in flows] == [b.flow_id]
