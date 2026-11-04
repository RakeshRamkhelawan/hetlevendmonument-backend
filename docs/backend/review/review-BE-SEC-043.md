# Review BE-SEC-043 -- OpenAPI-oppervlakte dicht buiten development

**Status: APPROVED WITH MINOR GAPS**
**Datum:** 2026-08-14
**Reviewer:** Gate 2 (`code-reviewer` + `security-reviewer`), plus eigen naverificatie van elke
bevinding

## Samenvatting

De hardening zelf is correct en in beide richtingen aangetoond. De review-ronde was zwaar: beide
reviewers gaven **CHANGES_REQUESTED** op het oorspronkelijke plan en vonden samen twaalf plekken
die de oorspronkelijke scope van drie punten miste, waarvan twee een productie-deploy stopten.
Al die bevindingen zijn zelf nagemeten voordat ze zijn verwerkt -- twee bleken deels onjuist en
zijn niet overgenomen zoals aangeleverd.

## Bevindingen en verwerking

| ID | Ernst | Bevinding | Verwerkt |
| --- | --- | --- | --- |
| R-001 | CRITICAL | `smoke_test.ps1` liet `deploy_prod.ps1` de stack terugrollen bij een geslaagde deploy | Ja -- eigen `Test-EndpointIsClosed`-helper; beide richtingen aangetoond |
| R-002 | CRITICAL | `deploy_to_production.sh` deed `return 1` op een gehardende API | Ja -- `/health/ready` plus 4xx-eis |
| R-003 | HIGH | De guard gebruikte `importlib.reload`; het reload-vrije ontwerp bestond al in `d47b44db` | Ja -- terug naar `patch.object`, van 2 reloads naar 0 |
| R-004 | HIGH | Geen enkele test pinde `staging`; een mutatie naar `!= "production"` bleef groen | Ja -- geparametriseerd over 6 omgevingen; mutatie bewezen dodelijk |
| R-005 | HIGH | De class-docstring claimde mutatie-bewijs voor een verwijderde test | Ja -- docstring beschrijft nu de vier daadwerkelijk gedraaide mutaties |
| R-006 | HIGH | `pytest tests/smoke/` verzamelde nul tests (`python_files = "test_*.py"`) | Ja -- hernoemd; hernoemen brak eerst drie bestaande tests, dus een skip-fixture erbij |
| R-007 | HIGH | `smoke_test.ps1:114` gebruikte `Test-EndpointJson`, dat geen statusparameter heeft | Ja -- eigen helper i.p.v. de gedeelde `catch` verbouwen, dus nul risico voor bestaande aanroepers |
| R-008 | HIGH | Fail-secure default maakte een lokale `uvicorn` productie via de dev-scripts | Ja -- `ENVIRONMENT=development` in `start_dev.ps1` en `start_local.ps1` |
| R-009 | MEDIUM | Een exacte 404-eis kan slagen tegen een dode server | Ja -- readiness-anker in dezelfde test, plus een 4xx-BEREIK. Reden: een reverse proxy of tussenliggende laag kan een andere 4xx geven, en een harde 404-eis in een poort die terugrolt is een rollback-risico |
| R-010 | MEDIUM | `app_factory.py` had beide ternary-takken op `/docs`; `tool_broker/main.py` zette niets | Ja -- beide gelijkgetrokken; guard toetst WAARDEN, niet de vorm |
| R-011 | MEDIUM | Tests legden de omgekeerde invariant vast en bleven groen door een kale test-app | Ja -- `test_health_endpoints`, `test_tenant_middleware`, `test_refactor_integrity`, `auth_flow`, `pack_lifecycle`, loadtest |
| R-012 | MEDIUM | `/health` wordt door `ProbeBypassMiddleware` statisch beantwoord | Ja -- deploy-checks op `/health/ready` |
| R-013 | LOW | `/redoc` zat in geen enkele smoke-check | Ja -- toegevoegd aan beide |

## Twee bevindingen die na eigen meting NIET zijn overgenomen zoals aangeleverd

1. **"Drie blokkerende CI-integratietests falen al."** Nagemeten: `integration_app`
   (`tests/integration/conftest.py:879`) bouwt een eigen kale `FastAPI()`, dus die tests bleven
   groen. De onderliggende observatie was wel juist en belangrijker: ze legden de OMGEKEERDE
   invariant vast en zouden groen blijven als `src/main.py` terugvalt. Zo verwerkt.
2. **"Staging geeft 403, geen 404."** Nagemeten: met `testing=False` geeft staging 404. De
   opgegeven oorzaak (IP-allowlist) is in ronde 2 WEERLEGD: `src/core/security/ip_whitelist.py`
   zet `/docs`, `/redoc` en `/openapi.json` in `bypass_paths` en `IP_WHITELIST_ENABLED` staat
   default op false, dus een 403 uit die laag kan op deze paden niet voorkomen. Ik had die
   ONGEVERIFIEERDE oorzaak wel als WHY-comment in vijf bestanden geschreven -- op 2026-08-14
   vervangen door de ware reden (proxy/tussenlaag + rollback-risico). Het 4xx-bereik blijft.

## Openstaande punten (MINOR GAPS)

| Punt | Waarom niet nu | Borging |
| --- | --- | --- |
| `frontend/src/pages/APIDocs.tsx` toont een fout in productie | Productbeslissing van Rakesh | **OP-137** in ADR-036 |
| `tests/contracts/test_api_contracts.py:710-733` is tolerant (`in [200, 401]`) en de vervolgtak wordt vacuum | Draait in geen blokkerende poort; vraagt de in-process-aanpak | **OP-138** in ADR-036 |
| `docs/prod-readiness.md` par. 2.9 claimt "all 10 checks pass" terwijl het aantal checks is gewijzigd | Buiten scope; checklist is een eigen document | Genoemd in de spec, out of scope |
| Geen CI-verificatie | Tegoed op | Expliciet vermeld in spec en final-approver brief |

## Ronde 2 (2026-08-14, op commit `0b91c3a7`)

Beide reviewers opnieuw CHANGES_REQUESTED. Dertien bevindingen, alle verwerkt:

| ID | Ernst | Bevinding | Verwerkt |
| --- | --- | --- | --- |
| F-1 | HIGH | De nieuwe guard toetste alleen `docs_url`, dus `openapi_url="/openapi.json"` passeerde groen | Ja -- alle drie de kwargs, plus ONBEPAALD voor niet-herleidbare waarden. Legde meteen een echt gat bloot: `src/core/api/main.py:144` zette `openapi_url` niet |
| F-2 | HIGH | Beide CD-workflows toetsten alleen `/health`; de ADR claimde anders | Ja -- `/health/ready` plus een 4xx-eis op `/openapi.json` in productie en staging; ADR-rij gecorrigeerd |
| F-3 | MED-HIGH | De `000`-tak was dode code: curl schrijft zelf `000` en `|| echo "000"` plakte er een tweede achter | Ja -- `|| true`; empirisch nagemeten: `captured=[000] len=3` |
| F-5 | MEDIUM | De 403-rechtvaardiging was onwaar, op vijf plekken | Ja -- ware reden op alle vijf |
| F-6 | MEDIUM | OP-137/OP-138 naar backlog zonder guard | Ja -- frontend-guard voor OP-137 (mutatie-getest in beide richtingen); OP-138 opgelost i.p.v. geguard |
| F-7 | MEDIUM | Reden voor de gedupliceerde helper was onwaar (geen importcyclus) | Ja -- een `src/core/shared/environment.py`, door beide geimporteerd; reden nu "module-level side effects" |
| F-10 | LOW | `prod-readiness.md` claimde "all 10 checks" | Ja -- aantal en reden gecorrigeerd |
| F-11 | LOW | Test 7 zocht `X-Request-ID` op `/health`, waar ProbeBypass short-circuit | Ja -- naar `/health/ready` |
| F-12 | LOW | De comment citeerde een ongemounte module als bewijs | Ja -- verwijzing naar de gemounte `v1/health/dependencies.py` |
| F-13 | LOW | Mojibake in `HANDOVER_CONTEXT.md` | Nagemeten PRE-EXISTING: zit ook in de ouder-commit. Bestand nu byte-getrouw herbouwd op mijn eigen regel na |
| F-4 | MEDIUM | Smoke was een stille no-op bij een vergeten variabele | Ja -- `SMOKE_STRICT=1` maakt dat hard rood; runbook aangepast |
| F-8 | LOW | Journaal-commentaar | Deels -- de langste grafsteen ingekort; de rest bewust behouden omdat hij het WAAROM van een omgedraaide assertie draagt |
| F-9 | LOW | Mutatietests in de gedeelde working copy | Ja -- ronde 2 volledig in een eigen `git worktree` |

## Conclusie

Geen open CRITICAL of HIGH. De hardening is aangetoond in beide richtingen, op zowel het
app-object als tegen een echt draaiende server, en er staan twee mutatie-getestte guards op.
**APPROVED WITH MINOR GAPS.**
