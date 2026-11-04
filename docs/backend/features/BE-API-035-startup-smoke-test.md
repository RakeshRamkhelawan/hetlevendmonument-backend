# BE-API-035: FA-004 Startup Smoke-Test (ADR-033 router registratie)

**ID:** BE-API-035
**Sprint:** SP-API-009 Dag 4
**Status:** DONE
**Datum:** 2026-06-11

## Beschrijving

Voegt twee ontbrekende architecture smoke-tests toe die bewaken dat de ADR-033
router registry operationeel is na startup. FA-004 uit de SP-API-009 audit:
geen test aanwezig die bewijst dat `register_all_routers()` slaagt en dat
`src.core.api.main.app` een bruikbaar ASGI entry point is.

## Wat gewijzigd

- **Nieuw:** `tests/architecture/test_startup.py`
  - `test_register_all_routers_returns_positive_count`: verifieert dat
    `register_all_routers(FastAPI())` een int > 0 retourneert (124 routers).
  - `test_app_module_has_app_object`: verifieert dat `src.core.api.main.app`
    aanwezig en niet None is.

## Waarom

ADR-033 FA-004: zonder smoke-test kan een silent failure in de router registry
(bijv. ImportError in een lazy registry, of `register_all_routers` retourneert 0)
onopgemerkt blijven totdat de applicatie live draait. De tests bewaken de
minimale startup correctheid.

## Testbewijs

```
pytest tests/architecture/test_startup.py -v
  2 passed

pytest tests/architecture/
  74 passed, 3 xfailed

python -m pyright: 0 errors (baseline ongewijzigd)
ruff check tests/architecture/test_startup.py: All checks passed
```

## Notitie: tests direct groen

FA-004 voegt tests toe voor bestaande werkende functionaliteit (niet een bug-fix).
De tests waren direct groen omdat `register_all_routers` al 124 routers
registreerde en `app` al aanwezig was. Dit is verwacht en correct voor
coverage-toevoeging.

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
