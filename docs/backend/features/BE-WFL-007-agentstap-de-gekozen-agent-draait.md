# BE-WFL-007 -- agentstap dag 1: de gekozen agent draait, met alleen de rechten van de starter

| | |
|---|---|
| **ID** | BE-WFL-007 |
| **ADR** | Keten G van de meetlat (agentstap in een eigen workflow, Rakesh 2026-10-23) |
| **Sprint** | pilot december, agentstap dag 1 (backend; dag 2 is het scherm) |
| **Branch** | `iter/agentstap2` |
| **Commits** | `b291443e`, `f647f7bb`, `86a4641e` |
| **Datum** | 2026-10-24 |

---

## 1. Het probleem in een zin

Een agentstap in een eigen workflow kon geen enkele agent starten, en de router negeerde bovendien welke agent de
klant koos.

## 2. Wat er gemeten was (2026-10-23, vooraf)

Live: "Agent executor_agent_001 not found in process". De router zocht een agent via een methode die niet bestaat
(`_resolve_agent`), en de keuze van de klant stond alleen als metadata.

## 3. Wat er veranderd is

- **De gekozen agent draait.** `ProductionAgentRuntime.run_agentstap` (nieuw, `src/core/workflow/providers.py`) roept
  `src/core/als/agents/workflow_stap.py` aan: de agent komt uit de ALS-catalogus (`get_agent_instance`), zonder
  router-keuze en zonder nieuwe fabriek. De engine (`_execute_agent_task`) geeft de starter (`execution.initiated_by`)
  en de klant van de uitvoering mee; de klant komt nooit uit de stapdefinitie of de invoer.
- **Kiesbaar = uitvoerbaar.** Alleen de bedrade vier (`UITVOERBARE_AGENT_SLEUTELS` in `packs.py`: skillsgaptraining,
  dunning, receiptscanner, vatcompliance) EN met een echte skill. De brief noemde `implemented_agent_keys()` (zo'n 135
  agents), maar daarvan heeft maar vier een uitvoerpad dat de starter meegeeft; de rest voert via het OODA-pad bewust
  geen tool uit. Een andere agent: de stap faalt met "deze agent kan nog niet in een workflow draaien".
  De lijst voor de bouwer: `GET /api/v1/vibe/agents/uitvoerbaar`, gefilterd op de pakketschakelaar van de klant.
- **Alleen de rechten van de starter.** Elke tool gaat VOOR de Council door `starter_heeft_toolrecht` (hook
  `_weiger_zonder_toolrecht_van_de_starter` in `specialist_base`), dan Council, HITL-vloer en broker met het profiel van
  de agent. Een HITL-tool wordt een ticket in `/hitl`; de stap meldt dat eerlijk als niet-uitgevoerd. Agents die
  geen tool uitvoeren maar zelf gegevens lezen (receiptscanner, vatcompliance) krijgen het leesrecht `receipts:read`
  (`EIGEN_LEESRECHT`, `rbac_service.user_has_resource_right`); de telling van dunning vraagt `list_receivables`.
- **De pakketschakelaar geldt ook hier** (`tenant_pack_activations`, zoals `PACK_NOT_ENABLED`); `dunning` is een eigen
  klantfunctie en valt er buiten, net als bij de debiteurenroute.
- **Foutteksten:** een ruwe uitzondering of toolfout komt niet in de stapuitvoer; een vaste Nederlandse reden, het detail
  staat in het log.

## 4. Bewijs

| Wat | Hoe gezien |
|---|---|
| een editor start een agentstap en de gekozen agent draait; een andere agent draait die, niet een vaste | `tests/integration/test_agentstap_de_gekozen_agent_draait.py` op een verse keten onder de applicatierol, met rollen uit de zaaier |
| een gebruiker zonder het recht voor de tool wordt geweigerd met reden, geen ticket | idem |
| een HITL-tool met recht wordt een ticket; een starter van een andere klant krijgt niets | idem |
| niet-uitvoerbare agent, niet-numerieke starter, geen klant, pakket uit: Nederlandse reden | idem |
| elke uitvoerbare agent wordt getoetst (via `act()` of een eigen leesrecht) | `tests/unit/als/test_agentstap_elke_uitvoerbare_agent_wordt_getoetst.py`, met mutatie |
| de architectuurtest van f408e2f6 blijft groen omdat de toets er IS | `tests/architecture/test_agentstap_en_taalmodelstap_voeren_geen_tool_uit_zonder_startertoets.py` |
| mutatiebewijs per onderdeel | docstring van het integratietestbestand (alle mutaties betrapt; een niet-betrapte gaf een extra test) |

## 5. Wat niet gemeten is

- De bouwer (frontend) gebruikt de nieuwe lijst nog niet: dat is dag 2. `GET /agents` en de AI-generator bieden nog
  databaseagents en ActivePieces-stukken aan; "kiesbaar = uitvoerbaar" is dus voor het scherm nog niet af.
- Een geplande workflow (starter is geen gebruikers-id) met een agentstap draait niet: fail-closed, bewust.
- Een agentstap die een ticket aanmaakt eindigt als `StapMislukt` ("wacht op goedkeuring"), niet als "gelukt, wacht":
  eerlijk, maar af te stemmen met de meetlat Keten G.
- De RLS-policy van `tenant_pack_activations` (het expliciete tenantfilter dekt het wel).
- Het live scenario in de draaiende applicatie (beeld) volgt bij dag 2.

## Trainingssamenvatting

**Actor:** een medewerker (rol `editor`) die een eigen workflow met een agentstap start.

**Voorwaarde:** het pakket van de gekozen agent staat voor het bedrijf aan (behalve de debiteurenagent), en de
medewerker heeft de rechten die de tools van die agent vragen.

**Actie:** de workflow starten met een agentstap op een agent uit de lijst `/api/v1/vibe/agents/uitvoerbaar`.

**Systeemreactie:** de gekozen agent draait voor het bedrijf van de uitvoering; elke tool wordt getoetst op het recht van
de medewerker; een tool die om goedkeuring vraagt wordt een goedkeuringsticket.

**Succes:** de stap geeft de uitkomst van die agent terug, voor die klant en binnen de rechten van de starter.

**Fout:** een agent die nog niet in een workflow kan draaien, een pakket dat uit staat, een ontbrekend recht of een
tool die goedkeuring vraagt geeft een stap die mislukt met een Nederlandse reden.

**Uitzonderingen:** een geplande workflow zonder bekende gebruiker start geen agentstap.
