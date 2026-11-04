"""Adapter voor de klantcontext -- de enige doorgang van agents naar `bypass_session`.

ADR-034 verbiedt `src.core.agents` om `src.core.database` rechtstreeks te importeren;
`src/core/agents/adapters/` is de enige toegestane doorgang (ADR-034 s5.5, zelfde
constructie als `redis_capability_cache.py`).

WAAROM DIT BESTAAT
------------------
`seed_agent_registry.py` schrijft in `registered_agents`. Gemeten 2026-09-16 op de
ketendatabase: die tabel heeft `relrowsecurity = t` en een policy. Draait dat script
zonder klantcontext, dan faalt de INSERT zodra `DATABASE_URL` naar `sanskritisetu_app`
wijst -- en de DELETE achter `--clear-existing` raakt dan nul rijen ZONDER foutmelding
(gemeten 2026-09-15).

Het script heeft `adopt_tenant` dus echt nodig. De eerste poging importeerde die
rechtstreeks en brak daarmee het contract "agent_runtime package may not import from the
database layer" (`lint-imports` meldde `Contracts: 8 kept, 1 broken`). Deze adapter is de
route die de architectuur daarvoor aanwijst, in plaats van een uitzonderingsregel in
`.importlinter` die de grens permanent een gat geeft.

Er staat bewust NIETS anders in dit bestand. Elke volgende behoefte aan de databaselaag
vanuit `src.core.agents` is een eigen afweging, geen gratis rit op deze deur.
"""

from __future__ import annotations

from src.core.database.bypass_session import adopt_tenant

__all__ = ["adopt_tenant"]
