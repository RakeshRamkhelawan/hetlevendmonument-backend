# Backend Feature Specification

## Metadata

- **Feature ID:** BE-ZAD-001
- **Feature naam:** Zero-Admin Bookkeeping afwerken -- een kwartaal voor stap 1 en 2, een eerlijke stap 3, het scherm Bonnen af en Nederlandse pakketnamen
- **Status:** Gereed op code en meting (Gate 2 afgerond, zie de review); de acceptatie met beeld van de draaiende applicatie is NIET door de bouwer gedaan
- **Auteur:** bouwsessie zeroadmin
- **Reviewer:** code-reviewer, quality-reviewer en security-reviewer (subagents, Gate 2)
- **Datum:** 2026-10-19
- **Gerelateerde user story / ticket:** brief `docs/agent-briefs/generated/2026-10-19-sprint-dag-zero-admin-afwerken.md` (pakket `mkb.zero_admin`, na het btw-overzicht BE-BTW-001); bevindingen uit de acceptaties van 2026-10-18 (bonlezer dag 4) en 2026-10-19 (btw-overzicht)
- **Gerelateerde router / module:** `src/core/als/bonlezer/btw_overzicht.py`, `src/core/als/bonlezer/bevestiging.py`, `src/core/als/agents/skills/{receiptscanner,vatcompliance,dunning}.py`, `src/core/api/v1/agentic/agentic_domain_router.py`, `src/core/api/v1/packs/`, `src/core/als/agents/loader.py`, `config/domain_packs.yaml`
- **Gerelateerde frontend endpoints:** `POST /api/v1/agentic/packs/execute` (`input_data.kwartaal`), `GET /api/v1/packs/activations` (`display_name`), `GET /api/v1/bonnen/bevestigd.csv`
- **Gerelateerde database tabellen:** geen (GEEN migratie, GEEN tabel)
- **Versie:** 1.0

## Doel en scope

### Doel

De vier punten die de acceptatie van het btw-overzicht openliet, zodat een klant het pakket zonder uitleg kan gebruiken:

1. **Een kwartaal voor het hele pakket.** Het venster Uitvoeren van mkb.zero_admin heeft een kwartaalkeuze (standaard het VORIGE afgesloten kwartaal: aangifte doe je achteraf). Stap 1 (bonnen) en stap 2 (btw) gebruiken hetzelfde kwartaal en noemen het in de uitslag. Vrije tekst bepaalt het kwartaal niet.
2. **Stap 3 zegt wat hij deed.** Geen kale "Gelukt" meer: de uitslag zegt hoeveel vorderingen openstaan en hoeveel herinneringen zijn voorgesteld.
3. **Het scherm Bonnen af:** terugkoppeling bij Bevestigen, het btw-blok springt naar het kwartaal van de bevestigde bon, "Controleren" verdwijnt na een geldige correctie, en de CSV van bevestigde bonnen krijgt de bestandsnaam en tijden in Nederlandse tijd.
4. **Nederlandse namen** voor alle 80 pakketten, uit een bron: de catalogus.

### Buiten scope

Geen migratie, geen nieuwe pakketten bedraden, geen omzetkant, niets indienen. Stap 3 stelt NIET zelf herinneringen voor (zie "Besluiten").

## Besluiten van de bouwer (aannames, niet van Rakesh)

- **Eén kwartaalregel, in `btw_overzicht.kwartaal_uit_pakketinvoer`**: alleen de sleutel `kwartaal` bepaalt het kwartaal, anders het vorige afgesloten kwartaal (UTC). De oude regel in stap 2 las ook een vrije tekst die precies een kwartaal was; die is vervallen (de acceptant vroeg om "het derde kwartaal van 2026" en kreeg het lopende). Een ongeldig `kwartaal` is een mislukte stap met een Nederlandse tekst.
- **Stap 1 gebruikt `BtwOverzicht.bonnen_samenvatting`**: dezelfde bonnen, dezelfde ontdubbeling en hetzelfde schema als stap 2, zodat de aantallen niet kunnen verschillen.
- **Stap 3 telt, hij stelt niet voor.** Gemeten voor de reparatie: antwoordt het taalmodel zonder `TOOL_CALL`, dan is `result_data` alleen `{"output": ..., "tool_calls": 0}` en meldde de uitslag "Gelukt" zonder dat iemand wist of er vorderingen openstonden. Nu draagt het resultaat twee tellingen die NIET van het model komen: `openstaand` (niet-betaalde vorderingen van deze tenant, per status gelezen met het statusfilter van de tool; `None` als tellen mislukte) en `voorgesteld` (tickets van deze run, alleen meldingen van de governance-poort). De stap zelf automatisch herinneringen laten voorstellen is een productkeuze (het maakt tickets aan voor elke open vordering) en niet vandaag gebouwd; de uitslag verwijst naar het scherm Debiteuren.
- **Alleen tellingen gaan naar het scherm**: `_samenvatting_debiteuren` laat `openstaand`, `voorgesteld` en `openstaand_afgekapt` door; de tekst van het model en alles wat op een persoon lijkt nooit.
- **De bevestiging bewaart de bestandsnaam** (`naam`, door de server bij de upload al schoongemaakt: zonder pad en stuurtekens, hooguit 120 tekens). Reden: het metabestand verdwijnt na 30 dagen, de bevestigde velden blijven (zie BE-BON-004, "optie 2"). De naam is dus even lang bewaard als de bevestigde velden; dat is een bewuste uitbreiding van wat daar staat en kan persoonsgegevens bevatten als een medewerker zijn bestand zo noemt. Bevestigingen van voor 2026-10-19 hebben geen naam: daar is de cel leeg en blijft `bestand_id` (laatste kolom) de sleutel.
- **CSV-tijd in Europe/Amsterdam met tijdzone** (`2026-10-17 11:00:00+02:00`); een tijd zonder zone geldt als UTC; onleesbaar is een lege cel; ontbreekt de tijdzonedatabase, dan blijft de tijd UTC (`+00:00`), nooit zonder zone.
- **"Controleren" volgt het formulier.** `frontend/src/lib/bon-controle.ts` spiegelt `moet_gecontroleerd`; een veld dat de medewerker aanraakte wordt opnieuw beoordeeld, een veld dat hij niet aanraakte houdt de aanwijzing van de server. Na een gelukte bevestiging en bij een eerder bevestigde bon staat er geen "Controleren" meer. De server toetst bij Bevestigen opnieuw en blijft de baas; de tabellen in de TypeScript-test en de Python-tests zijn dezelfde.
- **Het btw-blok springt naar het kwartaal van de bevestigde bon** als dat in de keuze staat (lopend + 4 vorige). Reden (gemeten door de acceptant): het blok stond op het lopende kwartaal, de bon was van een eerder kwartaal, dus er veranderde niets zichtbaars.
- **Weergavenamen:** `display_name` (Nederlands, alleen ASCII, uniek, niet gelijk aan de Engelse naam) voor alle 80 pakketten en `description` voor de twee pilootpakketten, in `config/domain_packs.yaml`; `pack_id` en de Engelse `name` blijven. De packs-API geeft `display_name` mee (valt terug op `name`). De acceptant sprak van 70 pakketten; het zijn er 80.

## Trainingssamenvatting

### Het pakket Boekhouding zonder gedoe uitvoeren (medewerker met `packs:execute`)

- **Actor:** een ingelogde gebruiker met `packs:execute`; het pakket staat aan voor het bedrijf.
- **Voorwaarde:** bonnen zijn bevestigd (scherm Bonnen); eventueel staan vorderingen in Debiteuren.
- **Actie:** op Pakketten bij "Boekhouding zonder gedoe" op Uitvoeren; een kwartaal kiezen (vooraf het vorige afgesloten kwartaal); eventueel tekst typen; Uitvoeren.
- **Systeemreactie:** stap 1 noemt het kwartaal, het aantal bonnen en de bedragen; stap 2 noemt hetzelfde kwartaal met de voorbelasting per tarief; stap 3 zegt "Geen openstaande vorderingen." of "N openstaande vorderingen. Er is geen herinnering voorgesteld; kies in het scherm Debiteuren welke u wilt versturen." of "N herinneringen voorgesteld (wachten op goedkeuring)."
- **Succes:** de uitslag per stap in gewone taal; niets is ingediend of verstuurd.
- **Fout:** een ongeldig kwartaal geeft een mislukte stap met een Nederlandse tekst; kon stap 3 niet tellen, dan staat er "Het aantal openstaande vorderingen kon niet worden bepaald. Kijk in het scherm Debiteuren."
- **Uitzondering:** een kwartaal zonder bevestigde bonnen is geslaagd met 0 en verwijst naar het scherm Bonnen.

### Een bon bevestigen op het scherm Bonnen

- **Actie:** velden nakijken, zo nodig corrigeren, Bevestigen. **Systeemreactie:** direct "Bezig met bevestigen...", daarna "De gegevens zijn bevestigd."; "Controleren" verdwijnt bij velden die kloppen; het btw-overzicht toont het kwartaal van de bon.

## Open punten

- **De kwartaalgrens volgt UTC**, niet Nederlandse tijd: op 1 oktober tussen 00:00 en 02:00 Amsterdamse tijd is "vorig kwartaal" nog Q2 in plaats van Q3. Backend en venster zijn onderling gelijk; een randgeval (reviewer, laag).
- **`bon-controle.ts` leest bedragen met `Number()`**: `1e2` geldt daar als 100, net als `Decimal("1e2")` in de server; hexadecimale invoer (`0x10`) niet in de server. Het formulier normaliseert bedragen vooraf; praktisch geen verschil (reviewer, laag).
- **De telling van stap 3 leest de registry rechtstreeks** (alleen lezen, eigen tenant, alleen een getal terug) en niet via de ToolBroker; `_prepare_tool_params` doet hetzelfde voor het voorbeeld van de brief. Een architecture-test die bewaakt dat deze skill alleen `list_receivables` aanroept, is niet toegevoegd (security, laag). De drie aanroepen per status zijn niet atomair: een vordering die ertussen van status wisselt kan dubbel geteld worden (hooguit te veel, nooit een open gemist); een `count()` per status zou lichter zijn.
- **Een run telt tot 3 x 200 vorderingen per tenant** (drie statussen); daarboven meldt het scherm "Minstens N".
- **De omvang van deze wijziging** (vier thema's in een tak) lag boven de grens van 400 regels; gesplitst is niet, omdat de thema's elkaar raken in dezelfde schermen.

## Regressierisico's

- De CSV van bevestigde bonnen heeft een andere kolomvolgorde (`bestandsnaam` eerst, `bestand_id` laatst) en `bevestigd_op` als Nederlandse tijd; een consument buiten de repo (niet gevonden) breekt daarop.
- `receiptscanner` telt nu een kwartaal in plaats van alle bonnen; een bon zonder geldige datum telt nergens meer mee.
- De standaard van het pakket (zonder `kwartaal`) is het vorige afgesloten kwartaal; de route `/bonnen/btw-overzicht` houdt het lopende kwartaal als standaard.
