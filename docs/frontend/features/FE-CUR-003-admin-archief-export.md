# FE-CUR-003 Tab "Archief" in het beheerscherm

**ID:** `FE-CUR-003` | **Datum:** 2026-11-01 | **Backend:** `BE-EP-054`

## Wat

Nieuw tabblad "Archief" in `portal/src/pages/AdminCuratie.tsx` met `portal/src/components/ArchiefExportPanel.tsx`:
knop "Maak nu een archiefexport", tabel met eerdere exports (datum, items, grootte, automatisch of
handmatig, controlegetal) en een downloadknop per export. API-client: `createArchiveExport`,
`getArchiveExports`, `downloadArchiveExport` in `portal/src/api/client.ts`.

## Trainingssamenvatting

- **Actor:** curator of beheerder.
- **Voorwaarde:** ingelogd met de rol curator of admin.
- **Actie:** Beheer > Archief > "Maak nu een archiefexport", of "Download" bij een regel.
- **Systeemreactie:** bouwt en controleert het pakket, toont het in de lijst; download levert een zip.
- **Succes:** melding met aantal items en grootte; de zip is een geldig BagIt 1.0-pakket.
- **Fout:** "De archiefexport is mislukt. Er is niets opgeslagen." of een downloadfout.
- **Uitzonderingen:** binnen een minuut na een vorige export weigert de server (429).
