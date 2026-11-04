# Review: BE-AGT-037 — Evaluatieset skillsgaptraining (Fase B / Fase 1 / dag 1)

| Veld | Waarde |
| --- | --- |
| Spec | `docs/backend/features/BE-AGT-037-skillsgaptraining-evaluatieset.md` |
| Reviewer | Fresh-eyes zelfreview (subagents niet toegestaan in deze sessie; gemeld aan Rakesh) |
| Datum | 2026-08-01 |
| Uitkomst | **APPROVED** |

---

## Controle tegen de code (geen aannames)

| Claim in spec | Verificatie | Oordeel |
| --- | --- | --- |
| Harnas roept de skill echt aan | `execute_with_manifest_prompt` (skillsgaptraining.py:33-55) doet een echte `generate()` en daarna `act()`; `_execute_step` resolveert via de catalog (Fase A dag 5) | Correct |
| `allowed_tools` = 5 tools | Manifest gelezen: query_hr_database, search_documents, generate_text, send_notification, schedule_training | Correct |
| Fail-closed filter zit voor de broker | `_parse_tool_calls` (specialist_base.py:208-215) slaat tools buiten `allowed_tools` over met een warning; de broker wordt niet bereikt | Correct |
| Ongeldige JSON wordt overgeslagen | idem regels 197-206, `continue` na `JSONDecodeError` | Correct -- taak R1 dekt dit |
| Tekstantwoord blijft behouden zonder tools | `act()` regels 230-243: `result_data={"output": decision, "tool_calls": 0}` | Correct |
| Dispatch draagt skill-identiteit en tenant | `act()` regels 250-256: `agent_id=self.agent_id`, `context={"tenant_id": self.tenant_id}` | Correct |
| Geen bestaande evaluatieset | Grep op `skillsgaptraining` in `tests/`: 4 bestanden, alle permissie- of orchestrator-gericht, geen gedragsmeetlat | Correct -- geen dubbele meetlat |

## Bevindingen

Geen CRITICAL, geen HIGH.

**Opmerking bij "alles direct groen" (belangrijkste review-punt):**
Alle 21 tests waren bij eerste run groen. Op zichzelf is dat zwak bewijs -- een test die
niets kan vangen is ook groen. Daarom is de set mutatie-getest voordat hij is
gecommit: drie gerichte mutaties (fail-closed filter uitschakelen, TOOL_CALL-contract
slopen, "Never invent data" verwijderen) maken respectievelijk 2, 1 en 1 taak rood, en na
herstel staat de set weer op 21. Daarmee is aangetoond dat de meetlat de eigenschappen
bewaakt die hij claimt te bewaken. Het manifest is byte-exact hersteld (`git status`
schoon, geverifieerd).

MINOR (bewuste keuzes, geen actie):
- R1 (ongeldige JSON) staat in categorie TOOL_DENY hoewel het strikt genomen robuustheid
  is en geen weigering. Bewust: de verwachte uitkomst is identiek (0 dispatches) en een
  vijfde categorie met een enkele taak voegt niets toe.
- De set mockt de LLM. Een echte-LLM-variant zou nondeterministisch zijn en het model
  meten in plaats van het harnas; dat hoort bij een aparte, handmatige evaluatie.

## Kwaliteitspoorten

- ruff: clean.
- ASCII: geen non-ASCII in het testbestand.
- Tenant-isolatie: expliciet getoetst -- elke dispatch moet `tenant_id` in de context
  hebben; de set draait onder tenant 42 (niet 1) zodat een hardcoded 1 zou opvallen.
- Security: de set voegt geen productiecode toe en verruimt niets. Twee taken bewaken
  juist de fail-closed toolfilter.
- Regressie: geen bestaande test aangepast; puur additief.

## Restpunt

De set dekt bewust geen loop-limieten (stappen/tijd/Prana) en geen Council-poort -- die
bestaan nog niet (Fase 2, D10 stap 5-6). Bij het bouwen daarvan hoort de set uitgebreid te
worden, anders meet hij straks een deel van het harnas niet meer.
