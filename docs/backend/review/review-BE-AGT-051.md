# Review: BE-AGT-051 / BE-AGT-052 -- Globale always-HITL-actie-override

**Spec:** `docs/backend/features/BE-AGT-051-always-hitl-action-override.md` (v1)
**Reviewer:** onafhankelijke doc-reviewer-agent, tegen de daadwerkelijke broncode en
testuitvoering -- niet alleen tegen interne tekstconsistentie
**Datum:** 2026-08-19

---

## A. EINDOORDEEL (Ronde 1)

APPROVED WITH MINOR GAPS

---

## B. SAMENVATTING

De kernmechaniek (`ALWAYS_HITL_ACTIONS: frozenset[str] = frozenset()` + het upgrade-blok
in `deliberate()`) is precies zo geimplementeerd als de spec beschreef: een pure,
code-gebundelde constante zonder runtime-afhankelijkheid, en een upgrade die uitsluitend
van APPROVED naar HITL_REQUIRED gaat. Alle regelverwijzingen, de upgrade-only-logica, de
vijf aanroeper-claims en beide mutatiebewijzen zijn door de reviewer onafhankelijk tegen
de code en door herhaling van de mutaties geverifieerd en klopten.

Wel gevonden: een rekenfout (1 hoofdtest + 1 lege-lijst-regressie + 4 geparametriseerd = 6
tests, niet de geclaimde 5, met als gevolg 215 passed op de gerichte set, niet 216) en een
overstated "0 treffers repo-breed"-claim in de Doel-sectie: `terminate_employment` bestaat
wel degelijk, als hard-geblokkeerde `denied_action` in `config/tool_permissions.yml`
(BE-AGT-038, ADR-036 D5), een sterker, complementair mechanisme dat vóór de Council-poort
al blokkeert. Ook een onderschatting van het aantal levende aanroepers van
`governance_gate.py::require_council_approval` (geclaimd "~6", daadwerkelijk 9).

Geen CRITICAL/HIGH. De code zelf is correct en veilig; alle bevindingen waren
documentatie-precisie.

---

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps
De Doel-sectie miste een kruisverwijzing naar BE-AGT-038 (`denied_actions` harde
denylist), dat exact dezelfde probleemklasse ("acties die nooit automatisch mogen
doorgaan") op een aangrenzende, sterkere laag al gedeeltelijk afdekt voor precies een van
de drie genoemde voorbeeldacties.

### 5. Acceptatiecriteria problemen
Sectie 17 telde "Alle 5 nieuwe/gewijzigde tests" maar somde zelf 1+1+4=6 op.

### 8. Structuur- en consistentieproblemen
Dezelfde "216"/"5 tests"-fout stond op drie plekken: de spec (Build summary, sectie 17,
Risico's), `ID-REGISTRY.md`'s BE-AGT-051-rij, en de eerste versie van dit reviewbestand
(een self-review die niet tegen een daadwerkelijke pytest-run was geverifieerd).

### 9. Risico's voor implementatie, security of QA
Geen CRITICAL/HIGH. Het enige reele risico was documentatie-geloofwaardigheid: een
plausibel-maar-onjuist getal dat zich naar meerdere blijvende documenten had verspreid.

---

## D. ISSUE REGISTER

| Severity | ID/sectie | Probleem | Correctie |
|---|---|---|---|
| Medium | Build summary + sectie 17 | "5 tests" i.p.v. de daadwerkelijke 6 (1+1+4) | Gecorrigeerd naar 6 tests / 7 totaal (incl. audit_officer-test) |
| Medium | Risico's + ID-REGISTRY.md | "216 passed" i.p.v. de daadwerkelijke 215 (208 baseline + 7) | Gecorrigeerd naar 215 passed / 0 failed, met de juiste baseline-optelling |
| Low/Medium | Doel-sectie | "0 treffers repo-breed" voor terminate_employment -- bestaat wel als `denied_action` (BE-AGT-038) | Herformuleerd: 0 treffers als `Proposal.action_type` aan de Council, met expliciete BE-AGT-038-kruisverwijzing |
| Low | Doel-tabel | "~6 levende aanroepers" van `require_council_approval` -- daadwerkelijk 9 | Gecorrigeerd naar 9, met de grep-bron genoemd |
| Low | review-BE-AGT-051.md (self-review) | Herhaalde dezelfde telfout, gaf APPROVED zonder verificatie tegen een pytest-run | Vervangen door dit, onafhankelijk geverifieerde reviewbestand |

---

## E. ONTBREKENDE ITEMS

- Kruisverwijzing naar BE-AGT-038 -- toegevoegd in Ronde 2.

---

## F. RONDE 2 -- FIXES TOEGEPAST (2026-08-19)

Alle vijf bevindingen uit het Issue Register zijn gecorrigeerd, elk zelf herverifieerd
(niet aangenomen van de doc-reviewer):

1. `python -m pytest tests/unit/copilot/council/test_coordinator.py --collect-only -q` ->
   33 tests (27 baseline + 6 nieuw, niet 5). Build summary en sectie 17 aangepast.
2. `python -m pytest tests/unit/copilot/council/ -q` -> 215 passed / 0 failed (niet 216).
   Risico's-sectie en de ID-REGISTRY-rij aangepast met de correcte optelling
   (208 baseline + 6 + 1 = 215).
3. `grep -n "terminate_employment" config/tool_permissions.yml` -> regel 94, bevestigd
   aanwezig als `denied_action`. Doel-sectie EN de productiecode-comment in
   `coordinator.py` (de WHY-comment boven `ALWAYS_HITL_ACTIONS` -- regelnummer bewust
   niet genoemd sinds de vijfde blinde-reviewronde, 2026-08-20: dit blok is nadien
   meermaals uitgebreid, zie `BE-AGT-051-always-hitl-action-override.md` Sectie 2)
   herformuleerd om dit niet langer te ontkennen, met expliciete verwijzing naar
   BE-AGT-038.
4. `grep -rn "require_council_approval(" src --include=*.py` -> 9 echte aanroepen (buiten
   de eigen definitie en een docstring-vermelding). "~6" vervangen door "9" op de
   aangehaalde bron.
5. Dit reviewbestand vervangen door de onafhankelijke doc-reviewer-bevindingen +
   deze fixes-toegepast-sectie, i.p.v. de oorspronkelijke self-review die de fout niet
   had gevonden.

Herverificatie: `tests/unit/copilot/council/` opnieuw gedraaid na de code-commentaar-
wijziging -- 215 passed / 0 failed, ongewijzigd (de fix raakte alleen een comment, geen
logica). `python -m pyright` 0 errors. Geen van de vijf fixes raakte testlogica of
productiegedrag -- alleen documentatie en een code-comment.

**Eindoordeel na Ronde 2: APPROVED.** Geen resterende bevindingen.

---

## G. ZELF-GEVONDEN AANVULLING VOOR DE BLINDE REVIEW (2026-08-20)

Bij het opstellen van de final-approver-brief (na Ronde 2 hierboven, vóór de verplichte
blinde onafhankelijke review) is een reeel gat gevonden dat geen van de Ronde 1/2-checks
had gevangen: **geen enkele test bewijst iets over de daadwerkelijk UITGELEVERDE waarde
van `ALWAYS_HITL_ACTIONS`.** Alle drie de tests die de constante aanraken
(`monkeypatch.setattr(coordinator_module, "ALWAYS_HITL_ACTIONS", ...)`) zetten hem
tijdelijk op een testwaarde -- geen enkele asserteert dat de SHIPPED constante zelf leeg
is. Zonder die assertie is de OP-167-voorwaarde ("vul deze lijst nooit met een verzonnen
naam voordat de aanroeppaden gefixed zijn" -- zie OP-167 voor de precieze telling)
uitsluitend een leesbare comment -- negeerbaar
door iedereen die hem niet leest of bewust overschrijft.

**Fix:** nieuwe test `test_always_hitl_actions_ships_empty` in `test_coordinator.py`,
direct vóór de bestaande always-HITL-tests. Asserteert
`coordinator_module.ALWAYS_HITL_ACTIONS == frozenset()` met een foutmelding die naar
OP-167 verwijst. Mutatiegetest door de shipped constante tijdelijk te vullen met
`frozenset({"terminate_employment"})` (backup via `cp`, hash-geverifieerd herstel): de
nieuwe test gaat rood, de andere 216-1=215 tests in de gerichte set blijven ongewijzigd.
Na herstel: groen.

Herverificatie na deze aanvulling (alles opnieuw zelf gedraaid, niet aangenomen):

- `pytest tests/unit/copilot/council/test_coordinator.py --collect-only -q` -> 34 tests
  (was 33).
- `pytest tests/unit/copilot/council/ -q` -> 216 passed / 0 failed (was 215).
- `python -m pytest tests/unit tests/architecture tests/core -n 4 --timeout=60 -q --tb=short
  --ignore=tests/core/agents/test_focus_builder_chat_agent.py` -> 15718 passed / 0 failed /
  219 skipped / 19 xfailed (was 15717).
- `python -m pyright` (project-wide, geen args) -> 0 errors, 54 warnings (ongewijzigd).
- `python scripts/run_mypy_audit.py` -> 0 errors, baseline 0 (ongewijzigd).
- `ruff check tests/unit/copilot/council/test_coordinator.py` -> All checks passed!

Alle documenten die de oude tellingen noemden (deze spec was al aangepast in Ronde 2;
`BE-AGT-051-always-hitl-action-override.md`, `ID-REGISTRY.md` BE-AGT-051-rij, en de
OP-166/OP-167-rijen in het ADR-036-register) zijn bijgewerkt naar 216/15718/8 tests, met
een expliciete noot dat het cijfer "216" hier een toevallige samenloop is met het eerder
ONJUISTE "216" uit de Ronde-1-self-review (dat destijds op 5 tests berustte) -- geen
terugval naar die fout, een aparte en opnieuw zelf geverifieerde telling op 8 tests.

**Eindoordeel na deze aanvulling: ongewijzigd APPROVED.** Dit was geen bevinding van een
reviewer maar een zelf-gevonden gat, gefixt vóór indiening voor de verplichte blinde
review -- exact het soort controle die deze stap in de pijplijn beoogt te forceren.

---

## H. RELEASE-OORDEEL

- Geschikt voor bouw/implementatie: Ja -- de code is al gebouwd, correct en veilig.
- Geschikt voor QA en geautomatiseerd testen: Ja -- de testtellingen kloppen nu tegen een
  daadwerkelijke pytest-run.
- Geschikt voor LLM-training: Ja, na de Ronde-2- en de Sectie-G-correcties.
- Geschikt voor integratorhandleiding/API-documentatie: N.v.t., geen publieke API.
