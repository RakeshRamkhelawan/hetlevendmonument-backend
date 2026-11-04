# Review: BE-AGT-049 -- Annex III/HITL-classificatie wordt een echte floor op het Council-gate

**Spec:** docs/backend/features/BE-AGT-049-annex-iii-hitl-floor.md (v1)
**Reviewer:** onafhankelijke doc-reviewer-agent
**Datum:** 2026-08-18
**Methode:** elke technische claim (functiesignatuur, regelverwijzingen, testnamen, tellingen,
ID-verwijzingen) is nagelopen tegen de daadwerkelijke broncode/testbestanden in de werkboom
(niet alleen tegen de spec-tekst zelf).
Geverifieerd met Read/Grep/Bash: skill_manifest.py, specialist_base.py,
skillsgaptraining.yml, test_hr_agents_declare_their_annex_iii_classification.py,
test_council_gate_per_action.py, packs.py, governance/ai_act_classifier.py,
copilot/council/factory.py, docs/adr/036-...md (rijen OP-144 en OP-165),
docs/backend/features/ID-REGISTRY.md, git status/git diff/git log (dit is een
uncommitte werkboom-wijziging). De genoemde testbestanden zijn daadwerkelijk gedraaid
(16 + 650 + 2 tests, allemaal groen). pyright/mypy zijn gericht op de twee
productiebestanden gedraaid (0/0). De volledige mandatory suite (15703 passed) is NIET
zelf herdraaid -- dat is buiten de scope van een doc-review op een reeds gereviewde,
groene fix, en zou meer dan 10 minuten kosten. Een manifest-telling
(query_hr_database/analyze_skill_gap over alle 135 manifesten) is met een los script
herhaald en bevestigt de spec's cijfers exact.

---

## A. EINDOORDEEL

APPROVED WITH MINOR GAPS

---

## B. SAMENVATTING

Dit is een ongewoon precies gedocumenteerde spec. Vrijwel elke concrete, verifieerbare
claim klopt woordelijk met de broncode: de regelverwijzingen naar effective_verdict (383,
386, 426, 435 in specialist_base.py), de dataclass-velden en YAML-defaults in
skill_manifest.py (regel 55-56, 81-82), de exacte lijst van zeven "ripple"-testbestanden
(precies zeven treffers, geen enkele extra of ontbrekende), de "2 constructieplekken" in
test_agent_governance_hardening.py, de SkillManifest.to_config-patch in
test_pack_orchestrator_execute_step.py, de decision_id-toevoeging in
tests/fixtures/agent_governance.py, de testnamen in test_council_gate_per_action.py
(inclusief de exacte asserties erin), _PILOT_WIRED_AGENT_IDS = frozenset({"skillsgaptraining"})
in packs.py, de Ce-ceiling van 225 (opnieuw gemeten, ongewijzigd), en de
vijftien/vier/elf-telling van HR-datatoegangsskills (opnieuw gemeten met een los script:
exact 15/4/11, en de 11 namen komen letterlijk overeen met KNOWN_UNDECLARED). Ook de claim
dat hr_culture niet in HIGH_RISK_DEPARTMENTS valt en query_hr_database geen
HIGH_RISK_KEYWORDS matcht is nagerekend tegen de exacte-match/substring-logica in
governance/ai_act_classifier.py en klopt.

Er is echter een reele, verifieerbare structuurfout die de spec ongewijzigd overneemt uit
de voorganger (BE-AGT-048, Dag 2): het flow-ID BE-FLW-050 wordt in dit document vier keer
gebruikt om "de bestaande HITL-ticketflow (OP-163)" aan te duiden, maar BE-FLW-050 staat in
docs/backend/features/ID-REGISTRY.md (regel 547, geregistreerd 2026-07-29) al op een
volledig ander, ongerelateerd artefact: de periodieke purge van verlopen
soft-deleted memory_items (BE-GDPR-003). Dit is geen slordigheid in dit document alleen --
het is een ID-botsing die is ontstaan in BE-AGT-048 (die zelf nooit een registry-rij voor
"BE-FLW-050" heeft aangemaakt, in strijd met de eigen builder-prompt-eis "Controleer altijd
ID-REGISTRY.md voordat je een nieuw ID toewijst") en die twee reviewrondes op BE-AGT-048 is
gepasseerd. BE-AGT-049 had de kans dit te signaleren of te corrigeren en heeft dat niet
gedaan; in plaats daarvan citeert het de botsende ID nog drie keer extra. Voor een document
dat mede bedoeld is als LLM-trainingsbron is een niet-unieke identifier die naar het
verkeerde artefact wijst een structureel probleem, geen kosmetisch puntje.

Daarnaast bevat de Risico's-sectie een claim ("een per ongeluk verwijderde assertie in een
ANDERE, ongewijzigde test") zonder bestandsnaam of testnaam -- niet verifieerbaar en niet
traceerbaar voor een latere lezer. Verder zijn er twee kleine, maar aanwijsbare
regelbereik-onnauwkeurigheden in de "Locatie"-velden. Geen van deze bevindingen is CRITICAL:
er is geen tenant-isolatie- of security-issue gevonden, en de kernclaims over het
afdwinggedrag van de floor kloppen aantoonbaar. Vandaar APPROVED WITH MINOR GAPS in plaats
van NEEDS REVISION.

---

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

- Geen ontbrekende endpoints/services/modellen -- dit is bewust een niet-HTTP, interne
  agent-gedragswijziging, en dat is correct als zodanig gedocumenteerd (Type, sectie 8/9
  overal "n.v.t.").
- De "Backend inventory"-tabel geeft geen aparte rij aan de testinfrastructuurwijzigingen
  (architecture-test, fixtures, 7 ripple-bestanden) -- dat is consistent met hoe de
  voorganger-spec (BE-AGT-048) en het project-ID-schema testbestanden behandelen (geen eigen
  BE-XXX-ID), dus dit is geen gat op zichzelf.
- Geen vermelding van een commit-hash of branch-referentie in het document zelf, omdat de
  wijziging nog niet gecommit is. Dat is inherent aan de "wacht op review"-status en geen
  gap zolang dat voor de lezer duidelijk is (het is: "Status: GEBOUWD, wacht op review").

### 2. Functionele onduidelijkheden

- Geen. De functionele beschrijving ("een Annex III/HITL-skill mag nooit meer automatisch
  doorgaan, ongeacht Council-stemming") is concreet, getoetst tegen de code, en consistent
  tussen Doel, artefact-secties 4/5 en Trainingssamenvatting.

### 3. Technische onduidelijkheden

- Locatie-regelbereik specialist_base.py:366-411 is te kort voor wat het beweert te
  dekken. De tekst zegt dit bereik omvat "de floor-berekening en de APPROVED/HITL_REQUIRED-
  takken die er gebruik van maken". De floor-berekening zelf staat op 366-381; de
  APPROVED-tak op 383-384; de HITL_REQUIRED-tak loopt echter door tot en met de ticket-aanmaak
  en return op regel 428, en de default-return die effective_verdict ook gebruikt staat op
  regel 435 -- buiten het genoemde bereik 366-411. Dit wordt elders in de sectie (Technische
  beschrijving, "regel 426 en 435") wel correct los aangehaald, dus een lezer die de detailtekst
  leest wordt niet misleid, maar het Locatie-veld zelf is onvolledig.
- Locatie-regelbereik skill_manifest.py:94-113 dekt niet de hele to_config()-methode.
  De methode loopt door tot en met regel 119 (afsluitende budget-subdict en de sluitende
  accolade); 113 stopt midden in de budget-dict. Klein, maar een lezer die "regel 94-113"
  opent ziet de methode niet volledig sluiten.

### 4. Ontbrekende foutstatussen en edge cases

- Niet van toepassing (geen HTTP-endpoint) -- correct als zodanig behandeld in sectie 13/QA.
  Sectie 13 verwijst terecht naar het bestaande brede except Exception in act(); bevestigd
  in de code (regel 709-722: de Council-poort en _council_rejection-aanroep staan in dezelfde
  try, met logging en een generieke gate_error-string bij falen).

### 5. Acceptatiecriteria problemen

- Alle vier acceptatiecriteria in sectie 17 zijn getoetst tegen een met naam genoemde test, en
  alle vier tests bestaan en zijn hier opnieuw gedraaid en groen:
  test_approved_verdict_still_floors_to_a_ticket_for_the_pilot_skill,
  test_a_non_hitl_skill_still_executes_directly_on_approval,
  test_council_is_consulted_once_per_tool_call, en de Ce-ceiling-test
  (test_agent_runtime_ce_dag2_final_target, opnieuw gemeten: Ce blijft <= 225). Dit is
  precies het testbare niveau dat de reviewregels eisen.
- Het vijfde punt ("Volledige mandatory suite: 15703 passed, 0 failed") is niet
  onafhankelijk herdraaid in deze review (kostentechnisch meer dan 10 minuten voor een reeds
  gereviewde, groene fix) en is dus een ongeverifieerde claim in de zin dat ik hem niet zelf
  heb gemeten -- geen tegenbewijs gevonden, maar ook geen herbevestiging op suite-niveau.

### 6. Integratorhandleiding / API-uitleg problemen

- Geen. Er is terecht geen publieke API-wijziging; de integratorhandleiding voor
  skill-bouwers ("zet human_in_the_loop: hitl als Annex III van toepassing is") is kort,
  concreet en klopt met de code (SkillManifest.load() leest dat veld letterlijk uit YAML met
  default "hotl", en to_config() geeft het nu door).

### 7. Trainingsdata problemen

- De BE-FLW-050-ID-botsing (zie hoofdbevinding) is een trainingsdata-probleem in engere
  zin: een geautomatiseerd systeem dat op ID leert dat "BE-FLW-050 = deze flow" traint op
  twee tegenstrijdige documenten. Dit is de belangrijkste bevinding van deze review.
- Verder is de Trainingssamenvatting-sectie (19) voor beide artefacten compact, eenduidig en
  consistent met de rest van het document -- geen probleem.

### 8. Structuur- en consistentieproblemen

- HIGH: BE-FLW-050 is een dubbel toegewezen ID. Zie Issue Register #1.
- De "elf van de twaalf"-telling is intern correct, maar de formulering in de bovenliggende
  ADR-036-rij (OP-144, en de vrijwel identieke formulering in
  test_hr_agents_declare_their_annex_iii_classification.py) is op het eerste gezicht
  ambigu ("Elf van de resterende twaalf blijven open" kan gelezen worden als "van 12 nu
  nog aanwezige gevallen blijven er 11 open", terwijl de bedoelde lezing is "van de
  oorspronkelijk 12 die none verklaarden, inclusief de nu gefixte piloot, blijven er 11
  open"). Dit is geen fout in BE-AGT-049 zelf (dat document schrijft correct en ondubbelzinnig
  "de overige elf HR-datatoegangsskills"), en de cijfers zijn met een los script herrekend en
  kloppen exact (15 manifesten met een HR-datatool, 4 verklaren annex_iii/hitl
  skillsgaptraining, employeesentiment, internalmobility, talentacquisition, 11
  verklaren none en komen 1-op-1 overeen met KNOWN_UNDECLARED). Alleen ter info opgenomen
  omdat de taakomschrijving vroeg dit specifiek te controleren -- geen issue-register-regel
  nodig, de spec zelf is hier correct.
- Build summary, Backend inventory en detailsecties zijn intern consistent (geen bestand dat
  in de ene sectie wel en de andere niet voorkomt, buiten de al genoemde regelbereik-nuances).

### 9. Risico's voor implementatie, security of QA

- Geen CRITICAL/HIGH security- of tenant-isolatierisico's gevonden; de spec's eigen claim
  ("self.config.get(...) komt uitsluitend uit het code-gebundelde YAML-manifest, nooit
  uit request body") is bevestigd: nul human_in_the_loop=-kwarg-aanroepen buiten testcode in
  src/.
- MEDIUM: niet-traceerbare claim in Risico's. "een per ongeluk verwijderde assertie in
  een ANDERE, ongewijzigde test (een boundary-fout bij het toevoegen van een nieuwe
  testklasse)" noemt geen bestandsnaam of testnaam. Zie Issue Register #2.
- Het "Open aannames"-punt over de ontbrekende enum-validatie op human_in_the_loop is zelf
  correct en eerlijk geformuleerd (bevestigd: SkillManifest.load() doet alleen data.get(...),
  geen validatie) -- dit is een voorbeeld van goede risicodocumentatie, geen bevinding.

---

## D. ISSUE REGISTER

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
|---|---|---|---|---|
| High | Metadata; Backend inventory; BE-AGT-049 sectie 3; BE-SEC-047 sectie 3 (4x "BE-FLW-050") | BE-FLW-050 is in ID-REGISTRY.md (regel 547, 2026-07-29) al geregistreerd voor "Periodieke purge van verlopen soft-deleted memory_items" (BE-GDPR-003), een volledig ongerelateerd artefact. Dit document hergebruikt dezelfde ID voor de HITL-ticketflow (OP-163) zonder dat ooit apart te registreren. | Het project-uitgangspunt is "elk backend-artefact krijgt een unieke identifier" en de builder-prompt eist expliciet dat ID-REGISTRY.md gecontroleerd wordt voor een nieuwe ID wordt toegewezen. Een dubbel toegewezen Flow-ID stuurt een lezer of een LLM-trainingspipeline die op ID zoekt naar het verkeerde document, en verbergt dat de HITL-ticketflow zelf nooit een eigen, geregistreerde Flow-ID heeft gekregen (BE-AGT-048's registry-rijen bevatten geen BE-FLW-rij, alleen BE-AGT-048 en BE-SEC-046). | Wijs een nieuw, ongebruikt Flow-ID toe aan de HITL-ticket-aanmaak-flow, registreer het met een eigen rij in ID-REGISTRY.md, en vervang alle vier voorkomens van BE-FLW-050 in dit document (en met terugwerkende kracht in BE-AGT-048-hitl-required-ticket-creation.md) door dat nieuwe ID. |
| Medium | Risico's ("Ronde 1 vond ... een per ongeluk verwijderde assertie in een ANDERE, ongewijzigde test") | De claim noemt geen bestandsnaam, testnaam of testklasse voor de andere, ongewijzigde test waarin een assertie per ongeluk verdween. | Een latere lezer kan deze claim niet verifieren of opzoeken. De reviewregels eisen concrete, traceerbare bevindingen, niet een samenvatting zonder verwijzing. | Voeg het bestandspad en de testnaam toe, met een korte omschrijving van welke assertie het betrof en waarom de nieuwe testklasse hem raakte. |
| Low | BE-AGT-049 sectie 2, Locatie specialist_base.py:366-411 | Het genoemde regelbereik dekt de HITL_REQUIRED-tak niet volledig (die loopt door tot regel 428) en niet de default-return op regel 435, terwijl de tekst claimt dat het bereik de APPROVED- en HITL_REQUIRED-takken omvat die effective_verdict gebruiken. | Een lezer die alleen het Locatie-veld gebruikt om de code te openen, ziet de HITL_REQUIRED-tak niet volledig; de detailtekst compenseert dit met losse regelverwijzingen, maar het Locatie-veld zelf is onnauwkeurig. | Wijzig naar specialist_base.py:366-435. |
| Low | BE-AGT-049 sectie 2, Locatie skill_manifest.py:94-113 | to_config() loopt door tot en met regel 119 (sluiting van de budget-subdict en de methode); het genoemde bereik stopt op 113, midden in de budget-dict. | Kleine onnauwkeurigheid die de methode-grens verkeerd weergeeft. | Wijzig naar skill_manifest.py:94-119. |

---

## E. ONTBREKENDE ITEMS

- Geen ontbrekende endpoints, services of flows binnen de scope van deze fix.
- Wel ontbrekend, structureel (zie Issue Register #1): een correct geregistreerd, uniek
  Flow-ID voor de OP-163/D4-002-HITL-ticketflow. Dat ontbreekt niet alleen hier maar al sinds
  BE-AGT-048 (Dag 2) -- deze spec had de kans het recht te zetten en heeft dat niet gedaan.
- Geen los feature-doc-item ontbreekt voor de zeven ripple-testbestanden; die worden
  voldoende gedekt onder BE-AGT-049 sectie 12 (Afhankelijkheden), conform hoe eerdere sprints
  (BE-AGT-048) dat ook deden.

---

## F. VERBETERDE TEKSTVOORSTELLEN

Metadata-veld "Gerelateerde router / module" en de vier BE-FLW-050-verwijzingen -- vervang
door een correct, nieuw geregistreerd ID zodra dat is toegewezen. Tot die tijd, als
tussenstap die het probleem tenminste zichtbaar maakt in plaats van stilzwijgend laat staan,
zou elke vermelding aangevuld kunnen worden met een expliciete kanttekening dat dit ID
al elders geregistreerd staat en dat de HITL-ticketflow nog geen eigen, correct
geregistreerd Flow-ID heeft.

Risico's-sectie, de niet-traceerbare zin over de per ongeluk verwijderde assertie, zou
aangevuld moeten worden met het exacte bestandspad en de exacte testnaam van de test waarin
de assertie verdween, plus een korte reden waarom de nieuwe testklasse die assertie raakte.
Zonder die twee gegevens is de zin een bewering zonder bewijs, terwijl de rest van het
document dat bewijsniveau consequent wel haalt.

---

## G. RELEASE-OORDEEL

- Geschikt voor bouw/implementatie: Ja. De fix is al gebouwd; de spec beschrijft exact
  wat er is veranderd en waar, met regelverwijzingen die (op de twee LOW-onnauwkeurigheden na)
  kloppen.
- Geschikt voor QA en geautomatiseerd testen: Ja. Alle vier de genoemde acceptatiecriteria
  zijn gekoppeld aan een met naam genoemde, bestaande, groene test; deze review heeft ze
  opnieuw gedraaid.
- Geschikt voor LLM-training: Met voorbehoud. De inhoudelijke, technische claims zijn
  uitzonderlijk goed verifieerbaar en accuraat. Het BE-FLW-050-ID-conflict (High) moet eerst
  opgelost worden -- een trainingscorpus met twee documenten die beweren dezelfde unieke ID te
  bezitten voor verschillende artefacten is een structurele datakwaliteitsfout, niet slechts
  een stijlpuntje.
- Geschikt voor integratorhandleiding/API-documentatie: Ja, met de kwalificatie dat er
  geen publieke API is gewijzigd; de korte toelichting voor toekomstige skill-bouwers is
  voldoende en correct.

---

## H. RONDE 2 -- FIXES TOEGEPAST (2026-08-18)

Alle vier bevindingen uit het Issue Register (D) zijn gecorrigeerd:

1. **High (BE-FLW-050-botsing).** Nieuw, ongebruikt Flow-ID `BE-FLW-058` toegewezen (destijds
   gekozen als `BE-FLW-057`, het toen hoogste-plus-1 nummer zichtbaar in `ID-REGISTRY.md` --
   zie de correctie hieronder voor de latere overstap naar `BE-FLW-058`) en geregistreerd in
   `docs/backend/features/ID-REGISTRY.md` met een eigen rij die zowel de flow als de
   correctie zelf documenteert. Alle voorkomens van `BE-FLW-050` vervangen door `BE-FLW-058`
   in dit artefact (`BE-AGT-049-annex-iii-hitl-floor.md`, 12 vervangingen) EN, zoals de
   correctie-instructie eiste, met terugwerkende kracht in het Dag-2-artefact
   (`BE-AGT-048-hitl-required-ticket-creation.md`, 5 vervangingen). BE-FLW-050 zelf blijft
   ongewijzigd bij BE-GDPR-003 staan. **Correctie 2026-08-19 (nazorg, ontdekt door de tweede
   blinde review op commit `bb3f4a76`, hier verwerkt tijdens de derde-ronde-nazorg):** deze
   ronde koos oorspronkelijk `BE-FLW-057`, wat op dat moment het hoogste-plus-1 nummer in
   `ID-REGISTRY.md` leek. Die tweede blinde review toonde dat `BE-FLW-057` ZELF al 15x in
   gebruik was in `BE-SEC-045-agent-factory-governance-gate.md` (dag 1), nooit in de
   registry opgenomen -- de "volgend vrij ID"-check had alleen de registry doorzocht, niet
   de daadwerkelijke specs op disk. Alle verwijzingen naar `BE-FLW-057` in dit artefact zijn
   daarom vervangen door `BE-FLW-058` (het bovenstaande "12 vervangingen" gold oorspronkelijk
   voor de overstap van 050 naar 057; het is nu 057 naar 058 op dezelfde 12 plekken).
2. **Medium (niet-traceerbare Risico's-claim).** De zin in sectie 9/Risico's is aangevuld
   met het exacte bestandspad en testnaam
   (`tests/unit/als/test_council_gate_per_action.py::TestMissingInitiatorFailsClosed::
   test_missing_initiator_prevents_execution`), de exacte regel (`assert result.success is
   False`) en de reden (de `old_string`-grens van de `Edit` die een nieuwe testklasse aan
   het bestand toevoegde nam de laatste regel van de VORIGE test niet mee).
3. **Low (specialist_base.py:366-411).** Gewijzigd naar `366-435` op beide plekken waar het
   voorkwam (sectie 2 Locatie).
4. **Low (skill_manifest.py:94-113).** Gewijzigd naar `94-119` op beide plekken waar het
   voorkwam (sectie 2 Locatie en sectie 6 Technische beschrijving).

Herverificatie: `python scripts/validate_feature_docs.py` geeft exit 0, geen nieuwe
incomplete IDs, BE-AGT-049/BE-SEC-047/BE-FLW-058 allemaal `[OK]`. Geen van de vier fixes
raakte productiecode -- alleen documentatie, dus geen hertest van pytest/pyright nodig.

**Eindoordeel na Ronde 2: APPROVED.** Geen resterende bevindingen.

## I. RONDE 3 -- NAZORG (2026-08-19, derde blinde review)

Deze review-doc zelf bevatte na de BE-FLW-057->058-hernoeming nog 3 verstopte, verouderde
verwijzingen (regels die het OUDE ID `BE-FLW-057` noemden nadat dat ID elders al hernoemd
was) -- gevonden door de derde verplichte blinde review, die specifiek zocht naar
"leftover Flow-ID-verwijzingen in een review-bestand" (dezelfde defectklasse als M-4 uit de
eerste blinde-reviewronde op dit sprintdag). Gecorrigeerd hierboven (sectie H, punten 1 en
de herverificatie-regel). Geen productiecode of test geraakt -- alleen deze reviewtekst.
