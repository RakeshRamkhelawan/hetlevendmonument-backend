# Review BE-GOV-020 — AuditService consolidatie naar canoniek hash-chain-pad

## A. Eindoordeel

APPROVED WITH MINOR GAPS

## B. Samenvatting

De specificatie beschrijft de consolidatie van drie non-canonieke audit-schrijfpaden naar het canonieke `AuditService.log_action()` pad met hash-chain. Er wordt een nieuwe Dramatiq-actor geintroduceerd, `governance/services/audit_service.py::log_event()` krijgt hash-chain populatie, en `SecurityAuditService` gebruikt de canonieke HashChainVerifier. De broncode bevestigt de actor en de hash-chain logica.

## C. Bevindingen per categorie

### 1. Coverage gaps

- De spec noemt de 5 hot-path-callers die nu de actor enqueuen, maar geeft niet aan welke concrete functie-aanroepen zijn aangepast. TODO: minstens een voorbeeld noemen.
- De spec noemt dat de actor is geregistreerd in `src/workers/actors.py`. Dat is kritiek, maar het pad wordt niet expliciet getoond.

### 2. Functionele onduidelijkheden

- Geen. Het doel (alle audit writes naar hash-chain) is helder.

### 3. Technische onduidelijkheden

- De `flush()`-not-`commit()` semantiek wordt genoemd. De broncode van `audit_service.py::log_event()` toont `await db.flush()` binnen een `begin_nested()` block, wat consistent is.
- De spec noemt `pg_advisory_xact_lock` en `HashChainVerifier`. Broncode bevestigt dit.

### 4. Ontbrekende foutstatussen en edge cases

- De spec noemt dat hash-chain populatie best-effort is (entry written without hash bij falen). Broncode bevestigt dit.
- Een edge case ontbreekt: de actor gebruikt `asyncio.run(_write_audit_log(...))` binnen een Dramatiq sync actor. Dit is correct, maar niet gedocumenteerd als pattern.

### 5. Acceptatiecriteria problemen

- Geen expliciete acceptatiecriteria. Testbewijs is aanwezig.

### 6. Integratorhandleiding / API-uitleg problemen

- De Trainingssamenvatting is goed en noemt expliciet het fire-and-forget karakter.

### 7. Trainingsdata problemen

- Geschikt voor LLM-training.

### 8. Structuur- en consistentieproblemen

- Compacte feature-note. De backlog-testen worden expliciet benoemd.

### 9. Risico's voor implementatie, security of QA

- De 6 overige modules die AuditLog zonder hash-chain construeren (backlog SP-GOV-ARCH-5) zijn correct vastgelegd.

## D. Issue Register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Low | Oplossing / hot-path-callers | Geen concreet voorbeeld van aangepaste caller | Reviewers kunnen niet zien welke code nu de actor enqueue | Voeg een voorbeeld toe, bijv. `token_blacklist.blacklist_token()` roept nu `write_audit_log_task.send(...)` aan |
| Low | Actor-implementatie | `asyncio.run()` binnen Dramatiq actor niet toegelicht | Niet-standaard pattern verdient uitleg | Noteer dat de actor sync is (Dramatiq) en daarom `asyncio.run()` gebruikt om de async `AuditService.log_action()` aan te roepen |

## E. Ontbrekende items

- Geen functioneel ontbrekende items.

## F. Verbeterde tekstvoorstellen

- "De 5 sessieloze hot-path-callers enqueuen nu een echte hash-chained write" -> "De 5 sessieloze hot-path-callers (bijv. `token_blacklist.blacklist_token(...)`) enqueuen nu `write_audit_log_task.send(...)` voor een hash-chained write."

## G. Release-oordeel

- Geschikt voor bouw / implementatie: ja.
- Geschikt voor QA en geautomatiseerd testen: ja.
- Geschikt voor LLM-training: ja, met bovenstaande minor gaps.
- Geschikt voor integratorhandleiding / API-documentatie: beperkt; intern audit-mechanisme.
