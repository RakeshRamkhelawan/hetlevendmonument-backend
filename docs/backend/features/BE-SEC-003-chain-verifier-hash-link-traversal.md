# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-003
- Feature naam: chain_verifier hash-link traversal (B-004 fix)
- Status: APPROVED
- Auteur: Claude Sonnet 4.6
- Reviewer: code-reviewer + quality-reviewer subagents
- Datum: 2026-05-30
- Gerelateerde user story / ticket: MASTER-AUDIT-COMPLEET.md B-004
- Gerelateerde router / module: `src/core/copilot/audit/chain_verifier.py`
- Gerelateerde frontend endpoints: geen (admin/intern)
- Gerelateerde database tabellen: `council_decisions`, `officer_verdicts`
- Versie: 1.0

---

## Doel en scope

### Doel

Correcte verificatie van de SHA-256 hash chain voor copilot council decisions.
De vorige implementatie sorteerde op `timestamp ASC`, wat bij concurrent writes
non-deterministisch is: twee gelijktijdige inserts kunnen dezelfde timestamp produceren
(`func.now()` = transactie-starttijd), waardoor de verifier de verkeerde volgorde ziet
en valse "broken link" meldingen genereert. Dit ondermijnt de auditbaarheid van het systeem.

### In scope

- Vervangen van `ORDER BY timestamp ASC` door hash-link traversal (linked list)
- Genesis-detectie via `previous_decision_hash IS NULL`
- Cycle-detectie via `seen` set
- OOM-guard: weiger chains groter dan 50.000 rijen
- Correcte afhandeling van date-range queries (window-start zonder genesis)

### Out of scope

- Wijzigingen in de auditwriter of het hash-berekeningsalgoritme
- Streaming/chunking optimalisatie voor chains > 50k (post-MVP)
- Parallel verification of sharding

---

## Build summary

- Nieuw gebouwd: geen nieuwe bestanden
- Gewijzigd: `src/core/copilot/audit/chain_verifier.py` — methode `verify_tenant_chain()`
- Verwijderd: `ORDER BY timestamp.asc()` + `db.stream()` aanroep
- Beinvloede bestaande flows: BE-FLW (intern) — chain verificatie via admin endpoints

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SEC-003 | ChainVerifier.verify_tenant_chain() | Security fix / service | `src/core/copilot/audit/chain_verifier.py` | Wijziging | Audit chain verificatie |

---

## API-flows

### Flow: Audit chain verificatie

- Naam: Hash chain integrity verification
- Trigger: directe service call (admin audit endpoint of geplande job)
- Voorwaarden: tenant_id vereist; optioneel from_dt/to_dt
- Request-pad: `ChainVerifier(db).verify_tenant_chain(tenant_id, from_dt, to_dt)`
- Service-stappen:
  1. `SELECT * FROM council_decisions WHERE tenant_id = :tid` (optioneel gefilterd op datum)
  2. Bouw `{decision_hash: row}` dict + `{previous_decision_hash: row}` forward-map
  3. Zoek start: genesis (`previous_decision_hash IS NULL`) of window-start (predecessor buiten set)
  4. Als geen start gevonden en records aanwezig: circulaire chain gedetecteerd → `is_valid=False`
  5. Walk linked list via forward-map; voeg hashes toe aan `seen` set
  6. Verifieer elke record: herbereken hash, vergelijk met opgeslagen `decision_hash`
  7. Voeg `BrokenLink` toe bij mismatch
- DB-operaties: SELECT met `selectinload(officer_verdicts)`, geen writes
- Successtatus: `ChainVerificationResult(is_valid=True, total_entries=N, verified_entries=N, ...)`
- Foutpaden:
  - Circulaire chain: `is_valid=False, reason="Circular chain detected"`
  - Chain te groot: `is_valid=False, reason="Chain too large to verify (N > 50000)"`
  - Hash mismatch: `is_valid=False, broken_links=[BrokenLink(reason="Decision hash recomputation mismatch")]`
  - Ontbrekende predecessor: `is_valid=False, broken_links=[BrokenLink(reason="Predecessor record missing")]`
- Eindtoestand: alleen reads; geen DB-wijzigingen

---

## Detaildocumentatie per artefact

---

## [BE-SEC-003] ChainVerifier.verify_tenant_chain()

### 1. Type

- Security fix / service methode

### 2. Locatie

- Bestandspad: `src/core/copilot/audit/chain_verifier.py`
- Klasse / functie: `ChainVerifier.verify_tenant_chain()`

### 3. Gerelateerde flow

- Audit chain verificatie (zie API-flows boven)

### 4. Doel

Verifieer de integriteit van de SHA-256 hash chain voor alle council decisions van een tenant,
door de linked list via `previous_decision_hash` te doorlopen in plaats van te sorteren op timestamp.

### 5. Functionele beschrijving

- Controleert of elke council decision in de audit log een geldige SHA-256 hash heeft
- Controleert of de hash-keten ononderbroken is (elke record verwijst naar zijn voorganger)
- Detecteert manipulatie: als iemand een record heeft aangepast, klopt de hash niet meer
- Geeft een gedetailleerd rapport terug: welke records zijn correct, welke zijn gebroken en waarom

### 6. Technische beschrijving

- Laadt alle records met `selectinload(officer_verdicts)` voor hash-recomputation
- Bouwt twee lookup dicts: `by_hash` (hash -> row) en `next_by_prev` (previous_hash -> next row)
- Vindt de start van de chain: genesis (`previous_decision_hash IS None`) of window-start
- Doorloopt de linked list iteratief met een `seen: set[str]` voor cycle-detectie
- Herberekent hash via `_compute_canonical_json()` + `_compute_decision_hash()` voor elk record
- Brute-forceert `ProposalTrigger` waarden (5 opties) omdat trigger niet in DB staat
- OOM-guard: bij > `CHAIN_VERIFY_MAX_ROWS` (50.000) wordt verificatie geweigerd

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: service-level (caller verantwoordelijk voor auth)
- Vereiste rol / scope: admin of audit-systeem
- Tenant-isolatie: `WHERE tenant_id = :tenant_id` in de SQL query
- Feature flag: geen

### 8. Request-specificatie

- Methode: service call (geen HTTP endpoint)
- Handtekening: `async def verify_tenant_chain(self, tenant_id: int, from_dt: datetime | None = None, to_dt: datetime | None = None) -> ChainVerificationResult`
- Path parameters: n.v.t.
- Query parameters: n.v.t.
- Request body: n.v.t.
- Verplichte headers: n.v.t.

### 9. Response-specificatie

- Successtatus: `ChainVerificationResult` dataclass
  - `is_valid: bool`
  - `total_entries: int`
  - `verified_entries: int`
  - `broken_links: list[BrokenLink]`
  - `verification_time_ms: float`
  - `tenant_id: int`
  - `checked_at: datetime`
- Foutstatussen: geen exceptions; fout-cases worden weergegeven via `is_valid=False` + `broken_links`

### 10. Validaties en constraints

- `tenant_id` moet een positief integer zijn
- `from_dt` en `to_dt` moeten timezone-aware zijn indien opgegeven
- Chains groter dan 50.000 records worden geweigerd (OOM guard)

### 11. Business rules

- Timestamp-volgorde is NIET bepalend voor de chain-volgorde: alleen hash-links tellen
- Een record waarvan de predecessor buiten het date-range filter valt, wordt als window-start behandeld; de predecessor-link voor dat record wordt niet gecheckt
- Een circulaire chain (geen acyclisch begin) is altijd `is_valid=False`
- Bij hash mismatch: alle 5 ProposalTrigger-waarden worden geprobeerd; pas als geen enkele match geeft, wordt een `BrokenLink` aangemaakt

### 12. Afhankelijkheden

- `CouncilDecisionRow` ORM model (met `decision_hash`, `previous_decision_hash`, `officer_verdicts`)
- `OfficerVerdictRow` ORM model
- `ProposalTrigger` enum
- `selectinload` voor eager loading van officer_verdicts (lazy loading werkt niet in async)

### 13. Foutafhandeling

- Chain te groot: `ChainVerificationResult(is_valid=False, broken_links=[BrokenLink(reason="Chain too large...")])`
- Circulaire chain: `ChainVerificationResult(is_valid=False, broken_links=[BrokenLink(reason="Circular chain detected")])`
- Ontbrekende predecessor: `BrokenLink(reason="Predecessor record missing from chain")`
- Hash mismatch (tampering): `BrokenLink(reason="Decision hash recomputation mismatch (tampering detected)")`
- Database errors: niet afgevangen in de methode — propageren naar caller

### 14. Transacties en dataïntegriteit

- Alleen READ operaties; geen writes, geen transactie vereist
- `selectinload` voorkomt N+1 queries voor officer_verdicts

### 15. Telemetry / logging / tracing

- `verification_time_ms` in het resultaat voor performance tracking
- Geen expliciete logger calls in de methode; caller kan resultaat loggen

### 16. Caching

- Gecached: nee
- Cache-sleutel: n.v.t.
- TTL: n.v.t.
- Invalidatie: n.v.t.

### 17. Acceptatiecriteria

- `ORDER BY timestamp` komt niet voor in de source code van `chain_verifier.py`
- `previous_hash is None` identificeert de genesis record
- `seen` set detecteert en rapporteert circulaire chains
- Chain van 3 records in willekeurige timestamp-volgorde: `is_valid=True` en `verified_entries=3`
- Chain waarbij record 2 is aangepast: `is_valid=False` met `BrokenLink` voor record 2
- Chain van 50.001 records: `is_valid=False` met reason "Chain too large"
- Date-range query zonder genesis in window: geen valse broken-link voor eerste record

### 18. Integratoruitleg

- Directe service call: `result = await ChainVerifier(db).verify_tenant_chain(tenant_id=1)`
- Check `result.is_valid` voor de conclusie
- Loop over `result.broken_links` voor details per gebroken record
- Gebruik `from_dt`/`to_dt` voor grote tenants; verifieer in stukken van maximaal 50.000 records
- `result.verification_time_ms` geeft de doorlooptijd in milliseconden

### 19. Trainingssamenvatting

- Actor: admin systeem of geplande audit job
- Voorwaarde: tenant heeft council decisions in de database
- Actie: `await ChainVerifier(db).verify_tenant_chain(tenant_id, from_dt, to_dt)`
- Systeemverwerking: laad alle records, bouw linked list, doorloop chain, verifieer hashes
- Succesrespons: `ChainVerificationResult(is_valid=True, verified_entries=N)`
- Foutrespons: `ChainVerificationResult(is_valid=False, broken_links=[...])`
- Uitzonderingen: circulaire chain, chain te groot (>50k), ontbrekende predecessor

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Injecteer `AsyncSession` en maak een `ChainVerifier(db)` instantie
- Roep `verify_tenant_chain(tenant_id)` aan voor een volledige verificatie
- Check `result.is_valid == True` voor een schone chain
- Bij grote tenants: gebruik `from_dt` en `to_dt` om in tijdsvakken te verifiëren (max 50k records per aanroep)
- `broken_links` lijst geeft per gebroken record: `decision_id`, `reason`, en verwachte/werkelijke hash

---

## Open aannames

- De `ProposalTrigger` waarden zijn stabiel; toevoegen van een nieuwe trigger-waarde vereist geen chain-migratie
- 50.000 records als OOM-grens is conservatief voor een verificatie-operatie; kan worden verhoogd post-MVP

## Open vragen

- Geen

## Risico's

- Bij chains groter dan 50k moeten callers de range zelf opdelen; er is nog geen helper hiervoor

---

## QA-checks

- [x] Service functioneel getest (happy path: 10 unit tests)
- [x] Alle fout-cases getest (circular, too large, hash mismatch, missing predecessor)
- [x] Tenant-isolatie: WHERE tenant_id filter aanwezig
- [x] Validaties getest (timestamp-sort afwezig in source)
- [x] Edge cases: window-start zonder genesis, lege chain
- [ ] Performance getest met 50k records (post-MVP)
- [x] Logging: verification_time_ms aanwezig in resultaat

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle services en methoden geinventariseerd
- [x] Alle relevante fout-cases beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] Review: zie `docs/backend/review/review-BE-SEC-003.md`
