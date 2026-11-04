STATUS: APPROVED
# Backend Feature Review -- BE-CRD-002

## Metadata

- Feature ID: BE-CRD-002
- Feature naam: Crediteuren dag 2: de crediteurenagent verwerkt een gelezen inkoopfactuur zelf
- Review datum: 2026-10-24
- Reviewers: security-reviewer en code-reviewer (subagents), een ronde Gate 2 op `git diff ce0e395a` van de tak `iter/crediteuren-dag2-wip`; zelfreview op de verwerking
- Spec locatie: `docs/backend/features/BE-CRD-002-crediteuren-dag2-agent-verwerkt-inkoopfactuur.md`

---

## Eindoordeel

**APPROVED** na verwerking. Beide reviewers gaven bevindingen; allen zijn BEREDENEERD (de reviewers konden niets draaien) en door de bouwer zelf nagemeten of beredeneerd voordat iets is aangenomen. Wat gerepareerd is staat hieronder, met het mutatiebewijs dat de nieuwe tests echt rood worden. Wat bewust blijft liggen staat er met de reden. Een tweede ronde is niet gevraagd; het maximum is twee.

**Eerlijk over de volgorde.** De reparaties hieronder zijn gebouwd en daarna met mutaties getoetst; de tests zijn dus niet eerst rood gezien tegen de oude code. Het mutatiebewijs (zie onderaan) toont wel dat elke reparatie door een test wordt bewaakt.

## Bevindingen en afhandeling

| ID | Ernst | Bevinding | Afhandeling |
|---|---|---|---|
| S1 / C9 | HIGH | het gemaskeerde IBAN (de eerste acht en laatste vier tekens) is de enige discriminator; twee verschillende nummers kunnen hetzelfde masker geven, en dan verscheen de waarschuwing in het scherm niet (het scherm vergeleek de maskers) | beredeneerd en bevestigd in de code: de BACKEND geeft nu `iban_wijkt_af` (en `goedkeuren_mogelijk`) mee in het ticket (gebonden in de goedkeuringsbinding); het scherm gebruikt alleen die vlag. Mutaties R1 en F18 rood |
| S2 / C4 | HIGH | de aanpasroute omzeilt de zelfgoedkeuringsregel en de vier-ogen-instelling | de route roept nu dezelfde toets aan als goedkeuren (`_refuse_self_approval_audited`); met vier ogen aan mag de uploader zijn eigen ticket niet sluiten, een collega wel, met vier ogen uit wel. Drie tests; mutatie R13 rood |
| C1 | HIGH | een ticket zonder alle velden kan niet worden goedgekeurd (de tool weigert na verbruik van het ticket) en er is geen aanpasscherm | het ticket draagt `goedkeuren_mogelijk`; de kaart toont dan geen goedkeurknop en legt uit wat er moet gebeuren (met de hand vastleggen en afkeuren met reden). Een aanpasscherm is niet gebouwd, zie de spec. Mutaties R2 en F15 rood |
| C2 | HIGH | na een mislukte uitvoering is het ticket `consumed` en de claim blijft staan: de factuur is een doodlopend spoor (bijvoorbeeld twee facturen van dezelfde nieuwe leverancier) | bij "veranderd sinds het ticket" of "niet meer leesbaar" geeft de tool de claim van DIT ticket vrij en schrijft `payable_ticket_mislukt`; de volgende verwerking maakt een vers ticket of legt de factuur schoon vast. Scenario A gemeten (test); B (een tijdelijke bonlezerfout) en C (een verlopen ticket) niet apart. Mutatie R12 rood |
| S4 / C3 | MEDIUM | een claim zonder uitkomst blijft staan na een uitzondering of een herstart; de factuur is 30 dagen op slot en de pagina stopt na tien minuten zonder melding | elke uitzondering na de claim schrijft `mislukt` (en logt); een claim ouder dan 10 minuten op `bezig` wordt overgenomen; de pagina toont na de maximale wachttijd een melding. Mutaties R7, R8, R9 en F17 rood |
| S5 | MEDIUM | audit-lacune: `created_by` en gebruiker leeg, `supplier_iban_changed` zonder ticket, goedkeurder en oud/nieuw | de claim bewaart de uploader; `created_by` en de auditregels gebruiken hem; `supplier_iban_changed` noemt ticket, verantwoordelijke en het oude en nieuwe IBAN gemaskeerd (de volledige nummers staan er niet in). Mutaties R10 en R11 rood |
| S6 / C5 | MEDIUM | een lookalike-leverancier; en een factuur van X met het IBAN van een bekende Y wordt schoon geboekt op Y | nieuwe redenen `lijkt_op_bekende_leverancier` (NFKC, hoofdletters en leestekens genegeerd) en `naam_wijkt_af` (gevonden op IBAN, naam op de factuur anders); beide worden een ticket. Een lookalike in een ander schrift (Cyrillisch) wordt NIET herkend. Mutaties R5 en R6 rood |
| S7 | MEDIUM | uitputting door wachtende achtergrondtaken | 5 per tenant en 25 in het proces, het pollinterval loopt op tot 15 s; een start die er niet bij past komt later via de stand. Mutatie R14 rood |
| C6 | MEDIUM | de vervaldatum is de eerste datum op de regel: bij `Factuurdatum 01-10 Vervaldatum 31-10` gelijk aan de factuurdatum, dus ten onrechte schoon | gemeten met een test en gerepareerd: de datum NA het label. Mutatie R15 rood |
| C7 | LOW/MEDIUM | `valuta` is altijd EUR zodra het woord of teken ergens staat; `andere_valuta` was onbereikbaar | de bonlezer leest ook USD en GBP; staan er twee soorten tekens in de tekst dan is de valuta onzeker. Mutatie R16 rood |
| C8 | MEDIUM | de pagina stopte met volgen na een enkele fout en bij een voorgelegd ticket | twee nieuwe pogingen na een tijdelijke fout; een voorgelegde factuur wordt gevolgd tot de goedkeurder besluit. Mutaties F16 en F19 rood |
| C10 | LOW/MEDIUM | een bon kreeg `iban`, `vervaldatum`, `valuta` terug (een IBAN op een kassabon kan een persoonsgegeven zijn) en een bon kon door de crediteurenagent worden opgepakt | `BonDienst.status` laat die drie velden bij een bon weg; uploads dragen een soort (`bon` of `factuur`) en de agent en de factuurroutes zien alleen `factuur`. Mutaties R3, R4 en R17 rood; vijf unittests |
| S8 / C11 | LOW | na een herstart van de API start de eerste gebruiker die de stand opent de verwerking en wordt de verantwoordelijke; `_BEZIG` geldt per proces | bewust niet opgelost: de gebruiker die de stand opent heeft ook `payables:write` binnen dezelfde tenant en de claim voorkomt dubbel werk. Genoteerd in de spec |
| S9 | LOW | race tussen aanpassen en goedkeuren | beredeneerd: het sluiten van het ticket is een `UPDATE ... WHERE status = 'pending'`, dus een van beide verliest; echte gelijktijdigheid is niet gemeten |
| S3 | MEDIUM | een schone factuur wordt zonder bedragsgrens of afwijkingscheck automatisch vastgelegd | bewust niet: wie `payables:write` heeft kan hetzelfde met het invoerscherm van dag 1; vastleggen betaalt niets. Een drempel hoort bij dag 3 (betaalvoorstel) en staat op de agentkaart als "nog niet gebouwd" |
| S10 | LOW | het eerste geldige IBAN uit de tekstlaag; verborgen tekst in een pdf | niet opgelost; zie de spec |
| C12 | -- | de keten tekst -> veldenlaag -> beoordeling is nooit samen getest; de start van de agent was alleen een stub | de start heeft nu unittests (begrenzing); de keten met een echte pdf is de acceptatie (zie FE-PGS-038) |

Wat de reviewers positief vonden en de bouwer bevestigde: elke nieuwe repositorymethode en registryfunctie filtert op de tenant uit de context (isolatietests voor `find_match`, `find_duplicate` en `update_iban`, mutaties B13 tot en met B16 rood); de parameters van een toolaanroep komen nooit van buiten (`bestand_id` wordt gevalideerd voor de `TOOL_CALL`-tekst en alle andere parameters komen uit de beoordeling); een vervalst ticketnummer faalt bij het verzilveren; de transacties in het aanpassen en in `_leg_vast` zijn atomair; geen IBAN of bedrag in de auditregels en op de event bus.

## Mutatiebewijs (wegwerp-worktree, kopie als terugweg, tegen een eigen database)

57 mutaties, alle rood na aanvulling van de tests.

- **Eerste ronde (backend, 20):** B1 tot en met B20, onder meer: dubbele factuur niet opgespoord, afwijkend IBAN geen reden, de MEDIUM-tool weigert een uitzondering niet, na goedkeuren niet opnieuw vergeleken, nieuw IBAN niet gezet, een stuurteken in de naam vertrouwd, de skill werkt zonder verantwoordelijke gebruiker, de claim legt geen beslag, aanpassen zonder ticketcontrole en zonder goedkeurrecht, de start ontbreekt, vier tenantfilters weg, ticket niet verplicht, ticket sluit niet. **Twee mutanten overleefden eerst** (B17: een reden zonder ticket was door een tweede verplichting toch geweigerd; B19: een onbekende leverancier zonder IBAN op de factuur gaf geen ticket). Beide wezen op echte gaten in de tests; na aanvulling rood.
- **Frontend (14):** F1 tot en met F14. **Een mutant overleefde eerst** (F12, het slot tegen dubbelklik: de uitgeschakelde knop vangt de tweede klik al); na een test op het formulier zelf rood.
- **Tweede ronde na de Gate 2-reparaties (23):** R1 tot en met R18 en F15 tot en met F19.
- **Gelijkwaardig:** geen.
- **De andere kant** (een legitiem geval mag niet blijven hangen): elke weigering heeft een test waarin hetzelfde geval met het goede antwoord slaagt: een bekende leverancier met gelijk IBAN wordt zonder klik vastgelegd; een goedkeuring van een geldig ticket legt precies de getoonde factuur vast; een collega kan een ticket sluiten als vier ogen aan staat; een bon blijft zijn eigen velden houden; een schone upload wordt niet tegengehouden door de begrenzing.

## Niet gemeten

- Echte gelijktijdigheid (twee goedkeuringen of een goedkeuring en een aanpassing tegelijk).
- Het gedrag onder meerdere Gunicorn-workers (de claim vangt een dubbele start op; de begrenzing geldt per proces).
- Een mislukte uitvoering door een tijdelijke bonlezerfout of een verlopen ticket (alleen "veranderd" is getest).
- De volledige `tests/architecture`- en vitest-ronde: zie de eindmelding.
- Het lezen van pdf's met een andere opmaak dan de drie verzonnen facturen van de acceptatie.
