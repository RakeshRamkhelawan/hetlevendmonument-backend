STATUS: APPROVED WITH NOTES

# Review BE-WFL-008 -- agentstap dag 2 (het scherm)

| | |
|---|---|
| **Feature** | BE-WFL-008 |
| **Branch** | `iter/agentstap2` |
| **Commits** | `9dc26068`, `7d06619e`, `1f72e4c3`, `c5811344`, `0cc9514c` |
| **Datum** | 2026-10-25 |
| **Eindoordeel** | APPROVED WITH NOTES -- geen open CRITICAL of HIGH |

---

## 1. Verloop

Gate 2 in twee rondes, read-only reviewers (niets gedraaid, alleen gelezen via `git diff` en `git show` op sha).
De eerste poging op de gestagede wijziging gaf geen oordeel: een reviewer in een eigen worktree kan de index van een
andere worktree niet lezen. Daarom is eerst gecommit en is op sha beoordeeld.

**Ronde 1:** security-reviewer, code-reviewer en kwaliteitsreviewer: alle drie CHANGES_REQUESTED.

| Bevinding | Ernst | Afhandeling |
|---|---|---|
| `reden` toonde de ruwe `str(e)` van de engine (adres met wachtwoord, SQL) | MEDIUM (security) | alleen een reden van een agentstap met `StapMislukt`; al het andere de vaste tekst (`1f72e4c3`) |
| een gekozen agent was niet te wissen bij een lege lijst; de stap kon dan niet worden opgeslagen | BLOCKER (code) | waarschuwing en wisknop ook bij een lege lijst (`c5811344`) |
| `raise ValidationError(str)` (cyclus, losse knoop) gaf een TypeError aan de klant | LOW | `GeneratorValidatieFout`, met tests (`c5811344`) |
| `**node.config` kon de gevalideerde `agent_id` overschrijven | LOW | config eerst, `agent_id` en `instruction` daarna, `instruction` altijd een tekst |
| `result_json["error"]` ongefilterd naar de klant | LOW | pad weggehaald; een mislukte stap zonder klantreden krijgt de vaste tekst |
| `handleExecute` stuurde `instruction` niet altijd mee | LOW | meegestuurd bij elke stap met `agent_id`, terugval op de titel |
| non-ASCII (vinkje, lange streep) | LOW | `(gekozen)`, komma (`c5811344`) |

**Ronde 2:** code-reviewer GO, kwaliteitsreviewer GO. Drie opmerkingen verwerkt in `0cc9514c`: wisknop ook bij een
laadfout, `||` in plaats van `??` bij de opdracht, ASCII in `KoppelingKiezer.tsx`. De security-reviewer is niet opnieuw
gevraagd; zijn enige bevinding is opgelost en met vier mutaties bewezen.

## 2. Open, met naam

- **`uitkomst` en `output_data` zijn voor iedereen met `workflows:read` in het bedrijf zichtbaar**, ook van een uitvoering
  die een ander startte. Productkeuze voor de regie (wie mag welke uitvoering inzien); `output_data` bestond al.
- **`engine.py:1204` doet `instruction.format(**context)` op vrije tekst.** Een opdracht met accolades ("geef {totaal}")
  geeft een `KeyError`; de klant ziet dan de vaste tekst en kan het niet zelf herstellen. Engine, buiten deze dag; naar de
  regie. Niet gemeten: of de uitleesroute `{input_json.x}` bruikbaar is.
- `GET /api/v1/vibe/agents/uitvoerbaar` heeft geen rate limit en geen cache; elke aanroep opent per agent een sessie
  (net als `/agents`).
- Een stap zonder `result_json` toont de technische `task_ref` in plaats van de agentnaam (cosmetisch).
- `KoppelingKiezer.tsx` bevat nog inline stijlen, ruwe hex-kleuren en een `div` met klik; die stonden al in
  `AgentPickerDropdown.tsx`. Eigen opruimtaak.
- De frontend-handleiding (`docs/user-guide/frontend/`) is niet geschreven.

## 3. Eindoordeel

**APPROVED WITH NOTES.** Het scherm biedt alleen agents die echt draaien aan, een stap met een agent heeft altijd een
opdracht en is altijd te wissen, en na het starten staat per stap in het Nederlands wat er gebeurde zonder dat een ruwe
fouttekst bij de medewerker komt. Of de draaiende applicatie dit ook zo laat zien, is door de acceptant beoordeeld; zie de
melding aan de regie.
