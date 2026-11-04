"""Het antwoord op "wachtwoord vergeten" is Nederlands en verraadt niet of het adres bestaat (studio-nazorg, brief punt 4).

De API antwoordde Engels ("If the email exists, a reset link has been sent"), terwijl het scherm Nederlands toont. Het antwoord
blijft BEWUST gelijk voor een bestaand adres, een onbekend adres en een fout: een ander antwoord zou verraden welke adressen
bestaan.

Mutatiebewijs (2026-10-27): de laatste return van `forgot_password` teruggezet op de Engelse tekst: 2 rode tests (onbekend
adres/fout en de AST-toets); de tekst van `HERSTEL_ANTWOORD` op Engels gezet: 2 rode tests. De andere kant op: alle drie de
paden (bestaand adres, onbekend adres, fout) moeten slagen met dezelfde constante, anders is "alles weigeren" een oplossing.
"""

from __future__ import annotations

import ast
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.api.auth import router_password
from src.core.api.auth.router_password import HERSTEL_ANTWOORD, forgot_password


def _aanroep() -> object:
    return getattr(forgot_password, "__wrapped__", forgot_password)


def _opzoeker(uitkomst: object):
    @asynccontextmanager
    async def _cm(_db: object):
        resultaat = MagicMock()
        resultaat.one_or_none.return_value = uitkomst
        opzoeker = MagicMock()
        opzoeker.execute = AsyncMock(return_value=resultaat)
        yield opzoeker

    return _cm


async def _vraag(adres: str = "iemand@example.org") -> dict[str, str]:
    return await _aanroep()(  # type: ignore[operator,no-any-return]
        SimpleNamespace(email=adres), MagicMock(), MagicMock(), AsyncMock()
    )


@pytest.mark.asyncio
async def test_een_onbekend_adres_krijgt_het_nederlandse_antwoord() -> None:
    with patch.object(router_password, "pre_auth_lookup", _opzoeker(None)):
        antwoord = await _vraag()

    assert antwoord == HERSTEL_ANTWOORD


@pytest.mark.asyncio
async def test_een_fout_krijgt_hetzelfde_antwoord() -> None:
    def kapot(_db: object) -> object:
        raise RuntimeError("database weg")

    with patch.object(router_password, "pre_auth_lookup", kapot):
        antwoord = await _vraag()

    assert antwoord == HERSTEL_ANTWOORD


@pytest.mark.asyncio
async def test_een_bestaand_adres_krijgt_hetzelfde_antwoord() -> None:
    verstuurd = AsyncMock()

    @asynccontextmanager
    async def aannemen(_db: object, _tenant: object):
        yield

    with (
        patch.object(router_password, "pre_auth_lookup", _opzoeker((7, 1))),
        patch.object(router_password, "get_redis_client", AsyncMock(return_value=MagicMock())),
        patch.object(router_password, "geef_resettoken_uit", AsyncMock(return_value="tok")),
        patch.object(router_password, "_verstuur_herstelmail", verstuurd),
        patch.object(router_password, "adopt_tenant", aannemen),
        patch.object(router_password, "log_security_event", AsyncMock()),
        patch.dict("os.environ", {"FRONTEND_URL": "https://app.example.org", "ENVIRONMENT": "development"}),
    ):
        antwoord = await _vraag()

    assert antwoord == HERSTEL_ANTWOORD


def test_het_antwoord_is_nederlands() -> None:
    assert "herstellink" in HERSTEL_ANTWOORD["message"]


def test_het_antwoord_zegt_niet_dat_het_adres_bestaat() -> None:
    tekst = HERSTEL_ANTWOORD["message"].lower()

    assert tekst.startswith("als dit adres bij ons bekend is")


def test_elke_return_van_de_route_geeft_dezelfde_constante() -> None:
    """Structuur, geen tekst: elk `return` in `forgot_password` is `HERSTEL_ANTWOORD` (geen losse tekst die kan verschillen)."""
    boom = ast.parse(Path(router_password.__file__).read_text(encoding="utf-8"))
    functie = next(
        n for n in ast.walk(boom) if isinstance(n, ast.AsyncFunctionDef) and n.name == "forgot_password"
    )
    returns = [n.value for n in ast.walk(functie) if isinstance(n, ast.Return)]

    assert returns and all(isinstance(r, ast.Name) and r.id == "HERSTEL_ANTWOORD" for r in returns)
