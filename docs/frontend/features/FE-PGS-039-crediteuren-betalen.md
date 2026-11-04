# FE-PGS-039 -- Crediteuren: betalen (betaalvoorstel van de agent, de kaart in de goedkeurwachtrij, het betaalbestand)

**Sprint:** Keten F, crediteuren dag 3 (2026-10-25), backend BE-CRD-003
**Status:** Geimplementeerd en onafhankelijk geaccepteerd met beeld (2026-10-26, `D:/tmp/crd-acceptatie3/`); Gate 2 twee rondes GO, zie review-FE-PGS-039
**Datum:** 2026-10-25
**Bestanden:** `frontend/src/components/payables/BetaalSectie.tsx`, `frontend/src/components/hitl/PaymentRunDetails.tsx`, `frontend/src/components/hitl/HITLActionCard.tsx`, `frontend/src/lib/hitl/actie-omschrijving.ts`, `frontend/src/lib/api/payables.ts`, `frontend/src/pages/PayablesPage.tsx`
**Handleiding:** `docs/user-guide/frontend/crediteuren-betalen.md`

---

## Beschrijving

- **Betaalvoorstel op de pagina Crediteuren.** Wie `payables:write` heeft ziet onder "Betaalvoorstel" wat er nu aan de beurt is ("Nu aan de beurt: N facturen, samen EUR ...") en de knop "Betaalvoorstel laten maken". De agent legt EEN voorstel voor aan de goedkeurder; het scherm zegt hoeveel facturen en hoeveel geld, met een verwijzing "Naar de goedkeuringen", en bij vier ogen dat iemand anders moet goedkeuren. "Er is nu niets te betalen" als er niets aan de beurt is. Een 409 van de server toont zijn Nederlandse tekst, nooit de Engelse terugvaltekst "Conflict."; een tweede klik tijdens het maken doet niets dubbel.
- **De kaart "Betaalvoorstel" in de goedkeurwachtrij.** Een tabel met per factuur leverancier, factuurnummer, bedrag, vervaldatum (dag-maand-jaar), het gemaskeerde IBAN en de reden, daaronder het aantal, het totaal en "Waarom de agent dit voorlegt" volledig. Een gele melding "Vier ogen" (rol `note`) ALLEEN als de BACKEND dat zegt (`vier_ogen_vereist`), met het drempelbedrag. De knop heet "Goedkeuren voor betaling"; afkeuren vraagt een reden over het voorstel. Nooit ruwe JSON.
- **Het betaalbestand ophalen.** Wie het goedkeurrecht `payables:approve` heeft ziet onder "Betaalbestand ophalen" hoeveel goedgekeurde facturen er zijn, een waarschuwing dat het bestand maar een keer wordt gemaakt, en een formulier (naam van het eigen bedrijf, eigen IBAN, uitvoerdatum). De knop is uit zonder goedgekeurde facturen, met uitleg. Het bestand komt als tekst in het JSON-antwoord (de gedeelde API-client leest elk antwoord als JSON); de browser maakt er een download van. Na het downloaden zegt het scherm hoeveel facturen en hoeveel geld, dat het bestand niet opnieuw wordt gemaakt en dat er niets is verstuurd; de lijst ververst. Bij een weigering (409) blijft het scherm met de Nederlandse tekst van de server en wordt er niets gedownload.
- **Rechten.** Het scherm toont de secties naar `payables:write` en `payables:approve` (UI-aanwijzing; de backend toetst per route). De actie heet "Een betaalvoorstel van de crediteurenagent goedkeuren" (spiegel van `FOUR_EYES_ACTIONS`).

## Trainingssamenvatting

### Een betaalvoorstel laten maken

- Actor: crediteurenadministrateur
- Voorwaarde: de gebruiker heeft de rol `crediteuren` en opent Crediteuren
- Actie: kiest "Betaalvoorstel laten maken"
- Systeemreactie: de agent legt een voorstel voor; het scherm zegt hoeveel facturen en hoeveel geld, en verwijst naar de goedkeuringen
- Succes: het voorstel staat in de wachtrij van de goedkeurder
- Fout: een weigering van de server verschijnt in gewone taal; er verandert niets aan de facturen
- Uitzonderingen: "Er is nu niets te betalen" als er niets aan de beurt is

### Een betaalvoorstel goedkeuren

- Actor: goedkeurder
- Voorwaarde: de gebruiker heeft `payables:approve` en opent Goedkeuringen; boven het drempelbedrag is hij niet degene die het voorstel liet maken
- Actie: leest de kaart "Betaalvoorstel" en kiest "Goedkeuren voor betaling" of "Afkeuren" met een reden
- Systeemreactie: bij goedkeuren krijgen alle facturen de status goedgekeurd, of geen enkele (bij een gewijzigde factuur of IBAN); bij afkeuren blijft alles onbetaald
- Succes: de facturen zijn goedgekeurd
- Fout: de aanvrager boven het drempelbedrag krijgt een weigering (403); zonder reden (of korter dan 10 tekens) is afkeuren niet mogelijk
- Uitzonderingen: een verlopen voorstel kan niet meer worden goedgekeurd

### Het betaalbestand ophalen

- Actor: goedkeurder
- Voorwaarde: er zijn goedgekeurde facturen
- Actie: vult naam, eigen IBAN en uitvoerdatum in en kiest "Betaalbestand downloaden"
- Systeemreactie: een SEPA-bestand wordt gedownload; de facturen staan daarna op "In betaalbestand"; er is niets naar een bank verstuurd
- Succes: het scherm zegt hoeveel facturen en hoeveel geld, en dat het bestand niet opnieuw wordt gemaakt
- Fout: bij een ongeldig IBAN of een uitvoerdatum in het verleden weigert de server met een Nederlandse tekst; er is geen bestand en de facturen blijven goedgekeurd
- Uitzonderingen: een factuur waarvan de leverancier na de goedkeuring is gewijzigd gaat niet mee en wordt teruggezet naar gecontroleerd (het scherm noemt hem); een tweede verzoek vindt niets meer; het bestand kan niet opnieuw worden gemaakt, maar het scherm houdt het laatste bestand vast voor "Bewaar het laatste bestand nogmaals" als de download mislukt

## Bewust laten liggen

| Punt | Reden |
|---|---|
| Geen scherm voor het drempelbedrag | de waarde staat in `Tenant.settings`; een beheerroute volgt in de nazorg |
| Eigen IBAN en naam bij elk bestand opnieuw invullen | de rekening per klant instellen hoort bij het inrichtscherm voor koppelingen |
| Geen lijst van eerdere betaalbestanden | het bestand wordt niet bewaard (zie BE-CRD-003, besluit 7) |
| Geen aanpassen van een voorstel | een voorstel wordt afgekeurd en opnieuw gemaakt |

## Niet gemeten

- Een telefoonscherm.
- Een echte schermlezer; alleen rollen, labels en `aria-live` zijn getoetst.
- Een bank die het bestand inleest.
