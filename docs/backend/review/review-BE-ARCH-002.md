# Review: BE-ARCH-002 Geen naive datetime preventietest

## A. EINDOORDEEL

APPROVED WITH MINOR GAPS

## B. SAMENVATTING

De spec beschrijft correct de architectuur-test die verbiedt naive `datetime.now()` en `datetime.utcnow()` in `src/`. De implementatie in `tests/architecture/test_no_naive_datetime.py` gebruikt AST-gebaseerde detectie die rekening houdt met import-aliassen en zowel `datetime.now()` als `datetime.datetime.now()` dekt. De test is klein, gericht en slagen. Enkele randvoorwaarden ontbreken in de spec.

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

- De spec noemt dat de test `src/` scant, maar niet dat `tests/` en `.venv/` buiten scope blijven.
- De spec noemt dat de test AST-gebaseerd is, maar beschrijft niet concreet hoe alias-imports worden behandeld.
- Trainingssamenvatting ontbrak; wordt in deze ronde toegevoegd.

### 2. Functionele onduidelijkheden

- Geen.

### 3. Technische onduidelijkheden

- Geen.

### 4. Ontbrekende foutstatussen en edge cases

- Geen beschrijving van `_EXEMPT_FILES`: momenteel leeg, maar de mechanismekans is niet uitgelegd.
- Geen beschrijving van het feit dat dynamische reflectie (bijv. `getattr(datetime, "now")()`) niet gedekt wordt.

### 5. Acceptatiecriteria problemen

- Geen expliciete acceptatiecriteria opgenomen.

### 6. Integratorhandleiding / API-uitleg problemen

- De integratoruitleg is beperkt. Een korte uitleg voor ontwikkelaars over het gebruik van `datetime.now(timezone.utc)` ontbreekt.

### 7. Trainingsdata problemen

- Trainingssamenvatting ontbrak.

### 8. Structuur- en consistentieproblemen

- Geen.

### 9. Risico's voor implementatie, security of QA

- Geen materiele risico's. De test is een lichtgewicht regressie-guard.

## D. ISSUE REGISTER

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
|----------|--------------|----------|----------------------------|--------------------|
| Low | Oplossing | `_EXEMPT_FILES` mechanisme en scope (alleen `src/`) niet beschreven. | Toekomstige reviewers weten niet hoe een uitzondering toegevoegd kan worden. | Voeg toe dat de scan alleen `src/` omvat en dat uitzonderingen in `_EXEMPT_FILES` staan. |
| Low | Oplossing | AST-alias-afhandeling en niet-gedekte dynamische reflectie niet concreet. | Ontwikkelaars kunnen denken dat alle vormen gedekt zijn. | Documenteer alias-tracking en expliciete scope-grens (geen `getattr`). |
| Low | Acceptatiecriteria | Geen expliciete criteria. | QA weet niet zonder tests wat "klaar" is. | Voeg 2 criteria toe. |
| Low | Trainingssamenvatting | Sectie ontbrak. | Vereiste voor LLM-training. | Toegevoegd in deze ronde. |

## E. ONTBREKENDE ITEMS

- Scope-beschrijving (alleen `src/`).
- Documentatie van `_EXEMPT_FILES` en alias-tracking.

## F. VERBETERDE TEKSTVOORSTELLEN

Oplossing sectie mag uitbreiden met:

> De scan beperkt zich tot `src/`; `tests/` en virtuele-omgevingen vallen buiten scope. `_datetime_aliases()` volgt zowel `import datetime`, `import datetime as dt`, `from datetime import datetime` als aliassen. De detectie is statisch: dynamische constructies zoals `getattr(datetime, "now")()` worden niet gedekt.

## G. RELEASE-OORDEEL

- Geschikt voor bouw / implementatie: Ja.
- Geschikt voor QA en geautomatiseerd testen: Ja.
- Geschikt voor LLM-training: Ja, na toevoeging Trainingssamenvatting.
- Geschikt voor integratorhandleiding / API-documentatie: Ja, met kleine aanvulling.
