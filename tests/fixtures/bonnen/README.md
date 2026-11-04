# Testset bonnen en facturen (bonlezer)

24 documenten met VERZONNEN gegevens en de juiste antwoorden erbij. Er staat geen echte persoon,
klant of bon in: leveranciers, adressen, KvK- en btw-nummers zijn verzonnen (een toevallige
overeenkomst met een bestaand bedrijf is niet bedoeld en niet gecontroleerd).

## Waarom zelf gemaakt

Er bestaat geen openbare set Nederlandse kassabonnen of facturen met antwoorden
(`docs/onderzoek-open-source-bonlezer.md`, sectie "Testset"), en echte bonnen van personen komen
niet in de repo (besluit Rakesh, 2026-10-10).

## Wat erin zit

| Soort | Aantal | Wat | Namen |
| --- | --- | --- | --- |
| `factuur_pdf` | 8 | factuur als PDF MET tekstlaag, drie sjablonen | `factuur_01` t/m `factuur_08` |
| `factuur_scan` | 4 | factuur als PDF met alleen een beeld (OCR nodig), licht scheef en korrelig | `factuur_09` t/m `factuur_12` |
| `bon_foto` | 12 | kassabon als foto-achtig JPG, de storing loopt op van netjes tot scheef, korrelig en onscherp | `bon_01` t/m `bon_12` |

Per document drie bestanden met dezelfde naam:

- `<naam>.pdf` of `<naam>.jpg`: wat een lezer te zien krijgt;
- `<naam>.json`: de JUISTE antwoorden. Velden: `soort`, `leverancier`, `datum` (ISO, `YYYY-MM-DD`),
  `totaal` (decimale tekst, incl. btw), `factuurnummer` (`null` bij een kassabon),
  `btw` (per tarief, `"9"` en `"21"`, het btw-BEDRAG), `btw_nummer`, `kvk_nummer`;
- `<naam>.tekst.txt`: de exacte regels die op het document staan. Daarmee wordt de veldenlaag los van
  het lezen (OCR) gemeten.

## Hoe ze gemaakt zijn

`python scripts/maak_bonnen_testset.py` (vast zaad, dus elke run geeft dezelfde bytes;
`--controle` geeft een fout als de bestanden in de repo afwijken van de generator).

- De bedragen kloppen intern: btw per tarief wordt per groep afgerond (half-up) en het totaal is
  de som. Facturen rekenen btw bovenop de nettobedragen, bonnen halen de btw uit de brutobedragen.
- De datums staan op zes manieren geschreven (`15-10-2026`, `15/10/2026`, `15 oktober 2026`,
  `15.10.2026`, `2026-10-15`, `15-10-26`); totaal- en btw-regels staan op meerdere manieren
  (`TOTAAL`, `TE BETALEN`, `Totaal incl. btw`; `BTW 21%`, `BTW 21% over ...`, een tabel
  `Tarief Netto BTW Bruto`).
- De beelden zijn gerenderd en daarna bewerkt (draaiing tot ongeveer 7 graden, een lichtverloop,
  korrel, lichte onscherpte, JPEG). Dat is een benadering van een foto, geen foto.

## Wat deze set NIET is

- Geen echte foto's: geen kreukels, glans, schaduw, thermisch papier of afgesneden randen.
- Een lettertype en een taal (Nederlands); geen handschrift.
- Gemaakt door dezelfde hand als de regels die ze testen. Een uitslag op de `.tekst.txt` is daarom
  een BOVENGRENS voor die regels, geen bewijs dat ze op echte bonnen werken. Zie
  `docs/evidence/bonlezer-meting-2026-10-15.md`.

## Gebruik

- Unittests (zonder OCR): `tests/unit/bonlezer/test_veldenlaag.py` loopt over alle `.tekst.txt`.
- Meting met OCR (Docling + Tesseract, in een container zonder netwerk):
  `scripts/bonlezer/Dockerfile.meting` en `scripts/bonlezer_meting.py`.
- Git slaat deze bestanden zonder regeleindeomzetting op (`.gitattributes`); de generator vergelijkt
  byte voor byte.
