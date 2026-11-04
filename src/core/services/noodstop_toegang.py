"""De ene ingang van agent_runtime naar de noodstopcontrole (ADR-033: een chokepoint, geen verspreide koppeling).

Elke deur binnen agent_runtime (Council, chat, copilot, workflow-engine, actoren, scheduler van de monitoren)
controleert de stand van de klant via DEZE module, in plaats van elk zelf `src.core.noodstop` te importeren. Dat is
een eerlijke verandering van de vorm, niet van de werking:

- De controle is dezelfde functie: dit zijn alleen namen voor `guard.eis_klant_actief`, `guard.eis_chat_actief`,
  `guard.klant_staat_stil`, `guard.KlantStilgezet` en `metrics.NOODSTOP_GEWEIGERD`. Er zit geen eigen logica, geen
  cache en geen uitzondering in. Elke deur blijft zijn controle zelf AANROEPEN, op de plek waar hij telt; de
  architectuurtest `test_elke_deur_controleert_de_noodstop` bewaakt dat per deur.
- De afhankelijkheid van agent_runtime op `src.core.noodstop` is er nog steeds: ze loopt nu door een rand in plaats
  van tien. De DSM-meter telt de statements, dus Ce daalt; de koppeling zelf verhuist naar een enkele plek die je
  met een blik kunt zien en vervangen.
- `src.core.noodstop.weggegooid` staat er bewust NIET bij: dat laadt de auditdienst en de bypass-sessie, en dat
  hoort niet bij elke deur mee te komen (importcyclus-risico). `cva_tasks.py` importeert hem zelf.

Een nieuwe deur binnen agent_runtime importeert hier, niet uit `src.core.noodstop` (de DSM-test
`test_de_randen_sinds_247_bestaan_nog` en het plafond voor Ce houden dat vast).
"""

from __future__ import annotations

from src.core.noodstop import guard, metrics

KlantStilgezet = guard.KlantStilgezet
eis_klant_actief = guard.eis_klant_actief
eis_chat_actief = guard.eis_chat_actief
klant_staat_stil = guard.klant_staat_stil
NOODSTOP_GEWEIGERD = metrics.NOODSTOP_GEWEIGERD

__all__ = [
    "NOODSTOP_GEWEIGERD",
    "KlantStilgezet",
    "eis_chat_actief",
    "eis_klant_actief",
    "klant_staat_stil",
]
