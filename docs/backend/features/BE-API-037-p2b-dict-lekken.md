# BE-API-037 -- P2b Dict-lekken Fix: str(e) in API Responses

Sprint: SP-API-010 Dag 1
Datum: 2026-06-11
Categorie: security fix (OWASP A5)

---

## Samenvatting

Drie OWASP A5 informatielekken verwijderd uit twee API-sub-router bestanden. In alle drie gevallen
werd de exception-tekst (`str(e)`) doorgegeven aan de HTTP-response, waardoor interne
implementatiedetails zichtbaar waren voor clients.

---

## Gewijzigde bestanden

| Bestand | Functie | Lijn | VOOR | NA |
|---------|---------|------|------|----|
| `src/core/api/v1/autonomous/agents_router.py` | `create_autonomous_agent` | ~121 | `detail={"message": "Unexpected error occurred: %s" % str(e)[:200], "error_type": type(e).__name__}` | `detail="Internal error"` |
| `src/core/api/v1/autonomous/agents_router.py` | `autonomous_health_check` | ~313 | `"error": str(e)` in return dict | `"error": "Internal error"` |
| `src/core/api/v1/routing/router.py` | `routing_health` | ~151 | `"message": str(e)` in return dict; geen logging | `"message": "Internal error"` + `logger.error(..., exc_info=True)` |

---

## Beveiligingsrelevantie

- **OWASP A5 (Sensitive Data Exposure)**: Exception-berichten kunnen interne paden, classnames,
  configuratie-details en stack-structuur lekken.
- `type(e).__name__` in de `create_autonomous_agent` response lekte de Python-exception-klasse aan
  de client. Dit is ook een informatielek en is in dezelfde fix verwijderd.
- Health-endpoints mogen GEEN str(e) teruggeven. Ze retourneren een statusdict (geen
  HTTPException 500) -- dit is het juiste patroon voor health-checks in dit project.

---

## Tests

Testbestand: `tests/unit/api/v1/test_no_dict_str_e_leak.py`

- `test_agents_router_create_does_not_leak_str_e` -- POST /agents/create 500-pad
- `test_autonomous_health_check_does_not_leak_str_e` -- GET /autonomous/health foutpad
- `test_routing_health_does_not_leak_str_e` -- GET /routing/health foutpad

Alle drie: ROOD voor de fix, GROEN na de fix. Bevestigd door uitvoering.

---

## Naleving

- ADR-033: thin delivery layer -- alle wijzigingen zijn in exception-handling paths, geen
  domeinlogica aangeraakt.
- CLAUDE.md backend-patroon 10: `logger.error("...: %s: %s", type(e).__name__, e, exc_info=True)`.
- Ruff: geen nieuwe warnings.
- Pyright: 0 errors (baseline gehandhaafd).

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
