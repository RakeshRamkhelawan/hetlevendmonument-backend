# BE-EP-010 -- AgentConfig API Endpoints

**ID:** BE-EP-010
**Sprint:** SP-F Dag 4

## Samenvatting

REST API voor het beheren van AgentConfig-records: interval, timeouts, HITL-drempels en omgevingsvariabelen per agent. CRUD-endpoints met tenant-isolatie en validatie.

## Trainingssamenvatting

### Flow 1: AgentConfig aanmaken of bijwerken

- Actor: Platformbeheerder via de frontend of API
- Voorwaarde: Gebruiker heeft admin-rechten; agent_id bestaat in het systeem
- Actie: POST /api/v1/agent-configs of PUT /api/v1/agent-configs/{id}
- Systeemverwerking: AgentConfigRepository slaat de configuratie op in PostgreSQL; AgentRunner laadt de nieuwe configuratie bij de volgende activatiecyclus
- Succesrespons: HTTP 200 met de opgeslagen AgentConfig inclusief id en updated_at
- Foutrespons: HTTP 422 bij ongeldige waarden (interval < 0, timeout > 3600); HTTP 403 bij onvoldoende rechten
- Uitzonderingen: Als de agent op dit moment actief is, wordt de nieuwe configuratie pas bij de volgende cyclus toegepast
