"""Conftest voor de unittests: een unittest opent geen echte verbinding (ADR-036 OP-18).

Dit bestand bestond niet (gemeten 2026-08-31, ook niet op `origin/develop`) en dat was precies
waarom OP-18 open bleef staan: de vier tests die een echte databaseverbinding openden zijn destijds
per stuk gerepareerd, maar er was geen enkele fixture die een vijfde geval zou tegenhouden.

De blokkade zelf, de drie ontwerpkeuzes en het volledige mutatie-bewijs staan in
`tests/fixtures/netwerkblokkade.py`. Hier alleen ophangen -- hetzelfde patroon als
`tests/unit/als/conftest.py` en `tests/unit/agents/conftest.py`, die `tests/fixtures/
agent_governance.py` op dezelfde manier herexporteren. De implementatie staat daar en niet hier,
zodat de tests die deze guard bewaken de exceptie en de uitzonderingslijst kunnen IMPORTEREN:
`tests/unit` is geen package, dus `tests.unit.conftest` is niet importeerbaar.

Bewaakt door `tests/unit/test_geen_echte_verbindingen_in_unittests.py`.

**Blijft weg uit `tests/conftest.py`.** Daar loopt een andere workstream (OP-44: dat bestand heeft
twee keer een `pytest_collection_modifyitems`, waardoor de eerste -- de PostgreSQL-auto-skip --
dood is). De `pytest_configure` hieronder botst NIET met die in `tests/conftest.py`: pytest roept
de hook van ELKE conftest in de keten aan. Dat is juist het verschil met twee definities in
HETZELFDE bestand, waar de tweede de eerste overschrijft.
"""

from collections.abc import Callable

import pytest

from tests.fixtures.db_manager_staat import db_manager_blijft_zoals_hij_was  # noqa: F401
from tests.fixtures.netwerkblokkade import (  # noqa: F401
    blokkeer_echte_verbindingen,
    installeer_verbindingsblokkade,
    registreer_marker,
)


def pytest_configure(config: pytest.Config) -> None:
    """Registreer de opt-out-marker; `addopts` bevat `--strict-markers`."""
    registreer_marker(config)


@pytest.fixture
def procesrecht_voor_de_beslisser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brug de procesrecht-poort van de HITL-routes (ADR-039), alleen waar de test over iets ANDERS gaat.

    De HITL-routes toetsen sinds 2026-10-09 een goedkeurrecht in de database-RBAC
    (`src/core/auth/approval_rights.py`). Tests over zelfgoedkeuring, auditregels of de identiteit
    van de goedkeurder hebben geen database; zij zetten dit expliciet aan met
    `pytestmark = pytest.mark.usefixtures("procesrecht_voor_de_beslisser")`. Bewust NIET autouse:
    een autouse-fixture zou de poort zelf uitzetten voor elke test die hem juist moet meten. Het
    recht zelf staat in `tests/integration/test_goedkeuren_is_een_procesbevoegdheid.py` en
    `tests/unit/auth/test_approval_rights.py`.
    """

    async def _geen_weigering(*args: object, **kwargs: object) -> None:
        return None

    for module in (
        "src.core.api.v1.tool_broker.hitl_router",
        "src.core.api.v1.gatekeeper.gatekeeper_hitl_router",
    ):
        monkeypatch.setattr(f"{module}.require_any_approval_right", _geen_weigering)
    monkeypatch.setattr(
        "src.core.api.v1.tool_broker.hitl_router.require_approval_right_for_tool", _geen_weigering
    )

    async def _geen_filter(*args: object, **kwargs: object) -> None:
        return None

    # `None` = geen filter op tool: de lijst met openstaande tickets blijft hier ongefilterd.
    monkeypatch.setattr(
        "src.core.api.v1.tool_broker.hitl_router.tools_the_user_may_decide", _geen_filter
    )
    monkeypatch.setattr(
        "src.core.api.v1.gatekeeper.gatekeeper_hitl_router.require_approval_right_for_agent",
        _geen_weigering,
    )


@pytest.fixture
def procesrecht_poort(monkeypatch: pytest.MonkeyPatch) -> Callable[[set[str]], None]:
    """Zet de ECHTE procesrecht-poort terug en bepaal welke rechten de beslisser heeft.

    Gebruik: `procesrecht_poort({"receivables:approve"})`. Zonder database: alleen
    `has_approval_right` (de opzoeking in `role_permissions`) wordt vervangen; de mapping actie ->
    recht en de weigering zijn de echte code uit `src/core/auth/approval_rights.py`. Maakt een
    eerder gezette `procesrecht_voor_de_beslisser` ongedaan voor deze test.
    """
    from src.core.auth import approval_rights

    def _stel_in(rechten: set[str]) -> None:
        async def _heeft(db: object, user: object, right: str) -> bool:
            return right in rechten

        monkeypatch.setattr(approval_rights, "has_approval_right", _heeft)
        for module in (
            "src.core.api.v1.tool_broker.hitl_router",
            "src.core.api.v1.gatekeeper.gatekeeper_hitl_router",
        ):
            monkeypatch.setattr(
                f"{module}.require_any_approval_right", approval_rights.require_any_approval_right
            )
        monkeypatch.setattr(
            "src.core.api.v1.tool_broker.hitl_router.require_approval_right_for_tool",
            approval_rights.require_approval_right_for_tool,
        )
        monkeypatch.setattr(
            "src.core.api.v1.tool_broker.hitl_router.tools_the_user_may_decide",
            approval_rights.tools_the_user_may_decide,
        )
        monkeypatch.setattr(
            "src.core.api.v1.gatekeeper.gatekeeper_hitl_router.require_approval_right_for_agent",
            approval_rights.require_approval_right_for_agent,
        )

    return _stel_in
