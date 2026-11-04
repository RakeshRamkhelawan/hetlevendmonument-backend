"""De identiteit die een goedgekeurde HITL-actie uitvoert MOET die tool mogen draaien (OP-103).

**Waarom dit een eigen module is, en dat is de hele bevinding.** Deze asserties stonden in
`tests/unit/test_tool_broker_hitl.py`, en daar staat op regel 39-46 een autouse-fixture:

    @pytest.fixture(autouse=True)
    def _allow_all_tools():
        with patch("src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
                   return_value=True):
            yield

`mock.patch` splitst op de laatste punt: het doel is de KLASSE, en `is_tool_allowed` wordt als
klasse-attribuut vervangen. Dat geldt dus voor elke importeur en voor elke test in dat bestand
-- ook voor een vers `ToolPermissionManager()`-object. De backstop die daar moest bewaken dat
de uitvoerende identiteit de tool mag draaien, kon daardoor NOOIT falen. Een blinde reviewer
zette de identiteit op iets zonder profiel en 1538 tests bleven groen, terwijl in productie elk
HIGH-risk ticket dan een `PermissionError` geeft.

**De faalvorm heeft een naam gekregen: de testopstelling zet uit wat je meet.** Dat is iets
anders dan de vorm die deze reeks tot nu toe kenmerkte ("tekst doorzoeken waar structuur
getoetst moet worden"), en hij is verraderlijker: de assertie ZIET er goed uit en noemt precies
het juiste. Vastgelegd in `.claude/rules/quality-gates.md`.

Gemeten voor deze module is aangemaakt: `tests/unit/tool_broker/conftest.py` heeft exact een
autouse-fixture (`_deterministic_pseudonymisation_key`) en die raakt permissies niet. In
`tests/conftest.py` staan er drie (`enforce_testing_env`, `_reset_global_state`,
`ensure_main_thread_event_loop`), geen van alle over permissies. Deze module is dus echt schoon.

**Bewust de LETTERLIJKE waarde `"copilot"` en niet de constante.** Vergelijk je met
`_UITVOERENDE_IDENTITEIT`, dan beweegt de test mee met wat hij bewaakt: hernoem de constante en
alles blijft groen. De constante wordt hieronder apart vastgepind.

**Mutatietest (2026-08-09, beide richtingen):**
- `_UITVOERENDE_IDENTITEIT` in `hitl_repository.py` op `"admin"` gezet -> ROOD op
  `test_the_executing_identity_is_still_copilot`.
- `"delete_task"` uit het copilot-profiel in `config/tool_permissions.yml` gehaald -> ROOD op
  `test_the_executing_identity_may_run_the_hitl_tools`.
- LEGITIEM: een extra tool aan het copilot-profiel toegevoegd -> GROEN.
- De weigerkant is per constructie de tweede richting: zonder
  `test_an_identity_without_a_profile_is_refused` zou "sta alles toe" een geldige oplossing zijn.
"""

from __future__ import annotations

import pytest

from src.core.tool_broker.permission_manager import ToolPermissionManager

#: De identiteit waaronder een goedgekeurde HITL-actie draait, als LETTERLIJKE waarde.
_VERWACHTE_IDENTITEIT = "copilot"

#: De business-tools die via de HITL-lus goedgekeurd en daarna uitgevoerd worden.
#: `delete_task` is de HIGH-risk tool waar de poort op vuurt.
_HITL_TOOLS = ("delete_task", "update_task", "create_task", "list_tasks")


@pytest.fixture
def manager() -> ToolPermissionManager:
    """Een ECHTE permissiemanager, niet gepatcht. Dat is het hele punt van deze module."""
    return ToolPermissionManager()


def test_the_permission_check_is_not_patched_here(manager: ToolPermissionManager) -> None:
    """Vangnet: draait deze module toch onder een patch, dan zegt de rest niets.

    Zonder deze toets zou het TOEVOEGEN van een `_allow_all_tools`-fixture aan deze map de
    hele module stilletjes betekenisloos maken -- exact de manier waarop de oorspronkelijke
    backstop is gesneuveld, en dan zou de reparatie dezelfde dood sterven als het origineel.
    """
    assert manager.is_tool_allowed("agent_zonder_enig_profiel", "delete_task") is False, (
        "Een identiteit zonder profiel mag `delete_task` blijkbaar wel draaien. Dan is "
        "`is_tool_allowed` in deze testomgeving gepatcht (of de default-deny is weg) en "
        "bewaakt niets in dit bestand nog iets."
    )


def test_an_identity_without_a_profile_is_refused(manager: ToolPermissionManager) -> None:
    """De controle MOET kunnen falen -- anders is 'sta alles toe' een geldige oplossing.

    Dit is de tweede mutatierichting, als test opgeschreven. De reviewers zetten de uitvoerende
    identiteit op `"admin"` respectievelijk `"hitl_approver"`; geen van beide heeft een profiel
    in `config/tool_permissions.yml`.
    """
    for identiteit in ("admin", "hitl_approver", ""):
        assert manager.is_tool_allowed(identiteit, "delete_task") is False, (
            f"{identiteit!r} mag `delete_task` uitvoeren terwijl er geen profiel voor bestaat. "
            "De default-deny is dan weg, en elke identiteit kan elke goedgekeurde actie draaien."
        )


def test_the_executing_identity_may_run_the_hitl_tools(manager: ToolPermissionManager) -> None:
    """De echte kant: `copilot` moet de tools mogen die via HITL worden goedgekeurd."""
    geweigerd = [
        tool for tool in _HITL_TOOLS if not manager.is_tool_allowed(_VERWACHTE_IDENTITEIT, tool)
    ]

    assert not geweigerd, (
        f"{_VERWACHTE_IDENTITEIT!r} mag deze goedgekeurde tools NIET uitvoeren: {geweigerd}. "
        "Een mens keurt dan een actie goed die daarna stilzwijgend op de default-deny strandt: "
        "het ticket is verbruikt, er is een auditregel, en er is niets gebeurd (ADR-036 OP-103)."
    )


def test_the_executing_identity_is_still_copilot() -> None:
    """De constante vastgepind op de letterlijke waarde.

    `hitl_router` voert uit onder `_UITVOERENDE_IDENTITEIT`, en `create_hitl_request` toetst bij
    het AANMAKEN de permissies van diezelfde constante (OP-90). Loopt die naam weg van het
    profiel in `config/tool_permissions.yml`, dan toetst de ene controle iets anders dan er
    gebeurt -- en beide blijven groen als de test met de constante meebeweegt.
    """
    from src.core.tool_broker.hitl_repository import _UITVOERENDE_IDENTITEIT

    assert _UITVOERENDE_IDENTITEIT == _VERWACHTE_IDENTITEIT, (
        f"De uitvoerende identiteit is {_UITVOERENDE_IDENTITEIT!r} geworden in plaats van "
        f"{_VERWACHTE_IDENTITEIT!r}. Bestaat er een profiel met die naam in "
        "`config/tool_permissions.yml`? Zo niet, dan strandt elke goedgekeurde actie."
    )
