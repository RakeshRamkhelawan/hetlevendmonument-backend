# FE-PGS-038 -- Crediteuren: een factuur laten verwerken door de crediteurenagent, en het voorstel in de goedkeurwachtrij

**Sprint:** Keten F, crediteuren dag 2 (2026-10-24), backend BE-CRD-002
**Status:** Geimplementeerd en onafhankelijk geaccepteerd met beeld (2026-10-24, acceptant in drie rondes: GOEDGEKEURD MET OPMERKINGEN; beelden in `D:/tmp/crd-acceptatie2/`, buiten de repo). Gate 2: twee reviewers; bevindingen verwerkt, zie review-FE-PGS-038.
**Datum:** 2026-10-24
**Bestanden:** `frontend/src/pages/PayablesPage.tsx`, `frontend/src/lib/api/payables.ts`, `frontend/src/components/hitl/SupplierInvoiceDetails.tsx`, `frontend/src/components/hitl/HITLActionCard.tsx`, `frontend/src/lib/hitl/actie-omschrijving.ts`, `frontend/src/lib/rechten.ts`
**Handleiding:** `docs/user-guide/frontend/crediteuren-factuur-laten-verwerken.md`

---

## Beschrijving

- **Uploaden op de pagina Crediteuren.** Wie `payables:write` heeft ziet "Inkoopfactuur laten verwerken": een bestandsveld "Inkoopfactuur (pdf of foto)" en de knop "Factuur laten verwerken". Er is GEEN invoerscherm voor de velden: de crediteurenagent leest, koppelt en legt vast.
- **De stand per upload, in gewone taal.** Na het uploaden vraagt het scherm elke 3 seconden naar de stand (hoogstens 200 keer; een tijdelijke fout krijgt twee nieuwe pogingen). Teksten: "wordt gelezen en verwerkt", "heeft de factuur vastgelegd" (de lijst ververst dan vanzelf), "legt deze factuur voor aan de goedkeurder" met "Let op: afwijkend IBAN." of "De leverancier is nog niet bekend." en een verwijzing "Naar de goedkeuringen", "De goedkeurder heeft deze factuur afgekeurd. Er is niets vastgelegd.", "Het voorstel is verlopen zonder besluit", de Nederlandse reden bij een dubbele factuur, "kon niet worden gelezen. Voer hem met de hand in" en "kon deze factuur niet verwerken". Een technische reden van de agent gaat nooit naar de klant. Een voorgelegde factuur wordt gevolgd tot de goedkeurder besluit; na de maximale wachttijd staat er "Ververs de pagina voor de nieuwste stand."
- **Een geweigerde upload** toont de vaste Nederlandse tekst van de server (te groot, verkeerd soort, wachtrij vol, bonlezer niet bereikbaar); een slot houdt een dubbelklik bij een upload.
- **De goedkeurwachtrij** toont het voorstel van de agent als kaart "Inkoopfactuur vastleggen": leverancier (met "(nieuwe leverancier)" en, als hij afwijkt, "Naam op de factuur"), factuurnummer, bedrag in euro's, factuurdatum en vervaldatum als dag-maand-jaar, en "Waarom de agent dit voorlegt" volledig. Een amberkleurige waarschuwing ("Let op: afwijkend IBAN ... een bekende vorm van fraude") verschijnt ALLEEN als de BACKEND dat zegt (`iban_wijkt_af`): het IBAN is gemaskeerd en twee maskers kunnen gelijk zijn terwijl de nummers verschillen, dus het scherm vergelijkt de maskers niet zelf. De knop heet "Goedkeuren en vastleggen"; afkeuren vraagt een reden van minstens 10 tekens ("Leg uit waarom je deze factuur afkeurt").
- **Geen goedkeurknop zonder velden.** Staat er `goedkeuren_mogelijk: false` in het voorstel (een gegeven ontbreekt of de valuta is niet euro), dan toont de kaart "Goedkeuren kan niet" met wat te doen (met de hand vastleggen op de pagina Crediteuren en het voorstel afkeuren met die reden) en blijft alleen afkeuren over. Goedkeuren zou het ticket verbruiken zonder dat er iets wordt vastgelegd.
- **Rechten.** `payables:approve` is een procesrecht (rol `goedkeurder`, nooit via `*:*`) en staat in `PROCESRECHTEN` van `rechten.ts` (spiegel van `ALLE_PROCESRECHTEN`). De agent heet "Crediteurenagent" en de actie "Een inkoopfactuur vastleggen die de crediteurenagent voorlegt" (spiegel van `FOUR_EYES_ACTIONS`, per tenant instelbaar).

## Trainingssamenvatting

### Een factuur laten verwerken

- Actor: crediteurenadministrateur
- Voorwaarde: de gebruiker heeft de rol `crediteuren` en opent Crediteuren
- Actie: kiest een pdf of foto bij "Inkoopfactuur (pdf of foto)" en kiest "Factuur laten verwerken"
- Systeemreactie: "De factuur wordt gelezen en verwerkt."; daarna, vanzelf, wat de agent deed
- Succes: bij een bekende leverancier met gelijk IBAN en alle gegevens staat de factuur zonder verdere klik in de lijst met status "Ontvangen" en zegt het scherm dat de agent hem heeft vastgelegd
- Fout: een te groot of verkeerd bestand wordt geweigerd met een Nederlandse tekst; een onleesbare factuur geeft "Voer hem met de hand in"
- Uitzonderingen: een dubbele factuur wordt niet vastgelegd (met reden); een uitzondering gaat naar de goedkeurder

### Een voorstel van de agent beoordelen

- Actor: goedkeurder
- Voorwaarde: de gebruiker heeft `payables:approve` (rol `goedkeurder`) en opent Goedkeuringen
- Actie: leest de kaart "Inkoopfactuur vastleggen" en kiest "Goedkeuren en vastleggen" of "Afkeuren" met een reden
- Systeemreactie: bij goedkeuren legt de agent precies de getoonde factuur vast (en maakt een nieuwe leverancier aan of zet een goedgekeurd nieuw IBAN); bij afkeuren gebeurt er niets
- Succes: de factuur staat in de lijst van de crediteuren, of het uploadveld zegt dat het voorstel is afgekeurd
- Fout: zonder reden (of korter dan 10 tekens) is afkeuren niet mogelijk; staat vier ogen aan, dan mag de uploader het voorstel niet zelf beslissen (403)
- Uitzonderingen: zonder alle gegevens is er geen goedkeurknop

## Bewust laten liggen

| Punt | Reden |
|---|---|
| Geen aanpasscherm voor een ticket | het aanpassen is een API-route; voor een ticket zonder alle velden wijst de kaart op hand-invoer en afkeuren met reden |
| Geen bestandsvoorbeeld (de pdf) in het voorstel | een downloadroute voor het bestand is een eigen beveiligingsonderwerp |
| De pagina haalt de stand per upload alleen zolang hij openstaat | na verversen is de lijst van uploads weg; de lijst met facturen en de goedkeurwachtrij zijn de bron |
| Twee leveranciers met hetzelfde IBAN kunnen op de pagina worden toegevoegd | dag-1-gedrag; een waarschuwing hoort bij het leverancierbeheer (gemeld aan de regie) |

## Niet gemeten

- Een telefoonscherm.
- Een echte schermlezer; alleen rollen, labels en `aria-live` zijn met tests gemeten.
- Het gedrag van het uploadveld als het tabblad lang op de achtergrond staat (de browser vertraagt dan timers).
