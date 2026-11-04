# BE-CFG-020 — SP-API-009 Dag 1: DSM Migratie + Registries Cleanup

**ID:** BE-CFG-020
**Sprint:** SP-API-009 Dag 1
**ADR:** ADR-033
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

SP-API-009 Dag 1: Alle 50 registraties in `setup/router_registry.py` gecategoriseerd in A/B/C. 9 categorie-A items uitgecommentarieerd (dubbel geregistreerd via registries/). FA-002 `str(e)` fix toegepast. Monitoring en sandbox TODO-gedocumenteerd vanwege prefix-discrepantie.

---

## Categorisatie (46 imports geanalyseerd)

| Categorie | Aantal | Actie |
|-----------|--------|-------|
| A — Dubbel (uitgecommentarieerd) | 10 | import + available=False in setup/ |
| A — Dubbel met prefix-discrepantie (TODO) | 2 | monitoring + sandbox bewaard |
| B — Shim naar v1/ (TODO registries/) | 12 | Documentatie in docstring |
| C — Geen v1/ equivalent (bewaren) | 22 | Documentatie in docstring |

### Categorie A — uitgecommentarieerd

| Module | Vervangen door |
|--------|----------------|
| `agentic_flow_endpoints` | `registries/agentic.py` |
| `analytics_endpoints` | `registries/core_api.py` |
| `events_endpoints` | `registries/analytics.py` |
| `v1.company.board_router` | `registries/company.py` |
| `v1.company.department_router` | `registries/company.py` |
| `v1.company.external_agent_router` | `registries/company.py` |
| `v1.company.goal_router` | `registries/company.py` |
| `v1.company.onboarding_router` | `registries/company.py` |
| `v1.company.router` | `registries/company.py` |
| `v1.company.template_router` | `registries/company.py` |

### Categorie A — bewaard met TODO (prefix-discrepantie)

| Module | Discrepantie |
|--------|-------------|
| `monitoring_dashboard_endpoints` | setup=no-prefix, optional.py=`/api` |
| `sandbox_endpoints` | setup=no-prefix, integrations.py=`/api/v1` |

### FA-002 fix

`system_endpoints.py` regels 201 + 252: `str(e)` vervangen door `"Internal error"`.

---

## Impact

- DSM outgoing imports: **334 → 334** (onveranderd — DSM meet imports in bestanden, niet registraties)
- Dubbele route-registraties verwijderd: 9 module-level imports + bijbehorende `available=False` sentinels
- `register_routers()` docstring bijgewerkt met A/B/C categorisatie

---

## Trainingssamenvatting

### Flow 1: Dubbele registraties categoriseren en opruimen

**Actor:** Sprint-engineer  
**Voorwaarde:** `setup/router_registry.py` bevat imports die ook al in `registries/` staan  
**Actie:** Scan beide bestanden op import-overlap; splits in DUBBEL/UNIEK; commentarieer DUBBEL uit  
**Systeemverwerking:** Python `re.findall` op beide bestanden; set-intersection geeft exacte overlap; gefaseerd uitcommentariëren per batch van 5-6; regressiecheck na elke batch  
**Succesrespons:** Routes blijven beschikbaar via registries/; tests groen; geen dubbele registraties meer  
**Foutrespons:** Als uitcommentariëren > 1 test breekt: terugzetten + markeren als Categorie C. Bij `logger.error(...)` altijd `exc_info=True` per CLAUDE.md §11  
**Uitzonderingen:** Prefix-discrepantie (setup heeft andere prefix dan registries/) → NIET uitcommentariëren zonder prefix-impact te onderzoeken; TODO markeren

### Flow 2: Prefix-discrepantie detecteren

**Actor:** Sprint-engineer  
**Voorwaarde:** Twee registraties van dezelfde module maar met verschillende prefixen  
**Actie:** Controleer `app.include_router()` prefix in setup/ en in registries/; check of router zelf prefix heeft  
**Systeemverwerking:** Als setup=geen-prefix, registries=`/api/v1`, en router-zelf geen prefix → routes op ANDERE paden → NIET verwijderen  
**Succesrespons:** Discrepantie gedocumenteerd als TODO; beide registraties bewaard; geen API-wijziging  
**Foutrespons:** Als prefix onbedoeld dubbel is op ZELFDE pad → uitcommentariëren en verifiëren  
**Uitzonderingen:** Monitoring-endpoints hebben legacy no-prefix pad voor bestaande dashboards; verwijderen kan dashboards breken

### Flow 3: FA-002 str(e) security fix

**Actor:** Security reviewer  
**Voorwaarde:** Status-endpoint retourneert `str(e)` in response body; caller is niet-geauthenticeerd  
**Actie:** Vervang `str(e)` door generieke `"Internal error"` in catch-blokken  
**Systeemverwerking:** Interne foutdetails worden niet meer blootgesteld; `exc_info=True` logging behoudt stacktrace intern  
**Succesrespons:** Response body bevat geen exception-details; stacktrace beschikbaar in logs via `exc_info=True`  
**Foutrespons:** Als monitoring-tools op specifieke error-strings filteren: bestaande alertregels aanpassen  
**Uitzonderingen:** Endpoints die altijd HTTP 200 retourneren voor monitoring-tools (see WHY-comment in code) behouden bewust generieke error string
