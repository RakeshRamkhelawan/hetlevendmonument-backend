# Backend Feature Specification

## Metadata

- **Feature ID:** BE-BON-004
- **Feature naam:** Bonlezer dag 4 -- scherm Bonnen, bevestigen door een medewerker, opruiming na 30 dagen en de receiptscanner in het pakket
- **Status:** Gereed op code en meting (Gate 2 afgerond, zie de review); de acceptatie met beeld van de draaiende applicatie is NIET door de bouwer gedaan
- **Auteur:** bouwer bonlezer4 (sessie sanskritisetu-org-bd, nu -7d)
- **Reviewer:** code-reviewer, quality-reviewer en security-reviewer (subagents, Gate 2)
- **Datum:** 2026-10-17
- **Gerelateerde user story / ticket:** brief `docs/agent-briefs/generated/2026-10-17-sprint-dag-bonlezer-dag4-scherm-bevestigen-en-30-dagen.md` (SP-KLANT-04, `mkb.zero_admin`)
- **Gerelateerde router / module:** `src/core/api/v1/bonnen/`, `src/core/als/bonlezer/bevestiging.py`, `src/core/als/bonlezer/opruimen.py`, `src/core/tasks/bonnen_opruimen.py`, `src/workers/scheduler.py`, `src/core/als/agents/skills/receiptscanner.py`
- **Gerelateerde frontend endpoints:** `GET /api/v1/bonnen`, `GET /api/v1/bonnen/{id}`, `POST /api/v1/bonnen`, `PUT /api/v1/bonnen/{id}/bevestiging`, `GET /api/v1/bonnen/bevestigd.csv`
- **Gerelateerde database tabellen:** geen (GEEN migratie, GEEN tabel); wel een auditregel `bon_bevestigd` en een auditregel voor de opruiming in de bestaande auditlog
- **Versie:** 1.0

## Doel en scope

### Doel

Een medewerker ziet wat de bonlezer las, corrigeert het en bevestigt het. Alleen bevestigde velden gaan verder
(de receiptscanner-stap in pakket `mkb.zero_admin`). Een geuploade bon verdwijnt na 30 dagen vanzelf.

### In scope

- Scherm `/bonnen` (menu-item voor `receipts:read`; uploaden en bevestigen vragen `receipts:write`): upload
  (kiezen of slepen), lijst met stand (nog te bevestigen / bevestigd), velden met het woord "Controleren" bij
  twijfel, de tekst "Wij lezen uw bon uit en bewaren hem 30 dagen. Bewaar het origineel zelf; de Belastingdienst
  vraagt 7 jaar.", export van bevestigde bonnen als CSV.
- Velden zijn onbetrouwbare invoer: schema (7 vaste sleutels), btw-nummer (NL + 9 cijfers + B + 2 cijfers) en
  KvK (8 cijfers) strikt, stuurtekens en onzichtbare opmaaktekens (Unicode Cc en Cf) weg, in de CSV een
  apostrof voor een cel die met `=`, `+`, `-` of `@` begint, in het scherm alleen als tekst.
- Bevestigen: `PUT /api/v1/bonnen/{id}/bevestiging`; de velden komen in `<id>.bevestigd.json` naast de bon
  (geen tabel); een auditregel met wie, wanneer en welke bon, zonder de gegevens.
- Opruiming: dagelijks 04:30 UTC (APScheduler) een Dramatiq-actor in `workflow-worker` (uploadvolume
  schrijfbaar, alleen daar en in de API) die een geuploade bon en zijn metabestanden ouder dan 30 dagen
  verwijdert; per tenant het aantal in het log en in de auditlog; geen inhoud, geen bestandsnamen.
- Receiptscanner bedraad (`_PILOT_WIRED_AGENT_IDS`): `execute_with_manifest_prompt` geeft aantal, totaal en
  btw per tarief van de BEVESTIGDE bonnen van de tenant van de skill; zonder bevestigde bonnen succes met 0.
- Beveiliging uit Gate 2: CSRF op upload en bevestigen; 60 leesaanroepen en 30 bevestigingen per minuut per
  gebruiker.

### Toegevoegd na de acceptatie (2026-10-17)

- **Het leesresultaat blijft 30 dagen.** Gemeten: de resultaatsleutel in de bonlezer-Redis had 286 s van 300 s
  over. `RESULTAAT_TTL_MS` is nu 30 dagen (gemeten op de draaiende opstelling: 2.591.995.070 ms) en de backend
  legt het resultaat bij het eerste ophalen ook vast in `<id>.resultaat.json` (geen tabel). De opruiming
  verwijdert dat bestand met de bon na 30 dagen. Een opdracht zonder enig resultaat wordt na 480 s "verlopen".
  LET OP: de worker-image moet opnieuw gebouwd worden (de TTL staat in de worker).
- **"Controleren"** bij een leeg btw- of KvK-nummer, een ongeldige vorm, een leeg verplicht veld en btw groter dan
  het totaal (`moet_gecontroleerd`): een aanwijzing, alleen een ongeldige vorm of leeg verplicht veld blokkeert het
  bevestigen. De lijst toont ook het woord, de oorspronkelijke bestandsnaam (zonder pad en stuurtekens, hooguit
  120 tekens, alleen als tekst), de leverancier en de stand, en ververst zelf zolang een bon wordt gelezen.
- **Pakketuitslag:** een gelukte stap krijgt het `agent_id` van de stap (dus de naam "Bonnetjes lezen") en de
  receiptscanner geeft aantal, totaal en btw per tarief vrij; de tekenteller toont 0 bij een leeg veld.
- Op het scherm: "De gelezen gegevens die u bevestigt, bewaren wij tot 3 maanden na het einde van het kwartaal,
  voor uw btw-overzicht."

### Buiten scope

- Het btw-concept (vatcompliance is niet bedraad; stap 2 van het pakket faalt nog): eigen brief.
- Een bewaartermijn voor de bevestigde velden (zie "Open besluiten").
- Verwijderen van iets anders dan geuploade bonnen en metabestanden (interlock 1).

## Trainingssamenvatting

### Een bon controleren en bevestigen (medewerker)

- **Actor:** een ingelogde medewerker met `receipts:write` (rol `user`, `editor` of beheerder).
- **Voorwaarde:** een bon is geupload en door de bonlezer gelezen (of het leesresultaat is verlopen).
- **Actie:** in het scherm Bonnen op "Bekijken" klikken, de velden nalopen, corrigeren, op "Bevestigen" klikken.
- **Systeemreactie:** de server toetst de velden opnieuw, bewaart ze als bevestigd en schrijft een auditregel.
- **Succes:** "De gegevens zijn bevestigd."; de bon staat als bevestigd in de lijst.
- **Fout:** 422 met de namen van velden die niet kloppen (btw-nummer of KvK-nummer verkeerd, verplicht veld
  leeg); 403 zonder schrijfrecht; 429 bij te veel aanroepen.
- **Uitzondering:** een bon die niet gelezen kon worden of waarvan het resultaat verlopen is, vult de
  medewerker zelf in. Een bedrag mag als `1.234,56` of `12.50`; andere vormen gaan ongewijzigd naar de server.

## Open besluiten

- **Besluit Rakesh, letterlijk.** 2026-10-17, eerder: "inzake bewaren, wij doen 30 dagen bewaren en zijn daarmee
  lezer" (geldt voor de bon, het metabestand en het leesresultaat). 2026-10-17, op de vraag "na 30 dagen ook
  weg (1) of bewaren voor de btw-aangifte (2), bijvoorbeeld einde kwartaal + 3 maanden": "optie 2" (geldt voor
  de bevestigde velden). Vastgelegd door de regie (sanskritisetu-org-90).
- **Bewaartermijn van de bevestigde velden (besluit Rakesh 2026-10-17, "optie 2").** `<id>.bevestigd.json` (alleen
  cijfers en de leverancier) blijft bewaard tot het einde van het kwartaal van de bondatum plus 3 maanden en
  wordt daarna door dezelfde dagelijkse opruimtaak verwijderd (`ruim_bevestigd_op`, eigen auditregel met alleen
  het aantal). Bondatum 2026-02-26: tot en met 2026-06-30. Zonder leesbare bondatum blijft het bestand staan.
  De bon, zijn metabestand en het leesresultaat blijven op 30 dagen (akkoord "inzake bewaren, wij doen 30 dagen
  bewaren en zijn daarmee lezer"). **Twee veiligheidsgrenzen (besluit regie 2026-10-18, akkoord op het voorstel
  van de bouwer; een technische grens, geen nieuw bewaarbeleid):** de termijn eindigt niet eerder dan 30 dagen
  na het bevestigen en niet later dan 10 jaar daarna. Reden (security-review): de bondatum is invoer van een
  gebruiker. Zonder ondergrens verdwijnt een bevestiging met een bondatum van ver in het verleden bij de eerstvolgende
  run; zonder bovengrens blijft een bevestiging met een bondatum ver in de toekomst eeuwig staan. Een bondatum in
  het jaar 9999 mag de opruiming nooit laten crashen (gemeten: een ValueError blokkeerde alle tenants).
  Gevolg: een bevestiging met een bondatum van ver in het verleden blijft toch 30 dagen staan.
  **Nog niet gedaan:** de eerste echte run in een omgeving met data.
- Een tweede bevestiging overschrijft de eerste zonder versie; de auditregel bewaart alleen wie en wanneer.
- Het uploadvolume is in de `workflow-worker` schrijfbaar (dat proces voert ook agentstappen uit).
- Productie: `bonlezer_uploads` staat niet in `docker-compose.prod.yml` of Azure; voor deploy te regelen.

## Regressierisico's

- `docker-compose.yml`: `workflow-worker` kreeg het volume `bonlezer_uploads` en `BONLEZER_UPLOAD_ROOT`.
- Het schedulergedrag is aangepast (`ruim_bonnen_op` in de verwachte job-lijst).
