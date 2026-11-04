"""Kan het LOKALE model waar we standaard mee uitleveren een TOOL_CALL afgeven?

Waarom dit bestand bestaat, en waarom het NIET in tests/unit staat
-------------------------------------------------------------------
Sinds 2026-09-20 is Ollama de bodem van de LLM-keten: elke installatie draait hem mee,
zodat klantdata het eigen systeem niet hoeft te verlaten. Die belofte staat of valt bij
een model dat betrouwbaar genoeg is om de agent te laten werken, en het enige wat de
agent van het model nodig heeft is dit: een regel in de vorm

    TOOL_CALL: <naam> {"param": "waarde"}

`tests/unit/als/test_skillsgaptraining_evaluation_set.py` kan die vraag per ontwerp NIET
beantwoorden -- die zet de LLM bewust op een dubbel ("gemockt zodat de set deterministisch
is en geen echte LLM raakt"). Dat is daar de goede keuze: die set meet het HARNAS. Deze
meting gaat over het MODEL, en daarvoor moet er een echt model antwoorden.

Wat er gemeten wordt, en wat niet
---------------------------------
Gemeten: het manifest-systeemprompt gaat naar het draaiende model, het antwoord gaat door
DEZELFDE parser als in productie (`BaseSpecialistAgent._parse_tool_calls`), en er komt een
toegestane toolnaam uit. Niet gemeten: of het antwoord inhoudelijk goed is -- dat is een
andere vraag en hij hoort niet in een poort.

Waarom een drempel en geen harde eis
------------------------------------
Een taalmodel is niet deterministisch. Een enkele run die toevallig goed gaat bewijst niets,
en een enkele run die toevallig misgaat ook niet. Daarom drie monsters met een drempel van
twee. Die drempel is bewust laag: hij beantwoordt "is dit model bruikbaar", niet "is dit
model goed". Zakt hij, dan is het meegeleverde model te klein en moet er een groter model
(en een hogere geheugengrens) komen -- dat is dan een meting en geen mening.

Deze test draait NIET in de blokkerende poort: hij vraagt een draaiende Ollama en hij is
niet deterministisch. Hij draait bewust, met de hand of in een omgeving waar Ollama staat:

    pytest tests/llm -m requires_ollama -v

Hij staat NIET onder tests/integration/: die conftest eist sinds ADR-036 OP-243 een
expliciet aangewezen testdatabase, en deze meting raakt geen database. Een meting die een
Postgres nodig heeft die hij niet gebruikt, wordt nooit gedraaid.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.requires_ollama, pytest.mark.asyncio]

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.environ.get("LOKAAL_MODEL", "gemma4:e4b-it-qat")
MONSTERS = 3
DREMPEL = 2

MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "src/core/als/agents/skills/manifests/skillsgaptraining.yml"
)

# Een taak die zonder tool niet te beantwoorden is: de cijfers zitten in de database.
TAAK = (
    "Welke vaardigheidskloof heeft de rol 'Finance Analyst' binnen deze organisatie? "
    "Gebruik de beschikbare gegevens, verzin niets."
)


def _ollama_bereikbaar() -> str | None:
    """Geeft None als alles er is, anders de reden om over te slaan."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/v1/models", timeout=5) as antwoord:
            data = json.loads(antwoord.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return f"Ollama niet bereikbaar op {OLLAMA_URL}: {type(exc).__name__}"
    namen = {regel.get("id") for regel in data.get("data", [])}
    if MODEL not in namen:
        return f"model {MODEL} ontbreekt; aanwezig: {sorted(n for n in namen if n)}"
    return None


async def test_het_lokale_model_geeft_een_parseerbare_tool_call() -> None:
    """Drie monsters, minstens twee met een toegestane TOOL_CALL."""
    reden = _ollama_bereikbaar()
    if reden:
        pytest.skip(reden)

    from src.core.als.agents.skill_manifest import SkillManifest
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill
    from src.core.services.llm.base import LLMMessage
    from src.core.services.llm.service import LLMService

    manifest = SkillManifest.load(MANIFEST)
    toegestaan = set(manifest.allowed_tools)
    # De parser EN de prompt van de agent zelf, niet een kopie ervan. Gemeten 2026-09-20:
    # de eerste versie van deze meting stuurde `manifest.system_prompt` rechtstreeks, terwijl
    # productie er via `_met_toolnamen()` de toolnamen en een voorbeeld aan toevoegt. Hij
    # meldde daardoor ROOD op een prompt die nergens draait -- een meting die iets anders
    # toetst dan het systeem is geen meting.
    agent = SkillsGapTrainingSkill(tenant_id=1)
    systeemprompt = agent._met_toolnamen(str(agent.config["system_prompt"]))
    llm = LLMService(provider="ollama", model=MODEL, enable_cache=False)

    geslaagd = 0
    antwoorden: list[str] = []
    for _ in range(MONSTERS):
        antwoord = await llm.generate(
            [LLMMessage(role="user", content=f"Task: {TAAK}")],
            system_prompt=systeemprompt,
        )
        tekst = antwoord if isinstance(antwoord, str) else antwoord[0]
        antwoorden.append(tekst)
        calls = agent._parse_tool_calls(tekst)
        if calls and all(naam in toegestaan for naam, _ in calls):
            geslaagd += 1

    assert geslaagd >= DREMPEL, (
        f"model {MODEL} gaf {geslaagd} van {MONSTERS} keer een bruikbare TOOL_CALL "
        f"(drempel {DREMPEL}). Dit model is te klein voor de agentlaag: kies een groter "
        f"model en verhoog de geheugengrens van de ollama-service in docker-compose.yml.\n"
        + "\n---\n".join(antwoorden)
    )
