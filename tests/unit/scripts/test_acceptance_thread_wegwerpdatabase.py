"""`scripts/acceptance_thread.py` schrijft alleen in een herkenbare WEGWERPDATABASE (harde poort, eis 2/6).

Brief `docs/agent-briefs/generated/2026-10-14-sprint-dag-harde-poort-eis-3-en-6-overnemen.md`.
Stap 5 en stap 7 (en `--seed`) maken rijen aan in de database uit `DATABASE_URL` en wissen ze weer.
Tot 2026-10-14 deed het script dat zonder te controleren WAT voor database dat was, en slikte het
fouten in de opruimstap in (`except Exception: pass`): een mislukte opruiming liet wegwerprijen in
een echte database achter zonder dat iemand het zag.

Wat deze tests bewaken:

1. `controleer_wegwerp_database`: een lokale database met `test`, `wegwerp`, `acceptance`,
   `acceptatie`, `scratch` of `tmp` als deel van de naam (gescheiden door `_` of `-`) mag; alles
   anders weigert, ook een ontwikkel- of productienaam, een niet-lokale host en een naam die zo'n
   woord alleen als deel van een ander woord bevat (`latest`).
2. Stap 5, stap 7 en `--seed` weigeren bij zo'n URL, ZONDER een verbinding te proberen.
3. De opruiming meldt een fout in plaats van hem in te slikken.
4. Er staat in het hele script geen `except ...: pass` meer.

Mutatiebewijs (2026-10-14): staat in het verslag bij de oplevering; per test de mutatie die hem
rood maakt en een legitiem geval dat groen blijft.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "acceptance_thread.py"


def _laad_bestand(naam: str, pad: Path) -> ModuleType:
    """Laad een script via zijn pad en registreer het onder `naam`.

    `import scripts.x` werkt hier niet: `tests/unit/scripts/__init__.py` schaduwt de echte map
    `scripts/`. Registreren onder `naam` zorgt dat `acceptance_thread.py` DEZELFDE module krijgt
    (en dus dezelfde uitzonderingsklasse) als deze test.
    """
    spec = importlib.util.spec_from_file_location(naam, pad)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[naam] = module
    spec.loader.exec_module(module)
    return module


_wegwerp = _laad_bestand("wegwerp_database", REPO_ROOT / "scripts" / "wegwerp_database.py")
GeenWegwerpDatabase = _wegwerp.GeenWegwerpDatabase
controleer_wegwerp_database = _wegwerp.controleer_wegwerp_database

WEGWERP_URL = (
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/sanskritisetu_acceptatie_wegwerp"
)
ECHTE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5435/sanskritisetu"

TOEGESTAAN = [
    WEGWERP_URL,
    "postgresql+asyncpg://postgres:postgres@localhost:5455/sanskritisetu_test",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5455/avgc_test",
    "postgresql://u:p@[::1]:5432/scratch-acceptance",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/TEST",
]

GEWEIGERD = [
    ECHTE_URL,
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5455/sanskritisetu",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/sanskritisetu_dev",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/sanskritisetu_prod",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/latest",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/contest_data",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/",
    "postgresql+asyncpg://postgres:postgres@db.voorbeeld.nl:5432/sanskritisetu_test",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1.voorbeeld.nl:5432/sanskritisetu_test",
    "sqlite:///wegwerp_test.db",
    "dit is geen url",
    "",
    # Een queryparameter wint van host en databasenaam (asyncpg: `opts.update(url.query)`): de
    # controle ziet `localhost/x_test`, de verbinding gaat naar een andere server (Gate 2, security).
    "postgresql+asyncpg://u:p@localhost/x_test?host=db.intern.example&database=sanskritisetu",
    "postgresql+asyncpg://u:p@localhost/x_test?dbname=sanskritisetu",
    "postgresql+asyncpg://u:p@localhost/x_test?hostaddr=10.0.0.5",
    "postgresql+asyncpg://u:p@localhost/x_test?service=productie",
    "postgresql+asyncpg://u:p@localhost/x_test?ssl=disable",
]


@pytest.mark.parametrize("url", TOEGESTAAN)
def test_a_recognisable_throwaway_database_is_allowed(url: str) -> None:
    assert controleer_wegwerp_database(url)


@pytest.mark.parametrize("url", GEWEIGERD)
def test_anything_else_is_refused(url: str) -> None:
    with pytest.raises(GeenWegwerpDatabase):
        controleer_wegwerp_database(url)


def test_the_refusal_names_the_database_but_never_the_password() -> None:
    with pytest.raises(GeenWegwerpDatabase) as fout:
        controleer_wegwerp_database(
            "postgresql+asyncpg://postgres:geheimwachtwoord@127.0.0.1:5435/sanskritisetu"
        )

    tekst = str(fout.value)
    assert "sanskritisetu" in tekst and "geheimwachtwoord" not in tekst


def _laad(monkeypatch: pytest.MonkeyPatch, url: str) -> ModuleType:
    """Laad het script als module met een nagemaakte DATABASE_URL, zonder neveneffect op andere tests."""
    monkeypatch.setenv("DATABASE_URL", url)
    spec = importlib.util.spec_from_file_location("acceptance_thread_onder_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _geen_verbinding() -> MagicMock:
    """Een `create_async_engine` die de test laat falen als hij wordt aangeroepen."""
    return MagicMock(side_effect=AssertionError("er is een databaseverbinding geprobeerd"))


class TestDeStappenWeigerenZonderWegwerpnaam:
    def test_stage_7_refuses_a_database_without_a_throwaway_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = _laad(monkeypatch, ECHTE_URL)
        stap = mod.Stage(7, "x")

        with patch("sqlalchemy.ext.asyncio.create_async_engine", _geen_verbinding()):
            mod.stage_7_persisted(stap, "ollama")

        assert stap.status == mod.FAIL and "wegwerp" in stap.detail.lower()

    def test_stage_5_refuses_a_database_without_a_throwaway_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = _laad(monkeypatch, ECHTE_URL)
        stap = mod.Stage(5, "x")

        with patch("sqlalchemy.ext.asyncio.create_async_engine", _geen_verbinding()):
            mod.stage_5_gap_query(stap)

        assert stap.status == mod.FAIL and "wegwerp" in stap.detail.lower()

    def test_seeding_refuses_a_database_without_a_throwaway_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = _laad(monkeypatch, ECHTE_URL)
        monkeypatch.setattr(sys, "argv", ["acceptance_thread.py", "--seed"])

        # Zaaien opent een databaseverbinding; `_geen_verbinding` laat de test falen als dat gebeurt.
        with patch("sqlalchemy.ext.asyncio.create_async_engine", _geen_verbinding()):
            uitkomst = mod.main()

        assert uitkomst == 2

    def test_the_refusal_does_not_print_the_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mod = _laad(
            monkeypatch, ECHTE_URL.replace("postgres:postgres", "postgres:geheimwachtwoord")
        )
        stap = mod.Stage(7, "x")

        with patch("sqlalchemy.ext.asyncio.create_async_engine", _geen_verbinding()):
            mod.stage_7_persisted(stap, "ollama")

        assert "geheimwachtwoord" not in stap.detail

    def test_the_refusal_tells_how_to_fix_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Gate 2: de standaard-URL (`make test-db-up`, naam `sanskritisetu`) wordt nu geweigerd."""
        mod = _laad(monkeypatch, ECHTE_URL)
        stap = mod.Stage(7, "x")

        with patch("sqlalchemy.ext.asyncio.create_async_engine", _geen_verbinding()):
            mod.stage_7_persisted(stap, "ollama")

        assert "SANSKRITISETU_TEST_DATABASE_URL" in stap.detail and "createdb" in stap.detail

    def test_a_throwaway_database_lets_stage_7_go_on_to_the_database(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De andere kant: een wegwerpnaam wordt NIET geweigerd; stap 7 gaat dan naar de database."""
        mod = _laad(monkeypatch, WEGWERP_URL)
        stap = mod.Stage(7, "x")
        initialiseer = AsyncMock(return_value=False)

        with patch("src.core.database.database.initialize_database", initialiseer):
            mod.stage_7_persisted(stap, "ollama")

        initialiseer.assert_awaited_once()
        assert stap.status == mod.SKIP


class TestDeOpruimingSlaatEenFoutNietOver:
    def _fabriek(self, uitvoering: AsyncMock) -> Any:
        sessie = MagicMock()
        sessie.execute = uitvoering
        sessie.commit = AsyncMock()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=sessie)
        context.__aexit__ = AsyncMock(return_value=False)
        fabriek = MagicMock(return_value=context)
        fabriek.sessie = sessie
        return fabriek

    def test_a_failing_cleanup_raises_instead_of_being_swallowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = _laad(monkeypatch, WEGWERP_URL)
        fabriek = self._fabriek(AsyncMock(side_effect=RuntimeError("deadlock")))

        with pytest.raises(mod._OpruimFout) as fout:
            asyncio.run(mod._voer_opruiming_uit(fabriek, ["DELETE 1"]))

        assert "deadlock" in str(fout.value) and "achtergebleven" in str(fout.value)

    def test_the_original_error_stays_visible_when_the_cleanup_fails_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gate 2: een mislukte opruiming verving de oorspronkelijke fout in de melding."""
        mod = _laad(monkeypatch, WEGWERP_URL)
        fabriek = self._fabriek(AsyncMock(side_effect=RuntimeError("deadlock")))

        async def stap() -> None:
            try:
                raise RuntimeError("oorspronkelijke fout")
            finally:
                await mod._voer_opruiming_uit(fabriek, ["DELETE 1"])

        with pytest.raises(mod._OpruimFout) as fout:
            asyncio.run(stap())

        assert "oorspronkelijke fout" in str(fout.value) and "deadlock" in str(fout.value)

    def test_a_working_cleanup_runs_every_statement_and_commits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = _laad(monkeypatch, WEGWERP_URL)
        uitvoering = AsyncMock()
        fabriek = self._fabriek(uitvoering)

        asyncio.run(mod._voer_opruiming_uit(fabriek, ["DELETE 1", "DELETE 2"]))

        assert uitvoering.await_count == 2
        fabriek.sessie.commit.assert_awaited_once()


def test_the_script_has_no_silent_except_handler() -> None:
    """Geen enkele `except ...: pass` in het hele script (de opruimstap slikte fouten in)."""
    boom = ast.parse(SCRIPT.read_text(encoding="utf-8"))

    stil = [
        n.lineno
        for n in ast.walk(boom)
        if isinstance(n, ast.ExceptHandler) and all(isinstance(s, ast.Pass) for s in n.body)
    ]

    assert stil == [], f"stille except-handlers op regel {stil}"
