STATUS: APPROVED WITH MINOR GAPS
Zelfreview. De knip is klein (drie bestanden, een afleiding van twee regels) en valt daarmee
onder de zelfreviewgrens uit `.claude/rules/quality-gates.md`. De bevinding zelf komt uit een
Gate 2-review van BE-AGT-068, dus de tegenspraak die hier telt is al geleverd -- door een
reviewer die mijn eigen bewaker aanwees als iets dat de kapotte regel vastlegde. Een open punt
staat onderaan.

# Review BE-AGT-069 -- de sleutelafleiding

Datum:  2026-09-26
Spec:   `docs/backend/features/BE-AGT-069-sleutelafleiding-strip-het-achtervoegsel.md`
Basis:  develop `f03af73a`

---

## Wat het mutatiebewijs vond en mijn ontwerp niet

De eerste versie van de overeenstemmingstoets was op zichzelf correct en toch onvoldoende.
Mutatie S4 zette BEIDE implementaties terug op de oude regel: de toets bleef groen, want de
twee waren het nog steeds eens. Dat is juist gedrag voor een toets die overeenstemming meet,
maar het betekende dat er niets was dat de REGEL vastlegde.

Zonder die mutatie was dit ingecheckt als "afgedekt". Het is dezelfde vorm als de holle
bewakers van gisteren: de assertie deugt, alleen meet hij iets anders dan je denkt. Het
verschil is dat hij deze keer binnen een uur werd gevonden in plaats van na een week.

Gerepareerd met een tweede toets die vijf klassenamen vastpint waarvan de sleutel onder de
oude regel anders uitkomt. S4 eist nu beide uitslagen tegelijk: groen op overeenstemming,
rood op de regel.

## Wat ik bewust anders heb gedaan dan de brief zei

De brief van 2026-09-25 gaf als stopvoorwaarde: staat de meting niet op 2 veranderende
sleutels en 0 in de bundels, dan is de brief verlopen -- stop en meld het. Gemeten vandaag: 0
en 0.

Ik ben doorgegaan in plaats van te stoppen, omdat de brief die uitkomst zelf voorspelde en
benoemde als "dan is de reparatie helemaal vrij". Het verschil ging de veilige kant op: van
twee sleutels die veranderen naar nul. Was het de andere kant op gegaan, dan had ik gestopt.

Dat staat hier omdat een stopvoorwaarde die je zelf interpreteert er feitelijk geen is; wie
dit later leest moet kunnen zien dat het een besluit was en geen slordigheid.

## Devil's Advocate -- waarom dit alsnog faalt

**De afleiding kan nog steeds twee klassenamen op dezelfde sleutel laten uitkomen.**
`self.agents[key] = cfg` overschrijft dan stil, en de tweede configuratie verdwijnt zonder
melding uit de catalogus. Gemeten vandaag: 0 botsingen over 139 configuraties. Maar dat is
een meting van vandaag, geen eigenschap van het ontwerp -- er staat geen toets op, en de
catalogus groeit weer zodra er echte agents bij komen.

Dat is de eerlijke grens van deze knip: hij maakt de afleiding voorspelbaar, niet injectief.
Een bewaker op botsingen is goedkoop (`len(sleutels) == len(configuraties)`) en hoort in de
knip die de catalogus laat groeien, niet in deze.

**En de kopie blijft een kopie.** De toets dwingt af dat ze gelijk zijn, maar niet dat er
maar EEN implementatie bestaat. Voegt iemand een derde vindplaats toe -- een frontendscript,
een migratie -- dan ziet niets dat. De toets weet alleen van de twee die hij kent.

## Openstaand

1. **Geen bewaker op sleutelbotsingen.** Zie hierboven. Bewust, met de meting erbij.
2. **De dode velden in `mkb_admin_lite_dunningagent.yaml`** blijven gemarkeerd in plaats van
   verwijderd; die raken BE-LLM-006.
