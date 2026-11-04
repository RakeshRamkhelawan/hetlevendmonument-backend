# Review: BE-AGT-056 -- Minimaal statuscontract voor ExecutionResult.status (ADR-036 D7-001)

**Spec:** `docs/backend/features/BE-AGT-056-minimaal-statuscontract.md`
**Datum:** 2026-08-21

---

## A. EINDOORDEEL

APPROVED (na Gate 2 ronde 1 -- alle bevindingen verwerkt)

---

## B. SAMENVATTING

Twee onafhankelijke Gate-2-reviewers (code-reviewer + security-reviewer, elk zonder kennis
van de ander) beoordeelden de implementatie van het minimale statuscontract: een nieuwe
`ExecutionStatusContract(str, Enum)` (vijf gesloten waarden) die vanuit vijf productiebestanden
`ExecutionResult.status` vult, met een expliciete prioriteitsvolgorde bij samenloop en een
`"kind"`-tag op elke plek waar `specialist_base.py::act()` een fout toevoegt aan `errors`.

**Security-reviewer: GO, geen bevindingen.** Zelfstandig nagerekend (niet op het woord van de
implementatie aangenomen): de vijf statuswaarden zijn een gesloten enum, geschreven door
interne code op vaste plekken -- geen enkele leest van modeloutput, gebruikersinvoer of
tenant-data, dus geen nieuw PII-lekpad naast de reeds bestaande vrije-tekstvelden
(`error_message`/`result_data["errors"]`). Het `"kind"`-veld heeft geen extern leespad
(repo-breed gegrept, enige lezer is `_status_from_errors()` zelf; `ExecutionResultSchema`
heeft geen `status`-veld). De GEBLOKKEERD-domineert-GEDEELTELIJK-regel wist `result_data
["results"]` niet -- de onderliggende uitvoeringshistorie blijft intact naast de
classificatie. De `status="400"` -> `MISLUKT`-vervanging raakt geen enkele bestaande lezer
(eigen, onafhankelijke repo-brede grep, niet de claim van de brief overgenomen).
`tenant_id`/`agent_id` zijn in geen van de gewijzigde bestanden aangeraakt.

**Code-reviewer: CHANGES_REQUESTED in ronde 1** -- geen probleem met de kernkeuzes (de enum,
de prioriteitslogica, de `"kind"`-tagging, de plaatsing in `src/core/types.py`), maar twee
concrete gaten:

1. **Vier sibling-`ExecutionResult`-constructies bleven op `status=None` staan** --
   `packs.py:269` (`run_pack_by_id()`, structureel identiek aan een al-gefixte buurtak) en
   drie in `base_agent.py::process_task()` (dezelfde methode waarvan drie ANDERE takken al
   gefixed waren in de eerste implementatieronde). Exact de "sibling-branch-achtergelaten"-
   vorm die fix-sprint dag 6 zelf al twee keer vond.
2. **De `governance_unavailable`-tak (en zijn prioriteit) had geen enkele test** -- bewezen
   met een LIVE mutatie: die tak tijdelijk naar `GEBLOKKEERD` laten wijzen in plaats van
   `MISLUKT` liet alle op dat moment 64 gerichte tests groen.

**Beide bevindingen verwerkt in dezelfde sessie, geen enkele doorgeschoven zonder fix:**

1. Alle vier constructies kregen een expliciete `status=`-toewijzing (`packs.py:269` ->
   MISLUKT; taakvalidatie-mislukking -> MISLUKT; GDPR-profileringsweigering -> GEBLOKKEERD;
   agent-op-capaciteit -> MEER_BUDGET_NODIG). Daarna een uitputtende, programmatische controle
   (elke `ExecutionResult(...)`-aanroep in de drie kernbestanden geparsed op aanwezigheid van
   `status=`) bevestigde dat alle 17 constructies nu een status zetten -- niet aangenomen dat
   de vier genoemde plekken de enige waren.
2. Twee nieuwe tests toegevoegd (`test_a_broken_governance_gate_reports_mislukt`,
   `test_governance_unavailable_dominates_a_simultaneous_partial_success`), en zelf
   gereproduceerd dat EXACT de door de reviewer gebruikte mutatie beide nieuwe tests rood
   maakt, dan herstel weer groen.

**Bijvangst tijdens het verwerken van bevinding 1**: de reviewer merkte ook op dat het
document zelf een niet-bestaande methodenaam citeerde (`_execute_agent_step`, de echte naam
is `_run_single_step`) en onjuiste testtellingen ("8 nieuw/13 uitgebreid", zelf herverifieerd
naar 7/21 via `git diff`). Beide gecorrigeerd in de spec en de ID-REGISTRY-rij.

---

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

Opgelost. Alle 17 `ExecutionResult(...)`-constructies in de drie kernbestanden
(`specialist_base.py`, `packs.py`, `base_agent.py`) zetten nu een `status` -- geverifieerd
met een programmatische parse, niet met een handmatige telling.

### 8. Structuur- en consistentieproblemen

De feature-spec citeerde een niet-bestaande methodenaam en onjuiste testtellingen -- beide
gecorrigeerd (zie sectie B).

### 9. Risico's voor implementatie, security of QA

Geen CRITICAL/HIGH. Het enige reele risico (de twee Gate-2-bevindingen) is gefixt en
mutatiegetest voor commit.

---

## D. ISSUE REGISTER (Gate 2, ronde 1 -- alle verwerkt)

| Severity | Reviewer | Bevinding | Correctie |
|---|---|---|---|
| Medium-High | code-reviewer | Vier sibling-`ExecutionResult`-constructies bleven op `status=None` (`packs.py:269`, `base_agent.py:527,569,579`) | Alle vier expliciet gemapt; uitputtende programmatische controle over alle 17 constructies |
| Medium | code-reviewer | `governance_unavailable`-tak en zijn prioriteit hadden geen enkele test (bewezen met een live mutatie) | Twee nieuwe tests toegevoegd, mutatiegetest in beide richtingen |
| Low | code-reviewer | Niet-bestaande methodenaam (`_execute_agent_step`) en onjuiste testtellingen in de spec | Beide gecorrigeerd in de spec en de ID-REGISTRY-rij |
| -- | security-reviewer | Geen bevindingen (GO) | n.v.t. |

---

## E. ONTBREKENDE ITEMS

Geen. Zie sectie C.1 -- alle 17 constructies zijn nu gedekt.

---

## F. DOC-REVIEW

Niet apart uitgevoerd als losse ronde -- de code-reviewer's bevindingen over de spec zelf
(methodenaam, testtellingen) zijn in dezelfde sessie verwerkt als onderdeel van de
Gate-2-fixronde (zie sectie B).

**Herverificatie na alle fixes (zelf gedraaid, niet aangenomen):**
- `python -m pytest tests/unit/als/ tests/unit/agents/ tests/unit/core/ -q --timeout=60` ->
  1295 passed, 2 skipped, 0 failed.
- `python -m pytest tests/architecture/ -q --timeout=60` -> 671 passed, 1 xfailed (OP-170,
  ongewijzigd).
- `python -m pyright` (geen args) -> 0 errors, 54 warnings (baseline ongewijzigd).
- `python scripts/run_mypy_audit.py` -> 0 errors, baseline 0.
- `ruff check` op alle 12 gewijzigde bestanden -> All checks passed!
- ASCII-scan op alle gewijzigde bestanden -> schoon.
- `python scripts/validate_feature_docs.py` -> geen nieuwe incomplete IDs (na deze
  review-file).

**Pointer (2026-08-21, na de verplichte blinde eindreview, rondes 1 en 2)**: de "7/21"-telling
in sectie B hierboven is een tijdstip-snapshot van Gate 2 ronde 1 en is INMIDDELS vervangen --
de daadwerkelijke, drie keer herverifieerde eindtelling is 11 nieuwe tests (7 uit deze
Gate-2-ronde + 4 uit de blinde-eindreview-ronde-1-fix) en 22 uitgebreide tests. Zie
`docs/backend/features/BE-AGT-056-minimaal-statuscontract.md` secties 6b/6c en de
final-approver-brief voor de volledige correctiehistorie. Dit bestand blijft zelf ongewijzigd
als snapshot van Gate 2 ronde 1 specifiek.

---

## G. RELEASE-OORDEEL

- Geschikt voor bouw/implementatie: Ja -- de code is al gebouwd, correct, en mutatiegetest
  in beide richtingen voor elke statuswaarde en elke prioriteitsclaim.
- Geschikt voor QA en geautomatiseerd testen: Ja -- alle testtellingen kloppen tegen een
  daadwerkelijke pytest-run.
- Geschikt voor LLM-training: Ja.
- Geschikt voor integratorhandleiding/API-documentatie: N.v.t., geen publieke API-wijziging
  (`status` is write-only, geen HTTP-schema serialiseert het).
