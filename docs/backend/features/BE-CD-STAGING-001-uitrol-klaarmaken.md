# Backend Feature Specification

## Metadata

- **Feature ID:** BE-CD-STAGING-001
- **Feature naam:** De staging-uitrol klaarmaken: applicatierol, Mistral, alle werkers, mail en links
- **Status:** Klaargemaakt in de repo en getest op structuur; NIET uitgerold (interlock 2). Gate 2 staat in `docs/backend/review/review-BE-CD-STAGING-001.md`
- **Auteur:** bouwsessie staginguitrol
- **Reviewer:** security-reviewer (subagent, Gate 2)
- **Datum:** 2026-10-23
- **Gerelateerde ticket:** brief `docs/agent-briefs/generated/2026-10-23-sprint-dag-staging-uitrol-klaarmaken.md`
- **Gerelateerde module:** `.github/workflows/cd-staging.yml`, `docker-compose.prod.yml`, `docs/infra/UITROL-STAGING-2026-10.md`, `tests/architecture/test_staging_uitrol_gebruikt_de_applicatierol.py`
- **Gerelateerde database tabellen:** geen (GEEN migratie)
- **Versie:** 1.0

## Doel en scope

### Doel

De laatste geslaagde staging-uitrol was 2026-09-11. Sindsdien zijn de applicatierol (startcontrole die de eigenaarsrol weigert), het taalmodel (Mistral in plaats van DeepSeek), de leerwerker en de bonlezer, en mail en links veranderd; de workflow wist daar niets van. Deze dag maakt de workflow en de compose klaar en schrijft de lijst voor Rakesh.

### Buiten scope

Niet uitrollen, geen `gh workflow run cd-staging`, geen geheimen zetten, niets in Azure wijzigen. `cd-production.yml` is niet omgezet.

## Wat er veranderd is

- **Twee databasegeheimen.** De migratietaak houdt `STAGING_DATABASE_URL` (de eigenaar). API, werker, planner en leerwerker krijgen `STAGING_APP_DATABASE_URL` (rol `sanskritisetu_app`) als container-app-geheim `app-database-url`. Een preflight-stap faalt als beide dezelfde rol bevatten of de app-URL niet `sanskritisetu_app` is. De aparte inlogverbinding komt uit `STAGING_BYPASS_DATABASE_URL`.
- **Mistral in plaats van DeepSeek**, zonder stille terugval op `mock`: `STAGING_MISTRAL_API_KEY` is verplicht in de preflight; `LLM_PROVIDER=mistral`. DeepSeek is ook uit `docker-compose.prod.yml` (backend, leerwerker; de werkproces-werker kreeg de Mistral-instellingen erbij).
- **Alle werkers mee:** `learning-worker-staging` (zelfde image als de werker), en de bonlezer: een eigen image (`build-bonlezer`), een eigen Redis (`bonlezer-redis-staging`, geen poort naar buiten), de werker (`bonlezer-worker-staging`, uploadmap alleen-lezen) en een schrijfvolume op de API. De bonlezer stond in `docker-compose.yml` al; die compose-stand is nu bewaakt.
- **Mail en links:** `FRONTEND_URL`, `API_BASE_URL` (uit de ingress van de backend), `SMTP_HOST`, `EMAIL_FROM` en optioneel poort en inlog worden op API, werker en planner gezet; ontbreekt een verplicht geheim, dan faalt de preflight.
- **Hoofdsleutel:** `STAGING_MASTER_ENCRYPTION_KEY` is nieuw verplicht (versleutelt klantsleutels: AP-verbinding per klant, providersleutels); de workflow zette hem niet.
- **De lijst voor Rakesh:** `docs/infra/UITROL-STAGING-2026-10.md`: per geheim naam, plaats en inhoud (zonder waarde), de volgorde van de stappen, de controle erna en de controle van de kolomtypen.

## Trainingssamenvatting

### De beheerder start de staging-uitrol

- **Actor:** Rakesh (of wie hij aanwijst), na het zetten van de geheimen.
- **Voorwaarde:** alle geheimen uit `docs/infra/UITROL-STAGING-2026-10.md` staan in GitHub; de share `bonlezer-uploads` bestaat; de rollen in de database zijn ingericht.
- **Actie:** GitHub -> Actions -> `CD -- Staging` -> Run workflow.
- **Systeemreactie:** de preflight controleert de geheimen en de rollen; bij een tekort faalt de run voordat er iets verandert. Daarna bouwen de images, draait de migratie als eigenaar, en gaan API, werker, planner, leerwerker en bonlezer naar Azure; de gezondheidscontrole bepaalt of het blijft staan.
- **Succes:** `/health/ready` geeft 200, de API start onder `sanskritisetu_app`, een debiteurenvoorstel levert een mail op, een bon wordt gelezen.
- **Fout:** een ontbrekend of verkeerd geheim stopt de uitrol in de preflight; een falende gezondheidscontrole zet de API terug op het vorige image.
- **Uitzondering:** de volume-PATCH op de API en de Azure-resources van de bonlezer zijn niet tegen Azure gemeten (zie de lijst, "Niet gemeten").

## Bekende beperkingen

Zie "Niet gemeten" in `docs/infra/UITROL-STAGING-2026-10.md`: de workflow is in deze vorm nooit gedraaid; de volume-PATCH, de interne TCP-Redis, de Azure Files-rechten en het ontbrekende netwerkverbod voor de bonlezer zijn niet gemeten; ActivePieces gebruikt voor zijn eigen database nog de eigenaar.
