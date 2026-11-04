# Backend Feature Specification

## Metadata

- **Feature ID:** BE-CRD-002
- **Feature naam:** Crediteuren dag 2: de crediteurenagent verwerkt een gelezen inkoopfactuur zelf; een mens keurt alleen goed wat geld of een relatie raakt
- **Status:** Geimplementeerd (Gate 2: twee reviewers, een ronde, bevindingen nagemeten en verwerkt; zie review-BE-CRD-002)
- **Auteur:** bouwer (tak `iter/crediteuren-dag2-wip`, bovenop `iter/crediteuren` ce0e395a)
- **Reviewers:** security-reviewer en code-reviewer (Gate 2, een ronde)
- **Datum:** 2026-10-24
- **Gerelateerde brief:** `docs/agent-briefs/generated/2026-10-24-sprint-dag-crediteuren-dag2-de-agent-verwerkt-de-factuur.md` (vervangt de brief "inkoopfactuur inlezen"); meetlat Keten F (`docs/meetlat.md`)
- **Gerelateerde frontend:** FE-PGS-038
- **Gerelateerde modules:** `src/core/tool_broker/payables_registry.py`, `src/core/als/agents/skills/crediteuren.py` en `manifests/crediteuren.yml`, `src/core/als/bonlezer/factuur.py`, `dienst.py`, `src/core/services/inkoopfactuur_inlezen.py`, `crediteuren_verwerking.py`, `src/core/api/v1/payables/inlezen_*.py`, `src/core/repositories/payable_repository.py`
- **Database:** geen migratie. De inkoopfactuur en de leverancier bestaan sinds dag 1; het ticket gebruikt de bestaande tabel `hitl_tickets`; wat per upload moet worden onthouden staat in een zijbestand naast de upload (`<bestand_id>.factuur.json`).

---

## Doel en scope

### Doel

Een klant uploadt een inkoopfactuur (pdf of foto) en doet verder niets. De crediteurenagent leest hem (de bonlezer, zonder netwerk), zoekt de leverancier en legt een schone factuur zelf vast als `ontvangen`. Alles wat geld of een leverancierrelatie raakt, legt hij met het waarom voor aan een mens. Dit is dag 2 van Keten F en de eerste crediteurenstap die agent-first is (besluit Rakesh 2026-10-24: de agent doet het routinewerk, de mens keurt goed).

### Besluit

1. **Een eigen agent, `crediteuren`**, naar het voorbeeld van de debiteurenagent: skill, manifest met een Nederlandse rolbeschrijving en de agentkaartvelden, catalogusregel (`config/agents/mkb_admin_lite_crediteurenagent.yaml`), permissieprofiel in `config/tool_permissions.yml`, bedraad in `_PILOT_WIRED_AGENT_IDS`. Er is GEEN taalmodel: de stappen staan vast, maar elke actie loopt door `act()`, dus door de Council, de HITL-vloer en de broker.
2. **Twee brokertools.** `record_supplier_invoice` (MEDIUM) voor het schone geval (bekende leverancier, gelijk IBAN, geen dubbele factuur, alle velden zeker) en `propose_supplier_invoice` (HIGH) voor elke uitzondering. Beide tools beoordelen zelf OPNIEUW en weigeren wat niet klopt: de agent kan het MEDIUM-pad niet gebruiken om een uitzondering stil vast te leggen, en na goedkeuren legt de tool niets vast als wat de mens zag intussen is veranderd.
3. **De beoordeling is een leespad** (`PayablesToolRegistry.beoordeel`, zoals `DunningSkill._tel_openstaand`): de gelezen velden, de leverancier zoeken (IBAN, dan naam), een dubbele factuur opsporen. Uitkomsten: `schoon`, `uitzondering` (met redenen en het waarom in gewone taal), `dubbel`, `nog_niet_klaar`, `onleesbaar`, `onbekend`.
4. **Redenen voor een ticket:** onbekende leverancier, een naam die lijkt op een bekende leverancier, een naam die afwijkt van de leverancier met dit IBAN, een afwijkend IBAN (met fraudewaarschuwing), een nog onbekend IBAN, geen IBAN op de factuur terwijl er een bekend is, een onzeker of ontbrekend veld, een andere valuta dan euro. Een dubbele factuur geeft geen ticket maar een weigering met een Nederlandse reden in het logboek (`payable_duplicate_refused`).
5. **Het IBAN van een bekende leverancier verandert nooit stil.** Alleen na een goedgekeurd ticket (`update_iban`), met een auditregel `supplier_iban_changed` (ticket, wie de verwerking verantwoordde, oud en nieuw IBAN gemaskeerd).
6. **Het IBAN in het ticket is gemaskeerd** (`NL91ABNA******4300`). De inhoudswachter van de agent (`governance/input_guard.py`) blokkeert elk geldig IBAN in een tool-parameter en die vloer is niet versmald. De backend zegt zelf of het IBAN afwijkt (`iban_wijkt_af`) en of goedkeuren iets kan vastleggen (`goedkeuren_mogelijk`); het scherm leidt dat niet uit de maskers af, want twee maskers kunnen gelijk zijn terwijl de verborgen cijfers verschillen.
7. **Een upload wordt hooguit een keer verwerkt**: een claim naast de upload (`O_EXCL`, `FactuurKoppeling`) met de gebruiker die de verwerking verantwoordt en een tijdstempel. Een claim die langer dan 10 minuten op `bezig` staat is een onderbroken verwerking en wordt overgenomen. Elke uitzondering na de claim laat een uitkomst `mislukt` achter in plaats van een claim die blijft hangen.
8. **De agent start zelf**, in de achtergrond van de API (`crediteuren_verwerking.start_verwerking`): na de upload wacht hij tot de bonlezer klaar is en verwerkt de factuur, met de gebruiker van de upload als verantwoordelijke (de Council legt zijn besluit vast op een `user_id`; zonder verantwoordelijke gebruiker doet de agent niets). Begrensd: 5 wachtende verwerkingen per tenant, 25 in het proces, een oplopend pollinterval. `GET /api/v1/payables/inlezen/{bestand_id}` start de verwerking alsnog als er nog geen stand is (een herstart van de API mag niets laten liggen).
9. **Aanpassen** is de enige bevestigroute (`POST /api/v1/payables/inlezen/{bestand_id}/bevestiging`): een ticket en een reden (minstens 10 tekens) zijn verplicht, het recht `payables:approve` is nodig, de zelfgoedkeuringsregel en de vier-ogen-instelling gelden net als bij goedkeuren, en het ticket sluit als afgewezen met "handmatig vastgelegd als inkoopfactuur N: reden". De oude route waarbij een medewerker elk voorstel bevestigt is vervallen.
10. **Rechten.** Uploaden en de stand lezen vragen `payables:write` (rol `crediteuren`). Een ticket goedkeuren, afwijzen of aanpassen vraagt het nieuwe procesrecht `payables:approve` in de rol `goedkeurder` (nooit via `*:*`); `propose_supplier_invoice` staat in `approval_rights.RECHT_PER_TOOL`, de agent in `RECHT_PER_AGENT`, de actie in `FOUR_EYES_ACTIONS` (standaard uit, per tenant instelbaar).
11. **Een bon is geen factuur.** `BonDienst.uploaden(..., soort)` zet `bon` of `factuur` in het metabestand; de crediteurenagent en de factuurroutes zien alleen uploads van de soort `factuur`.
12. **De bonlezer leest drie velden erbij** (`iban` met controlesom, `vervaldatum` na het label, `valuta`): dezelfde leespijplijn, geen tweede. De valuta is alleen zeker als er precies een soort valutateken in de tekst staat.

### Gemeten (2026-10-24)

- **De inhoudswachter blokkeerde elk geldig IBAN in de ticketparameters** ("de invoer bevat gegevens die hier niet thuishoren: iban"): elf van de agenttests faalden daarop. Vandaar het gemaskeerde IBAN en de vlag van de backend.
- **De gedeelde testdatabase verloor tabellen** (`relation "payables" does not exist`) doordat andere sessies migratietests met een downgrade draaien op dezelfde database; een Council-besluit faalde daardoor af en toe met "blocked" (de audit-persistentie van de Council viel weg). De agenttests draaien daarom op een eigen database op dezelfde server (`crd_agent`); daar zijn de integratietests stabiel.
- **De werker bereikt de Redis van de bonlezer niet**, alleen de backend (compose: het koppelnetwerk `bonlezer_koppel`). Vandaar dat de agent in de backend start en niet in een werkertaak; zie "Bewust laten liggen".
- Gate 2 (beide reviewers beredeneerden, de bouwer mat na): zie review-BE-CRD-002.
- Mutatiebewijs: 57 mutaties (20 en 14 in de eerste ronde, 23 in de tweede voor de Gate 2-reparaties), na aanvulling van de tests alle rood.

## Trainingssamenvatting

### De crediteurenagent verwerkt een geuploade inkoopfactuur

- Actor: de crediteurenagent, gestart door de upload van een gebruiker met `payables:write`
- Voorwaarde: de bonlezer heeft de factuur gelezen; de gebruiker die de upload deed is de verantwoordelijke voor de verwerking
- Actie: de agent beoordeelt de gelezen velden (leverancier zoeken, IBAN vergelijken, dubbele factuur opsporen) en kiest `record_supplier_invoice` of `propose_supplier_invoice`
- Systeemreactie: een schone factuur wordt vastgelegd met status `ontvangen`; een uitzondering wordt een HIGH-ticket met het waarom in gewone taal; een dubbele factuur geeft geen ticket maar een Nederlandse reden
- Succes: de factuur staat zonder klik in de lijst, of het voorstel wacht in de goedkeurwachtrij
- Fout: een onleesbare of nog niet gelezen factuur wordt niet verwerkt; een uitzondering in de verwerking laat de uitkomst `mislukt` achter in plaats van een hangende claim
- Uitzonderingen: onbekende leverancier, afwijkend IBAN (met fraudewaarschuwing), onzeker of ontbrekend veld en een andere valuta dan euro gaan altijd langs een mens

### Een goedkeurder handelt een uitzondering af

- Actor: een gebruiker met `payables:approve` (rol `goedkeurder`)
- Voorwaarde: er staat een voorstel van de agent in de goedkeurwachtrij; staat vier ogen aan, dan is de goedkeurder iemand anders dan de uploader
- Actie: keurt goed, keurt af met een reden, of past aan via de bevestigroute met ticket en een reden van minstens 10 tekens
- Systeemreactie: bij goedkeuren legt de tool precies de voorgelegde factuur vast (nieuwe leverancier of nieuw IBAN alleen na dit besluit); bij afkeuren gebeurt er niets; bij aanpassen sluit het ticket als afgewezen met "handmatig vastgelegd"
- Succes: de factuur is vastgelegd of bewust niet vastgelegd, met een auditregel
- Fout: zonder het recht, zonder reden of bij zelfgoedkeuring weigert de server (403 of 409) met een Nederlandse tekst
- Uitzonderingen: een verlopen voorstel (SLA 4 uur) kan niet meer worden goedgekeurd

## Bewust laten liggen

| Punt | Reden |
|---|---|
| De agent start niet in de algemene werker | alleen de backend bereikt het leesresultaat van de bonlezer; een werkerstart vraagt een netwerkwijziging in compose (SP-KOPPEL-001) en is geen onderdeel van dag 2 |
| Een herstart van de API tijdens het wachten raakt de taak kwijt | opgevangen door de stand (`GET`) die de verwerking alsnog start en door de claim met tijdstempel |
| Geen drempelbedrag voor zelf vastleggen | een schone factuur van een bekende leverancier wordt altijd vastgelegd; vastleggen betaalt niets. De klantregel "drempelbedrag" staat op de agentkaart als niet gebouwd; dag 3 (betaalvoorstel) is waar bedragen tellen |
| Geen aanpassingsscherm | aanpassen is een API-route; voor een ticket zonder alle velden toont de kaart geen goedkeurknop en wijst op hand-invoer op de pagina Crediteuren plus afkeuren met reden |
| Een factuur met een Cyrillische letter in de naam (lookalike) wordt niet herkend | alleen een naam die na NFKC, hoofdletters en leestekens gelijk is aan een bekende leverancier wordt gemeld; een ander schrift niet |
| Meerdere geldige IBAN's in een factuur | de bonlezer geeft het eerste; een factuur met twee nummers geeft geen aparte waarschuwing |
| Geen vervaldatum afleiden uit "betaling binnen 14 dagen" | de agent raadt niet; zo'n factuur wordt een ticket zonder goedkeurknop |
| Een mislukte uitvoering na goedkeuren laat het ticket op `consumed` | de claim van dat ticket wordt vrijgegeven; de volgende verwerking maakt een vers ticket of legt de factuur schoon vast |
| De goedkeurder ziet de factuur zelf niet in het ticket | geen downloadroute voor het bestand; dag 3 of later |
