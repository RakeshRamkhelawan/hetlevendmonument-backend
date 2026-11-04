"""Gedeelde hulpmiddelen voor de voordeur-tests (SP-KLANT-01 dag 1).

Bewust GEEN `test_`-bestand: dit module bevat alleen opstelling, geen assertie.

De opstelling draait over de ECHTE app (`create_test_app()`), echte JWT's die de login
zelf uitgeeft en echte rijen in de test-PostgreSQL. Er is niets verzonnen aan beide kanten
van een vergelijking: de tenant, de rollen en het token komen uit het verzoek zelf, en de
controle leest de rijen terug met een EIGEN, aparte databaseverbinding.

**Wat deze opstelling NIET meet.** De test-PostgreSQL verbindt als `postgres` (tabeleigenaar)
en omzeilt Row Level Security. De isolatie wordt hier dus bewezen aan de applicatiekant (de
tenant komt uit het aangemaakte record, een tweede klant ziet niets van de eerste via de
API), NIET door de database. De meting onder de applicatierol `sanskritisetu_app` hoort bij
OP-151 en staat in `test_the_application_role_is_confined_to_its_tenant.py`.

**Welke autouse-fixtures raken wat hier gemeten wordt** (gecontroleerd in `tests/conftest.py`
en `tests/integration/conftest.py`):
- `reset_db_per_module` (module, autouse): leegt alles en zaait tenants 1 en 2, de rollen van
  tenant 1 en drie gebruikers. Dat is de BEGINSTAND die de tests hier verwachten; het zet
  niets uit wat gemeten wordt.
- `reset_rate_limiter` (function, autouse): leegt de governance-limiter. De limiter op
  `/auth/register` is `auth_limiter` (slowapi) en wordt daar NIET door geraakt; `limiters_leeg`
  hieronder leegt hem per test, zodat een test niet de teller van een vorige erft. De
  snelheidstest zelf doet zijn hele salvo binnen een test, na die reset.
- `enforce_testing_env`, `_reset_global_state`, `reset_cache_singleton`: geen van drieen raakt
  registratie, rollen of tenants.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from tests.fixtures.testdatabase import testdatabase_url

#: Sterk genoeg voor `_Aanmeldgegevens` (hoofdletter, kleine letter, cijfer, >= 8 tekens).
WACHTWOORD = "GeldigWachtwoord1"  # nosec B105 - testwaarde

#: De tenants die `reset_db_per_module` zaait. "Bestaand" betekent in deze tests: deze twee.
BESTAANDE_TENANTS = (1, 2)

_APP: dict[str, Any] = {}
_ENGINE: dict[str, Engine] = {}


def unieke_email(voorvoegsel: str = "klant") -> str:
    return f"{voorvoegsel}-{uuid.uuid4().hex[:10]}@voordeur.example"


def maak_app() -> Any:
    """De echte app, een keer per proces. Geen lifespan: die draait een test zelf waar nodig."""
    if "app" not in _APP:
        from src.main import create_test_app

        _APP["app"] = create_test_app()
    return _APP["app"]


def sql_engine() -> Engine:
    """Aparte, synchrone verbinding om rijen TERUG te lezen, los van de verbinding van de app."""
    if "engine" not in _ENGINE:
        _ENGINE["engine"] = create_engine(testdatabase_url(sync=True), pool_pre_ping=True)
    return _ENGINE["engine"]


def rijen(sql: str, **params: object) -> list[tuple[Any, ...]]:
    with sql_engine().connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql), params).fetchall()]


def een_waarde(sql: str, **params: object) -> Any:
    gevonden = rijen(sql, **params)
    return gevonden[0][0] if gevonden else None


def voer_uit(sql: str, **params: object) -> None:
    with sql_engine().begin() as conn:
        conn.execute(text(sql), params)


def tenant_ids() -> set[int]:
    return {r[0] for r in rijen("SELECT id FROM tenants")}


def tenant_van_gebruiker(email: str) -> list[int]:
    """Alle tenants waarin een gebruiker met dit adres staat (leeg = bestaat nergens)."""
    return [r[0] for r in rijen("SELECT tenant_id FROM users WHERE email = :e", e=email)]


def rolnamen_van_tenant(tenant_id: int) -> set[str]:
    return {r[0] for r in rijen("SELECT name FROM roles WHERE tenant_id = :t", t=tenant_id)}


def rolnamen_van_gebruiker(email: str) -> set[str]:
    return {
        r[0]
        for r in rijen(
            "SELECT r.name FROM user_roles ur "
            "JOIN users u ON u.id = ur.user_id JOIN roles r ON r.id = ur.role_id "
            "WHERE u.email = :e",
            e=email,
        )
    }


def zet_deploymentmodus(monkeypatch: pytest.MonkeyPatch, modus: str) -> None:
    """Zet `DEPLOYMENT_MODE` overal waar hij gelezen kan worden.

    De waarde wordt vandaag EEN KEER bij het importeren gelezen (`src/config.py:15`) en door
    `tenant_middleware` op naam geimporteerd. Een nieuw pad kan hem op dezelfde manier
    importeren, dus patchen we de omgevingsvariabele, `src.config` EN elke geladen
    `src.*`-module die een attribuut `DEPLOYMENT_MODE` heeft.
    """
    monkeypatch.setenv("DEPLOYMENT_MODE", modus)
    for naam, module in list(sys.modules.items()):
        if naam.startswith("src") and module is not None and hasattr(module, "DEPLOYMENT_MODE"):
            monkeypatch.setattr(module, "DEPLOYMENT_MODE", modus, raising=False)


@pytest.fixture
def limiters_leeg() -> Iterator[None]:
    """Leeg de tellers van de limiters die op de voordeur zitten, voor en na de test."""
    from src.core.api.auth.auth_config import auth_limiter
    from src.core.governance.rate_limiter import _rate_limiter

    def leeg() -> None:
        auth_limiter.reset()
        _rate_limiter._requests.clear()

    leeg()
    yield
    leeg()


@pytest.fixture
async def client(limiters_leeg: None) -> Any:
    transport = ASGITransport(app=maak_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def registreer(
    client: AsyncClient,
    email: str,
    *,
    extra_body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> Response:
    """De PUBLIEKE registratie: geen token, alleen wat het formulier stuurt."""
    body: dict[str, object] = {"email": email, "password": WACHTWOORD, "name": "Nieuwe Klant"}
    body.update(extra_body or {})
    return await client.post(
        "/api/v1/auth/register", json=body, headers=headers or {}, params=params or {}
    )


async def log_in(client: AsyncClient, email: str) -> str:
    """Echt inloggen; faalt luid met status en tekst, zodat de rode reden leesbaar is."""
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": WACHTWOORD})
    assert r.status_code == 200, f"inloggen als {email} gaf {r.status_code}: {r.text}"
    return str(r.json()["access_token"])


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
