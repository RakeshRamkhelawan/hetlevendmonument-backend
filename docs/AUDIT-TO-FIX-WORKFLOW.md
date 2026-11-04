# AUDIT-TO-FIX-WORKFLOW.md

> **Wanneer te gebruiken:** Zodra een audit (security, compliance, code review, pentest, AI Act)
> bevindingen heeft opgeleverd en je die wilt oplossen.
>
> Dit document beschrijft de volledige werkwijze van ruwe bevinding tot aantoonbaar gesloten issue.
>
> **Eigenaar:** Rakesh Ramkhelawan
> **Laatste update:** 2026-05-27
> **Relatie tot AI-WORKFLOW.md:** Dit document is een specialisatie. De standaard
> kwaliteitsloop uit `docs/AI-WORKFLOW.md` (Laag A/B/C, subagent-reviews, tests) is hier
> volledig van kracht. Dit document voegt de audit-specifieke fasen, templates en
> verificatie-eisen eraan toe.

---

## Fase 0 — Audit output structureren

**Doe dit voordat je ook maar één regel code schrijft.**

**Bij ADR-036-werk specifiek: leg eerst een snapshot van het register vast.**

```bash
python scripts/list_adr036_open_items.py --write-snapshot <sessiebestand>.json
```

Gemeten 2026-09-09: een sessie ADR-036-guardwerk sloot af met MEER open registerrijen dan bij
aanvang (66 -> 71), ondanks dat het doel was gaten te dichten. "Meet het aantal open rijen bij
begin en eind" stond al als richtlijn, maar een richtlijn die je uit het geheugen moet ophalen
tijdens een lange mechanische taak wordt gemist. Deze stap maakt de nulmeting een commando in
plaats van een herinnering -- zonder sessiebestand kan Fase 5 straks geen delta tonen.

Zet elke ruwe bevinding om naar dit vaste format. Zonder gestructureerde input is de rest van
het proces niet uitvoerbaar.

### Bevindingstemplate

```text
ID:               AUDIT-NNN
Titel:            <kort, actiegericht — max 10 woorden>
Omschrijving:     <wat is er mis, concreet>
Bewijs:           <bestand:regel, test die faalt, log-fragment, of screenshot-pad>
Root cause:       <WAAROM bestaat dit — niet het symptoom maar de oorzaak>
Impact:           CRITICAL / HIGH / MEDIUM / LOW
Type:             Security / Compliance / Reliability / Performance / Tech-debt
ADR-koppeling:    <ADR-NNN die geschonden of afwezig is, of "Geen">
Fix richting:     <1 zin: de correcte aanpak>
Afhankelijkheden: <AUDIT-NNN die geblokkeerd of blokkerend zijn, of "Geen">
Aangemaakt:       YYYY-MM-DD
Gesloten:         — (nog open)
```

### Voorbeeld (uit AI Act audit 2026-05-26)

```text
ID:               AUDIT-004
Titel:            /ai/suggest mist Council goedkeuringsgate
Omschrijving:     Focus Builder suggest-endpoint voert LLM-voorstellen uit zonder
                  Council-review, in strijd met ADR-031 autonomy ladder L2+.
Bewijs:           src/core/api/focus_builder_endpoints.py:87 — geen require_council_approval()
Root cause:       require_council_approval() helper bestond al maar werd niet consequent
                  toegepast op alle AI-routes bij introductie ADR-031.
Impact:           CRITICAL
Type:             Compliance
ADR-koppeling:    ADR-031
Fix richting:     require_council_approval() toevoegen als eerste call in endpoint handler.
Afhankelijkheden: AUDIT-003 (helper zelf moet correct zijn voor AUDIT-004 zinvol is)
Aangemaakt:       2026-05-26
Gesloten:         —
```

---

## Fase 1 — Triage en prioritering

### Severity-criteria (harde grenzen)

| Prioriteit | Criterium | Uiterste actie |
|-----------|-----------|---------------|
| **P0 — Launch blocker** | Productiedata kan lekken, security bypass actief mogelijk, compliance-deadline wordt gemist, of systeem kan crashen bij normaal gebruik | Fix vóór enige andere activiteit, in huidige sessie |
| **P1 — Sprint blocker** | Degradeert betrouwbaarheid aantoonbaar, technische schuld die exponentieel groeit, blokkeert een andere P0/P1 | Fix in eerstvolgende sprint |
| **P2 — Backlog** | Verbetering zonder actieve impact, nice-to-have hardening, documentatiegap | Plannen op rustig moment |

### Dependency-graaf tekenen

Voordat je een sprint plant, teken je een simpele graaf:

```text
AUDIT-001 (P0) ──► AUDIT-004 (P0)   [004 is geblokkeerd door 001]
AUDIT-002 (P0) ──► AUDIT-005 (P1)   [005 kan pas na 002]
AUDIT-003 (P0) ────────────────────  [standalone]
```

**Regel:** Geclusterde bevindingen met dezelfde root cause worden als één unit behandeld,
niet als losse tickets.

### Verplichte vraag per bevinding: blokkeert dit AANTOONBAAR iets vandaag?

**Besluit Rakesh 2026-09-07, hier vastgelegd als letterlijke triage-stap in plaats van alleen
als principe in `.claude/skills/valkuilen/SKILL.md`.** Beantwoord dit VOORDAT je een fix-route
kiest:

- **JA, gemeten** (onbereikbare code, een klasse die niemand instantieert, een pad zonder
  aanroeper, dode DDL, of -- specifiek voor audit-/guardwerk -- een testbewaker die zelf iets
  minder scherp ziet dan gedacht, geen kapotte productiecode) -> **alleen een sprint-dag-brief**
  in `docs/agent-briefs/generated/`, met de meting en de aanname waarop het besluit rust. GEEN
  guard, GEEN mutatiebewijs-traject.
  **Gewijzigd 2026-09-19 (besluit Rakesh):** hier stond "alleen een registerrij". Een nieuwe
  ADR-036-registerrij is geen toegestane bestemming meer -- zie CLAUDE.md, Absolute regels punt
  3, en de NOOIT-lijst in `.claude/rules/quality-gates.md`. De beslisboom zelf is onveranderd:
  de vraag of de bevinding AANTOONBAAR iets blokkeert bepaalt nog steeds de route, alleen gaat
  de lichte route nu naar een brief die ook echt wordt uitgevoerd in plaats van naar een rij die
  blijft staan.
- **NEE, of niet gemeten** -> de volle Fase 4 (test-first, kwaliteitsloop, mutatiebewijs in
  twee richtingen, regressietest).
- **"Ik denk dat het niet erg is" is geen meting.** Zonder een commando of bestand dat het
  aantoont, is het antwoord NEE.

Dit is de regel die op 2026-09-08/09 bestond maar niet werd toegepast op vijf van de zes
nieuwe ADR-036-rijen uit een externe review van reeds-gerepareerde guards -- allemaal
bevindingen over de kwaliteit van een testbewaker, geen kapotte applicatie, en toch met het
volle traject behandeld. Vandaar dat de vraag hier staat, op de plek waar de beslissing toch
al genomen wordt, niet alleen in een apart bestand dat je pas raadpleegt als je al vermoedt
dat je in een valkuil zit.

---

## Fase 2 — Root cause groupering

**Symptomen samenvoegen is de meest tijdbesparende stap in het hele proces.**

Stel dat drie bevindingen oppervlakkig los lijken:
- AUDIT-004: `/suggest` mist Council gate
- AUDIT-005: `/generate` mist Council gate
- AUDIT-006: `/tasks` mist Council gate

Root cause is identiek: ontbrekende `require_council_approval()` call. Fix = helper toepassen
op alle routes tegelijk. Zonder groupering schrijf je drie quasi-identieke commits en introduceer
je inconsistentie.

### Groepering beslisregel

> Als twee of meer bevindingen dezelfde root cause hebben, los je de root cause op — niet de
> instanties afzonderlijk.

Documenteer de groepering expliciet:

```text
ROOT-CAUSE-GROEP-1: "require_council_approval() niet universeel toegepast"
  Bevat: AUDIT-004, AUDIT-005, AUDIT-006
  Fix: 1 commit die alle drie afsluit
```

---

## Fase 3 — Sprint structureren

### Template fix-sprint (5 dagen)

```text
Dag 1: Root cause fixes P0 groep A
       + Regressietests schrijven voor groep A (red → green bewijs)

Dag 2: Root cause fixes P0 groep B
       + Integratietests groep A (echte backend)
       + Regressiecheck groep A

Dag 3: P1 fixes + integratietests
       + Bewijs vastleggen voor alle P0's

Dag 4: Verificatie alle P0's
       + pytest --stepwise volledige suite
       + Evidence-bestanden aanmaken

Dag 5: Re-audit P0's
       + CLAUDE.md en AI-WORKFLOW.md preventie-updates
       + Sprint review + P1 doorschuiven naar volgende sprint
```

### Regels voor sprint-planning

1. **Eén root cause per dag.** Als dag 2 faalt, weet je precies welke fix de regressie veroorzaakte.
2. **P0's zijn non-negotiable.** Ze schuiven niet door. De sprint stopt niet totdat alle P0's groen zijn.
3. **P1's mogen doorschuiven.** Maar alleen als dat expliciet gedocumenteerd is.
4. **Geen nieuwe features** in een fix-sprint. Scope creep maakt verificatie onmogelijk.

---

## Fase 4 — Fix uitvoeren

### Verplichte volgorde per bevinding (test-first)

```text
Stap 1: Schrijf een test die de bevinding reproduceert
        → Test MOET ROOD zijn. Als hij groen is, test je het verkeerde.
Stap 2: Voer de kwaliteitsloop uit (AI-WORKFLOW.md Laag A)
        → Onafhankelijke subagent code review + quality review
Stap 3: Implementeer de fix
Stap 4: Test wordt GROEN
        → Voer de volledige suite uit (pytest --stepwise) om regressies te detecteren
Stap 5: Voeg regressietest toe die de fix permanent beschermt
Stap 6: Leg bewijs vast (zie Fase 4 bewijs-template)
```

**Als je niet eerst een rode test kunt schrijven:** de bevinding is onvoldoende gespecificeerd.
Ga terug naar Fase 0 en verfijn het bewijs-veld.

### Bewijs-template per gesloten bevinding

```text
ID:               AUDIT-NNN
Status:           GESLOTEN
Fix commit:       <git hash>
Test die faalde:  tests/unit/test_X.py::test_Y
Verificatie cmd:  pytest tests/ -k "test_Y" -v
Reviewer:         <naam subagent of Rakesh>
Regressietest:    tests/unit/test_X.py::test_Y_regression
Gesloten op:      YYYY-MM-DD
```

### Integratietests: altijd echte backend

Geen mocks, geen stubs, geen placeholders. Alle services moeten draaien:
- PostgreSQL op poort 5455
- Redis actief
- Backend gestart

Dit is niet onderhandelbaar. Een bevinding die "groen" is op een gemockte integratie maar
kapot is op de echte stack, is niet gesloten.

---

## Fase 5 — Verificatie (re-audit)

Na elke fix-sprint voer je een formele re-audit uit:

### Re-audit checklist

```text
Voor elke bevinding in de sprint:
□ Bewijs-template ingevuld (commit hash + test naam + verificatie commando)
□ Test draait groen: pytest tests/ -k "<test_naam>" -v
□ Geen regressies: pytest --stepwise (volledige suite)
□ Integratietest slaagt op echte backend
□ Reviewer heeft APPROVED gegeven (niet de auteur zelf)

Voor de sprint als geheel:
□ Alle P0's hebben status GESLOTEN met bewijs
□ Alle P1's hebben status GESLOTEN of zijn gedocumenteerd als doorgeschoven
□ Geen nieuwe P0's geintroduceerd (regressiecheck)
```

**Kritieke regel:** Een bevinding is CLOSED als en alleen als het bewijs aanwezig is.
"Code ziet er correct uit" is geen bewijs. Een groene test met commit hash is bewijs.

### Bij ADR-036-werk: verplichte delta-melding voor de sprint-afsluiting

```bash
python scripts/list_adr036_open_items.py --diff-against <sessiebestand-uit-fase-0>.json
```

Neem de LETTERLIJKE output (dichtgegaan / nieuw open / netto) op in de sprint-afsluiting of
final-approver-brief. Geen samenvatting zonder dat blokje. Een toename is niet per definitie
fout -- een echte nieuwe ontdekking (zoals het P0-autorisatiecluster van 2026-09-01) hoort in
dit register -- maar moet dan EXPLICIET benoemd worden als nieuwe vondst, niet stilzwijgend
langs de samenvatting glippen zoals op 2026-09-08/09 gebeurde (66 -> 71 open, onvermeld in de
eerste samenvattingen van die sessie).

---

## Fase 6 — Preventie (verplichte laatste stap)

Elke afgesloten P0 levert preventie-output op. Zonder deze stap los je hetzelfde probleem
bij de volgende audit opnieuw op.

### Preventie-beslisregel

| Type fix | Verplichte preventie-output |
|----------|-----------------------------|
| Codepatroon was fout (bijv. naive datetime, tenant uit body) | Toevoegen aan **valkuilen-tabel in CLAUDE.md** |
| Process werd niet gevolgd (bijv. subagent review overgeslagen) | Toevoegen aan **anti-patronen tabel in AI-WORKFLOW.md** |
| Architectuurbeslissing ontbrak of onduidelijk was | **Nieuw of aangepast ADR** aanmaken |
| Verificatieproces faalde (bevinding eerder gemist) | Toevoegen aan **re-audit checklist** in dit document |

### Voorbeeld preventie-output (uit AI Act audit)

Bevinding: routes misten `require_council_approval()`.

Preventie in CLAUDE.md valkuilen-tabel:
```
| Nieuwe AI-route mist Council gate | ADR-031 verplicht governance voor alle AI-routes;
  require_council_approval() wordt over het hoofd gezien | Gebruik require_council_approval()
  als eerste call in elke endpoint die LLM-output produceert of uitvoert |
```

---

## Samenvatting: de volledige werkwijze als checklijst

```text
FASE 0 — Structureren
□ Elke bevinding in gestandaardiseerd format (ID / bewijs / root cause / impact / ADR)
□ Dependency-relaties expliciet benoemd

FASE 1 — Triage
□ P0 / P1 / P2 gesorteerd op harde criteria
□ Dependency-graaf gemaakt
□ Volgorde van P0-fixes bepaald op basis van afhankelijkheden

FASE 2 — Groupering
□ Bevindingen met identieke root cause samengevoegd
□ Root cause-groepen gedocumenteerd met gedeelde fix-aanpak

FASE 3 — Plannen
□ Fix-sprint gepland: 1 root cause per dag, regressie de dag erna
□ Geen nieuwe features in de sprint
□ Alle P0's zijn non-negotiable in de huidige sprint

FASE 4 — Fix uitvoeren
□ Test geschreven die bevinding reproduceert -> ROOD
□ Kwaliteitsloop Laag A doorlopen (onafhankelijke subagent reviews)
□ Fix geimplementeerd -> test GROEN
□ pytest --stepwise geen regressies
□ Regressietest toegevoegd
□ Bewijs-template ingevuld (commit + test + reviewer)
□ Integratietests op echte backend geslaagd

FASE 5 — Verificatie
□ Re-audit checklist afgevinkt voor elke bevinding
□ Alle P0's: status GESLOTEN met bewijs
□ P1's: GESLOTEN of gedocumenteerd doorgeschoven

FASE 6 — Preventie
□ CLAUDE.md valkuilen-tabel bijgewerkt (codepatronen)
□ AI-WORKFLOW.md anti-patronen bijgewerkt (process)
□ ADR aangemaakt of bijgewerkt (architectuur)
□ Dit document bijgewerkt indien re-audit checklist tekortschoot
```

---

## Veelgemaakte fouten

| Fout | Gevolg | Correctie |
|------|--------|-----------|
| Symptomen fixen zonder root cause te identificeren | Dezelfde klasse van bevindingen keert terug bij volgende audit | Fase 2 altijd uitvoeren vóór Fase 3 |
| Bevinding markeren als CLOSED zonder testbewijs | Valse zekerheid; audit-rapport klopt niet | Bewijs-template is verplicht; geen uitzonderingen |
| Test schrijven na de fix | Test is groen per definitie; bewijst niets | Test MOET rood zijn vóór de fix |
| Integratietests op mocks | Bevinding "opgelost" maar echte stack nog kapot | Altijd echte backend; zie Fase 4 |
| Fase 6 overslaan | Zelfde probleem bij volgende audit; geen institutioneel geheugen | CLAUDE.md/AI-WORKFLOW.md updaten is verplicht, niet optioneel |
| Twee root causes in één dag fixen | Bij regressie onbekend welke fix de oorzaak is | Eén root cause per dag |
| P2's upgraden naar P1 onder tijdsdruk | Sprint scope groeit, P0-verificatie wordt gehaast | P2 blijft P2 tenzij Rakesh expliciet upgradet |

---

*Eigenaar: Rakesh Ramkhelawan | Laatste update: 2026-05-27*
*Wijzigingen aan dit document vereisen expliciete toestemming van de eigenaar.*
