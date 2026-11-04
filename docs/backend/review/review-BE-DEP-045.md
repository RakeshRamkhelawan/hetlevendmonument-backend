# Review BE-DEP-045 — get_tenant_custom_data_service

## A. Eindoordeel

APPROVED WITH MINOR GAPS

## B. Samenvatting

De specificatie beschrijft de introductie van `get_tenant_custom_data_service` in `src/core/api/v1/tenant_custom_data/dependencies.py` en de refactor van `router.py` naar ADR-033. De broncode bevestigt dat de factory bestaat en dat `router.py` geen directe DB-imports meer bevat. De spec is technisch over het algemeen correct.

## C. Bevindingen per categorie

### 1. Coverage gaps

- De spec inventariseert BE-DEP-045 en BE-RTR-044. Dekkend.
- De spec vermeldt dat de factory `TenantCustomDataService(db=db, tenant_id=current_user.tenant_id)` retourneert. De broncode retourneert echter `TenantCustomDataService(TenantCustomDataRepository(db))` zonder `tenant_id`. In de router wordt `current_user.tenant_id` per methode-aanroep doorgegeven. De spec is hier onjuist.

### 2. Functionele onduidelijkheden

- Geen. De factory-rol is duidelijk.

### 3. Technische onduidelijkheden

- De spec zegt "Retourneert TenantCustomDataService(db=db, tenant_id=current_user.tenant_id)". Broncode: `TenantCustomDataService(TenantCustomDataRepository(db))`. Dit is een concrete inconsistentie.
- De spec zegt "TenantCustomDataService accepteert tenant_id in constructor" onder Open aannames. De broncode van `dependencies.py` geeft geen `tenant_id` mee, maar `router.py` roept methodes aan met `current_user.tenant_id`. De aanname klopt dus niet met de huidige code.

### 4. Ontbrekende foutstatussen en edge cases

- De spec noemt 401, 403, 404, 422, 500. De 401 wordt veroorzaakt door `get_current_user` in de router, niet in de factory. Dat is correct op router-niveau, maar de spec claimt dat auth in de factory zit.

### 5. Acceptatiecriteria problemen

- Criteria zijn testbaar. "Router.py bevat geen import van AsyncSession, get_db, select" is geverifieerd in broncode.

### 6. Integratorhandleiding / API-uitleg problemen

- Kort en correct.

### 7. Trainingsdata problemen

- Trainingssamenvatting volgt het verplichte mini-format. Geschikt.

### 8. Structuur- en consistentieproblemen

- Inconsistentie tussen spec en broncode over constructor-signatuur en tenant_id doorgeven.
- TODO(TYPE) comments in `router.py` voor `Any` types vallen buiten scope, maar de spec noemt ze niet.

### 9. Risico's voor implementatie, security of QA

- Laag risico. Tenant-isolatie wordt correct afgedwongen in de router/service, ook al is de spec onnauwkeurig over de constructeur.

## D. Issue Register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Medium | Technische beschrijving / Afhankelijkheden | Spec claimt dat factory `tenant_id` in service-constructor injecteert | Broncode injecteert alleen `TenantCustomDataRepository(db)` | Corrigeer technische beschrijving: factory injecteert repository; tenant_id wordt per methode in router doorgegeven |
| Low | Open aannames | "TenantCustomDataService accepteert tenant_id in constructor" | Niet overeenkomend met broncode | Corrigeer aanname of verwijder |

## E. Ontbrekende items

- Geen functioneel ontbrekende items.

## F. Verbeterde tekstvoorstellen

- "Retourneert TenantCustomDataService(db=db, tenant_id=current_user.tenant_id)" -> "Retourneert TenantCustomDataService(TenantCustomDataRepository(db)); tenant_id wordt per service-methode-aanroep uit de router doorgegeven."

## G. Release-oordeel

- Geschikt voor bouw / implementatie: ja.
- Geschikt voor QA en geautomatiseerd testen: ja.
- Geschikt voor LLM-training: ja, na correctie van constructor-beschrijving.
- Geschikt voor integratorhandleiding / API-documentatie: ja.
