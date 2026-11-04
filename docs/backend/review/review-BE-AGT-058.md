# Review: BE-AGT-058-hr-trainings-import.md

## A. Eindoordeel

**APPROVED WITH MINOR GAPS** -- alle bevindingen zijn direct gefixed (inclusief de enige
High-bevinding), geen open CRITICAL/HIGH resterend.

## B. Samenvatting

De doc-reviewer verifieerde elke technische claim in de spec tegen de daadwerkelijke
broncode (modellen, migratie, repositories, routers, schemas, rate limiter, middleware,
`hr_registry.py`, beide dag-4-integratietests, de composite-FK-architectuurtest) en vond
geen enkele feitelijke onjuistheid, gefabriceerd bestandspad, of gefabriceerde commit-hash.
Alle vijf commit-hashes bestaan in `git log`. De tenant-isolatie-/permissiestory -- de enige
categorie die dit project's eigen reviewkader automatisch als Critical markeert als hij
onderbelicht is -- was ongewoon sterk gedocumenteerd (mutatiegetest, niet alleen beweerd) en
kreeg terecht geen bevinding.

## C. Bevindingen en fixes

| Severity | Sectie | Bevinding | Fix |
| --- | --- | --- | --- |
| High | Sectie 5 / 8 | Een geobserveerde `WARNING BYPASS: Tenant filter DISABLED`-logregel werd "niet gefixt"/"buiten scope" verklaard zonder de door `.claude/rules/quality-gates.md` verplichte falende architecture-test of gedateerde-uitzondering-plus-staleness-test. | De eenmalige, handmatige mutatietest (die al aantoonde dat de EXPLICIETE `tenant_id`-filter de echte veiligheidslaag is, niet de bypass-logregel) omgezet in een permanente, geautomatiseerde guard: `tests/architecture/test_hr_repositories_explicit_tenant_filter.py`. AST-gebaseerd, controleert alle 7 methoden met een `tenant_id`-parameter op beide HR-repositories. Mutatiegetest in beide richtingen: `list_skills`'s filter tijdelijk verwijderd -> test ROOD (noemt exact `list_skills`); herstellen -> GROEN. Sectie 5/8 herschreven om te verwijzen naar deze guard i.p.v. de bevinding als "niet gefixt" te laten staan. |
| Medium | Sectie 3 | "3 van de 6 upsert-methoden" -- er zijn maar 5 upsert-methoden totaal, geen 6. | Gecorrigeerd naar "3 van de 5". |
| Medium | Sectie 6 (contract-tabel) | 422 (ontbrekend/ongeldig `entity_type` of `file`-veld, FastAPI's eigen Pydantic-validatie) werd nergens genoemd. | 422-rij toegevoegd aan de contract-tabel. |
| Medium | Proces (FEATURE_DOC_WORKFLOW.md Stap 1.5) | `ID-REGISTRY.md` had geen regels voor BE-AGT-058/059/060/061. | Vier regels toegevoegd, conform het bestaande tabelformaat. |
| Low | Sectie 6 (contract-tabel) | Geen 500-rij voor de vier endpoints. | 500-rij toegevoegd (generieke exception-handler, geen eigen afhandeling). |
| Low | Sectie 7, Flow 3 | `"gap_count": 1` gepresenteerd als exacte, testbewezen waarde; de test asserteert alleen `> 0`. | Herschreven naar `>= 1` met een expliciete toelichting dat `1` in dit scenario toevallig klopt maar geen apart-getest contract is. |
| Low | Sectie 7 | Geen flow illustreert het 409-pad (gelijktijdige-import-race) end-to-end. | Niet toegevoegd -- Low-severity, contract-tabel dekt het gedrag al, en de bestaande unit-tests (`TestConcurrentImportConflict`, dag 3) bewijzen dit al op de juiste laag. Bewust geen vierde flow toegevoegd om de spec niet onnodig te laten groeien. |

## D. Release-oordeel

- Geschikt voor bouw/implementatie: ja (er is niets meer te bouwen -- dit is de afronding).
- Geschikt voor QA en geautomatiseerd testen: ja, inclusief de nieuwe permanente
  architecture-guard.
- Geschikt voor LLM-training: ja -- Trainingssamenvatting-secties zijn compact en
  eenduidig, nu ook met correcte foutstatus-dekking.
- Geschikt voor integratorhandleiding: ja -- sectie 6 dekt nu alle relevante statuscodes.
