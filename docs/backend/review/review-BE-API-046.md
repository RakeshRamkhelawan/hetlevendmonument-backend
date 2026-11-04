STATUS: APPROVED

Goedkeuring: (regie 6b, 2026-10-22: herstelcommit 429db146 gericht gelezen, lek dicht; laatste taal- en logpunten in da00f108)

# Review BE-API-046 -- geen interne foutteksten naar de klant

Gate 2: security-reviewer (subagent), commit cc2fc821, ronde 1 op 2026-10-22. Max twee rondes.

## Bevindingen ronde 1 en wat ermee gedaan is

| # | Ernst | Bevinding | Afhandeling |
|---|---|---|---|
| 1 | Hoog | `/ready` (zonder inlog) toonde ruwe database-, Redis- en taalmodelfouten via `src/core/monitoring/health_checks.py` | OPGELOST: vaste tekst in bericht en details, details naar het log; test per controle |
| 2 | Hoog/Middel | `focus_suggestion_service.py`: `str(e)` in `SuggestionResponse.message` | OPGELOST: vaste tekst |
| 3 | Middel | `swarm_stream_service.py`: `str(e)` in SWARM_ERROR-event en resultaat | OPGELOST: vaste tekst, details naar het log |
| 4 | Middel | `src/core/api/main.py` (`@app.<methode>`, geen APIRouter) viel buiten de scope; 8 plekken met `str(exc)` | OPGELOST: plekken gerepareerd (ook de debug-tak) en de scope breder: `FastAPI(` en `@app.<methode>` tellen mee |
| 5 | Middel (sluimerend) | `tool_broker/exceptions.py` zet origineel fouttekst en traceback in de detail | NIET OPGEPAKT: geen bereikbaar pad gemeten (aanroepers vangen en geven vaste tekst); gemeld |
| 6 | Middel | De vrijstelling "eigen klasse" toetst niet de raise-plekken van die klassen | NIET OPGEPAKT, bewust: 89 `raise Eigen(f"..{e}")`-plekken gemeten, vrijwel allemaal interne verpakking zonder antwoordpad; de bereikbare (JSON/CSV-uploadfout, URL-validatie) dragen de eigen invoer van de klant. Een guard hierop zou 89 uitzonderingen of een bereikbaarheidsanalyse vragen; gemeld |
| 7 | Laag/Middel | Omzeilvarianten (alias, helper, `e.message`, `e.detail`, `format_exc`) | DEELS: `message`, `detail`, `reason`, `msg`, `response`, `__cause__` en `traceback.format_*` tellen nu als tekst; alias en helper blijven blind (gemeld) |
| 8 | Geen | `ValidatieFout` en de vier plekken | geen lek |
| 9 | Dode code | `cva_utils.py`, enkele services | NIET OPGEPAKT: geen lek |

Guard-uitbreiding: `HTTPException` telt als eigen klasse (de `detail` is de tekst van de eigen raise-plek, daar gevangen); twee gedateerde uitzonderingen in `security_middleware.py` met reden; `EXTRA_ANTWOORDBESTANDEN` voor drie bestanden zonder router die een antwoordmodel leveren.

## Mutatiebewijs na de reparaties

- `health_checks.py`: `details={"error": "unavailable"}` terug naar `str(e)` -> guard ROOD.
- Een extra functie met `str(e)` in `security_middleware.py` (bestand staat al op de lijst) -> guard ROOD.
- Legitieme gevallen (HTTPException-detail, vergelijking, logregel, eigen klasse) -> niet betrapt (tests in het guardbestand).

## Ronde 2 (commit 318c2043) -- CHANGES_REQUESTED, verwerkt

De reparaties uit ronde 1 zijn door de reviewer als volledig beoordeeld en de twee gedateerde uitzonderingen als juist. Een nieuw, bereikbaar lek:

| # | Ernst | Bevinding | Afhandeling |
|---|---|---|---|
| R2-1 | Hoog | `src/domains/flows/agentic_service.py`: `str(e)` en `response.error_message` in het antwoord van `generate_flow_from_prompt`, door `ai_router.py` ongefilterd in een 500-antwoord gezet | OPGELOST: vaste tekst; ook `execute_approved_plan` (`str(e)`) en `_legacy_generate_flow` (`str(e)[:100]` in de uitleg); het bestand staat nu in `EXTRA_ANTWOORDBESTANDEN`; test met beide paden (uitzondering en providerfout) |
| R2-2 | Laag | dezelfde soort in veel services zonder router (`executor_agent`, `cva_file_manager`, `workflow/providers.py`, `caching/*`), bereikbaarheid niet gemeten | NIET OPGEPAKT: scopekloof uit ronde 1 punt 6; gemeld |
| R2-3 | Laag | `_is_logcall` neemt elke `.error(...)`/`.warning(...)` als log; alias en helper blind | NIET OPGEPAKT: gemeld |

Let op: de twee rondes zijn op. De herstelcommit van R2-1 is NIET opnieuw door een reviewer gelezen.

## Regie-voorwaarden na ronde 2 (verwerkt in da00f108)

Taal: de flowgeneratie geeft vaste Nederlandse teksten; `exc_info=True` op de uitvoeringsfout. Afgesloten met het oordeel van de regie; zie de STATUS-regel bovenaan.
