# BE-WFL-008 -- agentstap dag 2: het scherm biedt alleen agents die echt draaien

| | |
|---|---|
| **ID** | BE-WFL-008 |
| **ADR** | Keten G van de meetlat (agentstap in een eigen workflow, Rakesh 2026-10-23) |
| **Sprint** | pilot december, agentstap dag 2 (het scherm; dag 1 is BE-WFL-007) |
| **Branch** | `iter/agentstap2` |
| **Commits** | `9dc26068`, `7d06619e`, `1f72e4c3` |
| **Datum** | 2026-10-25 |

---

## 1. Het probleem in een zin

Het workflowscherm liet een medewerker geen AI-agent kiezen die een stap echt kan uitvoeren: de enige "agent"-kiezer
koos een ActivePieces-koppeling, en de AI-generator bood agents aan die niet draaien.

## 2. Wat er gemeten was (taak 0, 2026-10-25)

De component die in het scherm een "agent" liet kiezen was `AgentPickerDropdown` (nu `KoppelingKiezer`), gebruikt in
`NodeInspectorPanel`, bereikbaar via `/studio` -> `FocusModeBuilderPage` -> `FocusModeBuilderEnhanced`. Die keuze
(`node.data.agent`) is een ActivePieces-koppeling, geen AI-agent. De uitvoerknop (`handleExecute`) stuurde
`node.data.agent` als `agent_id`, zonder `instruction`.

## 3. Wat er veranderd is

- **De kiezer.** `AgentStapKiezer` toont PRECIES de lijst van `GET /api/v1/vibe/agents/uitvoerbaar`, met Nederlandse naam
  en omschrijving (`AGENT_BESCHRIJVING` in `workflow_stap.py`). Een lege lijst toont de Nederlandse uitleg
  (`GEEN_AGENTS_UITLEG`): vraag de beheerder het pakket aan te zetten. Een gekozen agent die niet (meer) in de lijst staat
  krijgt een waarschuwing.
- **De opdracht.** Bij een gekozen agent verschijnt "Opdracht voor de agent" (`data.instruction`); zonder opdracht meldt
  de controle "Geef de AI-agent een opdracht.". `handleExecute` stuurt `agent_id` en `instruction` mee.
- **Koppelingen apart.** `AgentPickerDropdown` heet nu `KoppelingKiezer` en het veld "Koppeling (ActivePieces)".
- **De generator.** De AI-generator biedt alleen de uitvoerbare agents aan; zonder enige uitvoerbare agent wordt het
  taalmodel niet gebeld en leest de klant wat de beheerder moet aanzetten. Een voorstel met een andere agent geeft een
  Nederlandse melding in plaats van stil overgenomen te worden.
- **Uitkomst terugkijken.** `GET /api/v1/workflows/executions/{id}` levert `stappen`: per stap naam, Nederlandse status,
  uitkomst en reden (`src/core/workflow/stap_overzicht.py`). De uitvoeringsmonitor toont dit onder "Wat er per stap
  gebeurde". Een reden verschijnt alleen als hij voor de klant is gemaakt (agentstap met `StapMislukt`); al het andere
  krijgt een vaste tekst, het detail blijft in het log (Gate 2 security, bevinding 1).

## 4. Bewijs

| Wat | Hoe gezien |
|---|---|
| lijst, uitleg bij leeg, generator alleen uitvoerbaar | `tests/unit/api/test_workflowgenerator_alleen_uitvoerbare_agents.py` |
| elke uitvoerbare agent heeft een Nederlandse beschrijving | `tests/unit/als/test_uitvoerbare_agents_hebben_een_nederlandse_naam.py` |
| stappen per uitvoering, tenant- en uitvoeringsfilter | `tests/unit/api/test_uitvoeringsstatus_toont_de_stappen.py` |
| Nederlandse regel, geen ruwe fouttekst | `tests/unit/workflow/test_uitkomst_per_stap_in_het_nederlands.py` |
| kiezer, inspector, monitor | `AgentStapKiezer.test.tsx`, `NodeInspectorPanel.test.tsx`, `ExecutionMonitor.test.tsx` |
| mutatiebewijs per onderdeel | 8 backendmutaties en 12 frontendmutaties allemaal rood (een mutatie op een commentaarregel viel eerst groen, herhaald op de echte aanroep: rood); 4 mutaties op het redenfilter rood |

## 5. Wat niet gemeten is

- De uitvoeringsmonitor en de inspector draaien in de draaiende applicatie: beeld door de acceptant, zie de melding.
- Een Gate-2-bevinding blijft open met naam: `uitkomst` en `output_data` zijn voor iedereen met `workflows:read` in het
  bedrijf zichtbaar (niet per medewerker afgeschermd); productkeuze voor de regie.
- `GET /agents/uitvoerbaar` heeft geen rate limit, net als `/agents`.
- De vijfstaps frontend-documentatie (gebruikershandleiding in `docs/user-guide/frontend/`) is niet geschreven.

## Trainingssamenvatting

**Actor:** een medewerker (rol `editor`) die in de workflowbouwer een stap door een AI-agent laat uitvoeren.

**Voorwaarde:** het pakket van de agent staat voor het bedrijf aan.

**Actie:** een stap openen, een AI-agent kiezen uit de lijst, een opdracht typen, de workflow starten.

**Systeemreactie:** de lijst toont alleen agents die echt draaien; na het starten toont de monitor per stap wat de agent deed.

**Succes:** per stap staat "Uitgevoerd" met de uitkomst.

**Fout:** is er geen agent beschikbaar, dan staat er wat de beheerder moet aanzetten; een geweigerde stap toont een
Nederlandse reden of de vaste tekst "de stap is mislukt; vraag uw beheerder om het na te kijken".

**Uitzonderingen:** een stap zonder opdracht kan niet worden opgeslagen.
