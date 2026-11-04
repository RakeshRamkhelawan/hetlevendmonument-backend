# Review BE-DEP-047 — get_notifications_service

## A. Eindoordeel

APPROVED WITH MINOR GAPS

## B. Samenvatting

De specificatie beschrijft de introductie van `NotificationsService` en `get_notifications_service` voor de notifications router, waarmee directe DB-imports in de router worden verwijderd. De broncode bevestigt dat `service.py`, `dependencies.py` en `router.py` consistent zijn met ADR-033. Tenant+user isolatie wordt op elke query toegepast.

## C. Bevindingen per categorie

### 1. Coverage gaps

- De spec inventariseert BE-SVC-047, BE-DEP-047 en BE-RTR-047. Dekkend.
- De spec noemt dat `mark_all_read` een "bulk update via Python loop + commit" doet. Dat klopt met de broncode (Python loop met `await self.db.commit()`), maar het is geen echte bulk update op DB-niveau. Dat is een performance-observatie, geen functioneel probleem.

### 2. Functionele onduidelijkheden

- Geen. De drie methodes (`list_notifications`, `mark_all_read`, `mark_single_read`) zijn helder beschreven.

### 3. Technische onduidelijkheden

- De spec zegt "mark_all_read: bulk update via Python loop + commit; audit log via best_effort". De broncode bevestigt dit.
- De spec noemt dat `tenant_id` en `user_id` in de constructor zitten. Broncode bevestigt `__init__(db, tenant_id, user_id)`.

### 4. Ontbrekende foutstatussen en edge cases

- De spec noemt 401, 404, 422, 500. 403 ontbreekt, maar dat is correct omdat de service 404 retourneert als een notificatie niet bij de huidige user/tenant hoort (informatie-arm).
- Een edge case ontbreekt: `mark_all_read` commit per notificatie in de loop, niet als enkele transactie. Bij een crash halverwege kan de helft gemarkeerd zijn. De spec noemt dit niet.

### 5. Acceptatiecriteria problemen

- Criteria zijn testbaar en concreet. Het criterium "router.py bevat geen import van AsyncSession, get_db, select, func" is geverifieerd in broncode.

### 6. Integratorhandleiding / API-uitleg problemen

- De integratoruitleg is duidelijk en praktisch.

### 7. Trainingsdata problemen

- Trainingssamenvatting volgt het verplichte mini-format en is concreet.

### 8. Structuur- en consistentieproblemen

- De spec gebruikt het volledige backend template. Consistent.
- Klein inconsistentie: "bulk update" suggereert een enkele SQL UPDATE, maar de implementatie is een Python loop. Dat is misleidend voor implementeerders.

### 9. Risico's voor implementatie, security of QA

- Laag risico. Tenant+user isolatie is correct.
- De Python-loop commit kan bij grote aantallen notificaties traag zijn, maar dat valt buiten scope van deze refactor.

## D. Issue Register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Low | Technische beschrijving / mark_all_read | "bulk update" is feitelijk een Python loop met individuele commits | Misleidend voor performance-afwegingen | Wijzig naar "Python loop die per notificatie is_read zet, gevolgd door een enkele commit na de loop" of voeg opmerking toe dat dit geen SQL bulk UPDATE is |
| Low | Transacties en dataïntegriteit | Geen vermelding van partiële updates bij crashes | Bij een crash tussen commit en audit log kan de toestand inconsistent lijken | Documenteer dat `mark_all_read` idempotent is (meerdere keren aanroepen is veilig) |

## E. Ontbrekende items

- Geen.

## F. Verbeterde tekstvoorstellen

- "mark_all_read: bulk update via Python loop + commit" -> "mark_all_read: Python loop over ongelezen notificaties, zet is_read per rij, daarna commit; idempotent bij herhaalde aanroep."

## G. Release-oordeel

- Geschikt voor bouw / implementatie: ja.
- Geschikt voor QA en geautomatiseerd testen: ja.
- Geschikt voor LLM-training: ja.
- Geschikt voor integratorhandleiding / API-documentatie: ja.
