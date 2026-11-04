# Review: BE-ARCH-001 Dramatiq dict-payload actor tenant_id preventietest

## A. EINDOORDEEL

APPROVED WITH MINOR GAPS

## B. SAMENVATTING

De spec beschrijft correct het doel van de architectuur-test: voorkomen dat nieuwe Dramatiq-actors met dict-payload zonder tenant_id-validatie worden geintroduceerd. De twee tests (`test_dict_payload_dramatiq_actors_validate_tenant_id` en `test_no_unregistered_dict_payload_dramatiq_actors`) zijn concreet geimplementeerd in `tests/architecture/test_dramatiq_actors_tenant_id.py`. De verwijdering van `worker_simple.py` is goed gedocumenteerd. Enkele technische details van de AST-scan ontbreken in de spec.

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

- De spec noemt dat de test scant op een "tenant_id-guard-patroon", maar beschrijft niet wat de AST-scanner precies als guard accepteert (`if`-statement met tenant_id-naam in conditie en `raise`/`return` in body).
- De onderscheiding tussen expliciet getypeerde parameters (categorie 1) en dict-payload (categorie 2) is duidelijk, maar de spec noemt niet dat categorie-1 actors automatisch veilig worden geacht, ook als ze extra dict-typed hulpvelden hebben.
- Trainingssamenvatting ontbrak; wordt in deze ronde toegevoegd.

### 2. Functionele onduidelijkheden

- Geen.

### 3. Technische onduidelijkheden

- Geen.

### 4. Ontbrekende foutstatussen en edge cases

- Geen beschrijving van het geval dat een bekend actormodule geen dict-payload actor meer bevat: de test faalt met een assertion die aangeeft dat de lijst moet worden bijgewerkt.
- Geen beschrijving van alias-import edge case (bijv. `import dramatiq as dq`; de AST-check kijkt naar decorator naam `actor`).

### 5. Acceptatiecriteria problemen

- Geen expliciete acceptatiecriteria opgenomen.

### 6. Integratorhandleiding / API-uitleg problemen

- De integratoruitleg is beperkt. Een korte uitleg voor ontwikkelaars die een nieuwe dict-payload actor toevoegen ontbreekt.

### 7. Trainingsdata problemen

- Trainingssamenvatting ontbrak.

### 8. Structuur- en consistentieproblemen

- Geen.

### 9. Risico's voor implementatie, security of QA

- Geen materiele risico's. De test is een waardevolle regressie-guard.

## D. ISSUE REGISTER

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
|----------|--------------|----------|----------------------------|--------------------|
| Low | Oplossing | AST-guard criteria niet expliciet beschreven. | Reviewers weten niet exact welke patronen als validatie tellen. | Voeg toe: `if`-statement met tenant_id-naam in conditie en `raise`/`return` in body. |
| Low | Oplossing | Categorie 1 (expliciet getypeerde tenant_id) uitsluiting van dict-scan niet beschreven. | Ontwikkelaars kunnen denken dat elke dict parameter getest wordt. | Documenteer dat `tenant_id: int` de actor uitsluit van dict-payload scan. |
| Low | Acceptatiecriteria | Geen expliciete criteria. | QA weet niet zonder tests wat "klaar" is. | Voeg 2-3 criteria toe. |
| Low | Trainingssamenvatting | Sectie ontbrak. | Vereiste voor LLM-training. | Toegevoegd in deze ronde. |

## E. ONTBREKENDE ITEMS

- Expliciete beschrijving van AST-guard detectie.
- Ontwikkelaarsrichtlijn bij toevoegen van een nieuwe dict-payload actor.

## F. VERBETERDE TEKSTVOORSTELLEN

Oplossing sectie mag uitbreiden met:

> `_has_tenant_id_guard()` evalueert per dict-payload actor of er een `if`-statement bestaat waarin een tenant_id-gerelateerde naam voorkomt en waarvan de body een `raise` of `return` bevat. Alleen daadwerkelijk bereikbare code telt; comments of dode functies worden niet meegenomen.

## G. RELEASE-OORDEEL

- Geschikt voor bouw / implementatie: Ja.
- Geschikt voor QA en geautomatiseerd testen: Ja.
- Geschikt voor LLM-training: Ja, na toevoeging Trainingssamenvatting.
- Geschikt voor integratorhandleiding / API-documentatie: Ja, met kleine aanvulling.
