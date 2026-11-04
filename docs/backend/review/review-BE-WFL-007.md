STATUS: APPROVED WITH NOTES

# Review BE-WFL-007 -- agentstap dag 1

| | |
|---|---|
| **Feature** | BE-WFL-007 |
| **Branch** | `iter/agentstap2` |
| **Commits** | `b291443e`, `f647f7bb`, `86a4641e` |
| **Datum** | 2026-10-24 |
| **Eindoordeel** | APPROVED WITH NOTES -- geen open CRITICAL of HIGH |

---

## 1. Verloop

Gate 2 in twee rondes, elk met een security-reviewer en een code-reviewer (read-only, niets gedraaid).

**Ronde 1: beide CHANGES_REQUESTED.** Bevindingen en afhandeling:

| Bevinding | Ernst | Afhandeling |
|---|---|---|
| `receiptscanner` en `vatcompliance` lezen gegevens zonder tool en omzeilden de startertoets | MEDIUM | `EIGEN_LEESRECHT` (`receipts:read`), guard-test dat elke uitvoerbare agent getoetst wordt |
| `_prepare_tool_params` (leest de debiteur) stond voor de startertoets; de telling van dunning ook | LOW | toets staat nu eerst; telling alleen met `list_receivables` |
| ruwe uitzonderingstekst in de stapuitvoer | LOW | vaste Nederlandse reden, detail in het log |
| de agentlijst voor de bouwer was niet dezelfde als de uitvoerbare lijst | HIGH (code-review) | nieuwe route `/api/v1/vibe/agents/uitvoerbaar` |
| catalogus per stap herladen, alle skills geimporteerd | LOW | een keer geladen, per sleutel gecontroleerd |
| ontbrekende tests en mutatiebewijs in de docstring | MEDIUM | 13 extra tests; mutatielijst in de docstring |
| de pakketschakelaar gold niet in een workflowstap (gevonden door `test_pakketagent_heeft_een_bekende_aanroeper.py`) | MEDIUM | `_pakket_staat_aan`; `dunning` is een eigen klantfunctie |

**Ronde 2: beide GO.** Opmerkingen verwerkt: een databasefout in de controle of een storing in de agent geeft een vaste
reden (geen ruwe tekst); de lijst voor de bouwer is gefilterd op de pakketschakelaar.

## 2. Open, met naam

- De bouwer (frontend) gebruikt de nieuwe lijst nog niet (dag 2); `GET /agents` en de AI-generator bieden nog agents aan die
  een workflowstap niet kan draaien.
- De pakketroute eist `packs:execute`, de agentstap niet; de bereikbare gegevens blijven begrensd door `receipts:read`
  en de rechten per tool. Bewust vastgelegd als ontwerpkeuze, niet als lek.
- Een ticket (HITL) laat de stap mislukken met "wacht op goedkeuring"; af te stemmen met de meetlat Keten G.
- RLS-policy van `tenant_pack_activations`, een externe planner en het live beeld zijn niet nagegaan.

## 3. Eindoordeel

**APPROVED WITH NOTES.** De gekozen agent draait voor de klant van de uitvoering, elke tool en elke gegevensstap gaat
door het recht van de starter, en de pakketschakelaar blijft een echt slot. Het enige dat ontbreekt om "kiesbaar =
uitvoerbaar" voor de klant af te maken is het scherm van dag 2.
