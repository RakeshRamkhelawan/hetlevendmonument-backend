"""`orient()` moet de systeemprompt uit het manifest gebruiken (ADR-036 OP-10).

**De bevinding.** Elke skill declareert een `system_prompt` in zijn manifest, en
`SkillManifest.to_config()` zet die in de agentconfiguratie. Maar `orient()` in
`BaseSpecialistAgent` bouwt zijn eigen prompt uit `config["name"]` en
`config["description"]` en NEGEERT `config["system_prompt"]` volledig.

Gemeten op de basiscommit van deze wijziging (`python` over de AST van
`src/core/als/agents/skills/*.py`):

  * 135 manifesten, 135 skillbestanden, alle 135 erven van `BaseSpecialistAgent`;
  * 0 skills overschrijven `orient()`;
  * 1 skill (`skillsgaptraining`, de piloot) heeft een eigen pad
    `execute_with_manifest_prompt()` dat de manifestprompt WEL gebruikt;
  * 134 skills lopen dus uitsluitend via `orient()` en draaien met een prompt die hun
    zorgvuldig geschreven instructietekst niet bevat.

Dat is niet alleen verspilde configuratie: de manifestprompt draagt het TOOL_CALL-contract
en de instructie om nooit gegevens te verzinnen. Zonder die tekst kan een skill de
afgesproken toolsyntaxis niet kennen.

**Waarom achter de canary.** De wijziging raakt alle 134 skills tegelijk -- precies het
soort big-bang dat OP-02 aan de manifestkant net heeft afgeschaft. Hij rolt daarom uit via
hetzelfde mechanisme: `src.core.shared.rollout`, met een percentage dat zonder deploy te
wijzigen is.

De tests hieronder gebruiken een ECHTE skill (`TalentAcquisitionSkill`, een van de 134) en
de ECHTE `orient()`. De LLM wordt vervangen door een opvanger op de INSTANTIE
(`agent.llm = ...`), niet door een patch op de klasse: een klassepatch zou ook elke andere
test in dit bestand raken en is precies de constructie die eerder een assertie stilzwijgend
`assert True` maakte.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.als.agents.skills.talentacquisition import TalentAcquisitionSkill

ROLLOUT_ENV = "ORIENT_MANIFEST_PROMPT_ROLLOUT_PERCENTAGE"

# Een zin die ALLEEN in de manifestprompt staat en niet in de tekst die orient() zelf in
# elkaar zet. Gemeten: "Never invent data" komt in alle 135 manifesten voor en
# "Strictly follow the OODA loop." in geen enkel. De twee kenmerken kunnen elkaar dus
# niet per ongeluk dekken.
MANIFEST_KENMERK = "Never invent data"

# Kenmerk van de door orient() zelf gebouwde tekst.
ZELFGEBOUWD_KENMERK = "Strictly follow the OODA loop."

TENANT_BEREIK = range(1, 201)


class _OpvangLLM:
    """Vangt de systeemprompt op die `orient()` naar het model stuurt."""

    def __init__(self) -> None:
        self.system_prompt: str | None = None

    async def generate(self, messages: Any, system_prompt: str | None = None, **kwargs: Any) -> str:
        self.system_prompt = system_prompt
        return "geen tool-calls, alleen tekst"


async def _systeemprompt_voor_tenant(tenant_id: int) -> str:
    """De systeemprompt die `orient()` voor DEZE tenant daadwerkelijk verstuurt."""
    agent = TalentAcquisitionSkill(tenant_id=tenant_id)
    opvang = _OpvangLLM()
    agent.llm = opvang  # type: ignore[assignment]
    await agent.orient({"title": "een taak", "description": "een omschrijving"})
    assert opvang.system_prompt is not None, "orient() heeft het model niet aangeroepen"
    return opvang.system_prompt


def test_de_gekozen_skill_declareert_de_manifestprompt() -> None:
    """Vangnet: zonder deze controle kan de hoofdtest slagen om de verkeerde reden.

    Verdwijnt MANIFEST_KENMERK ooit uit dit manifest, dan meet de hoofdtest niets meer en
    zou hij groen blijven terwijl orient() de manifestprompt weer negeert.
    """
    agent = TalentAcquisitionSkill(tenant_id=1)
    prompt = str(agent.config["system_prompt"])
    assert MANIFEST_KENMERK in prompt, (
        f"Het manifest van talentacquisition bevat {MANIFEST_KENMERK!r} niet meer. "
        "Kies een ander kenmerk, anders toetst deze module niets."
    )
    assert ZELFGEBOUWD_KENMERK not in prompt, (
        "Het manifest bevat nu ook de zin die orient() zelf bouwt; dan kan de test de twee "
        "bronnen niet meer uit elkaar houden."
    )


@pytest.mark.asyncio
async def test_orient_gebruikt_de_manifestprompt_binnen_de_uitrol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bij 100 procent uitrol MOET de manifestprompt in de systeemprompt zitten (OP-10)."""
    monkeypatch.setenv(ROLLOUT_ENV, "100")
    prompt = await _systeemprompt_voor_tenant(1)
    assert MANIFEST_KENMERK in prompt, (
        "orient() stuurde een systeemprompt zonder de tekst uit het manifest, terwijl de "
        "uitrol op 100 procent staat. De 134 niet-piloot-skills draaien dan nog steeds "
        "zonder hun eigen instructies en zonder het TOOL_CALL-contract (ADR-036 OP-10)."
    )


@pytest.mark.asyncio
async def test_orient_houdt_de_oude_prompt_buiten_de_uitrol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bij 0 procent verandert er niets -- de uitrol moet echt een uitrol zijn.

    Zonder deze helft zou "gebruik altijd de manifestprompt" een geldige oplossing zijn, en
    dan is er geen gefaseerde uitrol maar dezelfde big-bang die OP-02 juist afschafte.
    """
    monkeypatch.setenv(ROLLOUT_ENV, "0")
    prompt = await _systeemprompt_voor_tenant(1)
    assert ZELFGEBOUWD_KENMERK in prompt, (
        "Buiten de uitrol hoort orient() zijn oorspronkelijke, zelfgebouwde prompt te "
        "sturen. Die is verdwenen; de wijziging is dus niet gefaseerd."
    )
    assert MANIFEST_KENMERK not in prompt, (
        "Buiten de uitrol kreeg de tenant toch de manifestprompt. Dan staat de canary open "
        "en raakt de wijziging alsnog iedereen tegelijk."
    )


@pytest.mark.asyncio
async def test_een_deel_van_de_tenants_krijgt_de_nieuwe_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bij 5 procent bestaan beide groepen tegelijk -- de kern van een canary.

    Deze test rekent de bucketformule niet na; hij stelt alleen vast dat de splitsing
    bestaat.
    """
    monkeypatch.setenv(ROLLOUT_ENV, "5")

    binnen: list[int] = []
    buiten: list[int] = []
    for tenant_id in TENANT_BEREIK:
        prompt = await _systeemprompt_voor_tenant(tenant_id)
        if MANIFEST_KENMERK in prompt:
            binnen.append(tenant_id)
        elif ZELFGEBOUWD_KENMERK in prompt:
            buiten.append(tenant_id)

    assert binnen, (
        f"Geen enkele van de {len(TENANT_BEREIK)} tenants kreeg de manifestprompt bij 5 "
        "procent uitrol. De wijziging bereikt niemand."
    )
    assert buiten, "Alle tenants kregen de manifestprompt. Dat is geen canary maar een big-bang."
    assert len(binnen) + len(buiten) == len(TENANT_BEREIK), (
        "Sommige tenants kregen geen van beide herkenbare prompts."
    )
