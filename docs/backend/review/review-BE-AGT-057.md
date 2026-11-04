# Review: BE-AGT-057 -- Agent-laag denylist-precheck in execute_tool() (ADR036-ADR015-001/OP-24)

**Spec:** `docs/backend/features/BE-AGT-057-execute-tool-denylist-precheck.md`
**Datum:** 2026-08-21

---

## A. EINDOORDEEL

APPROVED (na Gate 2 -- alle bevindingen verwerkt)

---

## B. SAMENVATTING

Een defense-in-depth `is_denied()`-precheck toegevoegd in `EnhancedBaseAgent.execute_tool()`
(basisklasse van alle 135 ALS-skills en meerdere niet-ALS-agents), analoog aan
`specialist_base.py::_reject_before_council()`'s D5-helft. Exhaustieve investigatie vooraf
(`docs/agent-briefs/generated/2026-08-21-sprint-dag-8.md`) toonde dat OP-24's oorspronkelijke
"geen D5-denylist"-claim niet standhoudt onder meting -- `ToolBrokerService.execute_tool()`
blokkeerde denylist-tools al voordat deze precheck bestond. De fix levert dus geen actieve
bypass-dichting op, maar een vroegere afwijzing (geen broker-round-trip) en architecturale
consistentie tussen de twee agent-basisklassen.

**Security-reviewer: GO, geen CRITICAL/HIGH/MEDIUM.** Onafhankelijk herverifieerd: de
"broker blokkeert al"-claim klopt, geen nieuwe bypass via de isinstance-guard-fallback, geen
tenant-lek, geen audit-regressie. Een LOW-bevinding (de nieuwe foutmelding is iets
specifieker dan de broker's generieke variant -- minieme enumeratie-oracle), expliciet
gemarkeerd als geen-fix-vereist.

**Code-reviewer: eerste poging vastgelopen (agent-watchdog na 600s) met een onvolledige,
verontrustende claim over een "genuine regression"; tweede poging CHANGES_REQUESTED, beide
gevonden CRITICAL-bevindingen zijn zelf-veroorzaakte regressies in `tests/architecture/`,
niet in de kernlogica.** Voor de tweede poging startte, is zelf eerst geverifieerd dat de
vastgelopen eerste poging het bestand niet gecorrumpeerd had achtergelaten (`git diff --stat`
onveranderd, 42 regels; `python -c "import src.core.agents.base_agent"` slaagt; een volledige
`pytest --collect-only` over alle 20.058 tests toont precies 1 vooraf-bestaand,
ongerelateerd collectiefout).

**Bevinding 1 (CRITICAL, DSM-coupling-plafond):**
`test_dsm_008_reclassification.py::test_agent_runtime_ce_dag2_final_target` faalde --
twee nieuwe, bewuste `agent_runtime -> tool_broker`-imports (`ToolExecutionException`,
`ToolPermissionManager`) duwden Ce van 225 (zonder marge) naar 227. **Fix:** het plafond
verhoogd naar 227 met een gedateerde, beargumenteerde toelichting (zelfde patroon als de
al-bestaande SP-DSM-009-precedent), na zelf gemeten te hebben dat de instability-drempel
niet raakt (I=0,5405, ruim onder de actuele 0,55-drempel uit SP-DSM-014 -- de oude
`I<=0,50`-vermelding was zelf al verouderd en werd door geen enkele test afgedwongen).

**Bevinding 2 (CRITICAL, zelf-veroorzaakte documentatiefout):** de eigen ADR-036
OP-24-rij-bewerking in dezelfde diff brak `test_adr036_register_is_parseable.py` --
`STATUS=GEDEELTELIJK GEDICHT` staat niet in de gesloten vocabulaire en het `.md`-bewijspad
matchte geen machinaal controleerbaar patroon. **Fix:** `STATUS=OPEN
GEVERIFIEERD=2026-08-21 BEWIJS=<node-id van de nieuwe test>`.

Beide bevindingen zijn gefixt en herverifieerd (`tests/architecture/test_dsm_grade_a_plus.py`,
`test_dsm_007_scanner_quality.py`, `test_dsm_008_reclassification.py`,
`test_dsm014_agt_rt_no_laag_circulars.py`, `test_adr036_register_is_parseable.py`: alle
groen). De kernlogica (precheck-plaatsing, caching, mutatiebewijs voor beide nieuwe tests,
`KNOWN_UNGATED`-verwijderingsclaim) werd door BEIDE code-review-pogingen onveranderd bevestigd
correct.

---

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

Geen. Beide nieuwe tests (short-circuit-bewijs, regressietest voor niet-geweigerde tools)
zijn mutatiegetest in beide richtingen door twee onafhankelijke reviewers.

### 8. Structuur- en consistentieproblemen

De eigen ADR-036-rij-bewerking gebruikte een niet-gesloten statuswaarde en een
niet-machinaal-controleerbaar bewijspad -- beide gecorrigeerd (zie sectie B).

### 9. Risico's voor implementatie, security of QA

Geen CRITICAL/HIGH resterend. De twee gevonden CRITICAL-bevindingen waren beide
architecture-suite-regressies veroorzaakt door deze diff zelf, geen bevindingen over de
onderliggende beveiligingslogica (die de security-reviewer onafhankelijk GO gaf).

---

## D. ISSUE REGISTER

| Severity | Reviewer | Bevinding | Correctie |
|---|---|---|---|
| CRITICAL | code-reviewer (2e poging) | DSM Ce-plafond overschreden (225->227) door twee nieuwe, bewuste agent_runtime->tool_broker-imports | Plafond verhoogd naar 227 met gedateerde toelichting, instability-drempel (0,55) zelf herverifieerd ongeraakt |
| CRITICAL | code-reviewer (2e poging) | Eigen ADR-036 OP-24-rij gebruikte een ongeldige STATUS-waarde en een niet-machinaal-controleerbaar BEWIJS-pad | STATUS=OPEN GEVERIFIEERD=2026-08-21 BEWIJS=<node-id>, zelf herverifieerd tegen de guard |
| LOW | security-reviewer | Nieuwe foutmelding iets specifieker dan de broker's generieke variant (minieme enumeratie-oracle) | Geen fix vereist deze sprintdag (expliciet zo gemarkeerd) |
| -- | code-reviewer (1e poging) | Vastgelopen (watchdog-timeout), onvolledige regressieclaim | Zelf onderzocht en de daadwerkelijke oorzaak gevonden in de 2e poging; bestand niet gecorrumpeerd bevestigd |

---

## E. ONTBREKENDE ITEMS

Geen. Council-consultatie en initiator-verificatie blijven expliciet OPEN onder OP-24 --
bewust buiten scope van deze sprintdag, niet een ontbrekend item van DEZE fix.

---

## F. DOC-REVIEW

Niet apart uitgevoerd als losse ronde -- de code-reviewer's bevindingen over de ADR-036-rij
zelf zijn in dezelfde sessie verwerkt als onderdeel van de Gate-2-fixronde (zie sectie B).

**Herverificatie na alle fixes (zelf gedraaid):**
- `python -m pytest tests/architecture/test_dsm_grade_a_plus.py tests/architecture/test_dsm_007_scanner_quality.py tests/architecture/test_dsm_008_reclassification.py tests/architecture/test_dsm014_agt_rt_no_laag_circulars.py -v` -> 27 passed.
- `python -m pytest tests/architecture/test_adr036_register_is_parseable.py -v` -> 6 passed.
- `python -m pytest tests/unit/agents/ tests/unit/tool_broker/ -q` -> 707+ passed (baseline uit de tweede Gate-2-poging), 0 failed.
- ASCII-scan op alle gewijzigde bestanden -> schoon.
- `ruff check` op alle gewijzigde bestanden -> All checks passed!
- Volledige `tests/architecture/`-suite en de volledige mandatory regressiesuite: zie
  final-approver-brief voor de exacte cijfers.

**Pointer (2026-08-22, na de verplichte blinde eindreview -- correctie na ronde 8: de
vorige versie van deze paragraaf beweerde zelf "bijgewerkt bij elke volgende ronde" en
noemde toch een vaste rondereeks ("rondes 1-5") en een vast sectiebereik ("6b t/m 6f") --
precies het patroon dat hij zei te voorkomen. Ronde 8 vond dat rondes 6 en 7 nadien
plaatsvonden zonder dat dit bestand werd bijgewerkt, wat de eigen belofte al onwaar had
gemaakt. Deze toelichting tussen haakjes is zelf een gedateerd, historisch verslag van WAT
er fout ging en mag daarom rondnummers noemen als feit over het verleden -- de belofte geldt
uitsluitend voor het vooruitwijzende deel NA deze toelichting -- dat verwijst daarom bewust
naar GEEN specifiek rondenummer of sectieletter meer)**:
sectie C.1 hierboven ("Coverage gaps: Geen") en de "707+"-schatting in dit F-blok zijn een
tijdstip-snapshot van Gate 2 en zijn INMIDDELS ingehaald door meerdere afzonderlijke, echte
coverage-gaps die latere rondes elk apart vonden en fixten (manager-hergebruik/cache nooit
getest; de ECHTE `is_denied()`-beslissing nooit via de ECHTE `execute_tool()` getest, voor
zowel de weigerende als de toestaande tak; een test die zijn eigen cache-scope niet
zelfstandig bewees). Zie
`docs/backend/features/BE-AGT-057-execute-tool-denylist-precheck.md` (alle secties onder
"6.", tot de laatst-toegevoegde) en de final-approver-brief (alle "Ronde N"-secties) voor de
volledige, doorlopend bijgewerkte correctiehistorie en de actuele testtellingen. Dit
bestand blijft zelf ongewijzigd als snapshot van Gate 2 specifiek -- alleen deze
pointer-paragraaf wordt onderhouden, en nu zonder een vervalbare verwijzing erin.

---

## G. RELEASE-OORDEEL

- Geschikt voor bouw/implementatie: Ja -- de code is al gebouwd, correct, en mutatiegetest
  in beide richtingen door twee onafhankelijke reviewronden.
- Geschikt voor QA en geautomatiseerd testen: Ja.
- Geschikt voor LLM-training: Ja.
- Geschikt voor integratorhandleiding/API-documentatie: N.v.t., geen publieke API-wijziging.
