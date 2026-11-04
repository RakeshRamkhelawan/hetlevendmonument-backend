# Feature Review: BE-AGT-019

- Feature ID: BE-AGT-019
- Reviewer: doc-reviewer subagent
- Datum: 2026-06-27
- Sprint: SP-AGT-006 Dag 2

---

## Beoordelingscriteria

### 1. Activatiecriterium -- volledig en correct?

**Oordeel: CORRECT**

Het activatiecriterium `use_llm=True AND _JUDGE_PANEL_LOWER <= score <= _JUDGE_PANEL_UPPER`
is expliciet en testbaar. De score die getoetst wordt is de score na Phase 2 LLM-blending,
wat correct is: het panel evalueert de gecombineerde heuristic+LLM score, niet de ruwe heuristic.

De grenzen zijn inclusief (`<=`), wat de spec bevestigt. De grenswaardentests
(score=0.35 exact, score=0.75 exact) zijn opgenomen in de acceptatiecriteria.

**Minor gap:** De spec vermeldt niet expliciet wat er gebeurt bij `use_llm=False` met score
in het panel-venster. De acceptatiecriteria benoemen dit wel ("Panel niet geactiveerd bij
use_llm=False"), maar de "Business rules" sectie van BE-AGT-019-F zou dit expliciet
als bullet moeten herhalen naast de andere regels.

---

### 2. Leave-one-out motivatie (2-sigma voor N=3) -- goed gemotiveerd?

**Oordeel: GOED GEMOTIVEERD**

De motivatie is wiskundig correct: voor N=3 geldt dat de maximale z-score ~1.15 is
(bewijs: voor drie waarden a, b, c waarbij c de outlier is, en sigma berekend over alle 3,
is z_max altijd < 2 ongeacht de spreiding). Een 2-sigma grens zou nooit triggeren.

De keuze voor leave-one-out met absolute drempel 0.30 is verdedigbaar voor kleine panels.
De drempel zelf (0.30) is echter niet gemotiveerd -- waarom niet 0.25 of 0.35?

**Minor gap:** Voeg een zin toe die uitlegt waarom 0.30 is gekozen als drempel. Bijv.:
"0.30 vertegenwoordigt een substantieel meningsverschil (30 procentpunten) dat de consensus
betekenisvol zou verschuiven."

---

### 3. Foutpaden -- volledig beschreven?

**Oordeel: GROTENDEELS VOLLEDIG**

Beschreven foutpaden:
- Alle judges timeout -> score ongewijzigd, geen judge_panel in metadata. OK.
- Partial failure (1 judge timeout) -> consensus van 2 succesvolle judges. OK.
- panel_verdict is None -> score ongewijzigd. OK.

**Minor gap (niet CRITICAL):** Het parse-error pad is impliciet maar niet expliciet
beschreven. Wat gebeurt er als een judge een antwoord geeft dat niet als score parseable
is? De spec zegt "asyncio.TimeoutError -> (index, None)" en "Alle andere exceptions ->
(index, None)", maar een ongeldige JSON-response van een judge die succesvol returnt
(geen exception) valt hier niet onder. Dit pad moet expliciet in _run_judge_panel of
_judge_panel_critique beschreven worden: "parse-fout -> (index, None), telt mee als
failed_judge".

---

### 4. Open aannames -- eerlijk?

**Oordeel: EERLIJK EN VOLLEDIG**

De twee open aannames zijn correct en eerlijk benoemd:
1. Alle judges gebruiken dezelfde LLM provider. Dit is de grootste beperking t.o.v.
   het echte Prometheus-eval patroon en is terecht als risico benoemd.
2. N=3 hardcoded. Dit is een bekende beperking en terecht als toekomstig sprint-item gelabeld.

Geen verborgen aannames gedetecteerd.

---

### 5. Tenant-isolatie -- risico?

**Oordeel: GEEN RISICO**

De judge panel logica bevindt zich volledig binnen de bestaande `CriticAgent` klasse,
die al per tenant_id geinitialiseerd wordt. Er zijn geen nieuwe database-writes,
geen nieuwe endpoints, en geen nieuwe cross-tenant data-accessen.

`_judge_panel_critique()`, `_run_judge_panel()` en `_build_judge_panel_verdict()` zijn
allemaal instantie-methoden die geen nieuwe state introduceren die buiten de
critique_task() scope leeft. De metadata["judge_panel"] wordt opgeslagen in het
bestaande `Critique` object dat al tenant_id draagt.

**Geen tenant-isolatie risico.**

---

## Bevindingen

### CRITICAL
Geen.

### HIGH
Geen.

### MEDIUM
Geen.

### MINOR

| Nr | Locatie | Bevinding | Aanbeveling |
|----|---------|-----------|-------------|
| M-001 | BE-AGT-019-F Business rules | use_llm=False conditie staat in acceptatiecriteria maar niet in Business rules bullet-lijst | Voeg toe: "Panel niet geactiveerd bij use_llm=False: score en metadata ongewijzigd" |
| M-002 | BE-AGT-019-E motivatie | Drempel 0.30 niet gemotiveerd | Voeg korte zin toe: "0.30 = 30pp meningsverschil dat consensus substantieel verschuift" |
| M-003 | BE-AGT-019-D foutpaden | Parse-error pad (ongeldige score van judge) impliciet, niet expliciet | Voeg toe aan _run_judge_panel of _judge_panel_critique: "parse-fout -> (index, None), telt als failed_judge" |

---

## Eindoordeel

**APPROVED WITH MINOR GAPS**

De spec is technisch correct, volledig op het parse-error pad na, en de design-keuzes
zijn goed gemotiveerd. De leave-one-out motivatie is wiskundig valide. Tenant-isolatie
is aantoonbaar niet geraakt. De drie minors zijn geen blokkeerders voor implementatie.
