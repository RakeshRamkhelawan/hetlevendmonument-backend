# Backend Feature Specification

## Metadata

- **Feature ID:** BE-CNL-001
- **Feature naam:** De council bij een koude start: opwarmen bij het opstarten en gewone taal voor de klant bij een technische blokkade
- **Status:** Geimplementeerd (Gate 2 ronde 1 verwerkt)
- **Auteur:** bouwer (tak `iter/council`)
- **Reviewer:** security-reviewer (Gate 2, een ronde)
- **Datum:** 2026-10-23
- **Gerelateerde brief:** `docs/agent-briefs/generated/2026-10-23-sprint-dag-council-weigert-niet-door-een-koude-start.md`; open punt uit BE-DEB-006
- **Gerelateerde modules:** `src/core/copilot/council/factory.py`, `src/core/copilot/council/technische_blokkade.py`, `src/core/copilot/council/members/audit_officer.py`, `src/core/als/agents/specialist_base.py`, `src/core/agents/base_agent.py`, `src/core/app_lifespan.py`
- **Database:** geen migratie, geen schemawijziging. De opwarming leest alleen.

---

## Doel en scope

### Doel

Bij de acceptatie van 2026-10-22 werd een debiteurenvoorstel vier keer geblokkeerd: alle functionarissen keurden goed behalve de RiskOfficer, die na zijn tijdsgrens een TIMEOUT-veto gaf. De klant las "Council-verdict blocked: ...". Twee dingen zijn aangepakt: de koude kosten van de eerste aanroep, en de tekst.

### Gemeten (vers proces, lokale testdatabase, geen Redis lokaal)

1. De werkelijke tijdsgrens van de RiskOfficer is **500 ms**: `policies/default.yaml` wint van de klassewaarde 600 (`coordinator.py:302-304`).
2. Alleen de RiskOfficer is bij zijn eerste aanroep traag. Het ShadowCEO-deel kost 0,1 tot 1 ms (los gemeten met stubs); het deel dat tijd kost is de registerquery `actor_track_record`.
3. Zonder voorverwarmde pool: eerste aanroep 128 tot 360 ms, tweede 5 tot 15 ms. Een kale `select 1` laat hem op 105 tot 121 ms; voorverwarmen met de echte registerquery brengt hem op 8 tot 13 ms. De koude kosten zijn dus de eerste verbinding plus de eerste uitvoering van die query (statement bouwen).
4. Met de productiepool (`db_manager`, `pool_pre_ping=True`, `pool_recycle=1800`; `initialize()` voert zelf al een `select 1` uit) en de database als `127.0.0.1`: zonder opwarming 46 tot 51 ms, met opwarming 6,5 tot 7,2 ms, met een vervangen verbinding (pool leeggemaakt na de opwarming) 40 tot 43 ms.
5. **De oorzaak van de vier blokkades bij de acceptatie (gemeten in de volle stack, 2026-10-23):** de omgeving van de hoofdmap zet de database als `localhost:5435`. Een NIEUWE verbinding naar `localhost` kost 2,1 s, naar `127.0.0.1` 48 tot 66 ms (vijf metingen met `asyncpg.connect`; `getaddrinfo` geeft `::1` vóór `127.0.0.1`, en `::1` wordt na circa 2,0 s geweigerd). De registerquery van de RiskOfficer heeft een verbinding nodig; kost die verbinding 2,1 s, dan loopt de RiskOfficer tegen zijn 500 ms aan. De volle API (zonder meerverbindingsopwarming, wel met opwarming van een verbinding) gaf drie keer achter elkaar een TIMEOUT-veto (RiskOfficer 519, 498, 509 ms) en de klant zag de nieuwe Nederlandse zin. Zonder enige opwarming, in-process met dezelfde omgeving: eerste aanroep 505 ms (TIMEOUT), daarna 17,7 en 4,7 ms; het ShadowCEO-deel 0,2 ms, de registerquery 505 ms.
6. Na de aanpassing (opwarming over drie verbindingen tegelijk), met de OORSPRONKELIJKE `localhost`-omgeving: drie voorstellen op een vers gestarte API: 33, 17,6 en 12,7 ms; alle drie goedgekeurd. Daarna twee verse starts van API, werker EN planner met direct het eerste voorstel: 25 ms en 35 ms, beide goedgekeurd. Met `127.0.0.1` als host (zelfde API): 174, 25 en 35 ms. Alles onder de 250 ms-drempel van de regie, dus **de tijdsgrens is niet verhoogd**.

### In scope

- `warm_up_risk_register` (factory) en de lifespanstap `_init_council_warmup`: de registerquery een keer uitvoeren onder een niet-bestaande tenant (`WARMUP_TENANT_ID`), met een tijdsgrens van 5 s, niet-fataal, de bestaande tenantcontext herstellend.
- `technische_blokkade.is_technisch_niet_beoordeeld`: een blokkade is technisch als er een veto met een code uit {TIMEOUT, CIRCUIT_BREAKER_OPEN, INTERNAL_ERROR} is en GEEN echt veto van een functionaris. Dan zegt de klanttekst: "Dit voorstel kon nu niet worden beoordeeld. Probeer het over een moment opnieuw." Toegepast op drie plekken: `AuditOfficer._generate_explanation`, `specialist_base._council_rejection` en `base_agent` (alleen bij verdict BLOCKED).

### Out of scope

- De council soepeler maken: een TIMEOUT blijft een veto, geen functionaris wordt overgeslagen.
- Een hogere tijdsgrens (gemeten onnodig).
- De volledige API meten met Redis (zie "Niet gemeten").

---

## Technische beschrijving

- De opwarming gebruikt dezelfde query als de RiskOfficer (`_RiskRegisterAdapter.actor_track_record`) en dezelfde tenantfilterhook (de lifespan zet `_init_tenant_filtering` als eerste stap), zodat de gecompileerde statements gelijk zijn. De test bewaakt dat deterministisch: na de opwarming bouwt de eerste echte query geen nieuw statement in de cache van de engine.
- De opwarming opent `verbindingen` (standaard 3) sessies tegelijk, omdat een voorstel meerdere sessies gebruikt en elke nieuwe verbinding naar `localhost` op Windows 2,1 s kost (zie "Gemeten", punt 5); met een pool met een enkele opgewarmde verbinding betaalde het eerste voorstel de rest. Een TIMEOUT breekt de lopende databasebewerking af, waarna die verbinding opnieuw moet worden geopend; daarom is alleen warm houden niet genoeg als de host traag resolvet. **De blijvende oplossing voor deze machine is `127.0.0.1` in plaats van `localhost` in de database-URL van de hoofdmap; dat bestand is niet van deze brief en is niet gewijzigd.** In staging en productie is de host een DNS-naam zonder IPv6-poging; dat is niet gemeten.
- `warm_up_risk_register` vangt elke fout en geeft False; `_RiskRegisterAdapter` vangt query-fouten zelf, dus True betekent "uitgevoerd", niet "de tabel is er". `_init_council_warmup` heeft de imports binnen de try, omdat de init-lus elke fout opnieuw raiset en de opwarming een versnelling is, geen voorwaarde.
- De klanttekst verandert alleen `explanation_for_user` voor nieuwe records; de redencodes blijven in `officer_verdicts` en in het logboek. `getattr(decision, "officer_verdicts", ())` staat bij twee aanroepers omdat bestaande testdubbels dat veld niet dragen; een echte `CouncilDecision` heeft het altijd, en bij ontbreken valt de tekst terug op de oude.

## Acceptatiecriteria

- Een TIMEOUT van een functionaris geeft nog steeds een geblokkeerde beslissing en de actie wordt niet uitgevoerd.
- De klanttekst bij een puur technische blokkade is Nederlands en bevat geen "Council-verdict", "TIMEOUT" of "Fail-secure"; een echt veto naast een TIMEOUT houdt zijn eigen uitleg.
- Na de opwarming bouwt de eerste registerquery geen nieuw statement.
- Een kapotte of hangende database laat het opstarten niet crashen of vastlopen.

Tests: `tests/unit/als/test_council_timeout_klanttekst.py` (12), `tests/integration/copilot/test_council_opwarmen.py` (6). Mutatiebewijs: 11 mutaties, allemaal rood (opwarming leeg, stap uit de lifespan, `except` weg, helper altijd False/True, helper negeert echt veto, elke van de drie tekstplekken, geen tijdsgrens, tenant niet hersteld).

## Trainingssamenvatting

### Een voorstel direct na een herstart van de API

- Actor: medewerker
- Voorwaarde: de API is net gestart; een voorstel (bijvoorbeeld een debiteurenherinnering) wordt ingediend
- Actie: het voorstel gaat naar de council
- Systeemreactie: de RiskOfficer beoordeelt binnen zijn tijdsgrens omdat de registerquery bij het opstarten al is opgewarmd
- Succes: het voorstel wordt beoordeeld zoals bij elke andere aanroep
- Fout: komt een functionaris toch in een TIMEOUT, dan wordt het voorstel niet uitgevoerd en leest de medewerker dat het nu niet beoordeeld kon worden en dat opnieuw proberen kan
- Uitzonderingen: een inhoudelijk veto (bijvoorbeeld ontbrekende rechten) houdt zijn eigen uitleg

## Bewust laten liggen

| Punt | Reden |
|---|---|
| `localhost` in de database-URL van de hoofdmap | de gemeten oorzaak (2,1 s per nieuwe verbinding); het omzetten naar `127.0.0.1` is een wijziging in een bestand met geheimen en niet van deze brief. De code vangt het nu op met meerdere opgewarmde verbindingen, maar na een TIMEOUT of een verlopen verbinding (`pool_recycle=1800`) kost een nieuwe verbinding op deze machine weer 2,1 s |
| Automatische retries in de agent- of toolketen op de nieuwe zin | LOW uit de review, niet nagemeten |
| Gedrag van het tenantfilter en de rijbeveiliging bij een tenant zonder rijen | LOW uit de review, niet gemeten; de opwarming leest alleen en gooit het resultaat weg |

## Gegevens die de meting in de lokale dev-database heeft achtergelaten

De volle-API-meting (2026-10-23, dev-database `sanskritisetu_postgres` op poort 5435, tenant 1, gebruiker 108 met de rol debiteuren) maakte acht voorstellen. Op de vorderingen 52, 50, 40, 33, 32, 24, 21 en 20 staat nu een herinnering die op goedkeuring wacht (status `wacht_op_goedkeuring` in het antwoord, met een HITL-ticket); drie daarvan (52, 50, 40) kregen eerst een TIMEOUT-veto zonder ticket en zijn later opnieuw voorgesteld. Het zijn lokale acceptatiegegevens; ze zijn bewust niet opgeruimd. Er is geen test- of productiedatabase geraakt.

## Niet gemeten

- Een echte wachttijd van 30 minuten voor de vervanging van een verbinding in de pool (nagebootst met het leegmaken van de pool, en op `localhost` bewezen als 2,1 s per nieuwe verbinding).
- Staging en productie (de hostresolutie daar).
- De acceptatie met beeld (meetlat): de klant ziet de zin in de pagina. Via de API is de tekst wel gezien ("niet_gelukt" met de nieuwe zin, drie keer, tijdens de TIMEOUT-reproductie); het echte-veto-geval is alleen met tests gedekt. De acceptatie met beeld is de stap van de acceptant.
- Het zakelijke antwoord op "waarom lukte het daarna met werker en planner aan": niet bewezen; de gemeten oorzaak (nieuwe verbindingen kosten 2,1 s) verklaart de TIMEOUTs, niet waarom ze na een herstart van werker en planner verdwenen.
