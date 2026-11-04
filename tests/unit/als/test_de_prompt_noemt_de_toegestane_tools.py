"""Het model moet de toolnamen ZIEN, niet ernaar verwezen krijgen.

Gemeten 2026-09-20. De manifest-prompt zei "You may use only the tools listed under
allowed_tools in your manifest", maar geen van de zes namen stond in die tekst. Tegen een
echt model (llama3.2:3b via Ollama) leverde dat drie van de drie keer een verzonnen
toolnaam op -- `databroker.get-organisaties`, `get_department_training` -- en zelfs een
eigen directive-vorm (`DATA_REQUEST:`). Na het toevoegen van de namen noemde hetzelfde
model wel de echte tool met geldige JSON.

Dit is geen kosmetische bewaker: zonder de namen kan GEEN enkel model kiezen, hoe groot ook,
en dan is de hele toolbrug onbereikbaar terwijl elke unit-test groen blijft -- die zetten de
LLM immers op een dubbel.

Mutatietest (2026-09-20), gedraaid met `scripts/mutation_harness.py`, beide richtingen:
1. `namen` hard op `[]` gezet, zodat de helper teruggeeft wat hij kreeg -> ROOD.
2. `namen[:-1]` gerenderd, dus vijf van de zes namen -> ROOD op de zesde. Deze tweede
   mutatie is de belangrijke: richting 1 alleen zou ook groen blijven bij een guard die
   slechts toetst DAT er iets is toegevoegd, in plaats van dat ELKE naam erin staat.
3. Ongewijzigd -> GROEN, en `test_de_bewaker_heeft_iets_te_toetsen` bewijst dat de
   toolverzameling niet leeg is; bij een lege lijst zou richting 1 vanzelf groen zijn.
"""

from __future__ import annotations

import pytest


def _skill() -> object:
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

    return SkillsGapTrainingSkill(tenant_id=1)


def test_de_bewaker_heeft_iets_te_toetsen() -> None:
    """Een lege toolverzameling zou de test hieronder betekenisloos maken."""
    agent = _skill()
    assert agent.allowed_tools, "de piloot-skill declareert geen tools -- dan toetst de volgende test niets"


def test_elke_toegestane_tool_staat_letterlijk_in_de_systeemprompt() -> None:
    """Elke naam uit allowed_tools komt voor in de prompt die naar het model gaat."""
    agent = _skill()
    prompt = agent._met_toolnamen(str(agent.config["system_prompt"]))

    ontbreekt = [naam for naam in agent.allowed_tools if naam not in prompt]

    assert not ontbreekt, (
        "Deze toegestane tools staan NIET in de systeemprompt, dus het model kan ze niet "
        f"kiezen en gaat namen verzinnen: {ontbreekt}"
    )


def test_een_lege_toollijst_laat_de_prompt_met_rust() -> None:
    """Zonder tools geen lijstje -- 'je mag deze tools gebruiken: (niets)' nodigt uit tot verzinnen."""
    agent = _skill()
    agent.allowed_tools = []  # type: ignore[attr-defined]
    origineel = "Doe iets nuttigs."

    assert agent._met_toolnamen(origineel) == origineel
