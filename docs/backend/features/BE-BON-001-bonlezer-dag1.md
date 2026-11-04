# Backend Feature Specification

## Metadata

- **Feature ID:** BE-BON-001
- **Feature naam:** Bonlezer dag 1 -- een eigen testset, een lezer (Docling + Tesseract nld) en een veldenlaag, met een meting per veld
- **Status:** Gereed voor de push (Gate 2 twee rondes afgerond, zie de review); de agent is NIET bedraad
- **Auteur:** bouwer bonlezer1 (sessie sanskritisetu-org-bd, nu -7d)
- **Reviewer:** code-reviewer, quality-reviewer en security-reviewer (subagents, Gate 2, twee rondes)
- **Datum:** 2026-10-15
- **Gerelateerde user story / ticket:** brief `docs/agent-briefs/generated/2026-10-15-sprint-dag-bonlezer-dag1-testset-en-lezen.md` (SP-KLANT-04, `mkb.zero_admin`); onderzoek `docs/onderzoek-open-source-bonlezer.md`
- **Gerelateerde router / module:** `src/core/als/bonlezer/` (`veldenlaag.py`, `lezer.py`, `meting.py`); GEEN router en GEEN endpoint
- **Gerelateerde frontend endpoints:** geen
- **Gerelateerde database tabellen:** geen (GEEN migratie)
- **Versie:** 1.0

## Doel en scope

### Doel

Een bon of factuur (PDF of beeld) wordt lokaal, zonder netwerk, omgezet in tekst en daaruit in velden:
leverancier, datum, totaal, btw per tarief (9% en 21%), factuurnummer, btw-nummer en KvK-nummer. Dag 1
levert niet de agent maar het MEETINSTRUMENT: een zelfgemaakte Nederlandse testset met de juiste
antwoorden, een lezer, een veldenlaag en een meting per veld.

### In scope

- `tests/fixtures/bonnen/`: 24 verzonnen documenten (8 facturen met tekstlaag, 4 gescande facturen,
  12 kassabonnen als foto-achtig beeld) met per stuk `.json` (antwoorden) en `.tekst.txt` (brontekst);
  `scripts/maak_bonnen_testset.py` maakt ze deterministisch.
- `src/core/als/bonlezer/veldenlaag.py`: `lees_velden(tekst) -> BonVelden`, `parse_bedrag`,
  `parse_datum`. Bedragen zijn `Decimal`.
- `src/core/als/bonlezer/lezer.py`: `BonLezer.lees(pad)`; Docling met Tesseract `nld` als OCR; regels
  opgebouwd uit de celposities (`regels_uit_resultaat`); een netwerkslot als tripdraad
  (`geen_netwerk()`); invoercontrole (`controleer_bestand`).
- `src/core/als/bonlezer/meting.py` en `scripts/bonlezer_meting.py`: tellen per veld goed/totaal en
  schrijven het verslag.
- `scripts/bonlezer/Dockerfile.meting`: wegwerp-meetimage; de meting draait met `--network none`.
- `requirements-bonlezer.txt` (apart, vastgepind), `docs/evidence/bonlezer-meting-2026-10-15.md` en
  `docs/evidence/bonlezer-licenties-2026-10-15.csv`.

### Buiten scope

- De agent bedraden (`receiptscanner`), een upload-route, een scherm, het btw-concept (dag 2-4).
- Een eigen worker-image of service (besluit regie 2026-10-15; komt in de brief voor dag 2).
- Echte bonnen of foto's; handschrift; andere talen.

## Stap 0 -- wat is gemeten (2026-10-15)

| Wat | Meting | Hoe |
| --- | --- | --- |
| Licenties | geen AGPL, GPL of LGPL onder 101 Python-pakketten; MPL-2.0 voor tqdm en certifi; libglib2.0-0 LGPL als dynamische systeembibliotheek | `pip-licenses` in de meetcontainer, `docs/evidence/bonlezer-licenties-2026-10-15.csv` |
| Docling-uitvoer | de platte export voegt regels samen: totaal 1 van 24 | meetscript, container zonder netwerk |
| Na regelopbouw uit celposities | totaal 24 van 24, btw 21% 21 van 21, btw 9% 15 van 16, leverancier 23 van 24 | idem, sha 09eba1dd |
| Grootte | minimaal bonlezer-image ongeveer 2,1 GB zwaarder; 52 nieuwe Python-pakketten, 1,31 GB | `docker history` en pakketmetadata, gerekend uit lagen |

## Gedrag

### De veldenlaag

Regels, geen model. Per veld: het laatste bedrag op een totaalregel (eerst "te betalen"/"totaal incl.",
dan een regel die met "totaal" begint, dan elke "totaal"-regel; "subtotaal", "excl." en "totaal btw"
tellen niet); btw per tarief uit een regel met "btw" of een tabelrij die met het tarief begint, waarbij
het btw-bedrag het getal is dat bij netto x tarief past. **De laag raadt niet**: bij een tabelrij met een
enkel bedrag, of twee of meer bedragen zonder passend paar, blijft het tarief leeg. Een spatie als
duizendtal (`1 234,56`) is dubbelzinnig en geeft geen bedrag. Invoer wordt afgekapt op 500 tekens per
regel en 200.000 tekens per document; alle herhalingen in de patronen zijn begrensd.

### De lezer

`controleer_bestand`: soort in `TOEGESTANE_SOORTEN`, bestand bestaat en is niet leeg, hoogstens 25 MB,
de eerste bytes passen bij de extensie, bij een beeld hoogstens 40 miljoen pixels (frames meegeteld).
Docling krijgt `max_num_pages=10`, `max_file_size` en een `document_timeout` van 120 s. Een pagina met
meer dan 2000 tekstcellen wordt geweigerd. Foutmeldingen noemen de bestandsnaam niet.

`geen_netwerk()` is een tripdraad en geen hek: het dekt `connect`, `connect_ex`, `sendto`, `sendmsg` en
`getaddrinfo` in dit proces, met een teller zodat overlappende blokken het slot niet laten staan. Het
dekt geen subproces (Tesseract), geen al open socket en geen rechtstreekse `_socket`-aanroep. De echte
afdwinging is een container met `--network none` of een netwerkbeleid op de worker.

### Foutcodes

Geen API. `OngeldigBestand` (ongeldig of te groot bestand), `GeenNetwerkToegestaan` (netwerkpoging
tijdens het lezen).

## Afhankelijkheden

Docling 2.139.0 (MIT), Tesseract 5.3 met `nld` (Apache-2.0), CPU-torch 2.14.1; alleen in
`requirements-bonlezer.txt` en de meetcontainer, NIET in `requirements-base.txt` of `-prod.txt`.
Pillow voor de pixelcontrole is een optionele import. De applicatie importeert `src.core.als.bonlezer`
nergens; `src/core/als/__init__.py` laadt het niet.

## Trainingssamenvatting

### Een bon of factuur lezen (ontwikkelaar of meetscript)

- **Actor:** de bonlezer-code of het meetscript; later de agent.
- **Voorwaarde:** bestand van een toegestane soort, binnen de grenzen; Docling-modellen vooraf in een
  map (`artifacts_pad`); geen netwerk nodig.
- **Actie:** `BonLezer(artifacts_pad=...).lees(pad)` geeft tekst met regels; `lees_velden(tekst)` geeft
  de velden.
- **Systeemreactie:** een `BonVelden` met `None` of een ontbrekend tarief voor wat niet te lezen is.
- **Succes:** de velden zijn goed of leeg.
- **Fout:** `OngeldigBestand` voor een bestand buiten de grenzen; een veld dat leeg blijft is geen fout.
- **Uitzondering:** een bon met een opmaak die niet in de testset zit kan een veld leeg of verkeerd
  laten; de meting zegt hoe vaak dat in de set gebeurt.

## Regressierisico's

- De veldenlaag is afgestemd op 24 documenten die dezelfde hand maakte als de regels; de OCR-cijfers
  gelden voor die set (`docs/evidence/bonlezer-meting-2026-10-15.md`).
- Het netwerkslot raakt het hele proces zolang een blok open is; draai de lezer niet in een proces dat
  tegelijk databaseverbindingen opent.
- Docling en torch maken het image ongeveer 2,1 GB zwaarder; daarom een eigen image of service.
- Een volgende versie van Docling kan de celstructuur veranderen (`pages[].assembled.elements[].cluster
  .cells[]`, gemeten voor 2.139.0); `regels_uit_resultaat` valt dan terug op de platte export.
