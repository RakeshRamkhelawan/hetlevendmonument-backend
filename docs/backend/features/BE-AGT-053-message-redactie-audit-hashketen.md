# BE-AGT-053 / BE-AGT-054 / BE-AGT-055 -- Message-redactie in de audit-hashketen

## Metadata

- **Sprint:** ADR-036 fix-sprint -- P0 + P1 uit de volledige audit (2026-08-18), dag 6 van 8
- **ADR:** ADR-036 D2-002/OP-38 (message-redactie), OP-170 (nieuw, bijvangst: forensics.py-drift),
  OP-171 (nieuw, bijvangst: `_FABRICATED_STATS`-regexgat, niet gefixt)
- **Datum:** 2026-08-20
- **Branch:** develop

---

## Doel en scope

### Doel

`proposal.message` (vrije, door het taalmodel geschreven babbeltekst naar de eindgebruiker,
"Final natural language text for the user") ging tot vandaag ONGEREDIGEERD de onuitwisbare
ADR-019-hashketen in: verbatim in `council_decisions.message` (Text, NOT NULL, geen wisroute --
OP-36) en verbatim meegehasht in `compute_canonical_json()`. Dit is dezelfde klasse bevinding als
`action_params` (OP-33, al gefixt): allebei zijn LLM-geschreven vrije tekst, allebei
aanvallerbeinvloed, allebei kunnen hetzelfde persoonsgegeven bevatten.

**Belangrijke scope-afbakening (na overleg met Rakesh, 2026-08-20).** ADR-036 OP-38 groepeert
oorspronkelijk DRIE velden onder dezelfde bevinding: `message`, `reasoning`, en (aangevuld
2026-08-05) `action_type` (apart als OP-49). Exhaustief nagelopen voor implementatie: `reasoning`
en `decision.explanation_for_user` worden RECHTSTREEKS aan de eindgebruiker geserveerd via
`copilot/api/explanation_builder.py:38-39` (`reasoning_summary=decision.reasoning`,
`explanation_for_user=decision.explanation_for_user`), onder AI Act art. 13/14
(transparantie/menselijk toezicht, `GET /api/v1/copilot/audit/{decision_id}`). Digesten zou die
wettelijke uitlegbaarheid slopen. `message` staat in GEEN response-schema van die
explainability-API (`DecisionExplanationResponse`, `copilot/api/schemas.py`) en wordt
uitsluitend gelezen door drie interne verifiers (`chain_verifier.py`, `report_generator.py`,
`forensics.py`) voor hash-herberekening, nooit voor menselijke weergave. Vandaag daarom ALLEEN
`message` gefixt; `reasoning`/`explanation_for_user` blijven OPEN onder OP-38 (art.-14-materiaal,
vereist een eigen afweging); `action_type` blijft OPEN onder OP-49.

| Veld | Geserveerd aan eindgebruiker? | Actie vandaag |
|---|---|---|
| `message` | Nee -- alleen gelezen door 3 interne hash-verifiers | GESLOTEN (BE-AGT-053) |
| `reasoning` | Ja -- `explanation_builder.py:38-39` (`reasoning_summary`) | OPEN (OP-38) |
| `explanation_for_user` | Ja -- `explanation_builder.py:38` | OPEN (OP-38) |
| `action_type` | Indirect (in `officer_verdicts.reason_text`) | OPEN (OP-49) |

### In scope

- `CouncilAuditWriter.persist()` redigeert `proposal.message` met `value_digest()`
  (`src/core/tool_broker/redaction.py:739-756`) -- NIET `redact_for_publication()`, want die
  verwacht een `Mapping`-payload met een tool-vocabulaire; `message` is een kale string. Zelfde
  aanroepplek als de bestaande `action_params`-redactie (OP-33), zelfde reden: de twee
  onafhankelijke verifiers herberekenen de hash uit de OPGESLAGEN rij, dus redigeren binnen
  `compute_canonical_json()` zou een al geredigeerde waarde nog eens redigeren.
- Lege `message` (de meest voorkomende waarde, default `message: str = ""`) blijft leeg --
  zelfde principe als `redact_for_publication()`'s bestaande `None`-uitzondering.
- **Bijvangst (BE-AGT-054), gevonden door Gate 2's security-reviewer**:
  `SanityOfficer`'s `HallucinationGuard`-VETO-pad zette de gematchte modeltekst (bv. een
  bestandsnaam die een persoonsnaam kan bevatten, zoals `"jan_jansen_salaris.pdf"`) ongeredigeerd
  in `officer_verdicts.reason_text`/`evidence` -- die evidence wordt NIET geredigeerd door
  `persist()` (bewuste keuze, zie `TestTheOfficerEvidenceIsTheSideDoorOfTheSameTransaction`) en
  gaat dus ongefilterd de hashketen in. Gefixt: alleen de trigger-CATEGORIE ("absolute_claim",
  "fabricated_stat", "ungrounded_file_ref") wordt vastgelegd, niet de gematchte tekst zelf --
  zelfde principe als de bestaande `ethics_officer`-fix (OP-95).
- **Bijvangst, geregistreerd maar NIET gefixt (OP-170)**: `forensics.py`'s
  `HashChainVerifier.verify_tenant_chain()` bouwt een EIGEN, uit de pas gelopen kopie van
  `compute_canonical_json()`'s dict (mist `model_id`/`model_version`) en meldt daardoor op ELKE
  rij "Content tampering detected", onafhankelijk van deze fix. Pre-existing, niet veroorzaakt
  door de message-redactie. Vastgelegd met een `xfail(strict=True)`-architecture-test
  (`tests/architecture/test_forensics_reconstructs_the_same_shape_as_persist.py`), niet gefixt
  vandaag (buiten scope).
- **Bijvangst (BE-AGT-055), gevonden door de verplichte blinde eindreview (ronde 1)**:
  `hallucination_guard.py::HallucinationGuard.check()` logde de gematchte bestandsnaam van zijn
  `ungrounded_file_ref`-regel als los `file=`-veld via `loguru` op INFO-niveau, ook in productie
  -- zelfde klasse PII-lek als BE-AGT-054, maar via applicatielogs in plaats van de hashketen.
  Gefixt: alleen het FEIT dat de regel triggerde wordt gelogd, niet de gematchte tekst.
  **Correctie na ronde 2**: de eerste versie liet de `fabricated_stat`-regel ongewijzigd, met de
  aanname dat die (net als `absolute_claim`) een gesloten patroon matcht en dus geen
  persoonsgegeven kan bevatten. Ronde 2 vond dat dit niet klopt voor de "Nx faster/slower/..."-
  tak (`\d+x ...`): een ONBEGRENSDE cijferreeks, in tegenstelling tot de begrensde
  percentage-tak (`\d{2,3}%`, max 3 cijfers) -- zelf nagemeten dat "0612345678x faster" matcht.
  Ook die tak kreeg daarom hetzelfde: alleen het FEIT loggen, niet de match. Alleen
  `absolute_claim` (echt gesloten woordenlijst, geen cijfer- of vrije-tekstcomponent) blijft
  ongewijzigd.
- **Bijvangst van een bijvangst, geregistreerd maar NIET gefixt (OP-171)**: tijdens het
  schrijven van de regressietest voor BE-AGT-055 bleek `_FABRICATED_STATS`' losse-percentage-
  alternatief (`\d{2,3}%\b`) in de praktijk vrijwel nooit te matchen (een `%`-teken gevolgd door
  een natuurlijk zinseinde voldoet nooit aan de sluitende `\b`). Zelf rechtstreeks nagemeten met
  losse regex-aanroepen, niet aangenomen. Ongerelateerd aan PII-redactie (dit is een
  betrouwbaarheidsgat: de regel matcht minder dan bedoeld, geen lek). Vastgelegd met een tweede
  `xfail(strict=True)`-test in hetzelfde testbestand, niet gefixt (eigen regex-correctheidsrisico
  in een safety-guard, buiten scope van vandaag).
- Golden-vector-test (`TestTheDecisionHashIsPinnedToAGoldenVector`) uitgebreid met een eigen
  `GOLDEN_MESSAGE`/hash: de bestaande vector riep `persist()` nooit aan en bood dus GEEN dekking
  voor de plaatsing van de message-redactie (dezelfde blinde vlek als de Gate-2-ronde-6-vondst
  die de oorspronkelijke vector veroorzaakte, nu gevonden door de security-reviewer voordat hij
  een probleem kon worden).

### Out of scope

- `reasoning`/`explanation_for_user`-redactie -- blijft OPEN onder OP-38, vereist een eigen
  afweging (wat moet een mens kunnen navolgen versus wat mag bewaard blijven), expliciet niet
  vandaag beslist.
- `action_type`-redactie -- blijft OPEN onder OP-49.
- Het fixen van `forensics.py`'s model_id/model_version-gat -- geregistreerd als OP-170, apart
  te plannen.
- Het fixen van `_FABRICATED_STATS`' losse-percentage-regex -- geregistreerd als OP-171, apart
  te plannen (een regex-wijziging in een safety-guard is een eigen correctheidsrisico).
- Normalisatie of caching van `value_digest()`-uitkomsten -- ongewijzigd hergebruik van een
  bestaand, al geteste primitief.

---

## Build summary

- Nieuw gebouwd: 6 tests in `tests/unit/copilot/test_council_persist_leaks_nothing.py`
  (2x `TestTheMessageIsNotStoredVerbatim`, 1x non-interferentie met action_params, 1x canonieke
  JSON, 1x verifier-recomputatie met geredigeerde message, 1x golden-vector-dubbele-pas voor
  message), 1 nieuwe architecture-test (`xfail(strict=True)`, OP-170).
- Gewijzigd (bestaand gedrag behouden, reconstructie-accuraatheid gecorrigeerd): 1 bestaande
  test (`test_recomputing_the_hash_from_the_stored_row_matches`) uitgebreid met
  `message=row.message` bij reconstructie -- zonder deze correctie faalt hij zodra `persist()`
  message redigeert, niet omdat de redactie verkeerd staat maar omdat de reconstructie zelf niet
  meer overeenkomt met wat `report_generator._reconstruct_proposal()` echt doet.
  `test_sanity_officer_vetos_hallucination` uitgebreid met een expliciete
  "categorie wel, matched tekst niet"-assertie (was: assertie op de gelekte tekst zelf).
- Golden vector bijgewerkt: `GOLDEN_MESSAGE` (nieuwe constante) + herberekende
  `GOLDEN_DECISION_HASH` (was `6637a692...f31d172`, nu `5277af91...4f9672`) + een nieuwe
  dubbele-pas-test specifiek voor message.
- Productiecode gewijzigd: `src/core/copilot/council/audit_writer.py` (import, docstring,
  `published_message`-berekening, `redacted_proposal`, row-insert),
  `src/core/copilot/council/members/sanity_officer.py` (categorie-extractie), 2
  documentatie-only comment-updates (`background_gate.py`, `specialist_base.py`) die door de
  redactie feitelijk onjuist waren geworden.
- Nieuw gebouwd (BE-AGT-055, ronde 1 blinde review): 4 tests in
  `tests/unit/learning/safety/test_hallucination_guard_does_not_log_the_matched_filename.py`
  (1x de fix zelf, 2x regressie op de twee ONgewijzigde regels, 1x `xfail(strict=True)` voor
  OP-171). Productiecode gewijzigd: `src/core/learning/safety/hallucination_guard.py` (het
  `ungrounded_file_ref`-logcall verliest zijn `file=`-veld) + alle pre-existing non-ASCII tekens
  in datzelfde bestand naar ASCII gecorrigeerd (drempelmodel: geisoleerd, 1 bestand, <15 min).

---

## Backend inventory

- `src/core/copilot/council/audit_writer.py` (gewijzigd)
- `src/core/copilot/council/members/sanity_officer.py` (gewijzigd)
- `src/core/copilot/council/background_gate.py` (comment-only)
- `src/core/als/agents/specialist_base.py` (comment-only)
- `tests/unit/copilot/test_council_persist_leaks_nothing.py` (uitgebreid)
- `tests/unit/copilot/council/test_sanity_officer.py` (uitgebreid)
- `tests/architecture/test_forensics_reconstructs_the_same_shape_as_persist.py` (nieuw, OP-170)
- `src/core/learning/safety/hallucination_guard.py` (gewijzigd, BE-AGT-055 + ASCII-cleanup)
- `tests/unit/learning/safety/test_hallucination_guard_does_not_log_the_matched_filename.py`
  (nieuw, BE-AGT-055 + OP-171)
- `docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md` (OP-38 deels gesloten +
  aanvulling BE-AGT-055, OP-170 en OP-171 nieuw geregistreerd)

---

## Detaildocumentatie per artefact

## [BE-AGT-053] Message-redactie in `CouncilAuditWriter.persist()`

### 1. Type

- Agent-/governance-gedrag (interne methode, geen HTTP-endpoint).

### 2. Locatie

- Bestandspad: `src/core/copilot/council/audit_writer.py` -- de `published_message`-berekening
  en de `redacted_proposal`-constructie in `persist()`, direct na de bestaande
  `action_params`-redactie. *(Exacte regelnummers bewust niet genoemd -- zie de les uit dag 5,
  vier rondes regelnummer-drift op precies dit type verwijzing: zoek op symboolnamen.)*
- Klasse / functie: `CouncilAuditWriter.persist()`.

### 3. Gerelateerde flow

- Geen apart Flow-ID -- een redactiestap binnen de bestaande audit-persist-flow (dezelfde flow
  die OP-33/`action_params` al redigeert).

### 4. Doel

- Voorkomen dat een persoonsgegeven in de vrije babbeltekst van het model permanent, onbewerkt
  in de ADR-019-hashketen belandt.

### 5. Functionele beschrijving

- Een niet-lege `proposal.message` wordt vervangen door `value_digest(proposal.message,
  tenant_id=proposal.tenant_id)` voordat de canonieke JSON wordt gehasht EN voordat de rij wordt
  geschreven. Een lege `message` blijft leeg.
- Effect op systeemtoestand: de LIVE respons aan de gebruiker (`CopilotTurnResponse.message`,
  afkomstig van `action.message`, NIET van `proposal.message`) is ONGEWIJZIGD -- deze fix raakt
  uitsluitend de permanente audit-kopie.

### 6. Technische beschrijving

- `published_message = value_digest(proposal.message, tenant_id=proposal.tenant_id) if
  proposal.message else ""`, gevolgd door `redacted_proposal = replace(proposal,
  action_params=published_params, message=published_message)` (uitbreiding van de bestaande
  `replace()`-aanroep, geen tweede). Row-insert gebruikt `redacted_proposal.message`, niet
  `proposal.message` -- ZELFDE waarde als in de canonieke JSON, anders is de hash niet meer na
  te rekenen uit de rij (exact de valstrik die `TestAVerifierRecomputingFromTheRowGetsTheStoredHash`
  bewaakt, nu voor twee velden).
- **Zelf-gevonden implementatiefout tijdens dit werk**: de eerste versie berekende
  `published_message` correct maar liet de row-insert nog op `message=proposal.message` staan --
  de hash werd dus WEL met de geredigeerde waarde berekend, maar de rij sloeg de RAUWE waarde op.
  Gevonden door de eigen testset te draaien (4 tests rood: de twee directe checks plus BEIDE
  verifier-recomputatietests), niet door aanname. Gefixt en mutatiegetest (zie sectie 17).

### 7. Zichtbaarheids- en toegangsregels

- Geen wijziging in autorisatie. De redactie raakt alleen wat er PERMANENT wordt opgeslagen,
  niet wie welke live-respons ziet.

### 8-16. n.v.t

### 17. Acceptatiecriteria

- Alle 6 nieuwe tests slagen (zie Build summary).
- Mutatiebewijs, beide richtingen, zelf uitgevoerd (backup/restore via `cp` + `git diff --stat`):
  - Redactie volledig weghalen (`published_message = proposal.message`): 2 tests rood (de
    directe "niet verbatim"-checks).
  - Alleen de row-insert laten wijzen naar de rauwe waarde (de zelf-gevonden fout hierboven,
    opnieuw geproduceerd): 4 tests rood (de 2 directe checks + beide
    verifier-recomputatietests) -- bewijst dat de testset deze exacte fout onafhankelijk vangt.
  - Golden vector: `test_a_second_redaction_pass_of_the_message_produces_a_different_hash`
    bewijst dat de message-golden-vector niet vacuum is.
- `python -m pytest tests/unit/copilot/test_council_persist_leaks_nothing.py -v` -> 18 passed
  (was 12, +6).

### 18. Integratoruitleg

- Geen publieke API-wijziging. Interne consumenten van `CouncilDecisionRow.message`
  (`chain_verifier.py`, `report_generator.py`, `forensics.py`) lezen de rij rechtstreeks en
  herberekenen dus automatisch correct tegen de nieuwe, geredigeerde waarde -- geen
  aanpassing aan die drie bestanden nodig (`forensics.py`'s pre-existing, ongerelateerde bug
  daargelaten, zie OP-170).

### 19. Trainingssamenvatting

- **Actor:** `CouncilAuditWriter.persist()`, aangeroepen door `AuditOfficer.finalize_and_persist()`.
- **Voorwaarde:** een `CouncilDecision` + `Proposal` met een niet-leeg `message`-veld wordt
  gepersisteerd.
- **Actie:** `persist()` redigeert `message` via `value_digest()` op de aanroepplek, voor de
  hash-berekening en voor de row-insert.
- **Systeemreactie:** `council_decisions.message` bevat een keyed HMAC-digest in plaats van de
  klaartekst; `decision_hash` is berekend over dezelfde geredigeerde waarde.
- **Succesrespons:** de rij wordt geschreven, de hash is door twee van de drie bestaande
  verifiers (`chain_verifier.py`, `report_generator.py`) consistent na te rekenen uit de
  opgeslagen (geredigeerde) waarde. De derde, `forensics.py`, heeft een pre-existing,
  ONGERELATEERD gat (ontbrekende `model_id`/`model_version` in zijn eigen dict-reconstructie,
  zie OP-170) waardoor hij op ELKE rij tampering meldt, onafhankelijk van deze fix -- geen
  regressie van vandaag, zie sectie 18.
- **Foutrespons:** zonder de omgevingsvariabele `TOOL_PAYLOAD_PSEUDONYM_KEY`
  (`redaction.py:102`, buiten development/test/local) gooit `value_digest()` een
  `RuntimeError` -- fail-closed, dezelfde keuze als voor `action_params`.
- **Uitzonderingen:** een lege `message` blijft leeg (geen digest van een informatieloze waarde).

---

## [BE-AGT-054] `SanityOfficer`-hallucinatie-evidence bevat geen gematchte modeltekst meer

### 1. Type

- Agent-/governance-gedrag (interne officer-logica).

### 2. Locatie

- Bestandspad: `src/core/copilot/council/members/sanity_officer.py`, de VETO-tak van de
  hallucinatiecheck in `deliberate()`.
- Klasse / functie: `SanityOfficer.deliberate()`.

### 3. Gerelateerde flow

- Geen apart Flow-ID -- onderdeel van de bestaande Council-deliberatieflow.

### 4. Doel

- Voorkomen dat de door `HallucinationGuard.check()` gematchte modeltekst (potentieel een
  bestandsnaam met een persoonsnaam) ongeredigeerd in de onuitwisbare hashketen belandt via
  `officer_verdicts.reason_text`/`evidence`.

### 5. Functionele beschrijving

- Bij een VETO wordt alleen de trigger-CATEGORIE ("absolute_claim", "fabricated_stat",
  "ungrounded_file_ref", of "unknown" als fallback) vastgelegd in zowel `reason_text` als
  `evidence["hallucination_reason"]`, niet de specifieke gematchte tekst.
- Effect op systeemtoestand: de VETO-beslissing zelf is ongewijzigd (`is_safe_msg`-logica niet
  aangeraakt) -- alleen wat over de MATCH wordt vastgelegd, verandert.

### 6. Technische beschrijving

- `hallucination_category = (hall_reason or "unknown").split(":", 1)[0]`, gebruikt in plaats
  van het rauwe `hall_reason` in beide plekken waar dat eerder stond.

### 7. Zichtbaarheids- en toegangsregels

- Geen wijziging.

### 8-16. n.v.t

### 17. Acceptatiecriteria

- `test_sanity_officer_vetos_hallucination` (bestaand, uitgebreid): asserteert nu dat de
  categorie WEL en de gematchte tekst NIET in `reason_text` staat, plus dat `evidence` alleen
  de categorie draagt.
- Mutatiebewijs (zelf uitgevoerd, backup/restore): de fix tijdelijk verwijderen
  (`hallucination_category = hall_reason`) maakt de nieuwe "secret.py not in reason_text"-assertie
  rood; herstel maakt hem weer groen.
- `python -m pytest tests/unit/copilot/council/test_sanity_officer.py -v` -> 5 passed
  (ongewijzigd aantal, bestaande test uitgebreid).

### 18. Integratoruitleg

- Geen publieke API-wijziging.

### 19. Trainingssamenvatting

- **Actor:** `SanityOfficer.deliberate()`.
- **Voorwaarde:** `HallucinationGuard.check()` retourneert `(False, reason)` voor een
  `absolute_claim`/`fabricated_stat`/`ungrounded_file_ref`-match.
- **Actie:** de officer legt alleen de categorie vast, niet de gematchte tekst.
- **Systeemreactie:** VETO met `reason_text`/`evidence` beperkt tot de categorie.
- **Succesrespons:** toezicht kan zien WELKE regel triggerde, zonder dat de specifieke
  modeltekst (mogelijk PII) de hashketen ingaat.
- **Foutrespons:** n.v.t. -- geen nieuw faalpad.
- **Uitzonderingen:** een ontbrekende/`None` `hall_reason` valt terug op de categorie "unknown".

---

## [BE-AGT-055] `HallucinationGuard` logt de gematchte match niet meer voor de twee tekst-/cijferafhankelijke regels

### 1. Type

- Agent-/governance-gedrag (interne safety-heuristiek, geen HTTP-endpoint).

### 2. Locatie

- Bestandspad: `src/core/learning/safety/hallucination_guard.py`, de `fabricated_stat`- en
  `ungrounded_file_ref`-takken in `HallucinationGuard.check()`.
- Klasse / functie: `HallucinationGuard.check()`.

### 3. Gerelateerde flow

- Geen apart Flow-ID -- een logging-detail binnen de bestaande Digital Twin-suggestiecontrole
  (ADR-025/026).

### 4. Doel

- Voorkomen dat een gematchte bestandsnaam (potentieel een persoonsnaam, bv.
  `"jan_jansen_salaris.py"`) OF een onbegrensde cijferreeks uit de `fabricated_stat`-regel
  (potentieel een telefoonnummer-achtige reeks, bv. via `"0612345678x faster"`) als los,
  doorzoekbaar veld in applicatielogs terechtkomt, bij het DEFAULT log-niveau (INFO) en dus
  ook in productie (JSON naar stdout via `src/core/logging/loguru_config.py`).

### 5. Functionele beschrijving

- Bij een `ungrounded_file_ref`- of `fabricated_stat`-match wordt alleen het FEIT dat de regel
  triggerde gelogd (`logger.info("hallucination_guard_ungrounded_file_ref")` resp.
  `logger.info("hallucination_guard_fabricated_stat")`), niet de gematchte tekst. De
  RETURN-waarde (`reason_str`, bv. `"ungrounded_file_ref:jan_jansen_salaris.py"` of
  `"fabricated_stat:0612345678x faster"`) blijft ONGEWIJZIGD -- de aanroeper (`SanityOfficer`)
  heeft die nodig en redigeert zelf al tot een categorie voordat het de ADR-019-hashketen
  ingaat (BE-AGT-054).
- De resterende regel (`absolute_claim`) logt nog steeds zijn match (`matched=...`) -- bewust
  ongewijzigd, want die matcht een echt gesloten, vaste woordenlijst zonder cijfer- of
  vrije-tekstcomponent en kan daardoor geen persoonsgegeven zijn.

### 6. Technische beschrijving

- `logger.info("hallucination_guard_ungrounded_file_ref", file=fname)` ->
  `logger.info("hallucination_guard_ungrounded_file_ref")`. Geen wijziging aan de
  regex-matching of de returnwaarde-opbouw.
- **Correctie na blinde reviewronde 2 (2026-08-20)**: de ronde-1-versie van deze fix liet
  `fabricated_stat` ongewijzigd, met de (onjuist gebleken) aanname dat die regel als geheel een
  gesloten cijferpatroon matcht. Ronde 2 vond dat `_FABRICATED_STATS`' "Nx faster/slower/..."-
  alternatief (`\d+x\s+(?:faster|slower|better|worse|more|less)`) een ONBEGRENSDE cijferreeks
  heeft, in tegenstelling tot de begrensde percentage-tak (`\d{2,3}%`, max 3 cijfers) -- zelf
  nagemeten dat `_FABRICATED_STATS.search("This runs 0612345678x faster than before.")` matcht
  op `"0612345678x faster"`. Fix: `logger.info("hallucination_guard_fabricated_stat",
  matched=stat_match.group(0))` -> `logger.info("hallucination_guard_fabricated_stat")`, zelfde
  behandeling als `ungrounded_file_ref`.
- **Bijvangst tijdens dit werk, apart geregistreerd als OP-171 (niet gefixt)**: bij het
  schrijven van de regressietest voor de `fabricated_stat`-regel bleek een los percentage
  (bv. `"95%"`) de regel NIET te triggeren -- rechtstreeks nagemeten met een geisoleerde
  regex-aanroep (`_FABRICATED_STATS.search("This is 95% faster than the old version.")` ->
  `None`), niet aangenomen. Oorzaak: de gedeelde sluitende `\b` aan het einde van
  `r"\b(\d{2,3}%|\d+x\s+(?:faster|slower|better|worse|more|less))\b"` vereist een woordkarakter
  aan minstens een kant van de grens; een `%` gevolgd door een spatie of leesteken (elk
  natuurlijk zinseinde) voldoet daar nooit aan. Ongerelateerd aan PII/redactie (dit is een
  betrouwbaarheidsgat van de guard, geen lek) en dus bewust NIET meegenomen in deze fix -- een
  regex-wijziging in een safety-guard is een eigen correctheidsrisico en verdient een eigen
  meting. Vastgelegd met `xfail(strict=True)` in hetzelfde testbestand.

### 7. Zichtbaarheids- en toegangsregels

- Geen wijziging.

### 8-16. n.v.t

### 17. Acceptatiecriteria

- `test_the_matched_filename_is_not_logged_as_a_field`: de bestandsnaam staat niet in de
  gerenderde `logger.info`-aanroep.
- `test_fabricated_stat_matches_are_not_logged_as_a_field`: de onbegrensde cijferreeks staat
  niet in de gerenderde `logger.info`-aanroep (ronde 2).
- `test_absolute_claim_matches_still_log_the_matched_word`: regressie -- de enige ongewijzigde
  regel logt zijn match nog steeds.
- `test_a_bare_percentage_triggers_the_fabricated_stat_rule` (OP-171): `xfail(strict=True)`,
  asserteert het GEWENSTE gedrag.
- Mutatiebewijs, beide richtingen, zelf uitgevoerd (backup/restore via `cp` +
  `git diff --stat`), voor BEIDE fixes:
  - Het `file=`-veld teruginzetten: `test_the_matched_filename_is_not_logged_as_a_field` rood
    (1 failed).
  - Het `matched=`-argument teruginzetten op de `fabricated_stat`-log-aanroep:
    `test_fabricated_stat_matches_are_not_logged_as_a_field` rood (1 failed).
  - `_FABRICATED_STATS` herschrijven naar `r"\b(?:\d{2,3}%|\d+x\s+(?:faster|slower|better|worse|
    more|less)\b)"` (zodat de losse-percentage-tak geen gedeelde sluitende `\b` meer heeft):
    `test_a_bare_percentage_triggers_the_fabricated_stat_rule` geeft `XPASS(strict)`, gerapporteerd
    als failure -- bewijst dat de OP-171-guard niet hol is.
- `python -m pytest tests/unit/learning/safety/test_hallucination_guard_does_not_log_the_matched_filename.py -v`
  -> 3 passed, 1 xfailed (aantal ongewijzigd t.o.v. ronde 1 -- een bestaande test kreeg een
  omgedraaide assertie, geen nieuwe testfunctie).

### 18. Integratoruitleg

- Geen publieke API-wijziging. Interne consumenten van `HallucinationGuard.check()`'s
  returnwaarde zien geen verschil -- alleen het logrecord verliest een veld.

### 19. Trainingssamenvatting

- **Actor:** `HallucinationGuard.check()`, aangeroepen vanuit de Digital Twin-suggestiecontrole.
- **Voorwaarde:** een suggestie bevat een bestandsnaam-vorm of een "Nx faster/slower/..."-vorm
  die niet voorkomt in resp. onbegrensd cijfers heeft t.o.v. de meegegeven context.
- **Actie:** de `ungrounded_file_ref`- of `fabricated_stat`-regel matcht en logt dat feit.
- **Systeemreactie:** `logger.info(...)` zonder extra velden; de functie retourneert
  `(False, reason_str)` zoals voorheen, met de match nog in `reason_str`.
- **Succesrespons:** de suggestie wordt geblokkeerd zoals bedoeld, zonder dat de gematchte tekst
  als doorzoekbaar logveld in productie-logs verschijnt.
- **Foutrespons:** n.v.t. -- geen nieuw faalpad.
- **Uitzonderingen:** de resterende detectieregel (`absolute_claim`) logt zijn match onveranderd,
  want die kan geen persoonsgegeven zijn (echt gesloten woordenlijst).

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

Geen publieke API-wijziging. Interne consumenten van `CouncilDecisionRow` die de rij
rechtstreeks uitlezen (geen response-model) zien vanaf nu een HMAC-digest in het
`message`-veld in plaats van de oorspronkelijke tekst. Dit raakt geen bekend response-schema
(zelf gecontroleerd: `message` komt in geen enkel Pydantic-responsemodel voor).

---

## Open aannames

- Dat de drie geidentificeerde lezers van `row.message`/`decision.message` specifiek
  (`chain_verifier.py`, `report_generator.py`, `forensics.py`) de volledige verzameling zijn --
  zelf gegrept over alle 16 bestanden die `CouncilDecisionRow` aanraken, geen vierde lezer van
  DIE rij gevonden. *(Precisering na doc-review, 2026-08-20: een kale grep op elke
  `.message`-attribuuttoegang vindt ook `copilot/api/turn_endpoint.py`'s `payload.message` --
  dat is het INKOMENDE gebruikersbericht, een ander object, en dus terecht buiten
  beschouwing; de conclusie hierboven bleef bij een bredere check overeind.)* Een toekomstige
  lezer die `row.message` voor menselijke weergave zou willen gebruiken, moet expliciet
  besluiten of dat een nieuwe OP-38-achtige afweging vereist.

## Open vragen

- Wanneer OP-38's resterende scope (`reasoning`/`explanation_for_user`) en OP-49
  (`action_type`) als eigen vervolgproject worden ingepland -- expliciet buiten scope van deze
  sprint, aan Rakesh om te plannen.
- Wanneer OP-170 (`forensics.py`'s model_id/model_version-gat) wordt opgepakt -- apart, klein,
  geen bekend productierisico (admin-CLI-tool, geen live oppervlak).
- Wanneer OP-171 (`_FABRICATED_STATS`' losse-percentage-regex) wordt opgepakt -- apart, klein,
  betrouwbaarheidsgat in een reeds-conservatieve heuristiek, geen bekend PII-risico.

## Risico's

- Geen CRITICAL/HIGH. Dit is een redactie-uitbreiding volgens een al bewezen patroon
  (`action_params`/OP-33), met een eigen primitief (`value_digest`) dat al elders in productie
  gebruikt wordt (OP-78). Gate 2 (code-reviewer + security-reviewer) gaven beiden
  CHANGES_REQUESTED in de eerste ronde -- alle bevindingen (stale comments, ontbrekende
  docstring-vermelding, OP-38/OP-49-reconciliatie, golden-vector-gat, sanity_officer-lek,
  forensics.py-drift) zijn in dezelfde sessie verwerkt, geen enkele naar een tweede Gate-2-ronde
  doorgeschoven zonder fix.
- Zelf-gevonden implementatiefout (row-insert bleef op de rauwe waarde staan) is gevonden door
  de EIGEN testset te draaien voor commit, niet door een externe review -- bewijst dat de
  mutatietest-discipline van dit project ook de eigen fouten vangt, niet alleen bevindingen van
  anderen.
- BE-AGT-055 (hallucination_guard.py-logfix) kwam uit de verplichte blinde eindreview (ronde 1),
  niet uit Gate 2 -- bevestigt de waarde van die extra, contextloze reviewronde. OP-171 is op
  zijn beurt een bijvangst VAN die bijvangst, zelf gevonden tijdens het schrijven van de
  regressietest, niet door de reviewer.

## QA-checks

```
python -m pytest tests/unit/copilot/test_council_persist_leaks_nothing.py -v --timeout=60
-> 18 passed (was 12, +6)
python -m pytest tests/unit/copilot/council/test_sanity_officer.py -v --timeout=60
-> 5 passed (ongewijzigd aantal, 1 bestaande test uitgebreid)
python -m pytest tests/architecture/test_forensics_reconstructs_the_same_shape_as_persist.py -v --timeout=60
-> 1 xfailed (OP-170, bewust)
python -m pytest tests/unit/learning/safety/test_hallucination_guard_does_not_log_the_matched_filename.py -v --timeout=60
-> 3 passed, 1 xfailed (OP-171, bewust)
python -m pytest tests/architecture/test_adr036_register_is_parseable.py -q --timeout=60
-> 6 passed
python -m pytest tests/unit/learning/safety/ tests/unit/copilot/ tests/architecture/test_adr036_register_is_parseable.py tests/architecture/test_forensics_reconstructs_the_same_shape_as_persist.py -q --timeout=60
-> 631 passed, 2 xfailed
python -m pyright
-> 0 errors, 54 warnings (ongewijzigd)
python -m pyright src/core/learning/safety/hallucination_guard.py tests/unit/learning/safety/test_hallucination_guard_does_not_log_the_matched_filename.py
-> 0 errors, 0 warnings
ruff check <gewijzigde bestanden>
-> All checks passed!
python scripts/validate_feature_docs.py
-> (in te vullen na dit document)
```

## Definition of Done

- [x] Rode tests geschreven voor implementatie
- [x] Gate 2 (code-reviewer + security-reviewer): beide CHANGES_REQUESTED in ronde 1, alle
      bevindingen verwerkt in dezelfde sessie
- [x] Implementatie voltooid, inclusief bijvangst-fixes (sanity_officer.py) en registratie van
      niet-gefixte bijvangst (forensics.py/OP-170)
- [x] Mutatiebewijs in beide richtingen voor elke wijziging, inclusief de eigen
      architecture-test (die zelf een AST-bug bevatte, gevonden en gefixt voor commit)
- [x] Golden vector bijgewerkt met expliciete, gedocumenteerde reden (geen stille wijziging)
- [x] ADR-036-register bijgewerkt: OP-38 deels gesloten + aanvulling, OP-170 nieuw, OP-171 nieuw
- [x] BE-AGT-055 (verplichte blinde review ronde 1-bevinding) gefixt en mutatiegetest in beide
      richtingen, inclusief de OP-171-bijvangst die daarbij aan het licht kwam
- [x] Volledige targeted-regressiesuite groen (631 passed, 2 xfailed, 0 failed)
- [x] Doc-gate (`validate_feature_docs.py`) groen (683/708, geen nieuwe incomplete IDs)
- [x] ID-REGISTRY bijgewerkt (BE-AGT-055-rij, teller 055->056)
- [x] Commit (`e2fd04ba`) + final-approver-brief + verplichte blinde review ronde 2 (GO WITH
      MINOR ISSUES, 3 bevindingen, alle verwerkt -- zie review-BE-AGT-053.md sectie I)
