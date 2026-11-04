# Backend Feature Specification

## Metadata

- **Feature ID:** BE-API-046
- **Feature naam:** Geen interne foutteksten naar de klant
- **Status:** Gereed op code en meting; Gate 2 (security-reviewer) staat in `docs/backend/review/review-BE-API-046.md`
- **Auteur:** bouwsessie foutteksten2
- **Reviewer:** security-reviewer (subagent, Gate 2)
- **Datum:** 2026-10-22
- **Gerelateerde ticket:** brief `docs/agent-briefs/generated/2026-10-21-sprint-dag-geen-interne-foutteksten-naar-de-klant.md`
- **Gerelateerde module:** 83 bestanden onder `src/` (routers, `*_endpoints.py`, websocketafhandelaars), `src/core/exceptions/exceptions.py` (nieuw: `ValidatieFout`)
- **Gerelateerde database tabellen:** geen (GEEN migratie)
- **Versie:** 1.0

## Doel en scope

### Doel

Een fout van buiten (httpx, database, taalmodel) draagt vaak een intern adres of een queryfragment in zijn tekst. Die tekst kwam via `str(e)`, `repr(e)`, `f"{e}"` of `e.args` in een antwoord naar de klant. Nu gaat er een vaste Nederlandse tekst naar de klant en staan type en details alleen in het logboek.

### Buiten scope

Geen gedragswijziging buiten foutteksten en logregels. Geen migratie. Geen nieuwe registerrij.

## Wat er veranderd is

- Alle plekken die een uitzonderingstekst in een antwoord zetten (HTTPException `detail`, `create_error_response`, JSON-velden, SSE-regels, websocketberichten) geven nu een vaste tekst. Details gaan naar het logboek met `exc_info`.
- Een bewuste validatietekst voor de klant loopt alleen nog via de eigen klasse `ValidatieFout(ValueError)`: gebruikt op de vier plekken waar een test de tekst eist (experiment aanmaken, setup, doel verwijderen, awareness-websocket). Elke andere `ValueError` geeft op een 400-plek "Ongeldig verzoek.".
- Vergelijkingen op `str(e)` voor besturing (`if "already has a mission" in str(e)`) zijn ongemoeid gelaten; die komen niet in een antwoord.

## Guard

`tests/architecture/test_geen_uitzonderingstekst_in_een_antwoord.py` loopt met AST over elke antwoordlaag (modules met `APIRouter(` of een websocket-import) en meldt elke `except`-tak van een vreemde fout waarin de tekst buiten een logkanaal wordt gemaakt. Sleutel van de uitzonderingslijst is `bestand::functie`; de lijst is leeg. Een staleness-test en een reden-per-regel-test horen erbij. Mutatiebewijs staat in de docstring van de guard.

## Trainingssamenvatting

### Een scherm laat een fout zien (elke ingelogde gebruiker)

- **Actor:** een ingelogde gebruiker op een willekeurig scherm.
- **Voorwaarde:** een externe dienst (taalmodel, database, ActivePieces) valt uit of geeft een fout.
- **Actie:** de gebruiker voert een handeling uit die die dienst nodig heeft.
- **Systeemreactie:** een vaste Nederlandse tekst, bijvoorbeeld "Er is een interne fout opgetreden." of "Ongeldig verzoek."; geen adres, query of providertekst.
- **Succes:** niet van toepassing; de fout is duidelijk en lekt niets.
- **Fout:** de vaste tekst met de juiste statuscode; details en soort staan alleen in het logboek.
- **Uitzondering:** een bewuste validatietekst (`ValidatieFout`) blijft zichtbaar, bijvoorbeeld "Cannot delete goal with children".

## Bekende beperkingen (niet gemeten of bewust gelaten)

- Op ongeveer 35 endpoints met een 4xx op een vreemde `ValueError` ziet de klant niet meer WAT er mis was; alleen "Ongeldig verzoek.".
- `src/core/api/v1/agentic/agency_capabilities.py` geeft `result.error_message` van een uitvoering door; dat is veld-uitvoer, geen uitzondering, en niet door de guard gedekt.
- De focus_builder-service logt `str(e)`; dat is een logregel en dus toegestaan.
- Een vergelijking van de tekst met een vaste waarde telt voor de guard als veilig; een lek via een andere variabele dan de uitzonderingsvariabele wordt niet gezien.
- Een eigen uitzonderingsklasse met vreemde fouttekst erin (`raise Eigen(f"..{e}")`, 89 plekken) wordt niet getoetst; zie de review.
- `tool_broker/exceptions.py` zet de originele fouttekst en traceback in een detail; geen bereikbaar pad gemeten.
- Alias (`err = e`) en helperfuncties met de uitzondering als parameter zijn blind voor de guard.

## Vervolg 2026-10-22: eigen validatieteksten weer zichtbaar op de pilotschermen

Brief `docs/agent-briefs/generated/2026-10-22-sprint-dag-validatieteksten-op-pilotschermen.md`. BE-API-046 maakte van elke 4xx op een `ValueError` een vaste tekst; op de pilotschermen was dat te veel:

- **Debiteuren:** `receivable_repository.py` gooit nu `ValidatieFout` met Nederlandse teksten (bedrag, valuta, status, bron, overgang, reden); de PATCH-route geeft die tekst als 409 door. Een vreemde `ValueError` geeft nog "Conflict.".
- **ActivePieces-verbinding aanmaken:** `ActivePiecesService.create_connection` gooit `ValidatieFout` (Nederlands, vaste tekst); de route geeft hem als 400 door.
- **AP-verbinding per tenant:** `OngeldigeApGegevens` erft nu van `ValidatieFout`; de route geeft de (al Nederlandse, vaste) tekst door.
- **LLM-provider inrichten:** de SSRF-reden (kan een opgelost intern adres noemen) gaat naar het log; de beheerder krijgt "Dit adres is niet toegestaan voor een taalmodel-provider.".

Niet gedaan: `flows_router` van ActivePieces en de overige beheer- en experimentschermen houden de vaste tekst; zij staan niet in de brief.
