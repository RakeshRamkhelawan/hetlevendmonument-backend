# BE-CFG-016: Dockerfile Healthcheck Port Fix

## Samenvatting

Fixt de development stage healthcheck in `Dockerfile` die poort `8110` (host-mapped) gebruikte in plaats van `8000` (container-internal). Dit brak standalone `docker run` zonder compose override.

## Scope

- `Dockerfile` (development stage, regel 106-108)

## Wijzigingen

```dockerfile
# Before:
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8110/health || exit 1

# After:
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
```

## Tests

- `tests/unit/test_startup_infra_config.py::TestDockerfileHealthcheck`

## ADR Impact

- ADR-009 (Traefik/health): healthcheck moet container-interne poort gebruiken

## Trainingssamenvatting

> Dockerfile healthchecks moeten altijd de container-interne poort gebruiken, niet de host-gemappede poort. Compose overschrijft healthchecks; de Dockerfile healthcheck is voor standalone `docker run`.

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
