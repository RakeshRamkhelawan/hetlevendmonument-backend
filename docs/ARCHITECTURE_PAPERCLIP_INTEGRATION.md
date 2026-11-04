# SanskritiSetu Architectuur: Company Orchestration Platform

**Versie:** 2.0
**Datum:** 11 maart 2026
**Status:** Architecturele Foundation voor Paperclip AI Integratie
**Prioriteit:** P0 — Strategic Platform Evolution

---

## Samenvatting

SanskritiSetu evolueert van een **agent orchestration platform** naar een **company orchestration platform** door Paperclip AI's "company-as-code" paradigma symbiotisch te integreren met de bestaande 161+ agents, 80+ Domain Packs, OODA workflow engine, en enterprise governance stack.

Deze architectuur beschrijft de volledige technische fundering voor deze transformatie, met strikte aandacht voor backward compatibility, tenant isolatie, en de drie architecturele invarianten (Gouden Regels).

---

## 1. Strategische Visie

### 1.1 One-Liner
> Na integratie kan elke tenant een **virtueel bedrijf** modelleren — compleet met organigram, afdelingen, doelhiërarchie, en budgetten — waarbij SanskritiSetu's Domain Packs automatisch worden geactiveerd op basis van de bedrijfsstructuur, externe agents via een open heartbeat protocol naadloos meedraaien, en elke taak altijd traceert naar het bedrijfsdoel ("het waarom").

### 1.2 Architectuurprincipe: Symbiotisch, niet Vervangend

```
┌─────────────────────────────────────────────────────────────────┐
│            COMPANY LAYER (nieuw — Paperclip-geïnspireerd)        │
│  Company Model · Org Chart · Goal Ancestry                       │
│  Board Governance · Company Templates                            │
│  Heartbeat Protocol (externe agents)                             │
├─────────────────────────────────────────────────────────────────┤
│         BESTAANDE SANSKRITISETU STACK                            │
│  161+ Agents · 80+ Domain Packs · OODA Engine                   │
│  PolicyEngine · Multi-Pack Assembly · Hybrid Search             │
│  Knowledge Management · Cost/Budget Tracking                    │
│  Pack Intelligence · Feedback Loop · CVA                        │
├─────────────────────────────────────────────────────────────────┤
│            INFRASTRUCTURE                                        │
│  PostgreSQL · Redis · RabbitMQ · Docker                         │
│  Multi-Tenant Isolation · Audit Logging · RBAC                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 Wat verandert er NIET

- De bestaande 161+ interne agents blijven ongewijzigd functioneren
- Domain Packs, Multi-Pack Assembly, en Pack Intelligence blijven intact
- OODA workflow engine, policy engine, en tenant isolation blijven de kern
- Alle bestaande API endpoints blijven backward-compatible
- De huidige frontend componenten blijven werken

---

## 2. De Drie Gouden Regels (Architecturele Invarianten)

Elk pad in het systeem — company creation, department routing, pack activation, procedure execution, external-agent dispatch, approval flows, en dashboards — MOET dezelfde vraag beantwoorden: **"Voor welk bedrijfsdoel gebeurt deze actie nu?"**

| # | Regel | Enforcement | Faalt wanneer |
|---|-------|-------------|---------------|
| **R1** | **Geen task execution zonder contextobject** met minimaal `company_id`, `department_id`, en `goal_chain` | `AgentExecutionContext` is verplicht parameter in `process_task()` en `ExternalAgentBridge.dispatch()`. Validatie faalt als required fields ontbreken. | Een agent of externe agent een taak ontvangt zonder volledige context. Systeem blokkeert execution en logt `CONTEXT_INCOMPLETE` event. |
| **R2** | **Geen pack-activatie zonder verklaarbare matchreden en confidence score** | `PackActivationResult` bevat altijd `match_reason: str`, `confidence: float`, `input_signals: list`, en `audit_log_id: UUID`. Activatie zonder deze velden is een schema-validatiefout. | Een pack wordt geactiveerd zonder dat de tenant of audit trail kan zien *waarom*. |
| **R3** | **Geen governance-beslissing zonder zichtbaar verband met doel, risico, en budgetcontext** | `BoardDecision.action_context` bevat verplicht `goal_id`, `risk_level`, en `budget_impact`. `BoardService.submit()` valideert completeness. | Een approval wordt gevraagd zonder dat de board member weet welk doel, risico, en budget het betreft. |

> **Implicatie:** Tenants die de Company Layer nog niet gebruiken krijgen een automatisch gegenereerde `default_context` met `company_id=null` en `goal_chain=[]`. De regels gelden altijd — het systeem degradeert graceful maar logt ontbrekende context als `CONTEXT_DEGRADED` metric.

---

## 3. Systeemarchitectuur (High-Level)

### 3.1 Lagenoverzicht

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND LAYER (React + Vite)                        │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────┐ ┌──────────────┐           │
│  │ Company      │ │ Org Chart    │ │ Goal Tree │ │ Board        │           │
│  │ Setup Wizard │ │ Builder      │ │ Dashboard │ │ Approval     │           │
│  └──────────────┘ └──────────────┘ └───────────┘ └──────────────┘           │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────┐ ┌──────────────┐           │
│  │ External     │ │ Pack         │ │ Mission   │ │ Template     │           │
│  │ Agent Hub    │ │ Selector     │ │ Control   │ │ Marketplace  │           │
│  └──────────────┘ └──────────────┘ └───────────┘ └──────────────┘           │
├─────────────────────────────────────────────────────────────────────────────┤
│                         API GATEWAY (FastAPI)                                │
│                                                                              │
│  /api/v1/companies/*          → Company CRUD + templates                    │
│  /api/v1/companies/{id}/org/* → Org chart management                        │
│  /api/v1/goals/*              → Goal hierarchy CRUD                         │
│  /api/v1/agents/external/*    → Heartbeat protocol                          │
│  /api/v1/board/*              → Board governance approvals                  │
│  /api/v1/templates/*          → Company template marketplace                │
│  /api/v1/onboarding/*         → Simplified onboarding wizard                │
│                                                                              │
│  (Bestaande endpoints ongewijzigd)                                          │
│  /api/v1/agentic/*  /api/v1/procedures/*  /api/v1/auth/*  etc.              │
├─────────────────────────────────────────────────────────────────────────────┤
│                         SERVICE LAYER                                        │
│                                                                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │ CompanyService   │  │ GoalService      │  │ BoardService     │          │
│  │ - create()       │  │ - create_goal()  │  │ - submit()       │          │
│  │ - activate_packs │  │ - get_ancestry() │  │ - approve()      │          │
│  │ - export/import  │  │ - track_progress │  │ - route()        │          │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘          │
│           │                     │                     │                     │
│  ┌────────▼─────────┐  ┌────────▼─────────┐  ┌────────▼─────────┐          │
│  │ ExternalAgentSvc │  │ PackScorer       │  │ PolicyEngine     │          │
│  │ - register()     │  │ (match logic)    │  │ (bestaand)       │          │
│  │ - heartbeat()    │  │                  │  │ + board rules    │          │
│  │ - dispatch()     │  │                  │  │                  │          │
│  └────────┬─────────┘  └──────────────────┘  └──────────────────┘          │
│           │                                                                  │
│  ┌────────▼────────────────────────────────────────────────────────┐       │
│  │              ExternalAgentBridge (Bridge Pattern)               │       │
│  │     Wraps external agents als EnhancedBaseAgent instances      │       │
│  │     → DomainPackOrchestrator ziet geen verschil               │       │
│  └─────────────────────────────────────────────────────────────────┘       │
├─────────────────────────────────────────────────────────────────────────────┤
│                         DOMAIN LAYER                                         │
│                                                                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │ Company          │  │ Goal             │  │ ExternalAgent    │          │
│  │ (aggregate root) │  │ (value object)   │  │ (entity)         │          │
│  │ - Departments    │  │ - GoalChain      │  │ - Heartbeat      │          │
│  │ - Mission        │  │ - Alignment      │  │ - Capabilities   │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
├─────────────────────────────────────────────────────────────────────────────┤
│                         DATA LAYER                                           │
│                                                                              │
│  PostgreSQL: companies, departments, goals, external_agents,                │
│              board_decisions, company_templates                              │
│  Redis:      heartbeat_status:{agent_id}, goal_progress_cache,              │
│              ancestry_cache:{goal_id}, board_queue:{tenant_id}              │
│  (Bestaande tabellen ongewijzigd)                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Core Flow: Task Execution met Goal Context

```
User Request
     │
     ▼
┌──────────────────────────────────────────────────────────────────────┐
│ DomainPackOrchestrator._run_single_step(step, context)              │
│                                                                      │
│  ├─ 1. GoalAlignmentValidator.validate(step.action, context)        │
│  │     → ALIGNED:       proceed to step 2                            │
│  │     → DRIFT_WARNING: log metric, proceed to step 2                │
│  │     → MISALIGNED:    escalate to BoardService, BLOCK execution    │
│  │                                                                    │
│  ├─ 2. PolicyEngine.validate_action(step.action, context.policy_scope)│
│  │     → (bestaande governance check)                                 │
│  │                                                                    │
│  └─ 3. Route naar agent:                                             │
│        ┌─────────────────┐    ┌──────────────────────┐              │
│        │ step.runtime    │    │ step.runtime         │              │
│        │ == "internal"   │    │ == "external"        │              │
│        └────────┬────────┘    └──────────┬───────────┘              │
│                 │                        │                           │
│                 ▼                        ▼                           │
│        ┌─────────────────┐    ┌──────────────────────┐              │
│        │ EnhancedBaseAgent│    │ ExternalAgentBridge  │              │
│        │ .process_task()  │    │ .dispatch(task)      │              │
│        └─────────────────┘    └──────────────────────┘              │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Uniform Agent Execution Context (Canoniek Contract)

Alle agents — intern, extern, pack-gebaseerd, board-gerelateerd — ontvangen **exact hetzelfde** contextobject. Dit voorkomt dat interne agents, externe agents, packs en governance ieder met net andere contextvelden werken.

```python
# src/core/company/context.py

class GoalChain(BaseModel):
    """Immutable goal ancestry chain — altijd top-down van missie naar taak"""
    mission_id: Optional[UUID] = None
    mission_title: Optional[str] = None
    strategic_goal_id: Optional[UUID] = None
    strategic_goal_title: Optional[str] = None
    project_goal_id: Optional[UUID] = None
    project_goal_title: Optional[str] = None
    task_goal_id: Optional[UUID] = None
    task_goal_title: Optional[str] = None

    def is_complete(self) -> bool:
        """Retourneert True als minstens mission + current task aanwezig zijn"""
        return self.mission_id is not None and self.task_goal_id is not None

    def depth(self) -> int:
        """Aantal niveaus in de keten (0-4)"""
        return sum(1 for v in [self.mission_id, self.strategic_goal_id,
                               self.project_goal_id, self.task_goal_id] if v is not None)


class PolicyScope(BaseModel):
    """Governance context meegegeven aan elke agent"""
    risk_level: str                          # LOW, MEDIUM, HIGH, CRITICAL
    requires_approval: bool = False
    approval_board_role: Optional[str] = None  # CEO, CFO, CTO, CHRO, etc.
    allowed_actions: List[str] = []            # Whitelist van toegestane acties
    forbidden_actions: List[str] = []          # Blacklist van verboden acties


class BudgetScope(BaseModel):
    """Budget context per department/company"""
    monthly_token_budget: Optional[int] = None
    tokens_consumed_this_month: Optional[int] = None
    budget_remaining_pct: Optional[float] = None  # 0.0-1.0


class AgentExecutionContext(BaseModel):
    """
    HET canonieke contextobject voor elke agent execution.
    Wordt meegegeven aan zowel EnhancedBaseAgent.process_task()
    als ExternalAgentBridge.dispatch() en heartbeat task responses.

    Enforcement: Gouden Regel R1 — geen execution zonder dit object.
    """
    # Identiteit
    tenant_id: int
    company_id: Optional[UUID] = None
    company_type: Optional[str] = None        # mkb, zzp, enterprise
    sector: Optional[str] = None              # retail, tech, services, ...

    # Organisatie
    department_id: Optional[UUID] = None
    department_name: Optional[str] = None
    board_role: Optional[str] = None          # Verantwoordelijke board member

    # Workflow
    pack_id: Optional[UUID] = None
    pack_name: Optional[str] = None
    procedure_id: Optional[UUID] = None
    task_id: UUID                              # Altijd verplicht
    trace_id: UUID                             # OpenTelemetry trace ID

    # Doelketen (Gouden Regel R1)
    goal_chain: GoalChain = GoalChain()

    # Governance (Gouden Regel R3)
    policy_scope: PolicyScope = PolicyScope(risk_level="LOW")

    # Budget
    budget_scope: BudgetScope = BudgetScope()

    # SLA
    sla_seconds: Optional[int] = None

    # Degraded mode indicator
    is_degraded: bool = False                  # True als company_id of goal_chain ontbreekt

    def validate_completeness(self) -> tuple[bool, list[str]]:
        """
        Valideert of het contextobject compleet is.
        Retourneert (is_valid, missing_fields).
        Bij degraded mode: logt waarschuwing maar blokkeert niet.
        """
        missing = []
        if self.company_id is None:
            missing.append("company_id")
        if not self.goal_chain.is_complete():
            missing.append("goal_chain (incomplete)")
        if self.department_id is None:
            missing.append("department_id")

        is_valid = len(missing) == 0
        if not is_valid:
            self.is_degraded = True
        return is_valid, missing
```

### 4.1 Integratie in bestaande code (non-breaking)

| Integratiepunt | Hoe `AgentExecutionContext` wordt meegegeven |
|----------------|----------------------------------------------|
| `EnhancedBaseAgent.process_task(task)` | `task.context: AgentExecutionContext` — nieuw optioneel veld op `TaskData` |
| `ExternalAgentBridge.dispatch(task)` | Context wordt geserialiseerd in heartbeat task response |
| `DomainPackOrchestrator._run_single_step()` | Context gebouwd uit execution + goal + department, doorgegeven aan agent |
| `PolicyEngine.validate_action()` | `policy_scope` uit context wordt meegestuurd |
| `BoardService.submit()` | `goal_chain` + `budget_scope` uit context worden meegestuurd |
| Externe agent `GET /tasks/next` response | Volledig `AgentExecutionContext` als JSON in response body |

### 4.2 Implementation Code Examples (Integratie in bestaande agents)

> **Gap fix:** Developers moeten exact weten hoe ze `AgentExecutionContext` wiren in bestaande code zonder breaking changes.

```python
# VOOR (legacy — bestaand gedrag, blijft werken)
class MyAgent(EnhancedBaseAgent):
    async def process_task(self, task: TaskData) -> TaskResult:
        result = await self._execute(task.input)
        return TaskResult(task_id=task.task_id, output=result)

# NA (met Company Layer — context optioneel, backward-compatible)
class MyAgent(EnhancedBaseAgent):
    async def process_task(self, task: TaskData) -> TaskResult:
        # Context is optioneel veld op TaskData — None voor legacy tenants
        context = task.context or AgentExecutionContext(
            tenant_id=self.tenant_id,
            task_id=task.task_id,
            trace_id=uuid4(),
            is_degraded=True,  # Geen company layer = degraded mode
        )

        # Valideer context (logt waarschuwing, blokkeert NIET)
        is_valid, missing = context.validate_completeness()
        if not is_valid:
            logger.warning(
                "CONTEXT_DEGRADED",
                extra={"missing_fields": missing, "task_id": str(task.task_id)},
            )

        result = await self._execute(task.input)

        # Log goal alignment alleen als context compleet is
        if context.goal_chain.is_complete():
            await self._log_goal_alignment(task.task_id, result, context)

        return TaskResult(task_id=task.task_id, output=result, context=context)
```

**Integratiestrategie `DomainPackOrchestrator._run_single_step()`:**

```python
# Context bouwen vanuit execution + goal + department
async def _build_execution_context(
    self,
    execution: ProcedureExecution,
    step: WorkflowStep,
) -> AgentExecutionContext:
    # Goal chain ophalen (gecached)
    goal_chain = GoalChain()
    if execution.goal_id:
        ancestry = await self._goal_service.get_ancestry(execution.goal_id)
        goal_chain = GoalChain.from_ancestry(ancestry)

    return AgentExecutionContext(
        tenant_id=execution.tenant_id,
        company_id=execution.company_id,       # nullable voor legacy
        department_id=step.department_id,      # nullable voor legacy
        pack_id=execution.pack_id,
        procedure_id=execution.id,
        task_id=uuid4(),
        trace_id=execution.trace_id or uuid4(),
        goal_chain=goal_chain,
        policy_scope=PolicyScope(risk_level=step.risk_level or "LOW"),
        budget_scope=await self._get_budget_scope(execution.tenant_id, execution.company_id),
        sla_seconds=step.sla_seconds,
    )
```

---

## 5. Data Modellen & Database Schema

### 5.1 Nieuwe Database Modellen

```python
# src/core/company/models.py

class Company(Base):
    """Virtual company model — child of Tenant"""
    __tablename__ = "companies"
    __table_args__ = (
        Index('idx_companies_tenant', 'tenant_id'),
        {'schema': 'public'}
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    company_type = Column(String(50), nullable=False)  # mkb, zzp, enterprise
    sector = Column(String(100), nullable=False)        # retail, tech, services, ...
    mission = Column(String(2000), nullable=True)
    config = Column(JSONB, nullable=False, default={})   # Additional company config
    template_id = Column(PG_UUID(as_uuid=True), nullable=True)  # Source template
    status = Column(String(50), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    departments = relationship("Department", back_populates="company", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="company", cascade="all, delete-orphan")


class Department(Base):
    """Department within a Company — maps to Domain Pack categories"""
    __tablename__ = "departments"
    __table_args__ = (
        Index('idx_departments_company', 'company_id'),
        Index('idx_departments_tenant', 'tenant_id'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, nullable=False, index=True)
    company_id = Column(PG_UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    parent_department_id = Column(PG_UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    head_user_id = Column(PG_UUID(as_uuid=True), nullable=True)  # Afdelingshoofd
    board_role = Column(String(50), nullable=True)  # CEO, CFO, CTO, CHRO, etc.
    budget_monthly_tokens = Column(Integer, nullable=True)
    domain_pack_ids = Column(JSONB, nullable=False, default=[])  # Geactiveerde packs
    config = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company = relationship("Company", back_populates="departments")
    parent = relationship("Department", remote_side=[id], backref="children")


class Goal(Base):
    """Hierarchical goal model — mission → strategic → project → task"""
    __tablename__ = "goals"
    __table_args__ = (
        Index('idx_goals_company', 'company_id'),
        Index('idx_goals_parent', 'parent_goal_id'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, nullable=False, index=True)
    company_id = Column(PG_UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    parent_goal_id = Column(PG_UUID(as_uuid=True), ForeignKey("goals.id"), nullable=True, index=True)
    department_id = Column(PG_UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    goal_type = Column(String(50), nullable=False)  # mission, strategic, project, task
    title = Column(String(500), nullable=False)
    description = Column(String(2000), nullable=True)
    kpis = Column(JSONB, nullable=False, default=[])  # [{name, target, current, unit}]
    status = Column(String(50), nullable=False, default="active")
    progress_pct = Column(Integer, nullable=False, default=0)  # 0-100
    deadline = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company = relationship("Company", back_populates="goals")
    parent = relationship("Goal", remote_side=[id], backref="children")


class ExternalAgent(Base):
    """External agent registered via heartbeat protocol"""
    __tablename__ = "external_agents"
    __table_args__ = (
        Index('idx_external_agents_tenant_status', 'tenant_id', 'status'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, nullable=False, index=True)
    company_id = Column(PG_UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    department_id = Column(PG_UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    name = Column(String(255), nullable=False)
    runtime = Column(String(50), nullable=False)  # python, node, shell, webhook, claude-code
    capabilities = Column(JSONB, nullable=False, default=[])
    webhook_url = Column(String(2000), nullable=True)
    api_key_hash = Column(String(255), nullable=False)  # bcrypt hash of agent API key
    heartbeat_interval_seconds = Column(Integer, nullable=False, default=30)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), nullable=False, default="registered")
    metrics = Column(JSONB, nullable=False, default={})
    config = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class BoardDecision(Base):
    """Board governance decision record"""
    __tablename__ = "board_decisions"
    __table_args__ = (
        Index('idx_board_decisions_queue', 'tenant_id', 'company_id', 'decision'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, nullable=False, index=True)
    company_id = Column(PG_UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    requested_by = Column(String(255), nullable=False)
    board_role = Column(String(50), nullable=False)
    action_type = Column(String(100), nullable=False)
    action_context = Column(JSONB, nullable=False, default={})
    goal_id = Column(PG_UUID(as_uuid=True), ForeignKey("goals.id"), nullable=True)
    decision = Column(String(50), nullable=True)  # approved, rejected, deferred
    decided_by = Column(PG_UUID(as_uuid=True), nullable=True)
    reason = Column(String(2000), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CompanyTemplate(Base):
    """Exportable/importable company blueprint"""
    __tablename__ = "company_templates"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    company_type = Column(String(50), nullable=False)
    sector = Column(String(100), nullable=False)
    description = Column(String(2000), nullable=True)
    template_definition = Column(JSONB, nullable=False)
    is_platform_template = Column(Boolean, nullable=False, default=False)
    contributed_by_tenant_id = Column(Integer, nullable=True)
    usage_count = Column(Integer, nullable=False, default=0)
    rating_sum = Column(Integer, nullable=False, default=0)
    rating_count = Column(Integer, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 5.2 Wijzigingen aan bestaande modellen

```python
# ProcedureExecution — nieuw veld toevoegen
class ProcedureExecution(Base):
    # ... bestaande velden ...
    goal_id = Column(PG_UUID(as_uuid=True), ForeignKey("goals.id"), nullable=True)

# DomainPack — nieuw veld toevoegen
class DomainPack(Base):
    # ... bestaande velden ...
    company_id = Column(PG_UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
```

### 5.3 Database Indexes & Performance

| Tabel | Index | Reden |
|-------|-------|-------|
| `companies` | `(tenant_id)` | Tenant query filtering |
| `departments` | `(company_id)`, `(tenant_id)` | Org chart queries |
| `goals` | `(company_id)`, `(parent_goal_id)` | Ancestry traversal |
| `external_agents` | `(tenant_id, status)` | Heartbeat status queries |
| `board_decisions` | `(tenant_id, company_id, decision)` | Approval queue filtering |

---

## 6. API Design

### 6.1 Nieuwe API Endpoints

#### Companies

| Method | Path | Beschrijving |
|--------|------|--------------|
| `POST` | `/api/v1/companies` | Company aanmaken |
| `GET` | `/api/v1/companies` | Lijst companies voor tenant |
| `GET` | `/api/v1/companies/{id}` | Company details incl. org chart |
| `PUT` | `/api/v1/companies/{id}` | Company wijzigen |
| `DELETE` | `/api/v1/companies/{id}` | Company soft-delete |
| `POST` | `/api/v1/companies/{id}/activate-packs` | Trigger automatische pack activatie |
| `POST` | `/api/v1/companies/{id}/export` | Export als template |
| `POST` | `/api/v1/companies/import` | Import vanuit template |

#### Departments (Org Chart)

| Method | Path | Beschrijving |
|--------|------|--------------|
| `POST` | `/api/v1/companies/{id}/departments` | Afdeling toevoegen |
| `GET` | `/api/v1/companies/{id}/departments` | Org chart ophalen (tree) |
| `PUT` | `/api/v1/departments/{id}` | Afdeling wijzigen |
| `DELETE` | `/api/v1/departments/{id}` | Afdeling verwijderen |
| `POST` | `/api/v1/departments/{id}/agents` | Agent toewijzen aan afdeling |

#### Goals

| Method | Path | Beschrijving |
|--------|------|--------------|
| `POST` | `/api/v1/companies/{id}/goals` | Goal aanmaken |
| `GET` | `/api/v1/companies/{id}/goals` | Goal tree ophalen |
| `GET` | `/api/v1/goals/{id}` | Goal details met ancestry |
| `GET` | `/api/v1/goals/{id}/ancestry` | Volledige goal chain |
| `PUT` | `/api/v1/goals/{id}` | Goal wijzigen |
| `PUT` | `/api/v1/goals/{id}/progress` | Voortgang updaten |

#### External Agents (Heartbeat Protocol)

| Method | Path | Beschrijving |
|--------|------|--------------|
| `POST` | `/api/v1/agents/external/register` | Agent registreren |
| `POST` | `/api/v1/agents/{id}/heartbeat` | Heartbeat sturen |
| `GET` | `/api/v1/agents/{id}/tasks/next` | Volgende taak ophalen |
| `POST` | `/api/v1/agents/{id}/tasks/{task_id}/complete` | Taak voltooien |
| `GET` | `/api/v1/agents/external` | Lijst externe agents |
| `DELETE` | `/api/v1/agents/external/{id}` | Agent deregistreren |

#### Board Governance

| Method | Path | Beschrijving |
|--------|------|--------------|
| `GET` | `/api/v1/board/queue` | Approval queue voor huidige user |
| `POST` | `/api/v1/board/decisions/{id}/approve` | Goedkeuren |
| `POST` | `/api/v1/board/decisions/{id}/reject` | Afwijzen |
| `GET` | `/api/v1/board/decisions` | Beslissingshistorie |

#### Templates

| Method | Path | Beschrijving |
|--------|------|--------------|
| `GET` | `/api/v1/templates/companies` | Beschikbare templates |
| `GET` | `/api/v1/templates/companies/{id}` | Template details |
| `POST` | `/api/v1/templates/companies/{id}/instantiate` | Template instantiëren |
| `POST` | `/api/v1/templates/companies/contribute` | Template bijdragen |

#### Onboarding

| Method | Path | Beschrijving |
|--------|------|--------------|
| `GET` | `/api/v1/onboarding/templates` | Aanbevolen templates |
| `POST` | `/api/v1/onboarding/ai-match` | AI matching: tekst → template |
| `POST` | `/api/v1/onboarding/complete` | Onboarding afronden |

### 6.2 Heartbeat Protocol Specificatie

```
REGISTRATIE
POST /api/v1/agents/external/register
{
  "name": "my-python-analyzer",
  "runtime": "python",
  "capabilities": ["analyze", "report"],
  "heartbeat_interval_seconds": 30,
  "webhook_url": "https://my-service.com/tasks",
  "department_id": "uuid-of-department"
}
→ Response: {
    "agent_id": "ext-uuid",
    "api_key": "sk-...",
    "heartbeat_endpoint": "/api/v1/agents/ext-uuid/heartbeat"
  }

HEARTBEAT (elke 30s)
POST /api/v1/agents/{agent_id}/heartbeat
Headers: Authorization: Bearer sk-...
{
  "status": "idle" | "busy" | "error",
  "current_task_id": "uuid" | null,
  "progress": 0.75,
  "metrics": {
    "tasks_completed": 42,
    "avg_duration_seconds": 12.5
  }
}
→ Response: { "ack": true, "pending_tasks": [...] }

TAAK OPHALEN
GET /api/v1/agents/{agent_id}/tasks/next
→ Response: {
    "task_id": "uuid",
    "action": "analyze_supplier_contracts",
    "input": { ... },
    "goal_ancestry": {
      "mission": "Marktleider in duurzame retail",
      "strategic_goal": "Kosten verlagen 20%",
      "project_goal": "Supply chain optimalisatie",
      "task": "Leverancierscondities analyseren"
    },
    "sla_seconds": 300,
    "domain_pack": "logistics.global_route_shield",
    "context": { /* Volledige AgentExecutionContext */ }
  }

TAAK VOLTOOIEN
POST /api/v1/agents/{agent_id}/tasks/{task_id}/complete
{
  "status": "completed" | "failed",
  "output": { ... },
  "reasoning_trace": "..."
}
```

---

## 7. Service Layer Architectuur

### 7.1 Dependency Injection Integratie

```python
# src/core/container.py — uitbreiding

class Container(DeclarativeContainer):
    # ... bestaande providers ...

    # Company Layer (nieuw)
    company_service = providers.Factory(
        CompanyService,
        db_manager=database_manager,
        pack_matcher=pack_intent_matcher,
        tenant_context=tenant_context,
    )

    goal_service = providers.Factory(
        GoalService,
        db_manager=database_manager,
        tenant_context=tenant_context,
    )

    external_agent_service = providers.Factory(
        ExternalAgentService,
        db_manager=database_manager,
        policy_engine=policy_engine,
        budget_manager=budget_manager,
        tenant_context=tenant_context,
    )

    board_service = providers.Factory(
        BoardService,
        policy_engine=policy_engine,
        tenant_context=tenant_context,
    )

    template_service = providers.Factory(
        TemplateService,
        db_manager=database_manager,
        company_service=company_service,
        tenant_context=tenant_context,
    )
```

### 7.2 Pack Activation Scorer

```python
class PackActivationScorer:
    """Deterministisch scoremodel voor pack matching — Gouden Regel R2"""

    def score(self, pack: DomainPack, signals: ActivationSignals) -> PackScore:
        score = 0.0
        reasons = []

        # 1. Department name match (0.40)
        dept_match = self._match_department(pack.department, signals.department_name)
        if dept_match.exact:
            score += 0.40
            reasons.append(f"Department exact match: {pack.department}")
        elif dept_match.fuzzy_score > 0.7:
            score += 0.40 * dept_match.fuzzy_score
            reasons.append(f"Department fuzzy match: {dept_match.fuzzy_score:.0%}")

        # 2. Company type match (0.20)
        if pack.pack_id.startswith(signals.company_type + "."):
            score += 0.20
            reasons.append(f"Pack prefix matches company type: {signals.company_type}")

        # 3. Sector match via intent_tags (0.20)
        sector_overlap = set(pack.intent_tags) & set(signals.sector_tags)
        if sector_overlap:
            score += 0.20 * (len(sector_overlap) / max(len(pack.intent_tags), 1))
            reasons.append(f"Sector tag overlap: {sector_overlap}")

        # 4. Explicit selection (0.20)
        if pack.pack_id in signals.explicit_pack_ids:
            score += 0.20
            reasons.append("Explicitly selected by user/template")

        return PackScore(
            pack_id=pack.pack_id,
            score=score,
            reasons=reasons,
            confidence=self._calculate_confidence(score),
            input_signals=signals.to_list()
        )

    def _calculate_confidence(self, score: float) -> str:
        if score >= 0.90: return "EXACT"
        if score >= 0.70: return "HIGH"
        if score >= 0.50: return "MEDIUM"
        if score >= 0.30: return "LOW"
        return "NONE"
```

### 7.3 Goal Alignment Validator

```python
class GoalAlignmentValidator:
    """
    Valideert dat een voorgestelde actie past bij de actieve goal chain.
    Wordt aangeroepen door DomainPackOrchestrator VOORDAT een step wordt uitgevoerd.
    """

    async def validate(
        self,
        proposed_action: str,
        context: AgentExecutionContext,
    ) -> GoalAlignmentResult:
        """
        Returns:
          - ALIGNED: actie past bij goal chain → proceed
          - DRIFT_WARNING: actie is tangentieel → proceed + log warning
          - MISALIGNED: actie conflicteert met goal → block + escalate
        """
        if not context.goal_chain.is_complete():
            # Degraded mode: geen goal chain beschikbaar
            return GoalAlignmentResult(
                status="DRIFT_WARNING",
                reason="Goal chain incomplete — degraded mode",
                goal_alignment_score=0.0,
            )

        # Score berekenen via keyword overlap + semantic similarity
        alignment_score = await self._compute_alignment(
            action=proposed_action,
            goal_chain=context.goal_chain,
        )

        if alignment_score >= 0.6:
            return GoalAlignmentResult(status="ALIGNED", score=alignment_score)
        elif alignment_score >= 0.3:
            return GoalAlignmentResult(status="DRIFT_WARNING", score=alignment_score)
        else:
            return GoalAlignmentResult(status="MISALIGNED", score=alignment_score)
```

### 7.4 Board Governance Service

```python
class BoardService:
    """
    Presentatie- en routeringslaag bovenop PolicyEngine.
    Vertaalt technische policy-uitkomsten naar bedrijfstaal.
    """

    async def submit(
        self,
        action_type: str,
        action_context: dict,
        context: AgentExecutionContext,
    ) -> BoardDecision:
        """Submit een beslissing voor board approval — Gouden Regel R3"""

        # Valideer verplichte velden
        if not context.goal_chain.mission_id:
            raise ValueError("Board decision requires goal_id — Gouden Regel R3")

        # Bepaal board role op basis van action type en risk level
        board_role = self._route_to_board_member(
            action_type=action_type,
            risk_level=context.policy_scope.risk_level,
            department_id=context.department_id,
        )

        # Maak decision record
        decision = BoardDecision(
            tenant_id=context.tenant_id,
            company_id=context.company_id,
            requested_by=context.task_id,
            board_role=board_role,
            action_type=action_type,
            action_context={
                **action_context,
                "goal_id": context.goal_chain.mission_id,
                "risk_level": context.policy_scope.risk_level,
                "budget_impact": context.budget_scope.budget_remaining_pct,
            },
            goal_id=context.goal_chain.task_goal_id,
        )

        # Sla op en stuur notificatie
        await self._repository.save(decision)
        await self._notify_board_member(decision)

        return decision
```

---

## 8. Agent Bridge Architectuur

### 8.1 External Agent Bridge

```python
class ExternalAgentBridge(EnhancedBaseAgent):
    """
    Maakt een externe agent (heartbeat-based) bruikbaar als interne agent.
    De DomainPackOrchestrator ziet geen verschil.
    """

    def __init__(self, external_agent: ExternalAgent, service: ExternalAgentService):
        super().__init__(
            agent_id=f"ext-{external_agent.id}",
            name=external_agent.name,
            capabilities=external_agent.capabilities,
        )
        self._external = external_agent
        self._service = service

    async def process_task(self, task: TaskData) -> TaskResult:
        """
        1. Dispatch taak naar externe agent (webhook of queue)
        2. Wacht op completion via heartbeat polling
        3. Return resultaat in standaard TaskResult format
        4. Respecteert SLA timeout uit DomainPack step
        """
        # Validatie: context moet aanwezig zijn (R1)
        if not task.context:
            raise ValueError("Task missing AgentExecutionContext — Gouden Regel R1")

        # Dispatch taak
        task_assignment = await self._service.dispatch_task(
            agent_id=self._external.id,
            task=task,
        )

        # Poll voor completion (met timeout)
        result = await self._wait_for_completion(
            task_assignment.id,
            timeout_seconds=task.context.sla_seconds or 300,
        )

        return TaskResult(
            task_id=task.task_id,
            status=result.status,
            output=result.output,
            context=task.context,
        )

    async def _wait_for_completion(self, task_id: UUID, timeout_seconds: int) -> TaskCompletion:
        """Poll via heartbeat status tot completion of timeout"""
        deadline = datetime.utcnow() + timedelta(seconds=timeout_seconds)

        while datetime.utcnow() < deadline:
            status = await self._service.get_task_status(task_id)
            if status.state in ("completed", "failed"):
                return status
            await asyncio.sleep(5)  # Poll interval

        raise TaskTimeoutError(f"Task {task_id} timed out after {timeout_seconds}s")
```

### 8.2 Agent Execution Flow

```
                   DomainPackOrchestrator
                   (bestaand, ongewijzigd)
                          │
                   _run_single_step(step)
                          │
              ┌───────────┴───────────┐
              │                       │
    step.runtime == "internal"   step.runtime == "external"
              │                       │
     EnhancedBaseAgent         ExternalAgentBridge
     (bestaande agents)        (nieuw — wraps externe agent)
              │                       │
     Direct execution          ┌──────┴──────┐
                               │             │
                          Webhook        Task Queue
                          dispatch       dispatch
                               │             │
                          HTTP POST      Redis/RMQ
                          naar agent     message
                               │             │
                          Heartbeat      Heartbeat
                          polling        polling
                               │             │
                          TaskResult     TaskResult
```

### 8.3 External Agent Error Handling

> **Gap fix:** §8.1 beschrijft de happy path. Hier worden faalscenario's gedefinieerd.

**Retry strategie bij dispatch-fouten:**

```python
DISPATCH_RETRY_BACKOFF = [1, 5, 30]  # seconden

async def dispatch_task_with_retry(self, agent_id: UUID, task: TaskData) -> TaskAssignment:
    for attempt, delay in enumerate(DISPATCH_RETRY_BACKOFF):
        try:
            return await self._service.dispatch_task(agent_id, task)
        except (HTTPError, ConnectionError) as e:
            if attempt == len(DISPATCH_RETRY_BACKOFF) - 1:
                raise ExternalAgentDispatchError(
                    f"Agent {agent_id} unreachable after {len(DISPATCH_RETRY_BACKOFF)} attempts"
                ) from e
            await asyncio.sleep(delay)
```

**SLA escalatieladder:**

| Tijdsduur | Actie |
| --------- | ----- |
| 0 – 80% SLA | Normale executie |
| 80% – 100% SLA | Warning metric gelogd, escalatie voorbereid |
| 100% SLA overschreden | `BoardService.submit()` aangeroepen met `action_type="sla_override_request"` |
| Board keurt goed | +300s extensie toegekend |
| Board wijst af / geen respons (60s) | Taak gefaald, `TaskTimeoutError` geraised |

**Output validatie:**

```python
async def _validate_agent_output(self, output: dict, context: AgentExecutionContext) -> dict:
    # 1. Grootte limiet (max 10MB)
    if len(json.dumps(output)) > 10 * 1024 * 1024:
        raise OutputTooLargeError("External agent output exceeds 10MB limit")

    # 2. Schema validatie (verplichte velden)
    required = {"status", "result"}
    if not required.issubset(output.keys()):
        raise OutputSchemaError(f"Missing required fields: {required - output.keys()}")

    # 3. PolicyEngine check (bestaande governance)
    await self._policy_engine.validate_action(
        action=f"external_agent.output.{output.get('result_type', 'unknown')}",
        policy_scope=context.policy_scope,
    )

    return output
```

### 8.4 External Agent Crash Detection

> **Gap fix:** Wat als een agent crasht na heartbeat-ACK maar vóór taak-completion?

**Heartbeat deadline mechanisme:**

```
CRASH DETECTION FLOW:

  T+0:00  Agent heartbeat: status=busy, task_id=abc123
          → Server zet next_deadline = now + 2 * heartbeat_interval
  T+0:30  Verwacht heartbeat — NIET ontvangen
  T+1:00  next_deadline overschreden → agent.status = "stale"
          → Task abc123 gemarkeerd als "orphaned"
  T+2:00  Nog steeds geen heartbeat → agent.status = "dead"
          → Orphaned task herscheduled naar beschikbare agent
          → Alert: "Agent {name} offline since T+0:30"
  T+3:00  (geen re-registratie) → agent permanent verwijderd uit rotatie
```

**Lifecycle states:**

| Status | Betekenis | Actie |
| ------ | --------- | ----- |
| `registered` | Nieuw, nog geen heartbeat | Wacht op eerste heartbeat (max 60s) |
| `active` | Heartbeats op tijd | Taken ontvangen |
| `busy` | Taak in uitvoering | Geen nieuwe taken |
| `stale` | Heartbeat gemist | Taken geblokkeerd, alert verzonden |
| `dead` | 3+ gemiste heartbeats | Uit rotatie, taken herverdeeld |
| `deregistered` | Handmatig verwijderd | Alle openstaande taken geannuleerd |

---

## 9. Frontend Architectuur

### 9.1 Nieuwe Pagina's & Routes

| Pagina | Route | Component | Beschrijving |
|--------|-------|-----------|--------------|
| Company Setup Wizard | `/onboarding` | `CompanySetupWizard.tsx` | 3-staps onboarding flow |
| Company Dashboard | `/company` | `CompanyDashboard.tsx` | Bedrijfsoverzicht met org chart |
| Org Chart Builder | `/company/org-chart` | `OrgChartBuilder.tsx` | ReactFlow-based organigram editor |
| Goal Tree | `/company/goals` | `GoalTree.tsx` | Hiërarchische doelen met voortgang |
| Board Approvals | `/board` | `BoardApprovalQueue.tsx` | Approval queue voor board members |
| External Agent Hub | `/agents/external` | `ExternalAgentHub.tsx` | Registratie en monitoring |
| Template Marketplace | `/templates` | `TemplateMarketplace.tsx` | Browse en instantieer templates |

### 9.2 Component Structuur

```
frontend/src/components/company/
├── CompanySetupWizard.tsx         # 3-staps onboarding
├── CompanyDashboard.tsx           # Bedrijfsoverzicht
├── OrgChartBuilder.tsx            # ReactFlow organigram
├── OrgChartNode.tsx               # Custom node voor afdeling
├── DepartmentPanel.tsx            # Afdeling detail sidebar
├── GoalTree.tsx                   # Hiërarchische doelen
├── GoalCard.tsx                   # Goal met progress bar
├── GoalAncestryBreadcrumb.tsx     # Mission → Strategic → Project → Task

frontend/src/components/board/
├── BoardApprovalQueue.tsx         # Approval items lijst
├── BoardDecisionCard.tsx          # Individueel approval item
├── BoardRoleAvatar.tsx            # CEO/CFO/CTO avatar

frontend/src/components/external-agents/
├── ExternalAgentHub.tsx           # Overzicht externe agents
├── AgentRegistrationForm.tsx      # Registratie wizard
├── HeartbeatMonitor.tsx           # Real-time heartbeat status
├── AgentHealthIndicator.tsx       # Groen/geel/rood status

frontend/src/components/templates/
├── TemplateMarketplace.tsx        # Browse templates
├── TemplatePreview.tsx            # Template detail met preview
├── TemplateInstantiateModal.tsx   # Importeer en pas aan
```

### 9.3 State Management (Zustand)

```typescript
// frontend/src/store/useCompanyStore.ts
interface CompanyStore {
  company: Company | null;
  departments: Department[];
  goals: Goal[];
  setCompany: (company: Company) => void;
  addDepartment: (dept: Department) => void;
  updateGoalProgress: (goalId: string, progress: number) => void;
  fetchOrgChart: (companyId: string) => Promise<void>;
}

// frontend/src/store/useBoardStore.ts
interface BoardStore {
  pendingDecisions: BoardDecision[];
  fetchQueue: () => Promise<void>;
  approve: (decisionId: string, reason?: string) => Promise<void>;
  reject: (decisionId: string, reason: string) => Promise<void>;
}

// frontend/src/store/useExternalAgentStore.ts
interface ExternalAgentStore {
  agents: ExternalAgent[];
  heartbeatStatus: Record<string, AgentHealth>;
  registerAgent: (config: AgentRegistration) => Promise<string>;
  fetchAgents: () => Promise<void>;
  subscribeToHeartbeats: () => void;
}
```

### 9.4 Real-time Collaboration (Org Chart & Goals)

> **Gap fix:** Twee gebruikers bewerken tegelijkertijd de org chart — wie wint?

**WebSocket subscriptie per company:**

```typescript
// frontend/src/hooks/useOrgChartSync.ts
export function useOrgChartSync(companyId: string) {
  const { updateDepartment, revertDepartment } = useCompanyStore();

  useEffect(() => {
    const ws = new WebSocket(`/ws/org-chart/${companyId}`);

    ws.onmessage = (event) => {
      const { type, payload } = JSON.parse(event.data);

      if (type === "org_chart_updated") {
        // Andere gebruiker heeft wijziging doorgevoerd — refresh state
        updateDepartment(payload.department);
      }
      if (type === "conflict_detected") {
        // Onze optimistische update was verouderd — revert
        revertDepartment(payload.department_id);
        toast.warning("Iemand anders heeft deze afdeling gewijzigd. Pagina ververst.");
      }
    };

    return () => ws.close();
  }, [companyId]);
}
```

**Conflictresolutie flow:**

```
Gebruiker A sleept "Sales" onder "Marketing"  →  Optimistische update (UI direct)
                                               →  PATCH /departments/{id} + version=5
                                                         ↓
                                              Server: version=5 klopt → opgeslagen (version=6)
                                              WebSocket broadcast: org_chart_updated
                                                         ↓
Gebruiker B (had ook version=5)               ←  409 Conflict + huidige state
                                              UI: revert + toast "Iemand anders wijzigde dit"
```

---

## 10. Migratie & Backward Compatibility

### 10.1 Zero Breaking Changes Garantie

| Aspect | Garantie |
|--------|----------|
| Bestaande API endpoints | Ongewijzigd, geen signature changes |
| Database schema | Alleen ADDITIVE changes (nieuwe tabellen, nullable kolommen) |
| Interne agents | Geen wijzigingen aan `EnhancedBaseAgent` contract |
| Domain Packs | `domain_packs.yaml` en `DomainPackRegistry` ongewijzigd |
| Frontend routes | Geen bestaande routes verwijderd of verplaatst |
| Environment variables | Geen bestaande vars verwijderd, nieuwe vars optioneel met defaults |

### 10.2 Gradual Adoption

```
Tenant ZONDER Company (bestaand gedrag):
  → Domain Packs handmatig selecteren
  → Geen goal ancestry in executions
  → PolicyEngine zonder board metafoor
  → Geen externe agents
  → AgentExecutionContext.is_degraded = true

Tenant MET Company (na adoptie):
  → Automatische pack activatie op basis van afdelingen
  → Goal ancestry in elke execution
  → Board governance bovenop PolicyEngine
  → Externe agents via heartbeat
  → Company templates voor snelle setup
  → AgentExecutionContext.is_degraded = false
```

### 10.3 Migratie Strategie

```
Migratie 1: create_company_tables
  - companies, departments, goals
  - Indexes op tenant_id voor alle tabellen
  - RLS policies voor tenant isolation

Migratie 2: create_external_agent_tables
  - external_agents
  - Index op (tenant_id, status) voor heartbeat queries

Migratie 3: create_board_governance_tables
  - board_decisions
  - Index op (tenant_id, company_id, decision) voor approval queue

Migratie 4: create_company_template_tables
  - company_templates

Migratie 5: alter_existing_tables
  - procedure_executions: ADD goal_id (nullable, FK)
  - domain_packs: ADD company_id (nullable, FK)
  - Geen breaking changes — beide nullable

Alle migraties zijn ADDITIVE (geen DROP, geen ALTER bestaande kolommen).
Bestaande data blijft ongewijzigd functioneren.
```

### 10.4 Concurrent Editing & Conflict Resolution

> **Gap fix:** Optimistic locking voorkomt dat simultane edits data overschrijven.

```python
# Voeg version-veld toe aan Department en Goal modellen
class Department(Base):
    # ... bestaande velden ...
    version = Column(Integer, nullable=False, default=1, server_default="1")

# Update met conflict-detectie
async def update_department(
    self,
    dept_id: UUID,
    updates: DepartmentUpdate,
    expected_version: int,
    tenant_id: int,
) -> Department:
    stmt = (
        update(Department)
        .where(
            Department.id == dept_id,
            Department.version == expected_version,
            Department.tenant_id == tenant_id,  # tenant isolation
        )
        .values(**updates.dict(exclude_unset=True), version=Department.version + 1)
        .returning(Department)
    )
    result = await self._db.execute(stmt)
    row = result.fetchone()

    if row is None:
        raise ConflictError(
            "Department was modified by another user. Please refresh and retry."
        )

    # Broadcast via WebSocket
    await self._ws_manager.broadcast(
        f"org-chart:{dept_id.company_id}",
        {"type": "org_chart_updated", "payload": row.to_dict()},
    )
    return row
```

### 10.5 Feature Flags & Gradual Rollout

> **Gap fix:** Veilig uitrollen naar percentage tenants met kill switch.

```python
# src/core/feature_flags.py
COMPANY_LAYER_ROLLOUT: dict = {
    "enabled_tenant_ids": set(),       # Whitelist voor early adopters
    "rollout_percentage": 0,           # 0-100: percentage van alle tenants
    "kill_switch": False,              # True = volledig uitgeschakeld
}

def is_company_layer_enabled(tenant_id: int) -> bool:
    if COMPANY_LAYER_ROLLOUT["kill_switch"]:
        return False
    if tenant_id in COMPANY_LAYER_ROLLOUT["enabled_tenant_ids"]:
        return True
    return (tenant_id % 100) < COMPANY_LAYER_ROLLOUT["rollout_percentage"]
```

**Rollout schema:**

| Datum | Rollout % | Actie |
| ----- | --------- | ----- |
| Sprint 7 start | 0% | Alleen whitelisted tenants (intern testen) |
| Sprint 7 W2 | 10% | Early adopters + monitoring |
| Sprint 7 W3 | 25% | Controleer KPIs, geen regressions |
| Sprint 8 W1 | 50% | Halverwege evaluatie |
| Sprint 8 W2 | 100% | Volledige uitrol |

> **Kill switch:** Bij critical bug → `COMPANY_LAYER_ROLLOUT["kill_switch"] = True` via env var, herstart niet nodig (runtime config).

---

## 11. Security & Compliance

### 11.1 Heartbeat Protocol Security

| Risico | Mitigatie |
|--------|-----------|
| Ongeautoriseerde agent registratie | Alleen tenant admins kunnen agents registreren. API key wordt eenmalig getoond. |
| API key leakage | Keys worden bcrypt-gehasht opgeslagen. Rate limiting op heartbeat endpoint. |
| Spoofed heartbeats | Elke heartbeat gevalideerd met API key + tenant_id binding. |
| Malicious task output | Output doorloopt `PolicyEngine.validate_action()` voordat het wordt verwerkt. |
| DDoS via heartbeat endpoint | Rate limiting: max 10 heartbeats/minuut per agent. IP-based throttling. |
| Cross-tenant access | `ExternalAgent.tenant_id` enforced op alle queries. RLS policies op tabel. |

### 11.2 Template Security

| Risico | Mitigatie |
|--------|-----------|
| Secrets in export | Automated scrubbing van: API keys, wachtwoorden, tokens, webhook URLs met credentials |
| Malicious template import | Template validation: schema check, size limits, geen executable code |
| Template injection | Template definitions zijn declaratief (YAML/JSON), geen code execution |

### 11.3 Board Governance Security

| Risico | Mitigatie |
|--------|-----------|
| Unauthorized approvals | Board role → RBAC mapping enforced. Alleen assigned board members kunnen approven. |
| Approval bypass | `BoardService.approve()` valideert dat beslisser het juiste RBAC-recht heeft. |
| Audit trail | Elke board decision wordt gelogd met actor, timestamp, en reason. |

### 11.4 Compliance Impact

| Compliance Framework | Impact | Actie |
|---------------------|--------|-------|
| GDPR | Externe agents verwerken mogelijk persoonsgegevens | Data Processing Agreement template voor externe agents |
| EU AI Act | Externe agents zijn onderdeel van AI-systeem | Audit logging voor alle externe agent acties |
| SOC2 | Nieuw aanvalsoppervlak (heartbeat API) | Penetration test op heartbeat endpoints |

### 11.5 Rate Limiting per Endpoint

> **Gap fix:** Concrete limieten per endpoint zodat implementatie eenduidig is.

| Endpoint | Limiet | Scope | Overschreden → |
| -------- | ------ | ----- | -------------- |
| `POST /agents/{id}/heartbeat` | 10 req/min | Per agent | 429 Too Many Requests |
| `GET /agents/{id}/tasks/next` | 60 req/min | Per agent | 429 |
| `POST /companies` | 10 req/min | Per tenant | 429 |
| `POST /goals` | 100 req/min | Per tenant | 429 |
| `PUT /departments/{id}` | 30 req/min | Per user | 429 |
| `POST /board/decisions/{id}/approve` | Geen limiet | Per user | — (board members moeten altijd kunnen handelen) |
| `POST /onboarding/ai-match` | 5 req/min | Per tenant | 429 (LLM-call, kostbaar) |
| `POST /templates/companies/{id}/instantiate` | 3 req/min | Per tenant | 429 |

**Implementatie via bestaande `rate_limit_middleware.py`:**

```python
# Heartbeat endpoint — sliding window per agent_id
@router.post("/agents/{agent_id}/heartbeat")
@rate_limit(key="agent_id", limit=10, window_seconds=60)
async def heartbeat(agent_id: UUID, ...): ...

# Board decisions — geen limiet, maar audit elke actie
@router.post("/board/decisions/{decision_id}/approve")
@audit_log(action="board.approve")
async def approve_decision(decision_id: UUID, ...): ...
```

---

## 12. Testing Strategie

### 12.1 Test Coverage Targets

| Module | Target | Rationale |
|--------|--------|-----------|
| Company Service | 95% | Core business logic |
| Goal Service | 95% | Core business logic |
| External Agent Service | 98% | Security-critical (open protocol) |
| Board Service | 95% | Governance-critical |
| Template Export/Import | 95% | Data integrity |
| Heartbeat Protocol | 98% | External-facing API |
| Frontend components | 80% | UI complexity |

### 12.2 Nieuwe Test Suites

```
tests/
├── unit/
│   ├── company/
│   │   ├── test_company_service.py          # Company CRUD + template instantiation
│   │   ├── test_goal_service.py             # Goal hierarchy + ancestry resolver
│   │   ├── test_department_service.py       # Department CRUD + pack activation
│   │   └── test_board_service.py            # Board routing + approval logic
│   ├── external_agents/
│   │   ├── test_heartbeat_protocol.py       # Heartbeat validation + timeout
│   │   ├── test_external_agent_bridge.py    # Bridge → DomainPackOrchestrator
│   │   └── test_task_dispatch.py            # Webhook + queue dispatch
│   └── templates/
│       ├── test_template_export.py          # Export met secret scrubbing
│       └── test_template_import.py          # Import met collision handling
├── integration/
│   ├── test_company_onboarding_flow.py      # Template → Company → Packs → Goals
│   ├── test_external_agent_e2e.py           # Register → Heartbeat → Task → Complete
│   ├── test_goal_ancestry_in_execution.py   # Execution draagt goal chain mee
│   ├── test_board_approval_flow.py          # PolicyEngine → Board → Approval → Execute
│   └── test_mixed_agent_workflow.py         # Interne + externe agents in 1 pack
├── e2e/
│   ├── test_company_setup_wizard.py         # Playwright: volledige onboarding
│   └── test_board_approval_ui.py            # Playwright: approve/reject flow
└── security/
    ├── test_external_agent_isolation.py     # Externe agent kan niet cross-tenant
    ├── test_heartbeat_auth.py               # Alleen geauthenticeerde heartbeats
    ├── test_template_secret_scrubbing.py    # Geen secrets in exports
    └── test_board_rbac.py                   # Alleen board members kunnen approven
```

### 12.3 Meetbare Acceptatiecriteria per P0 Feature

#### AC-1: Company Model (P0)

| # | Criterium | Verificatie |
|---|-----------|-------------|
| AC-1.1 | `POST /api/v1/companies` retourneert 201 met company_id binnen 500ms | Integration test |
| AC-1.2 | Company met 5 departments aanmaken duurt < 2s end-to-end | Performance test |
| AC-1.3 | Org chart GET retourneert correcte tree-structuur | Unit test |
| AC-1.4 | Tenant A kan company van tenant B niet zien of wijzigen | Security test |
| AC-1.5 | Company zonder departments aanmaken is valide (ZZP use case) | Unit test |

#### AC-2: Goal Ancestry (P0)

| # | Criterium | Verificatie |
|---|-----------|-------------|
| AC-2.1 | `GET /goals/{id}/ancestry` retourneert volledige chain binnen 10ms | Performance test |
| AC-2.2 | Goal ancestry is aanwezig in `AgentExecutionContext` bij elke `process_task()` call | Integration test |
| AC-2.3 | Ancestry cache invalidatie werkt correct bij goal update | Unit test |
| AC-2.4 | Goal tree visualisatie toont max 4 niveaus met correcte progress rollup | E2E test |
| AC-2.5 | ProcedureExecution met goal_id bevat volledige goal_chain in audit_trail | Integration test |

#### AC-3: AgentExecutionContext (P0)

| # | Criterium | Verificatie |
|---|-----------|-------------|
| AC-3.1 | Intern agent ontvangt `AgentExecutionContext` met alle verplichte velden | Unit test |
| AC-3.2 | Extern agent `GET /tasks/next` response bevat volledige `AgentExecutionContext` als JSON | Integration test |
| AC-3.3 | Context met ontbrekende `company_id` markeert `is_degraded=true` en logt metric | Unit test |
| AC-3.4 | `validate_completeness()` retourneert correcte missing fields lijst | Unit test |
| AC-3.5 | Bestaande agents zonder Company Layer werken ongewijzigd met degraded context | Regression test |

---

## 13. Observability & Metrics

### 13.1 Goal Focus Metrics (Doelbesef)

Deze metrics meten of het systeem daadwerkelijk het bedrijfsdoel als stuurmechanisme gebruikt — het kernidee van deze architectuur.

| KPI | Baseline | Target (3 maanden) | Meetmethode | Alarm threshold |
|-----|----------|-------------------|-------------|-----------------|
| % taken met volledige context (`is_degraded=false`) | 0% | 70% | `AgentExecutionContext.is_degraded` counter | < 50% na 2 maanden |
| % beslissingen met traceerbare goal-alignment score | 0% | 60% | `goal_alignment_score IS NOT NULL` in audit trail | < 40% na 2 maanden |
| Gemiddelde goal alignment score | n/a | >= 0.65 | `AVG(goal_alignment_score)` per week | < 0.50 gemiddeld |
| % MISALIGNED acties dat daadwerkelijk geëscaleerd wordt | n/a | 100% | `MISALIGNED` events vs `BoardDecision` count | < 90% |
| % pack activaties met complete audit trail (R2) | 0% | 100% | `PackActivationResult` records vs activations | < 95% |
| % governance beslissingen met goal + budget context (R3) | 0% | 100% | `BoardDecision` records met non-null `goal_id` en `budget_impact` | < 90% |
| Goal ancestry depth per execution (gem.) | 0 | >= 2.5 | `AVG(GoalChain.depth())` | < 1.5 |

### 13.2 Performance Metrics

| KPI | Target | Meetmethode |
|-----|--------|-------------|
| Heartbeat latency (p95) | < 50ms | Prometheus histogram |
| Goal ancestry lookup | < 10ms | Prometheus histogram |
| Company creation (incl. pack activation) | < 3s | Prometheus histogram |
| Template instantiation | < 5s | Prometheus histogram |
| External agent task dispatch | < 200ms | Prometheus histogram |

### 13.3 Cache Coherency

> **Gap fix:** Ancestry cache (Redis) kan stale worden na goal-updates. Hier de invalidatie-strategie.

**Cache keys en TTLs:**

| Cache key | TTL | Geïnvalideerd wanneer |
| --------- | --- | --------------------- |
| `goal_ancestry:{goal_id}` | 1 uur | Goal zelf of enige voorouder gewijzigd |
| `goal_progress:{company_id}` | 5 min | `goal.progress_pct` geüpdatet |
| `pack_activation:{company_id}:{dept_id}` | 24 uur | Afdeling gewijzigd of pack (de)geactiveerd |
| `heartbeat_status:{agent_id}` | 2 min | Elke heartbeat overschrijft vorige waarde |

**Invalidatie bij goal-update:**

```python
async def update_goal(self, goal_id: UUID, updates: GoalUpdate) -> Goal:
    async with self._db.begin():
        goal = await self._db.get(Goal, goal_id)
        goal.update(**updates.dict(exclude_unset=True))
        await self._db.flush()

    # Invalideer ancestry cache voor dit goal EN alle descendants
    affected_ids = await self._get_descendant_ids(goal_id)
    affected_ids.add(goal_id)

    cache_keys = [f"goal_ancestry:{gid}" for gid in affected_ids]
    cache_keys.append(f"goal_progress:{goal.company_id}")
    await self._redis.delete(*cache_keys)

    # Publiceer event voor WebSocket real-time update
    await self._events.publish("goal.updated", {
        "goal_id": str(goal_id),
        "company_id": str(goal.company_id),
        "invalidated_cache_keys": cache_keys,
    })
```

---

## 14. Rollout Plan

### 14.1 MVP (Fase 1 — Must Ship)

| Feature | Scope | Waarom MVP |
|---------|-------|------------|
| Company Model | CRUD + org chart (departments) | Fundament voor alles |
| Goal Ancestry | Hiërarchie + ancestry resolver + OODA integratie | Kernbelofte van de PRD |
| AgentExecutionContext | Canoniek contextobject in alle agent executions | Gouden Regel R1 enforcement |
| Pack Activation (basic) | Score model + audit trail + confidence thresholds | Gouden Regel R2 enforcement |
| Goal Alignment Validator | Pre-execution validatie (ALIGNED/DRIFT/MISALIGNED) | Kernbelofte operationeel maken |

### 14.2 Post-MVP (Fase 2+ — Alleen na bewezen MVP waarde)

| Feature | Phase Gate | Bewijs vereist voordat fase start |
|---------|------------|-----------------------------------|
| External Agents + Heartbeat | Fase 2 gate | MVP KPI: >= 20% tenants met Company, >= 15% executions met goal_id |
| Board Governance | Fase 3 gate | Fase 2 KPI: >= 1 externe agent succesvol in productie |
| Company Templates | Fase 3 gate | MVP KPI: onboarding time < 10 minuten zonder template |
| Template Marketplace | Fase 3 gate | >= 5 tenants hebben company export gebruikt |
| Simplified Onboarding | Fase 4 gate | >= 3 templates beschikbaar en getest |

> **Consequentie:** Als MVP KPIs na 6 weken niet gehaald worden, wordt Fase 2 uitgesteld en wordt eerst geïnvesteerd in MVP-adoptie. Features worden niet gebouwd op hoop — alleen op bewezen behoefte.
>
> ⚠️ **BLOCKER:** Fase 1 kan pas starten nadat **Fase 6.2 (Orphaned Services Cleanup)** en **Fase 6.3 (WebSocket Config & Health Checks)** zijn voltooid. Deze cleanups zijn noodzakelijk voor stabiele Company Layer infra. Status: beide fases zijn nog open task descriptions (SPRINT2-6_SUMMARY.md: 2026-02-25).

---

## 15. Appendix

### 15.1 Terminologie

| Term | Definitie |
|------|-----------|
| **Company** | Virtueel bedrijfsmodel binnen een tenant, met organigram en doelen |
| **Department** | Afdeling binnen een Company, gekoppeld aan Domain Packs |
| **Goal Ancestry** | Hiërarchische doelketen: Mission → Strategic → Project → Task |
| **Heartbeat Protocol** | Open protocol waarmee externe agents communiceren met het platform |
| **Board Governance** | Niet-technische governance-metafoor bovenop PolicyEngine |
| **Company Template** | Exporteerbare bedrijfsstructuur die packs, goals, en config bundelt |
| **External Agent** | Agent die buiten SanskritiSetu draait maar via heartbeat meedoet |
| **ExternalAgentBridge** | Adapter die externe agents als interne agents presenteert |
| **Pack Activation** | Automatisch activeren van Domain Packs op basis van bedrijfsstructuur |
| **AgentExecutionContext** | Canoniek contextobject dat ELKE agent (intern + extern) ontvangt |
| **GoalChain** | Immutable doelketen binnen AgentExecutionContext |
| **Goal Alignment Validator** | Pre-execution validatie die checkt of een actie past bij de actieve goal chain |
| **PackActivationResult** | Auditeerbaar resultaat van pack matching met score, reden, en confidence |

### 15.2 Verwijzingen

- [Paperclip AI GitHub](https://github.com/paperclipai/paperclip)
- [Paperclip Website](https://paperclip.ing/)
- `CLAUDE.md` — Project conventions en commands
- `AGENTS.md` — Agent architectuur en project guide

---

*Dit document is een levend document en wordt bijgewerkt naarmate de implementatie vordert.*

**Goedkeuring vereist van:**
- [ ] Product Owner
- [ ] Lead Architect
- [ ] Security Lead
- [ ] Frontend Lead
- [ ] Backend Lead
