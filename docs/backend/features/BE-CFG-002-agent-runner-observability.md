# BE-CFG-002 -- AgentRunner Observability (Metrics + Health)

**ID:** BE-CFG-002
**Sprint:** SP-F Dag 5

## Samenvatting

Observability voor de AgentRunner pacemaker: Prometheus-metrics voor activatiefrequentie, foutpercentage en circuitbreaker-status. Health-check endpoint retourneert de status van alle geconfigureerde agents.

## Trainingssamenvatting

### Flow 1: AgentRunner metrics ophalen

- Actor: Prometheus scraper of monitoring dashboard
- Voorwaarde: AgentRunner draait en heeft agents geactiveerd
- Actie: GET /metrics of health-check endpoint aanroepen
- Systeemverwerking: Prometheus-counters en -gauges worden gelezen van de AgentRunner instantie
- Succesrespons: Metrics in Prometheus-formaat met activatieaantallen en foutpercentages per agent
- Foutrespons: HTTP 503 als AgentRunner niet beschikbaar is
- Uitzonderingen: Circuit-open agents worden als DEGRADED gerapporteerd
