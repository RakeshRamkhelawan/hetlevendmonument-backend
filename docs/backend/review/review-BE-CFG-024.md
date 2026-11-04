# Review BE-CFG-024 — Phase2 Feature Flag (PHASE2_ENABLED)

## A. Eindoordeel

APPROVED WITH MINOR GAPS

## B. Samenvatting

De specificatie beschrijft een gerichte, veilige wijziging: de phase2 router wordt alleen gemount wanneer `PHASE2_ENABLED=true` staat. De broncode in `src/core/api/setup/router_registry.py` bevestigt dit patroon (`import os` aanwezig, conditionele `app.include_router(phase2_router)`). De Trainingssamenvatting is concreet en noemt het gewenste 404-gedrag bij een niet-gemounte router.

## C. Bevindingen per categorie

### 1. Coverage gaps

- Geen structurele gaps. De enige wijziging (router-registratie-gating) is volledig beschreven.
- TODO: de spec noemt dat `.env.example` niet is bijgewerkt vanwege bestandsrechten. Dit is een echte minor gap: zonder voorbeeld in `.env.example` is de feature flag voor nieuwe ontwikkelaars niet zichtbaar.

### 2. Functionele onduidelijkheden

- Geen. Het onderscheid tussen import-tijd (try/except blijft) en registratie-tijd (flag gate) is expliciet.

### 3. Technische onduidelijkheden

- De spec vermeldt "import os toegevoegd aan module-level imports". Geverifieerd in broncode regel 6.
- De default waarde `"false"` is veilig voor productie en consistent beschreven.

### 4. Ontbrekende foutstatussen en edge cases

- De Trainingssamenvatting beschrijft correct dat een niet-gemounte router een 404 oplevert.
- Een edge case ontbreekt: wat gebeurt er als `PHASE2_ENABLED` een niet-booleaanse waarde bevat (bijv. `PHASE2_ENABLED=1` of `TRUE`)? De huidige check is `.lower() == "true"`, dus alles anders valt terug naar false. Dit is defensief, maar niet gedocumenteerd.

### 5. Acceptatiecriteria problemen

- De spec verwijst naar `tests/unit/test_sp_e07_phase2_gate.py`. De criteria zijn niet expliciet als checklist opgenomen, maar de testverwijzing maakt ze achterhaalbaar.

### 6. Integratorhandleiding / API-uitleg problemen

- De Trainingssamenvatting voldoet als integratoruitleg voor dit interne configuratie-item.

### 7. Trainingsdata problemen

- De Trainingssamenvatting gebruikt het verplichte mini-format in een tabel. Geschikt voor LLM-training.

### 8. Structuur- en consistentieproblemen

- De spec is een compact feature-note i.p.v. het volledige backend template. Dat is acceptabel voor een kleine configuratiewijziging, maar inconsistent met recentere specs die het volledige template gebruiken.

### 9. Risico's voor implementatie, security of QA

- Laag risico. De wijziging is fail-closed (default uit). Het enige risico is dat een operator de vlag niet kent omdat `.env.example` ontbreekt.

## D. Issue Register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Low | MINOR GAP in spec | `.env.example` niet bijgewerkt | Nieuwe ontwikkelaars zien de nieuwe vlag niet | Voeg toe aan `.env.example`: `# Phase 2 endpoints. Default: false\nPHASE2_ENABLED=false` |
| Low | Trainingssamenvatting / edge case | Gedrag bij niet-lower-case waarden niet gedocumenteerd | Operators kunnen `TRUE` of `1` verwachten te werken | Noteer expliciet dat alleen exact `"true"` de router mount |

## E. Ontbrekende items

- Geen functioneel ontbrekende items.

## F. Verbeterde tekstvoorstellen

- Vervang "Default \"false\" is veilig voor productie." door "Default \"false\" is veilig voor productie. Alleen de exacte waarde \"true\" (lower-case) mount de router; andere waarden zoals \"TRUE\" of \"1\" vallen terug naar false."

## G. Release-oordeel

- Geschikt voor bouw / implementatie: ja.
- Geschikt voor QA en geautomatiseerd testen: ja.
- Geschikt voor LLM-training: ja, met bovenstaande minor gaps.
- Geschikt voor integratorhandleiding / API-documentatie: ja.
