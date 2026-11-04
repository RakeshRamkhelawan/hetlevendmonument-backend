"""De agentdeur: `_reject_before_council` beoordeelt de INHOUD van de parameters.

**Waarom dit bestand bestaat, en het is een bevinding over mijn eigen werk.** Bij de eerste
versie van de InputGuard was de enige bescherming op dit pad een architectuurbewaker die met de
AST kijkt of `beoordeel(...)` ergens in de functie wordt aangeroepen. Een Gate 2-reviewer heeft
gemeten dat zo'n bewaker GROEN blijft bij drie mutaties die de wachter effectief uitzetten:

    de aanroep blijft, maar `if not oordeel.toegestaan:` wordt `if False:`   -> GROEN
    de aanroep wordt `logger.info(beoordeel(...))`, weigering weg            -> GROEN
    `beoordeel("")` in plaats van de echte parameters                        -> GROEN

Mijn twaalf mutaties toetsten VERWIJDEREN (weghalen, uitcommentarieren). Ze toetsten niet
NEUTRALISEREN, en dat is de goedkopere en waarschijnlijkere regressie. Voor de chatdeur was er
wel een gedragstest (`tests/unit/copilot/test_service.py::TestInputGuardOpDeChatdeur`); voor dit
pad was er NIETS. `git grep` over `tests/` vond geen enkele test die een BSN door
`_reject_before_council` stuurde.

Dit bestand meet daarom het GEDRAG: gaat er een weigering uit, en gaat een gewone payload door.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

TENANT = 1

#: Geldig volgens de elfproef. Een willekeurig negencijferig getal haalt die niet en zou deze
#: tests hol maken; een getal dat hem WEL haalt maar zonder contextwoord staat, wordt met opzet
#: doorgelaten (zie `test_een_getal_zonder_contextwoord_gaat_door`).
BSN = "123456782"
IBAN = "NL91ABNA0417164300"


def _agent() -> object:
    """De echte piloot-skill, met een verantwoordelijke mens erop.

    Zonder initiator weigert `_reject_before_council` op de TWEEDE grond (AI Act art. 14) en
    zou elke assertie hieronder groen zijn om de verkeerde reden -- de klassieke holle test.
    """
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

    agent = SkillsGapTrainingSkill(tenant_id=TENANT)
    agent._initiated_by_user_id = 42
    return agent


class TestDeAgentdeurWeigertOpInhoud:
    def test_een_bsn_met_contextwoord_in_de_parameters_wordt_geweigerd(self) -> None:
        agent = _agent()

        reden = agent._reject_before_council(  # type: ignore[attr-defined]
            "query_hr_database", {"role": f"BSN {BSN}"}
        )

        assert reden is not None, (
            "De parameters bevatten een BSN en de deur laat ze door. Dit pad is de enige plek "
            "waar de waarden nog zichtbaar zijn: de Council krijgt alleen de argumentNAMEN."
        )
        assert "bsn" in reden
        assert BSN not in reden, (
            "De weigering citeert het BSN terug. Die tekst belandt in `result_data['errors']` "
            "en dus in de leeropslag."
        )

    def test_een_waarde_in_een_geneste_structuur_wordt_ook_geweigerd(self) -> None:
        """Het gat dat Gate 2 aanwees: `params` is `json.loads()` van modeloutput.

        De nesting kiest het model dus zelf, en die payload gaat als `ticket_action_params`
        naar `hitl_tickets.payload` -- dat in `tool_broker/redaction.py` als "LIVE en RAUW"
        staat gedocumenteerd.
        """
        agent = _agent()

        reden = agent._reject_before_council(  # type: ignore[attr-defined]
            "schedule_training", {"employees": [{"iban": IBAN}]}
        )

        assert reden is not None
        assert "iban" in reden
        assert IBAN not in reden

    def test_een_gewone_payload_gaat_door(self) -> None:
        """De tegenrichting. Zonder deze test is "weiger alles" een geldige oplossing."""
        agent = _agent()

        reden = agent._reject_before_council(  # type: ignore[attr-defined]
            "query_hr_database", {"role": "Engineer", "limit": 50}
        )

        assert reden is None, f"Een gewone leestool-payload wordt geweigerd: {reden}"

    def test_een_getal_zonder_contextwoord_gaat_door(self) -> None:
        """Een ticketnummer dat de elfproef haalt mag geen tool-actie blokkeren.

        9,12% van willekeurige negencijferige nummers haalt die proef (gemeten over 20.000
        trekkingen), en dit systeem staat vol ticket- en runnummers. Zonder deze test glipt
        een blokkeergrond terug naar binnen die de agentketen onbruikbaar maakt.
        """
        agent = _agent()

        reden = agent._reject_before_council(  # type: ignore[attr-defined]
            "query_hr_database", {"role": f"ticket {BSN}"}
        )

        assert reden is None, f"Een ticketnummer blokkeert een tool-actie: {reden}"

    def test_lege_parameters_zijn_geen_weigering(self) -> None:
        agent = _agent()

        assert agent._reject_before_council("query_hr_database", {}) is None  # type: ignore[attr-defined]
        assert agent._reject_before_council("query_hr_database", None) is None  # type: ignore[attr-defined]
