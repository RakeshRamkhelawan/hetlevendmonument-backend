"""Proefaanroep van Mistral (EU): een kleine toolaanroep en JSON-uitvoer, echt over het netwerk.

Brief: docs/agent-briefs/generated/2026-10-15-sprint-dag-mistral-als-eu-taalmodel.md, besluit 4.

    python scripts/proef_mistral.py [--root <map met het omgevingsbestand>]

Draait ALLEEN als `MISTRAL_API_KEY` gezet is; anders meldt het "niet gemeten, sleutel ontbreekt" en stopt
met exitcode 2, zonder iets te versturen. De sleutel wordt geladen via de app-loader
(`src.core.env_loader.setup_environment`) en komt NOOIT in de uitvoer: het script toont alleen OF hij
gezet is. Dit script is geen test van de suite (het gebruikt het netwerk en kost een paar tokens).

Exitcodes: 0 = beide controles geslaagd, 1 = een controle mislukt, 2 = sleutel ontbreekt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

EXIT_GESLAAGD = 0
EXIT_MISLUKT = 1
EXIT_GEEN_SLEUTEL = 2

TOOL = {
    "name": "geef_weer",
    "description": "Geef het weer voor een stad.",
    "parameters": {
        "type": "object",
        "properties": {"stad": {"type": "string", "description": "Naam van de stad"}},
        "required": ["stad"],
    },
}


def _hoofdmap_van_de_checkout() -> Path:
    """De hoofdmap van de checkout; een worktree deelt het omgevingsbestand met de hoofdmap niet."""
    try:
        uit = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return Path(uit).parent
    except (OSError, subprocess.CalledProcessError):
        return REPO


def laad_sleutel(root: Path | None) -> bool:
    """Laad het omgevingsbestand via de app-loader; zegt alleen OF de sleutel nu gezet is."""
    from src.core.env_loader import setup_environment

    kandidaten = [root] if root else [REPO, _hoofdmap_van_de_checkout()]
    for map_ in kandidaten:
        if os.environ.get("MISTRAL_API_KEY"):
            break
        setup_environment(map_)
    return bool(os.environ.get("MISTRAL_API_KEY"))


async def _proef_toolaanroep(provider: object) -> tuple[bool, str]:
    antwoord = await provider.generate_response(  # type: ignore[attr-defined]
        "",
        messages=[{"role": "user", "content": "Wat is het weer in Utrecht? Gebruik de tool."}],
        tools=[TOOL],
        tool_choice="any",
        max_tokens=100,
    )
    if not antwoord.get("success"):
        return False, f"mislukt: {antwoord.get('error')}"
    oproepen = antwoord.get("function_calls") or []
    geldig = (
        bool(oproepen)
        and oproepen[0].get("name") == "geef_weer"
        and isinstance(oproepen[0].get("args"), dict)
    )
    return (
        geldig,
        f"model={antwoord.get('model')} oproepen={oproepen} tokens={antwoord.get('usage')}",
    )


async def _proef_json(provider: object) -> tuple[bool, str]:
    from src.core.llm.llm_client import LLMMessage

    antwoord = await provider.complete_json(  # type: ignore[attr-defined]
        [
            LLMMessage(
                role="user", content='Geef een JSON-object met de sleutel "ok" en waarde true.'
            )
        ],
        dict,
        max_tokens=50,
    )
    if not antwoord.success:
        return False, f"mislukt: {antwoord.error_message}"
    try:
        data = json.loads(antwoord.content)
    except json.JSONDecodeError:
        return False, "het antwoord is geen geldige JSON"
    return data.get("ok") is True, f"model={antwoord.model} json={data} tokens={antwoord.usage}"


async def proef() -> int:
    from src.core.llm.mistral_provider import MistralProvider

    provider = MistralProvider()
    resultaten = {
        "toolaanroep": await _proef_toolaanroep(provider),
        "json-uitvoer": await _proef_json(provider),
    }
    for naam, (gelukt, detail) in resultaten.items():
        print(f"[{'OK' if gelukt else 'MISLUKT'}] {naam}: {detail}")
    return EXIT_GESLAAGD if all(g for g, _ in resultaten.values()) else EXIT_MISLUKT


def main(argv: list[str] | None = None) -> int:
    ouder = argparse.ArgumentParser(description=__doc__)
    ouder.add_argument("--root", type=Path, default=None, help="map met het omgevingsbestand")
    args = ouder.parse_args(argv)

    if not laad_sleutel(args.root):
        print("niet gemeten: MISTRAL_API_KEY is niet gezet; er is niets verstuurd")
        return EXIT_GEEN_SLEUTEL
    print("MISTRAL_API_KEY: gezet (waarde wordt niet getoond)")
    return asyncio.run(proef())


if __name__ == "__main__":
    sys.exit(main())
