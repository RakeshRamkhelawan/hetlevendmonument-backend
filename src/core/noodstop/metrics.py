"""Tellers van de noodstop (noodstop per klant; ADR-036 OP-03).

Een weigering door de noodstop is een bedrijfsgebeurtenis: na het opheffen van een stop wil een
beheerder weten wat er is tegengehouden. Elke teller heeft bewust een LAAG aantal labels (geen
klant-id): per klant staat de uitsplitsing in de auditregels (`noodstop_changed`,
`noodstop_cva_bericht_weggegooid`), de teller geeft het totaalbeeld voor het platform.
"""

from __future__ import annotations

from prometheus_client import Counter

#: Een deur die een stilgezette (of onbekende) klant heeft geweigerd, per deur.
NOODSTOP_GEWEIGERD = Counter(
    "noodstop_geweigerd_total",
    "Aantal keren dat een deur een actie weigerde omdat de klant stilstaat of onbekend is.",
    ["deur"],
)

#: CVA-berichten (Telegram, WhatsApp) die zijn weggegooid omdat de klant stilstond, per kanaal.
CVA_BERICHTEN_WEGGEGOOID = Counter(
    "noodstop_cva_berichten_weggegooid_total",
    "Aantal inkomende CVA-berichten dat onbeantwoord bleef door de noodstop.",
    ["channel"],
)
