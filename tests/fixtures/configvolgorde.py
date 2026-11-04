"""De config mag niet gebouwd zijn voordat de testopstelling de omgeving zet (OP-243).

**Waarom dit bestaat en waarom het GEEN regelnummer toetst.**

`UnifiedConfig` wordt via `_ConfigProxy` gebouwd bij het eerste attribuut-gebruik en daarna
gecachet in `_config_instance`. Gebeurt dat voordat `tests/conftest.py` `DATABASE_URL` zet,
dan leest pydantic de env-bestanden, wint `.env.local`, en staat die waarde voor de HELE
sessie vast. Gemeten 2026-09-15: `os.environ["DATABASE_URL"]` wees naar poort 5455 en
`config.database_url` naar 5435, binnen dezelfde run.

De eerste reparatie zette `DATABASE_URL` een regel hoger en bewaakte dat met een AST-guard
op regelnummers. Die guard beschermde de ENE import die we toen kenden -- elke toekomstige
import boven die regel die `config` aanraakt, bevriest hem opnieuw en de guard blijft groen.
Dat is de oorzaak bewaken in plaats van de toestand.

**Wat hier in plaats daarvan staat.** Een controle op de EIGENSCHAP: is de config al
gebouwd op het moment dat wij de omgeving gaan zetten? Die vraag is in elke run te stellen,
ook in een unittestrun zonder database, en hij is onafhankelijk van WELKE import het deed.
Er is niets te ontwijken: wie de config eerder aanraakt, wat dan ook, laat deze controle
afgaan.

**Bewust geen reset erbij.** De ecosysteem-conventie voor een gecachete settings-instantie
is een `cache_clear()` (zie de FastAPI/pydantic-documentatie). Een reset zou hier een
gereedschap zijn om de fout te MASKEREN: de import blijft dan te vroeg staan en wij ruimen
stilletjes achter hem op. De juiste reactie is de import verplaatsen, en daarom faalt dit
luid in plaats van te repareren.
"""

from __future__ import annotations

import types

#: De module die de gecachete instantie vasthoudt. Als string, zodat deze controle die
#: module NIET zelf importeert -- dat zou precies de fout veroorzaken die hij moet vinden.
CONFIG_MODULE = "src.core.config.unified_config"

#: Het attribuut waarin `get_config()` zijn resultaat bewaart (unified_config.py:826).
CACHE_ATTRIBUUT = "_config_instance"


class ConfigTeVroegGebouwd(RuntimeError):
    """De configuratie stond al vast voordat de testopstelling hem kon sturen."""


def controleer_config_nog_niet_gebouwd(modules: dict[str, types.ModuleType]) -> None:
    """Faal als `unified_config` zijn instantie al heeft gebouwd.

    `modules` is `sys.modules` (expliciet meegegeven zodat dit testbaar is zonder de echte
    interpreterstaat te vervuilen).

    Is de module nog niet geimporteerd, dan is er niets gebouwd en is alles in orde -- dat
    is het normale geval.
    """
    module = modules.get(CONFIG_MODULE)
    if module is None:
        return
    if getattr(module, CACHE_ATTRIBUUT, None) is None:
        return

    raise ConfigTeVroegGebouwd(
        f"`{CONFIG_MODULE}.{CACHE_ATTRIBUUT}` is al gevuld voordat de testopstelling "
        f"DATABASE_URL heeft gezet.\n"
        f"\n"
        f"Gevolg: de configuratie staat nu vast op wat de env-bestanden opleverden "
        f"(in de praktijk `.env.local`), en alles wat de conftest hierna zet heeft GEEN "
        f"effect meer. Gemeten 2026-09-15: os.environ wees naar poort 5455 terwijl "
        f"config.database_url naar 5435 wees, binnen dezelfde run (ADR-036 OP-243).\n"
        f"\n"
        f"Oorzaak: een import BOVEN dit punt in `tests/conftest.py` raakt `config` aan. "
        f"Zoek die import op en verplaats hem naar BENEDEN, onder het zetten van de "
        f"omgevingsvariabelen. Los dit NIET op door de cache te legen -- dan blijft de "
        f"import te vroeg staan en ruim je de fout alleen op."
    )
