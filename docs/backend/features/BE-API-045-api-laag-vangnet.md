# Feature BE-API-045: API-laag Vangnet (Campagne)

## Overzicht
Systematische opbouw van een sluitend testvangnet en mutatiebewijs voor alle bereikbare HTTP-endpoints in `src/core/api/`.

- **Doel**: Voorkomen van regressies, data- en tenantlekken op de buitenste schil die klanten raken.
- **Strategie**: Endpoints-first, auth/tenant prioriteit, mutatiebewijs (voorwaarts ROOD, tegenrichting GROEN).

---

## Trainingssamenvatting

### Flow 1: CSRF Token Generatie
- Actor: Frontend Client
- Preconditie: Client start een sessie en vraagt CSRF token aan.
- Trigger: `GET /csrf-token`
- Gedrag: Server genereert cryptografisch veilig token, slaat dit met TTL op in Redis gekoppeld aan IP/User-Agent fingerprint en retourneert token met expiratie.
- Foutafhandeling: Bij Redis verbindingsfout retourneert server HTTP 500.

### Flow 2: Tenant Statistieken Toegang en Isolatie
- Actor: Geauthenticeerde Tenant Gebruiker of Platform Superuser
- Trigger: `GET /api/v1/tenants/{tenant_id}/stats`
- Autorisatie & Isolatie:
  - Platform superuser mag statistieken van elke tenant inzien.
  - Reguliere gebruiker mag alleen statistieken van het eigen `tenant_id` (uit JWT) inzien.
  - Bij cross-tenant toegangspoging door reguliere gebruiker wordt HTTP 403 geworpen.
- Foutafhandeling: Als tenant niet bestaat wordt HTTP 404 geretourneerd.

### Flow 3: Security Login (Legacy Endpoint)
- Actor: Gebruiker die inlogt via legacy route
- Trigger: `POST /api/v1/auth/login` (deprecated)
- Gedrag: Verifieert gebruikersnaam en bcrypt wachtwoordhash, logt security event en retourneert JWT token met bijbehorend beveiligingsniveau (ADMIN of AUTHORIZED).
- Foutafhandeling:
  - Ongeldige credentials: logt security event met ThreatLevel.MEDIUM en werpt HTTP 401.
  - Serverfout: werpt HTTP 500 Authentication error.

---

### Flow 4: Feature Flags Tenant Sub-router
- Actor: Geauthenticeerde Tenant Gebruiker
- Trigger: `GET /tenant/features`, `GET /tenant/tier`, `GET /tenant/features/{feature}/check`
- Autorisatie & Isolatie:
  - Tenant ID wordt uitsluitend verkregen via tenant context.
  - Zonder tenant context volgt HTTP 400.
  - Onbekende tenant volgt HTTP 404.
  - Feature controle valideert de actieve tier en upgrade requirements.

### Flow 5: Tenant Custom Data (EAV Key-Value Store)
- Actor: Geauthenticeerde Tenant Gebruiker
- Trigger: CRUD op `/api/v1/tenant-custom-data/{namespace}` en `{key}`
- Autorisatie & Isolatie:
  - Vereist authenticatie (HTTP 401 voor unauthenticated).
  - Elke operatie geeft `current_user.tenant_id` mee aan de servicelaag; cross-tenant toegang is architecturaal onmogelijk.
  - Ontbrekende key retourneert HTTP 404.

### Flow 6: Foundation Portal Magic-Link Authenticatie
- Actor: Portal Bezoeker / Gebruiker
- Trigger: `POST /auth/magic-link`, `POST /auth/magic-link/verify`, `POST /auth/logout`
- Beveiliging:
  - Generic response bij aanvraag (voorkomt email enumeratie).
  - Token hash (SHA-256) validatie met 15-minuten TTL.
  - Replay-preventie via atomaire UPDATE (used_at IS NULL); herhaald gebruik leidt tot HTTP 410.
  - Geblokkeerde gebruikers worden geweigerd met HTTP 403 en gelogd in audit trail.
  - Succesvolle verificatie levert JWT met `aud="portal"`.

### Flow 7: Token Refresh, Revoke, Introspection en Logout
- Actor: Frontend Client / Gesynchroniseerde Services (o.a. Hocuspocus)
- Trigger: `POST /refresh`, `POST /revoke`, `GET /validate`, `POST /verify-token`, `POST /logout`
- Beveiliging & Isolatie:
  - Refresh vereist geldig, niet-geblackliste refresh token; roteert cookies.
  - Revocatie en logout plaatsen JWT JTI in Redis blacklist met TTL gelijk aan resterende tokenlevensduur.
  - Introspectie en sync-server verificatie lossen tenant en gebruiker op via pre-auth verbinding en adopteren expliciet de tenant context.

### Flow 8: LLM Provider Health Status
- Actor: Health Monitor / Load Balancer
- Trigger: `GET /llm`
- Gedrag: Delegeert statusverzoek naar health core en retourneert status per geconfigureerde provider.

### Flow 9: Tenant Tool-Execution Audit Logs
- Actor: Tenant Administrator
- Trigger: `GET /tool-audit-logs`
- Autorisatie & Isolatie:
  - Vereist admin rol binnen de tenant; niet-admins krijgen HTTP 403.
  - Audit logs worden gepagineerd opgehaald met cryptografische hash chains.

### Flow 10: Foundation Portal Settings (White-Label Branding)
- Actor: Publieke Bezoeker
- Trigger: `GET /settings`
- Gedrag: Haalt tenant-specifieke white-label branding (kleuren, logo, richtlijnen) op binnen `public_tenant_scope`.
- Foutafhandeling: Retourneert HTTP 404 als instellingen voor tenant ontbreken.

### Flow 11: Agent OODA Analytics Endpoint (Contract Guard)
- Actor: Geauthenticeerde Frontend Client
- Trigger: `GET /analytics/agents/{agent_id}/ooda`
- Gedrag: Valideert tenant_id context en werpt gecontroleerd HTTP 501 NOT_IMPLEMENTED conform SP-C02-B roadmap.

### Flow 12: Realtime Canvas WebSocket Synchronisatie
- Actor: Canvas Medewerker
- Trigger: `WS /ws/{canvas_id}?client_id={id}`
- Gedrag: Delegeert websocket handshake en events (cursor, block sync, live presence) naar canvas websocket handler met tenant_id en user_id isolatie.

### Flow 13: Agentic Routing van Gebruikersvragen
- Actor: Geauthenticeerde Gebruiker
- Trigger: `POST /route`
- Gedrag: Routeert queries via GunaRouter met tenant context naar de best passende supervisor agent.

### Flow 14: Orchestration Statistieken
- Actor: Tenant Gebruiker / Monitor
- Trigger: `GET /stats`
- Autorisatie & Isolatie:
  - Vereist tenant context (HTTP 401 bij afwezigheid).
  - Retourneert statistieken van orchestrator, agent router en health monitor gebonden aan tenant_id.

### Flow 15: Compliance Council HITL Besluitvorming
- Actor: Compliance Reviewer
- Trigger: `GET /api/v1/council/decisions`
- Gedrag: Haalt openstaande HITL besluiten op uit repository met berekend risiconiveau en SLA deadline. Status anders dan 'pending' levert HTTP 400 op.

### Flow 16: Autonomous Workflow Executie
- Actor: Geauthenticeerde Gebruiker
- Trigger: `POST /api/v1/autonomous/workflows/{workflow_id}/execute`
- Gedrag: Plaatst asynchrone workflowtaak op de Dramatiq worker queue gekoppeld aan de huidige gebruiker en tenant_id, en retourneert een progress stream key.

### Flow 17: Knowledge Base Index Rebuild
- Actor: Beheerder met ADMIN_ALL permissie
- Trigger: `POST /index/rebuild`
- Autorisatie & Gedrag: Vereist expliciete OAuth2 ADMIN_ALL scope. Initialiseert en dispatchet index rebuild taak naar de knowledge_agent.

### Flow 18: Tool Version History
- Actor: Geauthenticeerde Gebruiker / Eigenaar
- Trigger: `GET /{tool_id}/versions`
- Isolatie & Foutafhandeling: Controleert tenant-eigenaarschap van het tool. Retourneert 404 indien onbekend of cross-tenant, anders gepagineerde versies.

### Flow 19: Fulltext Document Search
- Actor: Geauthenticeerde Tenant Gebruiker
- Trigger: `GET /search?q={query}`
- Isolatie & Gedrag: Dwingt af dat het tenant_id van de gebruiker overeenkomt met de context (HTTP 403 bij mismatch). Zoekt met PostgreSQL to_tsvector fulltext index binnen de eigen tenant.

### Flow 20: AI Decision Explainability (EU AI Act)
- Actor: Eigenaar van het AI Besluit
- Trigger: `GET /api/gdpr/decisions/{decision_id}/explanation`
- Autorisatie & Compliance: EU AI Act Art. 13/86 transparantie. Valideert zowel tenant_id als intra-tenant eigenaarschap (`decision.user_id == current_user.id`), weigert onbevoegden met HTTP 403.

### Flow 21: Predictive Analytics Forecasting
- Actor: Geauthenticeerde Gebruiker met AGENTS_READ scope
- Trigger: `POST /analytics/predict`
- Gedrag: Genereert tijdreeks- en capaciteitsvoorspellingen (bijv. resource demand) via PredictiveAnalyticsEngine binnen de geautoriseerde tenant context.

### Flow 22: FocusBuilder Flow Real-time Status Stream
- Actor: Eigenaar van de Flow via WebSocket
- Trigger: `WS /flows/{flow_id}/status`
- Autorisatie & Beveiliging: Vereist veilige HTTP-only access_token cookie (query param tokens uitgesloten conform SEC-AGT-004), verifieert flow-bestaan en tenant-eigenaarschap en weigert met websocket close 4001 of 4004 bij overtreding.

### Flow 23: Audit Hash Chain Integrity Monitor
- Actor: Tenant Compliance Officer
- Trigger: `GET /integrity/status`
- Gedrag: Berekent real-time integriteit en percentage geverifieerde hashes over het onveranderbare cryptografische audittrail voor de tenant.

### Flow 24: EU AI Act Compliance Overzichtsrapport
- Actor: Compliance Officer / Auditeur
- Trigger: `GET /report/ai-act/summary`
- Gedrag: Aggregeert AI-besluiten, berekent menselijk toezichtspercentage (human oversight rate) en verklaarbaarheidsscores over de gespecificeerde periode (1-365 dagen).

### Flow 25: GDPR Compliance Overzichtsrapport
- Actor: Data Protection Officer (DPO)
- Trigger: `GET /report/gdpr/summary`
- Gedrag: Aggregeert DSAR-verzoeken, gemiddelde reactietijd, geldige toestemmingsverklaringen en bewaartermijnovertredingen voor de tenant.

### Flow 26: Foundation Portal Takedown Request
- Actor: Portal User
- Trigger: `POST /{tenantSlug}/foundation/takedown`
- Isolatie & Autorisatie: Controleert of de gebruiker en content tot de tenant behoren (HTTP 403 bij mismatch), creëert een takedown-verzoek met status pending en stuurt best-effort meldingen.

### Flow 27: Feature Flag Tenant Toggle (Admin)
- Actor: Platform Admin
- Trigger: `POST /admin/features/{feature}/toggle?target_tenant_id={id}`
- Autorisatie & Isolatie: Vereist admin rol. Omzeilt tenant-filtering via TenantFilterBypass om feature flag voor een specifieke tenant aan of uit te zetten en verwijdert de Redis cache.

### Flow 28: Context-Aware Copilot Assistant Query
- Actor: Geauthenticeerde Tenant Gebruiker
- Trigger: `POST /assistant/ask`
- Gedrag: Haalt gebruikersgeschiedenis op uit Redis ConversationMemory per tenant, executeert het commando via UltimateCVAAgent en slaat de prompt en reactie persistent op.

### Flow 29: GDPR Data Subject Access Request (DSAR) Rapport
- Actor: Data Protection Officer (DPO)
- Trigger: `GET /report/gdpr/dsar`
- Gedrag: Haalt DSAR-verzoeken op per tenant, berekent overschrijding van de wettelijke 30-dagen termijn (status 'overdue') en levert gepagineerde resultaten en statusstatistieken.

### Flow 30: GDPR Artikel 15 Inzagerecht Audit-Trail
- Actor: Betrokkene (Data Subject)
- Trigger: `GET /api/gdpr/audit-trail`
- Compliance & Autorisatie: Valideert rechtmatige grondslag conform GDPR Art. 6 (HTTP 451 bij ontbreken). Filtert audit logs strikt op de eigen user_id binnen de tenant context met paginering.

### Flow 31: Real-time Workspace Collaboration
- Actor: Geauthenticeerde Workspace Deelnemer via WebSocket
- Trigger: `WS /ws/collaborate/{workspace_id}`
- Gedrag: Beheert multi-user aanwezigheid (presence), cursor-tracking en tool-selecties binnen een gedeelde workspace via CollaborationManager met automatische disconnect opruiming.

### Flow 32: Document Upload & Verwerking
- Actor: Geauthenticeerde Tenant Gebruiker
- Trigger: `POST /upload`
- Isolatie & Beveiliging: Dwingt tenant-isolatie af (HTTP 403 bij mismatch), valideert MIME-type whitelist en maximale bestandsgrootte (HTTP 413) en bewaart documentmetadata met status 'processing'.

### Flow 33: EU AI Act Besluitenrapport
- Actor: Compliance Auditeur
- Trigger: `GET /report/ai-act/decisions`
- Gedrag: Aggregeert geautomatiseerde besluiten per risiconiveau (low, medium, high), berekent verklaarbaarheidsscores en het percentage menselijk toezicht (human oversight rate).

### Flow 34: Analytics Dashboard KPI & Quota Overzicht
- Actor: Tenant Gebruiker
- Trigger: `GET /dashboard`
- Gedrag: Haalt realtime workflow statistieken, template-aanbevelingen, Web Vitals, API latency en quota-gebruik op binnen de eigen tenant.

### Flow 35: Governance Mission Risicobeoordeling
- Actor: Auditeur met AUDIT_READ scope
- Trigger: `GET /risks/{mission_id}`
- Gedrag: Genereert een deterministische risico-evaluatie voor een missie over operationele, financiele, compliance, technische, beveiligings- en reputatierisicocategorieën.

### Flow 36: Live Workflow Builder Streaming
- Actor: Workflow Ontwikkelaar via WebSocket
- Trigger: `WS /api/v1/builder/stream`
- Gedrag: Biedt realtime trefwoordextractie en stapsgewijze node-suggesties met ghost-posities via ConnectionManager.

### Flow 37: FocusBuilder Agent Tier Catalogus
- Actor: Tenant Gebruiker
- Trigger: `GET /api/v1/focus-builder/agents`
- Gedrag: Retourneert de drietraps agent-catalogus (live Activepieces apps met credentials, interne platform agents en beschikbare tools) met Redis caching.

### Flow 38: AI Act Compliance PDF Export
- Actor: Compliance Officer
- Trigger: `GET /report/pdf`
- Gedrag: Genereert een meertalig AI Act audit-rapport in PDF formaat met FPDF, inclusief score per beleidsdomein en volledige audit logging.

### Flow 39: Governance Anomaly Detection & Monitoring
- Actor: Auditeur met AUDIT_READ scope
- Trigger: `GET /anomalies`
- Gedrag: Detecteert afwijkingen (bias, kosten, performance) in AI-operaties en levert trends en statistieken over de gevraagde periode.

### Flow 40: Legacy Copilot Intent NLU Parser
- Actor: Copilot Gebruiker
- Trigger: `POST /api/v1/intents/parse`
- Gedrag: Parseert natuurlijke taal naar gestructureerde missieparameters en aanbevolen agent-type met automatische Deprecation headers conform API-migratieprotocol.

### Flow 41: Event Publishing & Subscription
- Actor: Geauthenticeerde Agent / Tenant Deelnemer
- Trigger: `POST /events/publish`, `POST /events/subscribe`
- Gedrag: Publiceert events naar de centrale event store of abonneert agents op specifieke topic filters.

### Flow 42: Management Audit & System Logs
- Actor: Platform Admin / SRE
- Trigger: `GET /logs`, `DELETE /logs`
- Gedrag: Biedt gepagineerde toegang tot recente systeemlogs en stelt administrators in staat het logbestand op te schonen.

### Flow 43: Tools Integration Registry
- Actor: Tenant Gebruiker
- Trigger: `GET /integrations`, `GET /integrations/{integration_id}`
- Gedrag: Biedt een lijst van geregistreerde tool-integraties en detailinformatie per integratie-ID met paginering.

### Flow 44: Legacy Tool Catalogus & Semantic Tool Search
- Actor: Geauthenticeerde Gebruiker
- Trigger: `GET /integrations/catalog`, `GET /integrations/search`
- Gedrag: Biedt ActivePieces tool-catalogus en semantische zoekfunctie met Deprecation en Sunset headers ter voorbereiding op migratie naar v1/tools/.

### Flow 45: ActivePieces Health & Readiness Probe
- Actor: Monitoring Systeem / K8s Probes
- Trigger: `GET /health`, `GET /health/ready`
- Gedrag: Verifieert connectiviteit en operationele status van de ActivePieces integratieservice en catalogus.

### Flow 46: Isolated Sandbox Execution Environment
- Actor: Geauthenticeerde Gebruiker / Agent Runtime
- Trigger: `POST /api/v1/sandbox/create`, `GET /api/v1/sandbox/{sandbox_id}/status`
- Gedrag: Maakt geisoleerde sandbox-omgevingen aan met configureerbare isolatieniveaus en resourcelimieten en bewaakt de status.

### Flow 47: Canvas Collaborator Management
- Actor: Canvas Eigenaar / Collaborator
- Trigger: `POST /{canvas_id}/collaborators`, `DELETE /{canvas_id}/collaborators/{user_id}`
- Gedrag: Voegt medewerkers toe aan een canvas met specifieke rollen (viewer, editor) of verwijdert hen, met strikte 404/403 foutafhandeling.

### Flow 48: Canvas Block Connection Routing
- Actor: Canvas Editor
- Trigger: `POST /{canvas_id}/connections`, `DELETE /{canvas_id}/connections/{connection_id}`
- Gedrag: Creëert en verwijdert visuele en logische verbindingen tussen blokken op het canvas met validatie van blok-existentie en permissies.

### Flow 49: Tenant Resource Usage Tracking
- Actor: Geauthenticeerde Tenant Gebruiker
- Trigger: `GET /usage/status`, `POST /usage/record`
- Gedrag: Rapporteert actueel verbruik versus abonnementslimieten (workflow runs, AI tokens) en biedt een endpoint voor handmatige verbruiksregistratie.

### Flow 50: ActivePieces Integration Badges & Piece Specs
- Actor: Geauthenticeerde Gebruiker / UI Component
- Trigger: `GET /integrations/source-badges`, `GET /integrations/pieces/{piece_name}`
- Gedrag: Haalt beschikbare ActivePieces integraties op als bron-badges (met fallback naar lege lijst bij niet-geconfigureerde credentials) en levert gedetailleerde piece-metadata.

### Flow 51: LLM Model Registry & Provider Connectivity
- Actor: Geauthenticeerde Gebruiker / UI Model Selectors
- Trigger: `GET /llm/models`, `GET /llm/status`
- Gedrag: Biedt een lijst van beschikbare LLM-modellen met metadata en capaciteiten, en test de real-time connectiviteit van geconfigureerde AI providers.

### Flow 52: Canvas Template Library & Instantiation
- Actor: Canvas Gebruiker
- Trigger: `GET /templates/list`, `POST /from-template/{template_id}`
- Gedrag: Biedt een catalogus van voorgedefinieerde canvas-templates (blank, strategy, workflow, dashboard) en creëert nieuwe canvasinstanties op basis van een gekozen template.

### Flow 53: GunaRouter Telemetry & Health Monitoring
- Actor: Platform Beheerder / Monitoring Probe
- Trigger: `GET /stats`, `GET /health`
- Gedrag: Exposeert statistieken over verdeling over de Drie Guna lagen (tamasic, rajasic, sattvic) inclusief Prana-kosten, en rapporteert de operationele status van de routing-subsystemen.

### Flow 54: Production Readiness & Baseline Telemetry
- Actor: SRE / Platform Auditeur met AGENTS_READ scope
- Trigger: `GET /production-report`, `GET /performance-baseline`
- Gedrag: Initialiseert en valideert alle productiesystemen voor een integraal opleveringsrapport en levert actuele baseline-prestatiemetrics versus SLA-doelstellingen.

### Flow 55: Multi-Tenant Tool Registration & Registry
- Actor: Tool Beheerder / Agent met AGENTS_WRITE scope
- Trigger: `POST /api/v1/tools/`, `GET /api/v1/tools/`
- Gedrag: Registreert nieuwe AI tools per tenant met schema- en capaciteitsdefinities en levert gefilterde overzichten (op categorie, capability) onder strikte tenant-isolatie.

### Flow 56: RBAC Dynamic Permission Checking
- Actor: Geauthenticeerde Tenant Gebruiker / Admin
- Trigger: `GET /rbac/users/{user_id}/permissions`, `POST /rbac/permissions/check`
- Gedrag: Haalt gebruikerspermissies op binnen tenant-context en verifieert specifieke permissies voor frontend UI-rendering, met 403-blokkade bij inzage in andermans permissies zonder USER_MANAGE rechten.

### Flow 57: Binary Workflow State Snapshot Store
- Actor: Geauthenticeerde Tenant Gebruiker / Collaborator
- Trigger: `POST /snapshots/{workflow_id}`, `GET /snapshots/{workflow_id}`
- Gedrag: Slaat binaire Yjs snapshots van workflows op met payloadgroottevalidatie (400 bij lege inhoud) en levert de meest recente binaire snapshot per workflow_id en tenant.

### Flow 58: SOP Visual React Flow Bridge
- Actor: Workflow Ontwikkelaar / Procesontwerper
- Trigger: `GET /api/v1/workflows/visual/sops/{sop_id}`, `POST /api/v1/workflows/visual/sops/{sop_id}`
- Gedrag: Vertaalt YAML-gedefinieerde Standard Operating Procedures (SOPs) naar React Flow interactieve graafrepresentaties en slaat bewerkte diagrammen weer persistent op als YAML.

### Flow 59: GDPR Art. 22(3) Human Review Request Pipeline
- Actor: Betrokkene (Data Subject)
- Trigger: `POST /human-review`, `GET /human-review-requests`
- Gedrag: Faciliteert het recht op menselijke tussenkomst bij geautomatiseerde besluitvorming conform GDPR Art. 22(3) en biedt overzicht van ingediende verzoeken met status en doorlooptijd.

### Flow 60: Real-Time Guna Routing Test & Reinforcement Feedback
- Actor: Geauthenticeerde Gebruiker / AI Router Supervisor
- Trigger: `POST /test`, `POST /feedback`
- Gedrag: Test en simuleert routing over de Drie Guna lagen (tamasic, rajasic, sattvic) en registreert feedbackresultaten voor deterministische routingoptimalisatie en leerloops.

### Flow 61: Foundation Newsletter Subscription & Preference Management
- Actor: Publieke Bezoeker
- Trigger: `POST /newsletter/subscribe`, `POST /newsletter/unsubscribe`
- Gedrag: Beheert publieke nieuwsbriefinschrijvingen en uitschrijvingen per tenant via SHA-256 tokens met enumeration-preventie en rate-limiting (3/uur per IP).

### Flow 62: AI System Health & High-Level Capabilities Overview
- Actor: Geauthenticeerde Gebruiker met AGENTS_READ scope
- Trigger: `GET /system/status`, `GET /capabilities`
- Gedrag: Rapporteert gedetailleerde operationele status en prestatiemetrics van AI subsystemen (adaptive learning, intelligent routing, predictive analytics) en de beschikbare feature-matrix.

### Flow 63: Tenant RAG Configuration & Strategy Management
- Actor: Tenant Administrator met WORKFLOWS_READ / WORKFLOWS_WRITE scopes
- Trigger: `GET /config`, `PUT /config`
- Gedrag: Beheert RAG-instellingen (embedding modellen, chunking strategieen, retrieval filters) per tenant met automatische notificatie bij modelwijzigingen die herindexering vereisen.

### Flow 64: HR Trainings Bulk Import & Registry
- Actor: HR Beheerder / Admin
- Trigger: `POST /trainings/import`, `GET /trainings`
- Gedrag: Verwerkt bulkuploads van trainingsdefinities en medewerker-trainingskoppelingen met Pydantic rij-validatie, unieke conflictafhandeling (409) en gepagineerd overzicht.

### Flow 65: AI Adaptive Learning Event Ingestion & Insights Retrieval
- Actor: Geauthenticeerde Gebruiker / Agent met AGENTS_WRITE / AGENTS_READ scopes
- Trigger: `POST /learning/event`, `GET /learning/insights`
- Gedrag: Registreert leer-events (feedback, interacties, systeemstatistieken) voor adaptieve modelaanpassing en ontsluit gegenereerde patronen en inzichten met betrouwbaarheidsscores.

### Flow 66: HR Skills Bulk Import & Registry
- Actor: HR Beheerder / Admin
- Trigger: `POST /skills/import`, `GET /skills`
- Gedrag: Verwerkt CSV/JSON uploads voor vaardigheden, rolvereisten en medewerker-beoordelingen met partial failure envelopes (200 met foutrijen) en gepagineerde catalogustoegang.

### Flow 67: Stripe Billing Checkout Session & Status Cache
- Actor: Tenant Eigenaar / Facturatiebeheerder
- Trigger: `POST /billing/create-checkout-session`, `GET /billing/status`
- Gedrag: Initialiseert Stripe checkout-sessies voor abonnementsupgrades met tier-escalatiepreventie en serveert abonnementsstatus via een TTL-cachelaag met databasefallback.

### Flow 68: Real-Time WebSocket Communication & Channel Rooms
- Actor: Real-time Client (Frontend / Agent)
- Trigger: `WS /ws/{channel}`, `WS /ws/{channel}/{room_id}`
- Gedrag: Biedt bidirectionele real-time communicatie over kanalen en kamers met kanaalnaamvalidatie, ping/pong-hartslag, status-enquêtes en broadcastfiltering onder strikte tenant-isolatie.

### Flow 69: CVA Public Managed Agent Lifecycle & Execution
- Actor: Geauthenticeerde Gebruiker met AGENTS_WRITE scope
- Trigger: `POST /cva/create_agent`, `POST /cva/execute/{agent_id}`
- Gedrag: Maakt en beheert lichtgewicht CVA agents in het centrale register en verdeelt executietaken over geregistreerde agents onder strikte tenant-resolutie.

### Flow 70: Analytics Ingest GDPR Data Portability & Right to Erasure
- Actor: Geauthenticeerde Gebruiker
- Trigger: `POST /events/export`, `DELETE /events/user`
- Gedrag: Exporteert alle telemetry- en sessie-events voor een geauthenticeerde gebruiker conform AVG/GDPR Art. 15/20 of wist analyticsdata en deactiveert actieve sessies conform Art. 17.

### Flow 71: Compliance Posture Score Calculation & Historical Tracking
- Actor: Geauthenticeerde Gebruiker met GOVERNANCE_READ scope
- Trigger: `GET /score`, `GET /score/history`
- Gedrag: Berekent gewogen compliance-scores (GDPR 40%, AI Act 35%, Audit 25%) voor de tenant via de calculator service en serveert historische trends met rate limiting.

### Flow 72: Admin Multi-Tenant LLM Provider Chain Management
- Actor: Systeembeheerder met ADMIN scope
- Trigger: `GET /admin/llm-providers`, `POST /admin/llm-providers`
- Gedrag: Biedt adviseursbeheer over de LLM provider failoverketen van een tenant met strikte SSRF-validatie, write-only sleutelbeleid en auditlogging bij weigeringen.

### Flow 73: Privacy DSAR Data Portability & Right to Erasure
- Actor: Geauthenticeerde Gebruiker
- Trigger: `GET /export`, `POST /forget`
- Gedrag: Verzamelt en streamt alle persoonsgegevens (workflows, tooling, gamificatie, CVA-dialogen) als JSON en verwijdert gebruikersdata bij expliciete e-mailbevestiging.

### Flow 74: Audit Log Hash Chain Cryptographic Integrity Verification
- Actor: Geauthenticeerde Gebruiker met GOVERNANCE_READ / GOVERNANCE_WRITE scopes
- Trigger: `GET /integrity/verify`, `POST /integrity/verify-entry`
- Gedrag: Verifieert cryptografische SHA-256 hashketens van het auditlog over tijdsvensters en valideert individuele logregels tegen tampering met gedetailleerde integriteitsrapporten.

### Flow 75: Audit Mission Trail Listing & GDPR Multi-Format Export
- Actor: Geauthenticeerde Gebruiker met AUDIT_READ scope
- Trigger: `GET /missions`, `GET /missions/{mission_id}/export`
- Gedrag: Ontsluit auditsporen voor operationele missies met paginering en filters, en exporteert complete verwerkingsregisters in JSON-, CSV- of gesimuleerd PDF-formaat.

### Flow 76: AI Workflow Optimization Suggestions & Architectural Variants
- Actor: Geauthenticeerde Gebruiker met WORKFLOWS_READ scope
- Trigger: `GET /api/v1/workflows/suggestions/{workflow_id}/suggestions`, `GET /api/v1/workflows/suggestions/{workflow_id}/variants`
- Gedrag: Analyseert workflowpatronen op ontbrekende foutafhandeling en auditstappen, en genereert geoptimaliseerde varianten (kosten, snelheid, betrouwbaarheid) met trade-off analyses.

---

## Batches Voortgang

### Batch 1 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 561 endpoints over 163 modules
- **Eindstand**: 558 endpoints over 160 modules (-3 endpoints, -3 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/auth/router_csrf.py` (1 endpoint: `GET /csrf-token`)
     - Test: `tests/unit/api/auth/test_router_csrf.py`
     - Mutatie: `expires_in` gemuteerd -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/tenants/tenants_stats_router.py` (1 endpoint: `GET /{tenant_id}/stats`)
     - Test: `tests/unit/api/v1/tenants/test_tenants_stats_router.py`
     - Mutatie: Tenant-isolatie check omzeild (`if False and ...`) -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/security/auth_router.py` (1 endpoint: `POST /auth/login`)
     - Test: `tests/unit/api/v1/security/test_security_auth_router.py`
     - Mutatie: Statuscode bij ongeldige inlog gewijzigd naar 403 i.p.v. 401 -> ROOD; herstel -> GROEN.

### Batch 2 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 558 endpoints over 160 modules
- **Eindstand**: 546 endpoints over 157 modules (-12 endpoints, -3 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/v1/feature_flags/tenant_router.py` (3 endpoints: `/tenant/features`, `/tenant/tier`, `/tenant/features/{feature}/check`)
     - Test: `tests/unit/api/v1/feature_flags/test_feature_flags_tenant_router.py`
     - Mutatie: `if not tenant_id:` omzeild met `if False and not tenant_id:` -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/tenant_custom_data/router.py` (6 endpoints: CRUD op custom data)
     - Test: `tests/unit/api/v1/tenant_custom_data/test_tenant_custom_data_router.py`
     - Mutatie: `if value is None:` gewijzigd naar `if value is not None:` -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/foundation/auth.py` (3 endpoints: `/auth/magic-link`, `/auth/magic-link/verify`, `/auth/logout`)
     - Test: `tests/unit/api/v1/foundation/test_foundation_auth_router.py`
     - Mutatie: `if user.is_blocked:` omzeild met `if False and user.is_blocked:` -> ROOD; herstel -> GROEN.

### Batch 3 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 546 endpoints over 157 modules
- **Eindstand**: 538 endpoints over 153 modules (-8 endpoints, -4 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/auth/router_token.py` (5 endpoints: `/refresh`, `/revoke`, `/validate`, `/verify-token`, `/logout`)
     - Test: `tests/unit/api/auth/test_router_token.py`
     - Mutatie: `if not refresh_token:` omzeild met `if False and not refresh_token:` -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/health/llm_router.py` (1 endpoint: `GET /llm`)
     - Test: `tests/unit/api/v1/health/test_health_llm_router.py`
     - Mutatie: Return waarde vervangen door `None` -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/tool_audit/router.py` (1 endpoint: `GET /tool-audit-logs`)
     - Test: `tests/unit/api/v1/tool_audit/test_tool_audit_router.py`
     - Mutatie: `if not _is_tenant_admin(current_user):` omzeild met `if False and not ...` -> ROOD; herstel -> GROEN.
  4. `src/core/api/v1/foundation/settings.py` (1 endpoint: `GET /settings`)
     - Test: `tests/unit/api/v1/foundation/test_foundation_settings_router.py`
     - Mutatie: `if settings is None:` omzeild met `if False and settings is None:` -> ROOD; herstel -> GROEN.

### Batch 4 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 538 endpoints over 153 modules
- **Eindstand**: 533 endpoints over 148 modules (-5 endpoints, -5 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/v1/analytics/agents.py` (1 endpoint: `GET /analytics/agents/{agent_id}/ooda`)
     - Test: `tests/unit/api/v1/analytics/test_analytics_agents_router.py`
     - Mutatie: `status_code=501` gewijzigd naar `500` -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/canvas/canvas_ws_router.py` (1 endpoint: `WS /ws/{canvas_id}`)
     - Test: `tests/unit/api/v1/canvas/test_canvas_ws_router.py`
     - Mutatie: `user_name` gewijzigd naar vaste afwijkende string -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/agentic/agentic_routing_router.py` (1 endpoint: `POST /route`)
     - Test: `tests/unit/api/v1/agentic/test_agentic_routing_router.py`
     - Mutatie: `supervisor_id` gemuteerd in response -> ROOD; herstel -> GROEN.
  4. `src/core/api/v1/orchestration/stats_router.py` (1 endpoint: `GET /stats`)
     - Test: `tests/unit/api/v1/orchestration/test_orchestration_stats_router.py`
     - Mutatie: `if tenant_id is None:` gewijzigd naar `if tenant_id is not None:` -> ROOD; herstel -> GROEN.
  5. `src/core/api/v1/council/router.py` (1 endpoint: `GET /api/v1/council/decisions`)
     - Test: `tests/unit/api/v1/council/test_council_router.py`
     - Mutatie: `if status != "pending":` omzeild met `if False and ...` -> ROOD; herstel -> GROEN.

### Batch 5 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 533 endpoints over 148 modules
- **Eindstand**: 528 endpoints over 143 modules (-5 endpoints, -5 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/v1/autonomous/router.py` (1 endpoint: `POST /workflows/{workflow_id}/execute`)
     - Test: `tests/unit/api/v1/autonomous/test_autonomous_router.py`
     - Mutatie: `status="queued"` gemuteerd naar `status="failed"` -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/knowledge/admin_router.py` (1 endpoint: `POST /index/rebuild`)
     - Test: `tests/unit/api/v1/knowledge/test_knowledge_admin_router.py`
     - Mutatie: `if result.success:` omgekeerd naar `if not result.success:` -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/tools/versions_router.py` (1 endpoint: `GET /{tool_id}/versions`)
     - Test: `tests/unit/api/v1/tools/test_tools_versions_router.py`
     - Mutatie: `if owner... is None:` gewijzigd naar `is not None:` -> ROOD; herstel -> GROEN.
  4. `src/core/api/v1/documents/search_router.py` (1 endpoint: `GET /search`)
     - Test: `tests/unit/api/v1/documents/test_documents_search_router.py`
     - Mutatie: `if current_user.tenant_id != tenant_id:` omzeild met `if False and ...` -> ROOD; herstel -> GROEN.
  5. `src/core/api/v1/gdpr_compliance/explanation_router.py` (1 endpoint: `GET /api/gdpr/decisions/{id}/explanation`)
     - Test: `tests/unit/api/v1/gdpr_compliance/test_gdpr_explanation_router.py`
     - Mutatie: `if decision.user_id != current_user_id:` omzeild met `if False and ...` -> ROOD; herstel -> GROEN.

### Batch 6 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 528 endpoints over 143 modules
- **Eindstand**: 523 endpoints over 138 modules (-5 endpoints, -5 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/v1/ai_features/analytics_router.py` (1 endpoint: `POST /analytics/predict`)
     - Test: `tests/unit/api/v1/ai_features/test_ai_features_analytics_router.py`
     - Mutatie: `prediction_id` prefix gewijzigd -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/focus_builder/ws_status_router.py` (1 endpoint: `WS /flows/{flow_id}/status`)
     - Test: `tests/unit/api/v1/focus_builder/test_focus_builder_ws_status_router.py`
     - Mutatie: WebSocket close code bij ontbrekende token gewijzigd (4001 naar 4099) -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/compliance/integrity_status_router.py` (1 endpoint: `GET /integrity/status`)
     - Test: `tests/unit/api/v1/compliance/test_compliance_integrity_status_router.py`
     - Mutatie: `status` gemuteerd naar `tampered` -> ROOD; herstel -> GROEN.
  4. `src/core/api/v1/compliance/ai_act_summary_router.py` (1 endpoint: `GET /report/ai-act/summary`)
     - Test: `tests/unit/api/v1/compliance/test_compliance_ai_act_summary_router.py`
     - Mutatie: `total_ai_decisions` telling gemuteerd (+999) -> ROOD; herstel -> GROEN.
  5. `src/core/api/v1/compliance/gdpr_summary_router.py` (1 endpoint: `GET /report/gdpr/summary`)
     - Test: `tests/unit/api/v1/compliance/test_compliance_gdpr_summary_router.py`
     - Mutatie: `total_data_subjects` telling gemuteerd (+999) -> ROOD; herstel -> GROEN.

### Batch 7 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 523 endpoints over 138 modules
- **Eindstand**: 518 endpoints over 133 modules (-5 endpoints, -5 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/v1/foundation/takedown.py` (1 endpoint: `POST /{tenantSlug}/foundation/takedown`)
     - Test: `tests/unit/api/v1/foundation/test_foundation_takedown_router.py`
     - Mutatie: tenant_id isolatie check omzeild (`if False and ...`) -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/feature_flags/admin_router.py` (1 endpoint: `POST /admin/features/{feature}/toggle`)
     - Test: `tests/unit/api/v1/feature_flags/test_feature_flags_admin_router.py`
     - Mutatie: `success` gemuteerd naar `False` -> ROOD; herstel -> GROEN.
  3. `src/core/api/assistant_endpoints.py` (1 endpoint: `POST /assistant/ask`)
     - Test: `tests/unit/api/test_assistant_endpoints.py`
     - Mutatie: `confidence` score gemuteerd (+99.0) -> ROOD; herstel -> GROEN.
  4. `src/core/api/v1/compliance/gdpr_dsar_router.py` (1 endpoint: `GET /report/gdpr/dsar`)
     - Test: `tests/unit/api/v1/compliance/test_compliance_gdpr_dsar_router.py`
     - Mutatie: `count` telling gemuteerd (+999) -> ROOD; herstel -> GROEN.
  5. `src/core/api/v1/gdpr_compliance/access_router.py` (1 endpoint: `GET /api/gdpr/audit-trail`)
     - Test: `tests/unit/api/v1/gdpr_compliance/test_gdpr_access_router.py`
     - Mutatie: `total_logs` telling gemuteerd (+999) -> ROOD; herstel -> GROEN.

### Batch 8 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 518 endpoints over 133 modules
- **Eindstand**: 513 endpoints over 128 modules (-5 endpoints, -5 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/v1/collaboration/router.py` (1 endpoint: `WS /ws/collaborate/{workspace_id}`)
     - Test: `tests/unit/api/v1/collaboration/test_collaboration_ws_router.py`
     - Mutatie: `users_list` type gewijzigd -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/documents/upload_router.py` (1 endpoint: `POST /upload`)
     - Test: `tests/unit/api/v1/documents/test_documents_upload_router.py`
     - Mutatie: tenant_id mismatch check omzeild (`if False and ...`) -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/compliance/ai_act_decisions_router.py` (1 endpoint: `GET /report/ai-act/decisions`)
     - Test: `tests/unit/api/v1/compliance/test_compliance_ai_act_decisions_router.py`
     - Mutatie: `count` telling gemuteerd (+999) -> ROOD; herstel -> GROEN.
  4. `src/core/api/v1/analytics_ingest/dashboard_router.py` (1 endpoint: `GET /dashboard`)
     - Test: `tests/unit/api/v1/analytics_ingest/test_analytics_dashboard_router.py`
     - Mutatie: `totalWorkflows` telling gemuteerd (+999) -> ROOD; herstel -> GROEN.
  5. `src/core/api/v1/governance_admin/router_risk.py` (1 endpoint: `GET /risks/{mission_id}`)
     - Test: `tests/unit/api/v1/governance_admin/test_governance_router_risk.py`
     - Mutatie: message prefix gemuteerd -> ROOD; herstel -> GROEN.

### Batch 9 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 513 endpoints over 128 modules
- **Eindstand**: 508 endpoints over 123 modules (-5 endpoints, -5 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/workflow_builder_ws.py` (1 endpoint: `WS /api/v1/builder/stream`)
     - Test: `tests/unit/api/test_workflow_builder_ws.py`
     - Mutatie: `keyword` type gemuteerd -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/focus_builder/agents.py` (1 endpoint: `GET /api/v1/focus-builder/agents`)
     - Test: `tests/unit/api/v1/focus_builder/test_focus_builder_agents_router.py`
     - Mutatie: `ap_unavailable` status omgekeerd -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/compliance/pdf_router.py` (1 endpoint: `GET /report/pdf`)
     - Test: `tests/unit/api/v1/compliance/test_compliance_pdf_router.py`
     - Mutatie: `media_type` gewijzigd naar text/plain -> ROOD; herstel -> GROEN.
  4. `src/core/api/v1/governance_admin/router_anomalies.py` (1 endpoint: `GET /anomalies`)
     - Test: `tests/unit/api/v1/governance_admin/test_governance_router_anomalies.py`
     - Mutatie: `anomalies` lijst geleegd -> ROOD; herstel -> GROEN.
  5. `src/core/api/v1/copilot_intent/parse_router.py` (1 endpoint: `POST /api/v1/intents/parse`)
     - Test: `tests/unit/api/v1/copilot_intent/test_copilot_intent_parse_router.py`
     - Mutatie: `success` gemuteerd naar `False` -> ROOD; herstel -> GROEN.

### Batch 10 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 508 endpoints over 123 modules
- **Eindstand**: 498 endpoints over 118 modules (-10 endpoints, -5 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/events_endpoints.py` (2 endpoints: `POST /events/publish`, `POST /events/subscribe`)
     - Test: `tests/unit/api/test_events_endpoints.py`
     - Mutatie: `status` gemuteerd naar `mutated_status` -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/management/logs_router.py` (2 endpoints: `GET /logs`, `DELETE /logs`)
     - Test: `tests/unit/api/v1/management/test_management_logs_router.py`
     - Mutatie: `logs` lijst geleegd in response -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/tools/integrations_router.py` (2 endpoints: `GET /integrations`, `GET /integrations/{integration_id}`)
     - Test: `tests/unit/api/v1/tools/test_tools_integrations_router.py`
     - Mutatie: `success` gemuteerd naar `False` -> ROOD; herstel -> GROEN.
  4. `src/core/api/tool_endpoints.py` (2 endpoints: `GET /integrations/catalog`, `GET /integrations/search`)
     - Test: `tests/unit/api/test_tool_endpoints.py`
     - Mutatie: `Deprecation` header gemuteerd naar `mutated_val` -> ROOD; herstel -> GROEN.
  5. `src/core/api/v1/activepieces/health_router.py` (2 endpoints: `GET /health`, `GET /health/ready`)
     - Test: `tests/unit/api/v1/activepieces/test_activepieces_health_router.py`
     - Mutatie: `status` gemuteerd naar `mutated_healthy` -> ROOD; herstel -> GROEN.

### Batch 11 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 498 endpoints over 118 modules
- **Eindstand**: 488 endpoints over 113 modules (-10 endpoints, -5 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/sandbox_endpoints.py` (2 endpoints: `POST /api/v1/sandbox/create`, `GET /api/v1/sandbox/{sandbox_id}/status`)
     - Test: `tests/unit/api/test_sandbox_endpoints.py`
     - Mutatie: `status` gemuteerd naar `mutated_status` -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/canvas/collaborators_router.py` (2 endpoints: `POST /{canvas_id}/collaborators`, `DELETE /{canvas_id}/collaborators/{user_id}`)
     - Test: `tests/unit/api/v1/canvas/test_canvas_collaborators_router.py`
     - Mutatie: `role` gemuteerd -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/canvas/connections_router.py` (2 endpoints: `POST /{canvas_id}/connections`, `DELETE /{canvas_id}/connections/{connection_id}`)
     - Test: `tests/unit/api/v1/canvas/test_canvas_connections_router.py`
     - Mutatie: `from_block_id` gemuteerd -> ROOD; herstel -> GROEN.
  4. `src/core/api/usage_endpoints.py` (2 endpoints: `GET /usage/status`, `POST /usage/record`)
     - Test: `tests/unit/api/test_usage_endpoints.py`
     - Mutatie: `limit` gemuteerd (50 naar 99999) -> ROOD; herstel -> GROEN.
  5. `src/core/api/v1/activepieces/catalog_router.py` (2 endpoints: `GET /integrations/source-badges`, `GET /integrations/pieces/{piece_name}`)
     - Test: `tests/unit/api/v1/activepieces/test_activepieces_catalog_router.py`
     - Mutatie: lege lijst gemuteerd naar `[None]` -> ROOD; herstel -> GROEN.

### Batch 12 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 488 endpoints over 113 modules
- **Eindstand**: 478 endpoints over 108 modules (-10 endpoints, -5 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/llm_endpoints.py` (2 endpoints: `GET /llm/models`, `GET /llm/status`)
     - Test: `tests/unit/api/test_llm_endpoints.py`
     - Mutatie: model `name` gemuteerd naar `mutated_name` -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/canvas/canvas_templates_router.py` (2 endpoints: `GET /templates/list`, `POST /from-template/{template_id}`)
     - Test: `tests/unit/api/v1/canvas/test_canvas_templates_router.py`
     - Mutatie: template id `blank` gemuteerd naar `mutated_blank` -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/routing/router_monitor.py` (2 endpoints: `GET /stats`, `GET /health`)
     - Test: `tests/unit/api/v1/routing/test_routing_router_monitor.py`
     - Mutatie: `prana_costs` geleegd naar `{}` -> ROOD; herstel -> GROEN.
  4. `src/core/api/v1/production/reporting_router.py` (2 endpoints: `GET /production-report`, `GET /performance-baseline`)
     - Test: `tests/unit/api/v1/production/test_production_reporting_router.py`
     - Mutatie: `max_response_time_ms` gemuteerd (100 naar 99999) -> ROOD; herstel -> GROEN.
  5. `src/core/api/v1/tool_broker/crud_router.py` (2 endpoints: `POST /api/v1/tools/`, `GET /api/v1/tools/`)
     - Test: `tests/unit/api/v1/tool_broker/test_tool_broker_crud_router.py`
     - Mutatie: tenant_id isolatie check omzeild (`if False and ...`) -> ROOD; herstel -> GROEN.

### Batch 13 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 478 endpoints over 108 modules
- **Eindstand**: 468 endpoints over 103 modules (-10 endpoints, -5 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/v1/rbac/permissions_router.py` (2 endpoints: `GET /rbac/users/{user_id}/permissions`, `POST /rbac/permissions/check`)
     - Test: `tests/unit/api/v1/rbac/test_rbac_permissions_router.py`
     - Mutatie: `permissions` geleegd in response -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/snapshot_endpoints.py` (2 endpoints: `POST /snapshots/{workflow_id}`, `GET /snapshots/{workflow_id}`)
     - Test: `tests/unit/api/v1/test_snapshot_endpoints.py`
     - Mutatie: lege snapshot content check omzeild (`if False and ...`) -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/workflow/workflow_visualization_router.py` (2 endpoints: `GET /api/v1/workflows/visual/sops/{sop_id}`, `POST /api/v1/workflows/visual/sops/{sop_id}`)
     - Test: `tests/unit/api/v1/workflow/test_workflow_visualization_router.py`
     - Mutatie: `success` gemuteerd naar `False` -> ROOD; herstel -> GROEN.
  4. `src/core/api/v1/privacy/human_review_router.py` (2 endpoints: `POST /human-review`, `GET /human-review-requests`)
     - Test: `tests/unit/api/v1/privacy/test_privacy_human_review_router.py`
     - Mutatie: `status` gemuteerd naar `mutated_status` -> ROOD; herstel -> GROEN.
  5. `src/core/api/v1/routing/router_ops.py` (2 endpoints: `POST /test`, `POST /feedback`)
     - Test: `tests/unit/api/v1/routing/test_routing_router_ops.py`
     - Mutatie: `confidence` gemuteerd naar `0.0` -> ROOD; herstel -> GROEN.

### Batch 14 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 468 endpoints over 103 modules
- **Eindstand**: 452 endpoints over 95 modules (-16 endpoints, -8 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/v1/foundation/newsletter.py` (2 endpoints: `POST /newsletter/subscribe`, `POST /newsletter/unsubscribe`)
     - Test: `tests/unit/api/v1/foundation/test_foundation_newsletter.py`
     - Mutatie: `message` gemuteerd naar `MUTATED subscription message` -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/ai_features/system_router.py` (2 endpoints: `GET /system/status`, `GET /capabilities`)
     - Test: `tests/unit/api/v1/ai_features/test_ai_features_system_router.py`
     - Mutatie: `success` gemuteerd naar `False` -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/memory/config_router.py` (2 endpoints: `GET /config`, `PUT /config`)
     - Test: `tests/unit/api/v1/memory/test_memory_config_router.py`
     - Mutatie: `message` gemuteerd naar `MUTATED_MESSAGE` -> ROOD; herstel -> GROEN.
  4. `src/core/api/v1/hr/trainings_import_router.py` (2 endpoints: `POST /trainings/import`, `GET /trainings`)
     - Test: `tests/unit/api/v1/hr/test_trainings_import_router.py`
     - Mutatie: `success` gemuteerd naar `False` -> ROOD; herstel -> GROEN.
  5. `src/core/api/v1/ai_features/learning_router.py` (2 endpoints: `POST /learning/event`, `GET /learning/insights`)
     - Test: `tests/unit/api/v1/ai_features/test_ai_features_learning_router.py`
     - Mutatie: `success` gemuteerd naar `False` -> ROOD; herstel -> GROEN.
  6. `src/core/api/v1/hr/skills_import_router.py` (2 endpoints: `POST /skills/import`, `GET /skills`)
     - Test: `tests/unit/api/v1/hr/test_skills_import_router.py`
     - Mutatie: `success` gemuteerd naar `False` -> ROOD; herstel -> GROEN.
  7. `src/core/api/billing_endpoints.py` (2 endpoints: `POST /billing/create-checkout-session`, `GET /billing/status`)
     - Test: `tests/unit/api/test_billing_endpoints.py`
     - Mutatie: `tier` gemuteerd naar `mutated_tier` -> ROOD; herstel -> GROEN.
  8. `src/core/api/v1/websocket/router.py` (2 endpoints: `WS /ws/{channel}`, `WS /ws/{channel}/{room_id}`)
     - Test: `tests/unit/api/v1/websocket/test_websocket_router.py`
     - Mutatie: kanaalvalidatieconditie omgekeerd -> ROOD; herstel -> GROEN.

### Batch 15 (2026-09-26, iter/api-vangnet-002)
- **Startstand**: 452 endpoints over 95 modules
- **Eindstand**: 436 endpoints over 87 modules (-16 endpoints, -8 modules)
- **Gedekte modules & endpoints**:
  1. `src/core/api/v1/cva/public_router.py` (2 endpoints: `POST /cva/create_agent`, `POST /cva/execute/{agent_id}`)
     - Test: `tests/unit/api/v1/cva/test_cva_public_router.py`
     - Mutatie: `@public_router.post("/create_agent"` gemuteerd -> ROOD; herstel -> GROEN.
  2. `src/core/api/v1/analytics_ingest/gdpr_router.py` (2 endpoints: `POST /events/export`, `DELETE /events/user`)
     - Test: `tests/unit/api/v1/analytics_ingest/test_analytics_ingest_gdpr_router.py`
     - Mutatie: `@router.post("/events/export"` gemuteerd -> ROOD; herstel -> GROEN.
  3. `src/core/api/v1/compliance/score_router.py` (2 endpoints: `GET /score`, `GET /score/history`)
     - Test: `tests/unit/api/v1/compliance/test_compliance_score_router.py`
     - Mutatie: `@score_router.get("/score"` gemuteerd -> ROOD; herstel -> GROEN.
  4. `src/core/api/v1/admin/llm_providers_router.py` (2 endpoints: `GET /admin/llm-providers`, `POST /admin/llm-providers`)
     - Test: `tests/unit/api/v1/admin/test_admin_llm_providers_router.py`
     - Mutatie: `@router.get("/llm-providers")` gemuteerd -> ROOD; herstel -> GROEN.
  5. `src/core/api/v1/privacy/dsar_router.py` (2 endpoints: `GET /export`, `POST /forget`)
     - Test: `tests/unit/api/v1/privacy/test_privacy_dsar_router.py`
     - Mutatie: `await session.commit()` (r204) verwijderd (-> `pass`) -> ROOD; herstel -> GROEN. (test_forget_me_success: assert mock_session.commit.called)
  6. `src/core/api/v1/compliance/integrity_verify_router.py` (2 endpoints: `GET /integrity/verify`, `POST /integrity/verify-entry`)
     - Test: `tests/unit/api/v1/compliance/test_compliance_integrity_verify_router.py`
     - Mutatie: `tampering_detected=result.tampering_detected` (r113) geflipped naar `not result.tampering_detected` -> ROOD; herstel -> GROEN. (test_verify_chain_integrity_success: assert data["tampering_detected"] is False)
  7. `src/core/api/v1/audit/missions_router.py` (2 endpoints: `GET /missions`, `GET /missions/{mission_id}/export`)
     - Test: `tests/unit/api/v1/audit/test_audit_missions_router.py`
     - Mutatie: `@router.get("/missions"` gemuteerd -> ROOD; herstel -> GROEN.
  8. `src/core/api/v1/workflow/workflow_suggestions_router.py` (2 endpoints: `GET /api/v1/workflows/suggestions/{workflow_id}/suggestions`, `GET /api/v1/workflows/suggestions/{workflow_id}/variants`)
     - Test: `tests/unit/api/v1/workflow/test_workflow_suggestions_router.py`
     - Mutatie: diep in filter-logica (r654): `v.strategy in strategies` -> `not in strategies` -> ROOD; herstel -> GROEN. (test_get_workflow_variants_filtered: assert len(variants) <= 1)
