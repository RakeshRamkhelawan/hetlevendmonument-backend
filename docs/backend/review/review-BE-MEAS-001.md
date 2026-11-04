STATUS: APPROVED WITH MINOR GAPS
Zelfreview. De knip is klein in regels (een lijst uitbreiden plus een bewaker) maar raakt het
instrument waarop de prioriteiten van de hele testcampagne rusten, dus hij is strenger
behandeld dan zijn omvang suggereert. Twee fouten van mijn hand zijn onderweg gevonden door
het mutatiebewijs en staan hieronder. Drie punten blijven open.

# Review BE-MEAS-001 -- de startpunten

Datum:  2026-09-26
Spec:   `docs/backend/features/BE-MEAS-001-startpunten-dekken-wat-er-draait.md`
Basis:  develop `1d87a070`

---

## Wat deze bevinding bijzonder maakt

De meeste bevindingen in dit project gaan over code die niets doet en `success=True`
teruggeeft. Deze gaat een laag hoger: het INSTRUMENT dat zulke code moet vinden, gaf zelf een
verkeerd antwoord -- en niemand kon dat zien, want een te hoog getal ziet er precies zo uit
als een juist getal.

Het getal stond van 2026-09-20 tot 2026-09-26 exact stil op 859, en dat werd in `CLAUDE.md`
genoteerd als "wat NIET bewoog". Achteraf is dat het signaal dat gemist is: een meting die
door zes sprints heen tot op de eenheid identiek blijft, is verdacht.

## De twee fouten die het mutatiebewijs vond

**Een onbewezen oorzaak in een docstring.** Ik schreef dat de bestandstoets
`src/alembic.ini` wegfiltert. Dat kan niet -- daar staat een schuine streep en de regex eist
een punt, dus die kandidaat ontstaat nooit. Nagemeten: de toets filtert vandaag NIETS weg,
5 kandidaten voor en 5 na. Hij is wel degelijk dragend, maar om een andere reden dan ik
opschreef. Dit is letterlijk wat `.claude/rules/quality-gates.md` verbiedt.

**Een mutatie die niets bewees.** Om aan te tonen dat die toets dragend is, zette ik ruis in
een `#`-comment van de Dockerfile. De scanner slaat commentaarregels over, dus de mutatie
bleef groen en ik had bijna geconcludeerd dat de toets overbodig was. Verplaatst naar een
echte `ENTRYPOINT`-regel, en toen viel het bewijs in twee delen: met de toets groen, zonder
de toets rood.

Beide fouten zaten in de VERANTWOORDING van een regel, niet in de regel zelf. Dat is het
patroon van deze sessie: de code deugde, de reden die ik erbij schreef niet.

## Devil's Advocate -- waarom dit alsnog faalt

**De bewaker kent maar drie bronnen.** Compose, Dockerfile, entrypoint-script, plus de
alembic-afleiding. Start iemand een proces via een cronjob op de host, een Azure Container
App-configuratie in `infra/`, een systemd-unit of een CI-stap, dan ziet de bewaker het niet en
staat de code weer stil als dood geboekt. De `.bicep`-bestanden en de
`cd-staging.yml`/`cd-production.yml`-workflows zijn NIET gescand. Dat is een bewuste grens,
geen vergetelheid -- maar het is precies de vorm waarin deze bevinding terugkomt.

**En de drempel `>= 5` verjaart.** Vandaag vindt hij er zes. Verdwijnt er een compose-bestand,
dan zakt hij naar vijf en blijft de bewaker groen terwijl hij minder ziet. Een exacte
verwachting zou hem bij elke legitieme wijziging rood maken; een ondergrens laat krimp toe.
Ik heb voor de ondergrens gekozen en meld de keuze, want hij is niet gratis.

## Openstaand

1. **`infra/` en de CD-workflows worden niet gescand.** Zie hierboven. Als staging of
   productie ooit een proces start dat niet in compose staat, mist deze bewaker het.
2. **`src/workers/scheduler.py` heeft nog steeds nul tests.** 662 regels, eigen container in
   productie. Deze knip maakt hem alleen ZICHTBAAR; hij verdient een eigen knip.
3. **De drie agent-Dockerfiles zonder `main.py`** blijven staan. Of die mappen weg kunnen is
   een aparte beslissing.
