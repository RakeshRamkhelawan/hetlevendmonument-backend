# FE-PGS-035 -- Debiteuren nazorg: besloten goedkeuringen, Nederlandse meldingen, menu per recht

**Sprint:** Debiteuren nazorg (2026-10-22), backend BE-DEB-005
**Status:** Geimplementeerd (frontend door de bouwer zelf nagekeken, zie review-FE-PGS-035; de backend door de security-reviewer)
**Datum:** 2026-10-22
**Bestanden:** `frontend/src/pages/HITLPage.tsx`, `frontend/src/hooks/useHITL.ts`, `frontend/src/lib/api/hitl.ts`,
`frontend/src/components/hitl/HITLActionCard.tsx`, `frontend/src/pages/Notifications.tsx`,
`frontend/src/components/layout/LegacyLayout.tsx`, `frontend/src/components/layout/BusinessSidebar.tsx`
**Handleiding:** `docs/user-guide/frontend/debiteuren-nazorg-goedkeuringen-menu.md`

---

## Beschrijving

- `/hitl`, Geschiedenis en de tabbladen Goedgekeurd en Afgekeurd: een goedkeurder ziet de besloten tickets van de eigen
  tenant (`GET /api/v1/tools/hitl/decided`) met wie besloot en wanneer; een beheerder houdt de volledige audit. Wie geen
  van beide is, ziet "De geschiedenis is alleen voor beheerders en goedkeurders." De teller "Vandaag goedgekeurd" telt de
  besluiten van vandaag mee. Een ticket met status `consumed` (goedgekeurd en uitgevoerd) telt als goedgekeurd.
- Goedkeuren met een uitvoeringsfout: geen ruwe code (`tool_failure`) meer naar de klant maar vaste Nederlandse tekst
  ("Ticket X is goedgekeurd, maar de actie is NIET uitgevoerd: ..."), via `uitvoeringsfoutUitleg`.
- De goedkeurkaart toont geen lege regel "Advies van de Co-Pilot" meer.
- `/notifications` is volledig Nederlands: Meldingen, Alle (N), Ongelezen (N), Alles als gelezen markeren, Geen meldingen,
  "U bent helemaal bij.", Bekijk details; de datum is nl-NL.
- Menu (het standaardmenu `LegacyLayout` en het zakelijke menu `BusinessSidebar`): Debiteuren voor wie `receivables:read`
  heeft; Goedkeuringen voor wie een goedkeurrecht per proces heeft (ADR-039: de beheerder keurt niets goed); Instellingen
  debiteuren en Vier ogen alleen voor de beheerder. Dit is een UI-aanwijzing; de backend dwingt het recht af.

## Trainingssamenvatting

### De besloten goedkeuringen bekijken

- Actor: goedkeurder
- Voorwaarde: ingelogd met een goedkeurrecht
- Actie: opent Goedkeuringen en kiest Geschiedenis (of Goedgekeurd/Afgekeurd)
- Systeemreactie: de besloten tickets van het eigen bedrijf, nieuwste eerst, met wie besloot en wanneer
- Succes: de zojuist goedgekeurde of afgekeurde herinnering staat erbij; "Vandaag goedgekeurd" telt mee
- Fout: zonder goedkeurrecht of beheerdersrol: "De geschiedenis is alleen voor beheerders en goedkeurders."
- Uitzonderingen: de inhoud van de aanvraag (de brief zelf) is in deze lijst niet te zien

### Goedkeuren terwijl de actie niet meer kan

- Actor: goedkeurder
- Voorwaarde: het voorstel hoort bij een factuur die intussen betaald is
- Actie: drukt op Goedkeuren
- Systeemreactie: het besluit wordt vastgelegd, de actie wordt niet uitgevoerd
- Succes: niet van toepassing
- Fout: "Ticket X is goedgekeurd, maar de actie is NIET uitgevoerd: <uitleg in gewone taal>"
- Uitzonderingen: bij een time-out of een onbekende foutcode staat een andere vaste Nederlandse tekst; nooit de ruwe code

### De menu-items vinden

- Actor: medewerker debiteuren, goedkeurder of beheerder
- Voorwaarde: ingelogd
- Actie: kijkt in de zijbalk
- Systeemreactie: alleen de items waar de rol recht op heeft
- Succes: debiteuren ziet Debiteuren; goedkeurder ziet Goedkeuringen; beheerder ziet Debiteuren, Instellingen debiteuren en Vier ogen
- Fout: een item dat ontbreekt betekent dat het recht ontbreekt, niet dat de pagina kapot is
- Uitzonderingen: een beheerder ziet Goedkeuringen alleen als hij ook een goedkeurrol heeft

## Regressierisico's

- Drie bestaande menutests leunden op de oude zichtbaarheid van Goedkeuringen en zijn aangepast (met uitleg in het
  commentaar): Goedkeuringen is niet meer voor een beheerder zonder goedkeurrecht.
- De beheerder krijgt in `/hitl` nog steeds de audit; alleen de goedkeurder haalt `/decided` op.
