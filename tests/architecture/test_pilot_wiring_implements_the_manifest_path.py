"""Elke bedrade piloot-skill MOET het manifest-pad daadwerkelijk implementeren.

Aanleiding (2026-08-15, bottom-up audit van ADR-036). `packs.py::_execute_step` roept
`execute_with_manifest_prompt()` aan op elke skill waarvan het `agent_id` in
`_PILOT_WIRED_AGENT_IDS` staat, achter een `cast(_ManifestPromptSkill, ...)`. Dat cast zet de
typecontrole uit op precies die regel, met als toelichting dat de guard erboven "garandeert"
dat de skill die methode heeft. Die garantie bestond niet: `SkillsGapTrainingSkill` had de
methode nooit, dus elke uitvoering van de piloot liep op een `AttributeError` die door de
brede `except` als "mislukt" werd gerapporteerd. Elf tests legden het gedrag vast en stonden
rood; niemand zag het omdat de CI-poort al een dag eerder afbrak (Any-ratel).

Deze guard maakt de belofte uit dat commentaar toetsbaar: staat een agent in de lijst, dan
implementeert hij de methode -- anders faalt de bedrading hier, en niet pas bij uitvoering in
productie.

MUTATIE-BEWIJS (uitgevoerd 2026-08-15, een regel per bewaakt element):

| Mutatie | Uitkomst |
| --- | --- |
| `execute_with_manifest_prompt` uit `skillsgaptraining.py` gehaald | ROOD |
| een tweede, niet-bestaande agent-id aan `_PILOT_WIRED_AGENT_IDS` toegevoegd | ROOD |
| een bestaande skill ZONDER de methode aan de lijst toegevoegd (`accountsreceivablepayable`) | ROOD |
| TEGENRICHTING: ongewijzigde repo | GROEN |

De derde mutatie is de belangrijkste: hij bootst precies na wat er gebeurt als iemand een
tweede skill bedraadt zonder het manifest-pad te bouwen -- de fout die deze guard bestaat om
te vangen.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

MANIFEST_METHOD = "execute_with_manifest_prompt"


def _skill_classes(agent_id: str) -> list[type]:
    """De skill-klassen in `src/core/als/agents/skills/<agent_id>.py`.

    Zelfde vindwijze als `AgentLoader.get_agent_instance()`: modulenaam uit het agent-id.
    De klassenaam komt daar uit de catalogusconfiguratie; die hoeft hier niet geladen te
    worden, want een module die geen enkele skill-klasse bevat is sowieso niet bedraadbaar.
    """
    module = importlib.import_module(f"src.core.als.agents.skills.{agent_id}")
    return [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if obj.__module__ == module.__name__ and obj.__name__.endswith("Skill")
    ]


@pytest.mark.architecture
def test_every_wired_pilot_skill_implements_the_manifest_path() -> None:
    """Een agent-id in de bedradingslijst zonder de methode is een productiestoring."""
    from src.core.als.enterprise.packs import _PILOT_WIRED_AGENT_IDS

    assert _PILOT_WIRED_AGENT_IDS, (
        "De bedradingslijst is leeg. Dan roept `_execute_step` het manifest-pad nooit aan en "
        "bewaakt deze guard niets meer -- verwijder hem dan bewust, of vul de lijst."
    )

    problemen: list[str] = []
    for agent_id in sorted(_PILOT_WIRED_AGENT_IDS):
        try:
            klassen = _skill_classes(agent_id)
        except ModuleNotFoundError:
            problemen.append(
                f"{agent_id}: er is geen module src/core/als/agents/skills/{agent_id}.py, "
                "dus `get_agent_instance()` valt terug op de basisklasse en die kent het "
                "manifest-pad niet"
            )
            continue

        if not klassen:
            problemen.append(f"{agent_id}: de module bevat geen enkele *Skill-klasse")
            continue

        if not any(hasattr(k, MANIFEST_METHOD) for k in klassen):
            namen = ", ".join(k.__name__ for k in klassen)
            problemen.append(
                f"{agent_id}: geen van de klassen ({namen}) implementeert {MANIFEST_METHOD}"
            )

    assert not problemen, (
        "Deze agents staan in `_PILOT_WIRED_AGENT_IDS` maar kunnen het manifest-pad niet "
        "uitvoeren. `packs.py::_execute_step` roept het toch aan, achter een `cast`, dus dit "
        "eindigt in productie in een AttributeError die als 'mislukt' wordt gerapporteerd:\n"
        + "\n".join(problemen)
    )


@pytest.mark.architecture
def test_the_protocol_and_the_implementation_agree_on_the_signature() -> None:
    """De aanroep in `_execute_step` geeft `initiated_by_user_id` mee als keyword.

    Zonder deze controle kan een implementatie de verantwoordelijke mens als positioneel
    argument verwachten, of helemaal niet -- en dan valt de AI Act art. 14-keten stil op een
    TypeError in plaats van op een weigering.
    """
    from src.core.als.enterprise.packs import _PILOT_WIRED_AGENT_IDS

    for agent_id in sorted(_PILOT_WIRED_AGENT_IDS):
        for klasse in _skill_classes(agent_id):
            methode = getattr(klasse, MANIFEST_METHOD, None)
            if methode is None:
                continue
            parameters = inspect.signature(methode).parameters
            assert "initiated_by_user_id" in parameters, (
                f"{klasse.__name__}.{MANIFEST_METHOD} accepteert geen "
                "`initiated_by_user_id`; `_execute_step` geeft die wel mee."
            )
            assert parameters["initiated_by_user_id"].kind is inspect.Parameter.KEYWORD_ONLY, (
                f"{klasse.__name__}.{MANIFEST_METHOD} neemt `initiated_by_user_id` niet als "
                "keyword-only argument, terwijl de aanroeper hem zo meegeeft."
            )
