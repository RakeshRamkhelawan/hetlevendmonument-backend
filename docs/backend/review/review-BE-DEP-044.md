# Review BE-DEP-044 — get_gamification_service

## A. Eindoordeel

APPROVED WITH MINOR GAPS

## B. Samenvatting

De specificatie beschrijft de introductie van een FastAPI Depends-factory `get_gamification_service` in `src/core/api/v1/gamification/dependencies.py` en de rewrite van `router.py` zonder directe DB-imports. De broncode bevestigt dat `dependencies.py` de factory bevat en dat `router.py` alleen nog `get_current_user` en `get_gamification_service` importeert. De ADR-033 doelstelling lijkt bereikt.

## C. Bevindingen per categorie

### 1. Coverage gaps

- De spec inventariseert BE-DEP-044 en BE-RTR-044. Dat dekt de wijziging.
- Een kleine gap: de spec vermeldt dat auth via `get_current_user` in de factory afgedwongen wordt, maar de broncode van `dependencies.py` toont geen `get_current_user` import of gebruik. Auth wordt in `router.py` per endpoint afgedwongen. De spec claimt dat auth in de factory zit, wat niet overeenkomt met de code.

### 2. Functionele onduidelijkheden

- Geen. De functie van de factory is helder.

### 3. Technische onduidelijkheden

- De spec zegt "`Depends(get_db)` voor AsyncSession; `Depends(get_current_user)` voor auth". In de broncode staat alleen `Depends(get_db)`. Dit is een foutieve claim.
- De spec zegt "GamificationService ontvangt tenant_id per methode-aanroep". De broncode van `dependencies.py` retourneert `GamificationService(db)` zonder tenant_id in de constructor. Dat is consistent met `router.py` die `current_user.id` en `current_user.tenant_id` doorgeeft aan de service-methodes.

### 4. Ontbrekende foutstatussen en edge cases

- De spec noemt 401, 403, 404, 422. De factory zelf kan alleen 401 veroorzaken als `get_current_user` erin zat; dat is niet het geval. In de huidige code zit auth in de router, dus de foutstatussen zijn router-level. Dat is acceptabel, maar de spec moet dat correct weergeven.

### 5. Acceptatiecriteria problemen

- Criterium "Router.py bevat geen import van AsyncSession, get_db, select, func" is testbaar.
- Criterium "Ongeauthenticeerde aanroepen geven 401" is testbaar via de router.
- Criterium "get_gamification_service retourneert een GamificationService instantie" is testbaar.

### 6. Integratorhandleiding / API-uitleg problemen

- De Integratoruitleg is kort en correct. De opmerking over `limit` (max 100) klopt met de broncode (`Query(default=50, ge=1, le=100)`).

### 7. Trainingsdata problemen

- De Trainingssamenvatting volgt het verplichte mini-format. Geschikt voor LLM-training.

### 8. Structuur- en consistentieproblemen

- Er is een inconsistentie tussen de spec en de broncode over waar auth wordt afgedwongen (factory vs router). Dit moet worden gecorrigeerd.
- De spec gebruikt het volledige backend template. Dat is consistent met de workflow.

### 9. Risico's voor implementatie, security of QA

- Laag risico. Auth wordt nog steeds correct afgedwongen, alleen niet op de plek die de spec claimt.

## D. Issue Register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Medium | Detaildocumentatie / Zichtbaarheids- en toegangsregels | Spec beweert dat auth via `get_current_user` in de factory afgedwongen wordt | In `dependencies.py` wordt geen `get_current_user` gebruikt; auth zit in de router endpoints | Corrigeer de spec: auth wordt afgedwongen in de router endpoints, de factory injecteert alleen DB |
| Low | Detaildocumentatie / Afhankelijkheden | `get_current_user` staat genoemd als afhankelijkheid van de factory | Niet aanwezig in broncode | Verwijder `get_current_user` uit de afhankelijkheden van BE-DEP-044; voeg toe aan BE-RTR-044 |

## E. Ontbrekende items

- Geen.

## F. Verbeterde tekstvoorstellen

- "Auth wordt via get_current_user afgedwongen" -> "Auth wordt via get_current_user afgedwongen in de router endpoints; de factory injecteert uitsluitend de DB-sessie."
- Verwijder `get_current_user` uit de afhankelijkheden van BE-DEP-044.

## G. Release-oordeel

- Geschikt voor bouw / implementatie: ja.
- Geschikt voor QA en geautomatiseerd testen: ja.
- Geschikt voor LLM-training: ja, na correctie van de auth-locatie.
- Geschikt voor integratorhandleiding / API-documentatie: ja.
