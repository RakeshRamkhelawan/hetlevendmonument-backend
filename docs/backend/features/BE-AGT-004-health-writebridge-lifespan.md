# Feature-specificatie: BE-AGT-004-health-writebridge-lifespan

**ID:** BE-AGT-004  
**Naam:** AgentHealthMonitorAgent Write-Bridge Lifespan Wiring (SP-WE-10b)  
**Datum:** 2026-06-01  
**Auteur:** Gemini  

## 1. Context en Doel
De `AgentHealthMonitorAgent` beschikte al over een write-bridge functionaliteit (inclusief `update_health_status()`), ontworpen om continue health transitions (b.v. degradaties) vanuit de monitoring loop asynchroon door te geven aan `AgentRouterAgent`. Dit systeem is gebouwd om health-aware routering mogelijk te maken (ADR-023).

Echter, deze write-bridge werd in productie nooit opgestart, omdat de vereiste initialisatie in de applicatielifespan ontbrak (`src/core/app_lifespan.py`). Doel van deze feature is de correcte initialisatie bij opstarten.

## 2. Architectuur en Design
* **Bestand:** `src/core/app_lifespan.py`
* **Implementatie:** Introductie van een de startup hook `_init_agent_health_write_bridge(app: FastAPI)`.
* **Tenant-iteratie:** Deze loop haalt alle actieve tenant-IDs op.
* **Component-Wiring:** Per tenant wordt `get_agent_router(tenant_id)` en `get_health_monitor(tenant_id, router_ref=router)` aangeroepen. De dependency injection is hiermee opgelost.
* **Start-conditie:** Een eerste scan `await monitor._check_all()` (die direct synchroniseert en buiten de lock de router update) en de background loop trigger `await monitor.start()` worden direct na initialisatie aangeroepen.

## 3. Veiligheid en Randvoorwaarden
- **Foutafhandeling:** Is verpakt in een veilige `try/except Exception` (best-effort) die waarschuwingen logt maar de server startup (andere systemen) niet afbreekt.
- **Tenant Isolation:** Geïnstantieerd per expliciete tenant ID-opvraging over de `db_manager.get_session()` scope. De monitor isoleert interne calls tot zijn gelockte omgeving per tenant.
- **Locks:** `monitor._check_all()` pusht expliciet wijzigingen naar de router BINNEN een scope die de monitor lock al heeft losgelaten (`CG-005` valkuil-oplossing). 

## 4. Trainingssamenvatting
- **Actor:** Applicatie (bij opstarten `app_lifespan`).
- **Voorwaarde:** Applicatie start op (vóór het accepteren van verzoeken), Redis cache is beschikbaar, tenant ids zijn geladen.
- **Actie:** Voert `_init_agent_health_write_bridge` uit; koppelt de `AgentHealthMonitorAgent` en `AgentRouterAgent` per actieve tenant en start de continue bewakingsloop.
- **Systeemverwerking:** Systeem zoekt in de DB alle tenant-IDs en zorgt dat de Singleton-instanties van router en monitor met elkaar zijn verbonden, waarna `monitor.start()` draait in asyncio achtergrond-taak.
- **Succesrespons:** Logs melden "[OK] AgentHealthMonitor write-bridge initialized for X tenants".
- **Foutrespons:** Logs melden "AgentHealthMonitor write-bridge initialization failed: ExceptionName: ...".
- **Uitzonderingen:** Bij databasefouten of Redis crashes tijdens opstarten, wordt de fout via logging afgevangen (no-op) zodat de applicatie, eventueel in degraded mode, alsnog kan opstarten.