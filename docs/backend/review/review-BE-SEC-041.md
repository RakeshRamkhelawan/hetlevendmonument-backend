# Review: BE-SEC-041 — Agent-aware ToolBrokerAdapter voor Council

> Reviewer-prompt: `docs/backend/FEATURE_DOC_WORKFLOW.md` stap 2
> Spec onder review: `docs/backend/features/BE-SEC-041-council-tool-broker-agent-id.md`
> Implementatie geverifieerd tegen: `src/core/copilot/council/factory.py`, `src/core/copilot/council/background_gate.py`, `tests/unit/test_council_tool_broker_agent_id.py`
> Datum: 2026-07-29

---

## A. EINDOORDEEL: APPROVED

## B. SAMENVATTING

De spec dekt alle gewijzigde artefacten (adapter, `build_council`, `_get_rbac_service`, background-gate-forwarding, tests), scheidt functioneel van technisch, beschrijft het fail-secure gedrag expliciet, en de acceptatiecriteria zijn 1-op-1 als draaiende tests geimplementeerd (6/6 groen). De claim "HTTP-gedrag identiek" is geverifieerd tegen de code: alle 9 `build_council(db)` call-sites gebruiken alleen de positionele parameter. De DSM-017-motivering voor `_get_rbac_service` klopt met de architectuur-test (`agent_runtime->auth = 15 <= 15`, suite 388/388 groen).

## C. BEVINDINGEN PER CATEGORIE

1. **Coverage gaps**: geen. Adapter, factory-functie, singleton, background-gate en tests zijn alle geinventariseerd met ID's.
2. **Functionele onduidelijkheden**: geen. De privilege-widening-probleemstelling en de oplossing zijn concreet en controleerbaar beschreven.
3. **Technische onduidelijkheden**: geen. De singleton-vs-fresh-officer-tak, de reden voor `_get_rbac_service` (edge-count), en de backwards-compatibiliteit zijn precies beschreven en kloppen met de code.
4. **Ontbrekende foutstatussen en edge cases**: geen endpoint, dus HTTP-foutstatussen terecht als n.v.t. gemarkeerd. De relevante foutpaden (default-deny, UPSTREAM_ERROR) zijn beschreven en getest.
5. **Acceptatiecriteria problemen**: geen. Alle 8 criteria zijn testbaar en 6 zijn direct als pytest-case uitvoerbaar; de overige 2 zijn suite-bewijs (gerichte tests + architectuur-suite).
6. **Integratorhandleiding / API-uitleg problemen**: geen. Drietal bullets, juiste abstractie voor koppelende teams.
7. **Trainingsdata problemen**: geen. Trainingssamenvatting compleet in het vaste format.
8. **Structuur- en consistentieproblemen**: geen. Build summary, inventory en detailsecties zijn consistent; flow BE-FLW-049 sluit aan bij de artefacten.
9. **Risico's voor implementatie, security of QA**: geen onbenoemde risico's. Het fail-secure risico (agents zonder profiel krijgen VETO) is expliciet benoemd, beargumenteerd en getest.

## D. ISSUE REGISTER

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie | Status |
| --- | --- | --- | --- | --- | --- |
| Low | tests, `TestFailSecureForUnknownAgent` | De test hangt af van de repo-config (`hr_skill` heeft nu geen profiel) | Als AUDIT-008 later een profiel voor `hr_skill` of de actie `some_action` toevoegt, kan deze test onverwacht rood worden | Bij AUDIT-008 (dag 4): als `hr_skill` een profiel krijgt, test herzien met een gegarandeerd profiel-loze agent-naam | Gedocumenteerd in spec (Risico's + Business rule 4); overdracht opgenomen in dag-4 brief |
| Low | tests, private-attribuut-toegang | Tests lezen `_voting_officers`, `_tool_broker`, `_agent_id` (white-box) | Refactors van internals kunnen tests breken zonder gedragswijziging | Bewust geaccepteerd: precedent in codebase (`test_council_factory.py` leest `_guardian`, `test_sp_we_08` leest `_PERSISTENT_RATE_LIMITER._limiter`); de gepinde internals zijn precies het onderwerp van de regressie | Verwerkt -- geen actie nodig |

Geen CRITICAL, HIGH of MEDIUM bevindingen. Geen open MINOR-bevindingen.

## E. ONTBREKENDE ITEMS

Geen vermoedelijk ontbrekende endpoints, services, flows of regels gedetecteerd.

## F. VERBETERDE TEKSTVOORSTELLEN

Geen -- de zwakste stukken (foutstatussen als n.v.t.) zijn al expliciet beargumenteerd.

## G. RELEASE-OORDEEL

- Geschikt voor bouw / implementatie: ja (reeds geimplementeerd, 6/6 tests groen)
- Geschikt voor QA en geautomatiseerd testen: ja (acceptatiecriteria mappen 1-op-1 op tests)
- Geschikt voor LLM-training: ja (functioneel/technisch gescheiden, concrete paden en symbolen)
- Geschikt voor integratorhandleiding / API-documentatie: ja

---

*Eindoordeel: APPROVED | Reviewer: onafhankelijke review-stap | Datum: 2026-07-29*
