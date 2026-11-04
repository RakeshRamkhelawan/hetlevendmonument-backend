# ADR Index

## Core Architecture Decision Records (001 - 029)

- [001 Use ADRs (Nygard format)](001-use-adrs-nygard-format.md)
- [002 Multi-tenancy: shared DB/shared schema with row-level isolation](002-multi-tenancy-shared-db-shared-schema-row-level.md)
- [003 Tenant boundary: JWT claim is source of truth](003-tenant-boundary-jwt-source-of-truth.md)
- [004 Tenant isolation enforcement: SQLAlchemy ORM hooks + repository policy](004-tenant-isolation-enforcement-sqlalchemy-orm-hooks-and-repository-policy.md)
- [005 DB hardening: tenant_id NOT NULL + RLS roadmap](005-db-level-hardening-tenantid-notnull-and-rls-roadmap.md)
- [006 Async jobs: Dramatiq with Redis broker](006-async-jobs-dramatiq-with-redis-broker.md)
- [007 Async result delivery: DB status + polling/WebSocket](007-async-result-delivery-db-status-polling-websocket.md)
- [008 WebSocket horizontal scaling: Redis Pub/Sub](008-websocket-horizontal-scaling-redis-pubsub.md)
- [009 Edge gateway: Traefik TLS termination and routing](009-edge-gateway-traefik-tls-routing.md)
- [010 FastAPI runtime: Gunicorn + Uvicorn workers](010-fastapi-runtime-gunicorn-uvicorn-workers.md)
- [011 Worker recycling: max_requests + jitter + timeouts](011-worker-recycling-max-requests-jitter-timeouts.md)
- [012 Health tiers: liveness/readiness/diagnostics](012-health-tiers-liveness-readiness-diagnostics.md)
- [013 Secrets/config quality gates in CI/CD](013-secrets-config-quality-gates-in-cicd.md)
- [014 Observability: metrics + tracing + logging stack](014-observability-metrics-tracing-logging-stack.md)
- [015 Agent/tool execution safety: allowlist + audit trail](015-agent-tool-execution-safety-allowlist-and-audit.md)
- [016 ShadowCEO: Red teaming and adversarial security](016-shadow-ceo-red-teaming.md)
- [017 Gatekeeper: Deterministic policy enforcement](017-gatekeeper-policy-enforcement.md)
- [018 Event Sourcing: Immutable event log](018-event-sourcing-immutable-log.md)
- [019 Audit Logging: GDPR/SOC2 compliance](019-audit-logging-compliance.md)
- [020 A2A Smart Contracts: Agent-to-agent agreements](020-a2a-smart-contracts.md)
- [021 Prana Economy: Token-based resource management](021-prana-economy-token-system.md)
- [022 Agent Self-Learning with ToolBroker Integration](022-agent-learning-toolbroker-integration.md)
- [023 Agent Orchestration System](023-agent-orchestration-system.md)
- [024 Unified Learning & ToolBroker](024-unified-learning-toolbroker.md)
- [025 Digital Twin Architecture](025-digital-twin-architecture.md)
- [026 Twin Production Hardening](026-twin-production-hardening.md)
- [027 Copilot Agent Council](027-copilot-agent-council.md)
- [028 Phase 2 Frontend Scope & Visual Redesign](028-phase-2-frontend-visual-redesign.md)
- [029 Foundation Portal Architecture](029-foundation-portal-architecture.md)
- [030 Build-Stack Security Program: supply chain, IaC, signing, logging](030-build-stack-security-program.md)
- [031 Platform-Wide AI Act Governance and Wiring](031-platform-wide-ai-act-governance-and-wiring.md)
- [032 Frontend Pagina-Architectuur & Volledige Scope Definitie](032-frontend-page-architecture-and-scope.md) *(incl. sectie 10: LLM-feature audit + platform P0-blockers)*
- [033 API Layer Service Boundary & Router Registry Architecture](033-api-layer-service-boundary.md) *(3-laags router compositie, import-linter contracts, orphan-detectie, Strangler Fig migratiestrategie)*
- [034 Agent Runtime Service Boundary](034-agent-runtime-service-boundary.md)
- [035 Single-Tenant Deployment Mode](035-single-tenant-deployment-mode.md) *(DEPLOYMENT_MODE schakelaar, worker-context decorator, frontend WS-URLs, Docker on-premise)*
- [036 Agentic Organizational Hierarchy & Platform-Wide Governance Reuse](036-agentic-organizational-hierarchy-governance-reuse.md) *(Hoofdagent/Directie/Manager/Worker-organogram, Hierarchical Task Blackboard (HTB) shared state, Council-poort platformbreed via nieuwe ingang, statuscontract/checkpoint, HR-piloot, expliciete regressieveiligheidsstrategie)*
- [037 ToolBroker Productiehardening & MCP-Server Productisering](037-toolbroker-production-hardening-and-mcp-server-productization.md) *(4-fasenroadmap: governance-wiring consistent maken, progressive disclosure/code-execution, marktconforme MCP-server-adapter, differentiators; G1-G10 codesnippet-onderbouwd)*
- [038 De netwerkgrens ligt bij de ingress, niet in de applicatie](038-netwerkgrens-container-apps-ingress-en-client-ip.md) *(Container Apps-ingress is de edge; ALLOWED_IP_RANGES wordt opt-in; client-IP komt van de rechtse vertrouwde hop -- X-Forwarded-For-spoofing omzeilde allowlist, blocked_ips, rate limiting, threat detection en de herkomst in de auditregels)*
- [039 Rollen en bevoegdheden in drie lagen](039-rollen-en-bevoegdhedenmodel-in-drie-lagen.md) *(Status: Accepted 2026-10-04; platformbeheer / klantbeheer / procesrollen met bedraglimiet, agent nooit meer dan de mens, vier-ogen als instelling, profielen zzp/klein/midden, expand-en-contract-migratie)*
- [040 Workflowbuilder met ActivePieces](040-workflowbuilder-met-activepieces.md) *(Status: Accepted 2026-10-06; AP blijft de motor, agents alleen via de ToolBroker, per tenant een eigen gratis Community-installatie door ons gehost, verbinding per tenant versleuteld bewaard, geen eigen NL-koppelingen in de pilot)*

## Specialized Enterprise Foundations & Hardening

These documents record decisions that establish modular frameworks and platform-wide production hardening strategies parallel to the core roadmap:

- [ADR-001: Company Layer Foundation](ADR-001-company-layer-foundation.md) *(Establishes the organization-as-code schema and department hierarchy)*
- [ADR-007: Production Hardening Phase 1](ADR-007-production-hardening-phase-1.md) *(Specifies platform resilience, security limits, egress control, and audit bridging)*
