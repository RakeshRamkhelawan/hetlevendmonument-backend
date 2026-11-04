# FE-PGS-040 -- Crediteuren nazorg: intrekken na goedkeuren en de reden bij een mislukte uitvoering

**Sprint:** Keten F, crediteuren nazorg (2026-10-27), backend BE-CRD-004
**Status:** Geimplementeerd; Gate 2 en acceptatie met beeld: zie review-FE-PGS-040
**Datum:** 2026-10-27
**Bestanden:** `frontend/src/components/payables/IntrekFormulier.tsx`, `frontend/src/pages/PayablesPage.tsx`, `frontend/src/components/hitl/HITLHistory.tsx`, `frontend/src/pages/HITLPage.tsx`, `frontend/src/hooks/useHITL.ts`, `frontend/src/lib/api/payables.ts`, `frontend/src/lib/api/payables-grens.ts`, `frontend/src/lib/api/hitl.ts`
**Handleiding:** `docs/user-guide/frontend/crediteuren-nazorg-intrekken.md`

---

## Beschrijving

- **Een goedgekeurde factuur intrekken.** Op de pagina Crediteuren staat bij een factuur met status Goedgekeurd een knop "Intrekken" voor wie het goedkeurrecht heeft (`payables:approve`). De knop opent een kort formulier: een reden van minstens 10 tekens (dezelfde grens als de server, `INTREKKEN_REDEN_MIN` in `payables-grens.ts`) en "Intrekken bevestigen". Na succes staat de melding "Factuur ... is ingetrokken en afgewezen." en ververst de lijst; de factuur heet dan Afgewezen. Een weigering van de server (bijvoorbeeld: het betaalbestand is al gemaakt) staat in gewone taal onder het veld en laat het formulier open. Een dubbelklik stuurt een verzoek.
- **Een goedgekeurd betaalvoorstel intrekken.** Een goedgekeurd voorstel staat niet meer in de wachtrij maar in de Geschiedenis (tab op de pagina Goedkeuringen). Klapt een goedkeurder een goedgekeurd betaalvoorstel open, dan staat er "Goedkeuring intrekken" (alleen voor wie besluiten mag nemen). Zelfde formulier. Na succes: "Het betaalvoorstel is ingetrokken. N facturen zijn vrijgegeven en kunnen opnieuw worden voorgesteld." Is het betaalbestand al gemaakt, dan zegt de server dat het niet meer kan (het bestand is eenmalig).
- **De reden bij een mislukte uitvoering.** Keurt een goedkeurder een voorstel goed en lukt de uitvoering niet (bijvoorbeeld omdat het rekeningnummer van een leverancier intussen is gewijzigd), dan toont de melding de vaste Nederlandse zin van de server (`execution_message`) en niet meer alleen "de actie kon niet worden uitgevoerd". Onbekende reden: de algemene uitleg bij de foutsoort zoals voorheen.
- **Verlopen.** Een aanvraag voorbij zijn termijn staat in de wachtrij als verlopen zonder knoppen (dat deed het scherm al; de server geeft de status `expired` nu ook bij het lezen).
- **Rechten.** De knoppen zijn een UI-aanwijzing; de backend toetst `payables:approve` per route.

## Trainingssamenvatting

### Een goedgekeurde factuur intrekken

- Actor: een gebruiker met het goedkeurrecht
- Voorwaarde: de factuur heeft status Goedgekeurd en zit in geen betaalbestand
- Actie: "Intrekken" kiezen, een reden van minstens 10 tekens invullen, "Intrekken bevestigen"
- Systeemreactie: de factuur wordt Afgewezen; de lijst ververst; een melding bevestigt het
- Succes: "Factuur ... is ingetrokken en afgewezen."
- Fout: een Nederlandse tekst van de server onder het veld (bijvoorbeeld dat het betaalbestand al gemaakt is)
- Uitzonderingen: zonder goedkeurrecht is er geen knop

### Een goedgekeurd betaalvoorstel intrekken

- Actor: een gebruiker met het goedkeurrecht
- Voorwaarde: het voorstel is goedgekeurd en er is nog geen betaalbestand van gemaakt
- Actie: in de Geschiedenis het voorstel openen, "Goedkeuring intrekken", een reden invullen, bevestigen
- Systeemreactie: de facturen komen vrij (Gecontroleerd) en kunnen opnieuw worden voorgesteld
- Succes: de melding bovenaan de pagina Goedkeuringen
- Fout: de server zegt dat het bestand eenmalig is en het voorstel dus niet meer in te trekken is

### De reden bij een mislukte uitvoering

- Actor: de goedkeurder
- Voorwaarde: een factuur of het IBAN van een leverancier veranderde na het voorstel
- Actie: het voorstel goedkeuren
- Systeemreactie: een melding met de vaste zin, bijvoorbeeld dat het rekeningnummer is gewijzigd en de facturen opnieuw worden voorgelegd
- Succes: de goedkeurder weet wat er nu gebeurt
- Fout: een onbekende reden geeft de algemene uitleg

## Bewust laten liggen

| Punt | Reden |
|---|---|
| Geen intrekknop op de kaart in de wachtrij | een goedgekeurd voorstel staat niet meer in de wachtrij; de Geschiedenis is de enige plek waar het zichtbaar is |
| Geen lijst van ingetrokken facturen of voorstellen | het auditlog bewaart wie, wat en waarom |
| Een voorstel van voor deze wijziging is niet in een keer in te trekken | de server kent zijn facturen niet; de facturen een voor een intrekken |

## Niet gemeten

- Een telefoonscherm.
- Een echte schermlezer; alleen rollen, labels en `aria-live`/`role="alert"` zijn getoetst.
