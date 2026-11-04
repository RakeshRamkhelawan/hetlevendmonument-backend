# Onderzoek: open-source bonlezer voor `receiptscanner`

Datum: 2026-10-09. Rol: vraag (alleen onderzoek, niets geinstalleerd, niets getest).

## Wat er al in de repo is

- `src/core/als/agents/skills/receiptscanner.py` + `manifests/receiptscanner.yml`: een
  skill die alleen een manifest laadt. Geen OCR.
- Config: `mkb_admin_lite_receiptscanner.yaml`.
- `src/workers/actors.py:564`: commentaar "Simulate processing (in production: OCR ...)".
- Geen OCR-pakket in `requirements*.txt` (gemeten met `git grep -i -E "tesseract|ocr|paddle"`).

Conclusie: er is nog geen bonlezer; de keuze is vrij.

## Vergelijking

Licentie code: gemeten met `gh api repos/<repo>/license`. Laatste push: `gh repo view`
(peildatum 2026-10-09). Gewichten: gelezen in het LICENSE-bestand of de modelkaart op
Hugging Face. "NL" en "CPU" komen uit documentatie, NIET zelf gemeten.

| Kandidaat | Licentie code | Licentie gewichten | Commercieel SaaS ok? | NL-taal | CPU | Onderhoud (laatste push, sterren) | Bron |
|---|---|---|---|---|---|---|---|
| Tesseract | Apache-2.0 | Apache-2.0 (tessdata, incl. `nld`) | Ja | Ja, `nld` model | Ja, licht | 2026-10-09, 77k | github.com/tesseract-ocr/tesseract |
| PaddleOCR (PP-OCR) | Apache-2.0 | Apache-2.0 (in repo) | Ja | Latijns schrift-model; NL niet specifiek | Ja | 2026-09-16, 91k | github.com/PaddlePaddle/PaddleOCR |
| docTR (Mindee) | Apache-2.0 | Apache-2.0 | Ja | Latijns/Frans-Engels getraind; NL-accenten niet gemeten | Ja, trager | 2026-10-09, 6k | github.com/mindee/doctr |
| EasyOCR | Apache-2.0 | Apache-2.0 | Ja | Ja, `nl` | Ja, traag | 2025-12-05, 30k (weinig actief) | github.com/JaidedAI/EasyOCR |
| Surya | Apache-2.0 | AI Pubs Open RAIL-M (gewijzigd) | **Nee boven grens** | Ja (90+ talen) | Traag | 2026-09-11, 21k | github.com/datalab-to/surya |
| Marker | Apache-2.0 (code) | Gebruikt Surya-gewichten | **Nee boven grens** | via Surya | Traag | 2026-10-02, 40k | github.com/datalab-to/marker |
| Donut | MIT | MIT (`donut-base`) | Ja | Niet op NL-bonnen getraind; vereist eigen fine-tuning | Zwaar | 2024-07-11 (stil) | github.com/clovaai/donut |
| Docling (IBM) | MIT | MIT (docling-ibm-models) | Ja | Via ingeplugde OCR (Tesseract/EasyOCR) | Ja | 2026-10-09, 69k | github.com/docling-project/docling |
| Unstructured | Apache-2.0 | n.v.t. (gebruikt Tesseract) | Ja | via Tesseract | Ja | 2026-10-09, 16k | github.com/Unstructured-IO/unstructured |
| invoice2data | MIT | n.v.t. (regels/sjablonen) | Ja | Sjablonen per leverancier, zelf te schrijven | Ja | 2026-10-06, 2k | github.com/invoice-x/invoice2data |
| OCRmyPDF | MPL-2.0 | n.v.t. (Tesseract) | Ja voor zichzelf; **let op Ghostscript (AGPL)** | via Tesseract | Ja | 2026-10-07, 35k | github.com/ocrmypdf/OCRmyPDF |
| LayoutLMv3 | MIT (unilm-code) | **CC-BY-NC-SA-4.0** | **Nee** (niet-commercieel) | Engels | Zwaar | 2026-09-21 | huggingface.co/microsoft/layoutlmv3-base |
| Qwen2.5-VL-3B | Apache-2.0 (code) | **qwen-research** | **Nee** | Ja | Zeer traag | -- | huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct |
| Qwen2.5-VL-7B | Apache-2.0 (code) | Apache-2.0 | Ja | Ja | Praktisch alleen GPU | -- | huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct |

### Citaten bij de afwijzingen

- **Surya/Marker**, `MODEL_LICENSE` sectie "Commercial": beperkingen gelden "(a) for any
  purpose if You (your employer, or the entity you are affiliated with) generated more than
  five million US Dollars ($5,000,000) in gross revenue in the prior year" en "(b) ... has
  raised more than five million US dollars ($5,000,000) in total equity or debt funding".
  README: "free for research, personal use, and startups under $5M funding/revenue".
  Vandaag mogelijk binnen de grens, maar een plafond onder een product is geen "volledig gratis".
- **LayoutLMv3**: modelkaart `license: cc-by-nc-sa-4.0` (NC = non-commercial).
- **Qwen2.5-VL-3B**: modelkaart `license_name: qwen-research`. De 7B-variant staat op
  `license: apache-2.0`.

### AGPL-risico

- **Ghostscript** (vereist door OCRmyPDF voor PDF/A-uitvoer) is AGPL-3.0. Wie een
  AGPL-programma aanpast en via een netwerk aanbiedt, moet de broncode van die aangepaste
  versie aanbieden (AGPL-3.0 sectie 13). Onaangepast als los programma aanroepen is een
  andere situatie, maar dat is een juridische vraag die hier niet beantwoord wordt.
- **PyMuPDF** (AGPL-3.0) is een veelgebruikte PDF-bibliotheek in deze ketens. Niet
  gebruiken; `pypdfium2` (Apache-2.0/BSD) of `pdfplumber` (MIT) zijn alternatieven.
  Niet nagelopen welke kandidaat PyMuPDF transitief meeneemt -- verifieer met
  `pip-licenses` na installatie in een losse venv.

## Aanbeveling

**Keuze: Docling (MIT) met Tesseract `nld` als OCR-motor, plus een eigen veldenlaag.**

Waarom:
- Code en gewichten MIT/Apache: geen omzetgrens, geen plicht tot openbaren.
- Draait lokaal op CPU in een container; geen financiele documenten naar buiten.
- Leest zowel foto's als PDF (met tekstlaag direct, zonder tekstlaag via OCR).
- Tesseract heeft een officieel Nederlands model en is het best onderhouden.
- Velden (leverancier, datum, bedrag, btw 9%/21%, factuurnummer) haal je daarna uit de
  tekst met eigen regels; patronen als "BTW 21%" en een totaalbedrag zijn op NL-bonnen
  goed te herkennen. invoice2data (MIT) kan hiervoor als sjabloonbasis dienen.

**Terugvaloptie: PaddleOCR (Apache-2.0)** als Tesseract op foto's (scheef, kreukels,
thermisch papier) te slecht leest. Sterker op foto's, maar zwaardere afhankelijkheid
(PaddlePaddle).

Later, als er een GPU is: Qwen2.5-VL-**7B** (Apache-2.0) kan velden direct uit het beeld
halen. NIET de 3B-variant (research-licentie).

## Risico's en wat NIET gemeten is

- Geen enkele kandidaat is gedraaid op een echte Nederlandse bon. Leesnauwkeurigheid is
  onbekend. Volgende stap: 20 echte bonnen/facturen (foto + PDF) door Tesseract-nld en
  PaddleOCR halen en per veld tellen.
- Docker-grootte niet gemeten (Docling haalt PyTorch binnen; verwacht honderden MB tot
  meer dan 1 GB).
- Transitieve licenties niet nagelopen (zie AGPL-risico).
- Btw-tarief afleiden uit tekst is foutgevoelig bij bonnen met gemengde tarieven.
- Dit is geen juridisch advies; licentieteksten zijn geciteerd, niet uitgelegd.

---

## Testset: openbare bonnen en facturen (2026-10-09)

Gezocht via internet en GitHub (`gh repo view --json licenseInfo`, `gh api .../contents`).
Er is GEEN openbare set met Nederlandse kassabonnen gevonden (zoekacties op Hugging Face
"dutch receipts", "kassabon", "dutch invoices" leverden niets op).

| Bron | Licentie (gemeten) | Taal/land | Aantal | Antwoorden erbij | Vorm | URL |
|---|---|---|---|---|---|---|
| invoice2data `tests/compare` | MIT (`gh repo view`) | o.a. 2x Coolblue (NL), verder EN/FR/IN/PL | 13 facturen | ja, `.json` per factuur | PDF (+ enkele PNG) | https://github.com/invoice-x/invoice2data/tree/master/tests/compare |
| SI-UBL testset (Peppol-autoriteit NL) | MIT (`gh repo view`) | NL e-factuur (SI-UBL 1.x/2.0, NLCIUS-CII, Peppol BIS 3) | tientallen XML | het XML-bestand IS het antwoord | XML, geen beeld | https://github.com/SimplerInvoicing/testset |
| SROIE (ICDAR 2019) | repo MIT; voor de data zelf geen licentie gevonden | Maleisie, Engels | 1000 bonnen | ja: bedrijf, adres, datum, totaal | foto/scan | https://github.com/zzzDavid/ICDAR-2019-SROIE |
| CORD (Clova) | CC BY 4.0 (`gh repo view clovaai/cord`) | Indonesie | ~11.000 bonnen (1000 openbaar) | ja, regels + totalen | foto | https://github.com/clovaai/cord |
| CORU / ReceiptSense | niet gemeten | Egypte, Arabisch/Engels | ~20.000 | ja | foto | https://arxiv.org/abs/2406.04493 |
| FATURA | niet gemeten | synthetisch, Engels | 10.000 | ja | beeld | https://arxiv.org/abs/2311.11856 |

Persoonsgegevens: de Coolblue-PDF's zijn echte facturen; niet geopend, dus niet vastgesteld
of er naam/adres van een klant in staat -- controleren voor gebruik. SROIE/CORD bevatten
winkelgegevens, geen klantgegevens (niet per bestand gecontroleerd).

Niet gemeten: Kaggle, Mendeley Data, Zenodo; voorbeeldfacturen van Belastingdienst/KVK
(niet gevonden als downloadbare set); de exacte licentie van SROIE-data, CORU en FATURA.

### Advies

1. **Gebruik invoice2data (2 NL-facturen met antwoorden, MIT) en SROIE/CORD** om de
   werking van Docling + Tesseract op bonfoto's te meten (bedrag, datum, leverancier).
   Die meten OCR-kwaliteit, niet Nederlandse btw.
2. **Maak de NL-btw-set zelf**, want die bestaat openbaar niet. Werkwijze (alleen
   beschreven, niet gemaakt): neem de SI-UBL-voorbeeld-XML's (MIT, juiste antwoorden
   staan erin: leverancier, datum, factuurnummer, btw 9%/21%, totaal), render ze met een
   UBL-naar-PDF-weergave of een factuursjabloon naar PDF, print er ~10 en fotografeer ze
   (scheef, kreukel, slecht licht). Zo ontstaan ~20 NL-testfacturen met bekende uitkomst
   en zonder persoonsgegevens. Voor kassabonnen: een eigen bonprinter-sjabloon met
   verzonnen winkel en 9%/21%-regels, op dezelfde manier gefotografeerd.
3. Commercieel testen: MIT en CC BY 4.0 staan dit toe (bij CC BY met naamsvermelding);
   SROIE pas gebruiken als de datalicentie is gevonden.
