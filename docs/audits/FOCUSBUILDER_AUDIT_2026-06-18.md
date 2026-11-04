# FocusBuilder Audit — 2026-06-18

Uitgevoerd door: Claude (Sonnet 4.6) — statische analyse van alle bronbestanden
Datum: 2026-06-18
Trigger: GET /api/v1/focus-builder/flows retourneert HTTP 500

---

## Executive Summary

De FocusBuilder feature is gebouwd op twee parallelle, incompatibele implementaties die nooit zijn samengevoegd. De meest urgente oorzaak van de 500-fout is dat `ActivePiecesClient()` wordt aangemaakt op het moment dat een HTTP-verzoek binnenkomt, en direct een `ValueError` gooit als de AP-credentials ontbreken in de omgeving — dit raakt elke endpoint, inclusief het simpele read-only `GET /flows`. Bovendien bestaat de `flows`-databasetabel niet: geen enkele Alembic-migratie maakt hem aan. Als de credentials wel beschikbaar zijn, crasht het systeem toch zodra het de database probeert te bereiken. Drie aanvullende problemen (dubbele modelnamen, repository die zelf commit, AP-aanroep voor DB-opslaan) verdiepen de instabiliteit voor schrijfoperaties. De frontend roept de juiste endpoints aan maar ontvangt structureel fouten terug.

---

## 1. Architectuuroverzicht

### Wat FocusBuilder is

FocusBuilder is het visuele workflow-bouwsysteem van SanskritiSetu. Gebruikers tekenen stromen van stappen ("nodes" en "edges") in een React Flow canvas. Bij opslaan wordt de visuele representatie gecompileerd naar het formaat van **ActivePieces** (een self-hosted workflow-engine), waarna de flow daar wordt uitgevoerd.

### Onderdelen en samenhang

```
Browser (React Flow canvas)
        |
        | HTTP/WebSocket
        v
FastAPI Backend
  src/core/api/v1/focus_builder/
    proxy.py               — kiest embedded vs. remote modus
    router.py              — composite router (ADR-033 Laag 2)
      flows_router.py      — CRUD /flows
      execution_router.py  — /flows/{id}/execute, /runs/{id}
      pieces_router.py     — /pieces, /pieces/{name}/schema, /pieces/sync
      ai_router.py         — /ai/suggest, /ai/generate
      ws_chat_router.py    — WebSocket chat
      ws_status_router.py  — WebSocket status
    shared.py              — gedeelde helpers, get_focus_builder_service()
    dependencies.py        — AgentCouncil, Digital Twin
        |
        | Depends(get_focus_builder_service)
        v
  src/domains/flows/service.py   (FocusBuilderService — ACTIEF)
    |           |
    |           v
    |     src/domains/flows/repository.py  (FlowRepository)
    |           |
    |           v
    |     src/domains/flows/models.py      (Flow, PiecesCacheMetadata)
    |           tabelnamen: "flows", "focus_builder_pieces_cache"
    |
    v
  src/core/activepieces/client.py  (ActivePiecesClient)
        |
        | HTTP
        v
  ActivePieces Engine (extern, self-hosted)

  src/core/focus_builder/service.py  (FocusBuilderService — INACTIEF, oud)
  src/core/focus_builder/models.py   (FocusBuilderFlow — tabelnaam: "focus_builder_flows")
  src/core/focus_builder/repositories.py
```

De proxy (`proxy.py`) kiest in `embedded`-modus (standaard) de router uit `src/core/api/v1/focus_builder/router.py`. Die router gebruikt via `shared.py` de **nieuwe** service uit `src/domains/flows/service.py`. De **oude** service in `src/core/focus_builder/service.py` is niet meer gekoppeld aan een router maar staat nog in de codebase.

---

## 2. Huidige Staat

### 2.1 Wat werkt goed

| Onderdeel | Bewijs |
|-----------|--------|
| Router-registratie (ADR-033) | `src/core/api/registries/workflows.py:44` roept `get_focus_builder_router()` correct aan via `proxy.py` |
| Proxy mode-selectie | `proxy.py:311-336` selecteert embedded vs. remote op basis van `FOCUSBUILDER_SERVICE_MODE` |
| Frontend API-paden | `frontend/src/lib/api/wave-a-paths.ts:30-34` en `client.ts:394-426` roepen `/api/v1/focus-builder/flows` e.d. aan — correct |
| Rate limiting | Alle endpoints hebben `@limiter.limit(...)` decorators conform de projectstandaard |
| AgentCouncil governance gate op execute | `execution_router.py:60-108` voert de governance-check uit voor flow-executie |
| Tenant isolatie in repository | `repository.py:23,44` filtert altijd op `Flow.tenant_id == self.tenant_id` |
| OpenTelemetry spans | `shared.py:36-48` voegt tenant- en user-attributen toe aan spans |
| Loggen met exc_info | `shared.py:117-119`, `flows_router.py:76`, `execution_router.py:82` loggen correct met `exc_info=True` |
| Digital Twin tracking (best_effort) | `shared.py:59-76` omhult Twin-tracking met `best_effort` zodat het primaire pad niet breekt |

### 2.2 Wat werkt niet (kapot)

#### KRITIEK-1: Elke endpoint retourneert 500 als AP-credentials ontbreken

- **Bestand:** `src/domains/flows/service.py:22`
- **Code:** `self.ap_client = ActivePiecesClient()`
- **Oorzaak:** `ActivePiecesClient.__init__` (`src/core/activepieces/client.py:74-77`) gooit direct een `ValueError` als `AP_SERVICE_EMAIL` of `AP_SERVICE_PASSWORD` niet gezet zijn in de environment.
- **Wanneer:** Bij elke HTTP-aanroep, ook bij read-only `GET /flows`. De dependency-injectie `get_focus_builder_service` instantieert `FocusBuilderService`, die `ActivePiecesClient()` aanroept in `__init__`. De `ValueError` wordt niet opgevangen en escaleert als HTTP 500.
- **HTTP-respons:** `500 Internal Server Error` — geen verdere details zichtbaar voor de client.

#### KRITIEK-2: `flows`-tabel bestaat niet in de database

- **Bestand:** `src/domains/flows/models.py:17` — `__tablename__ = "flows"`
- **Verificatie:** Grep over alle 31+ Alembic-migraties in `alembic/versions/` vindt **nul** bestanden die `op.create_table` aanroepen voor `"flows"` of `"focus_builder_pieces_cache"`.
- **Oorzaak:** De `domains/flows/` package is geschreven zonder bijbehorende Alembic-migratie. De `src/core/focus_builder/models.py` hanteert `"focus_builder_flows"` als tabelnaam — ook die tabel ontbreekt in de migraties.
- **Gevolg:** Bij elke DB-query crasht SQLAlchemy met `ProgrammingError: relation "flows" does not exist` → HTTP 500. Dit is de tweede zelfstandige oorzaak van de 500 als KRITIEK-1 niet aanwezig is.

#### KRITIEK-3: Twee modellen claimen dezelfde tabelnaam met verschillende kolommen

- **Bestand 1:** `src/core/focus_builder/models.py:57` — `FocusBuilderPieceCache.__tablename__ = "focus_builder_pieces_cache"` — kolommen: `piece_name`, `display_name`, `logo_url`, `actions`, `triggers`, `last_synced_at` (geen `description`, `piece_version`, `auth_config`)
- **Bestand 2:** `src/domains/flows/models.py:70` — `PiecesCacheMetadata.__tablename__ = "focus_builder_pieces_cache"` — kolommen: alles van model 1 plus `piece_version`, `description`, `auth_config`
- **Gevolg:** SQLAlchemy-mapper-conflict bij import. Beide modellen gebruiken `extend_existing=True`, waardoor de laatste die wordt geïmporteerd de tabel "wint". `_sync_pieces_catalog` schrijft `piece_version`/`description`/`auth_config` via `PiecesCacheMetadata`; als de mapper al geregistreerd is via `FocusBuilderPieceCache`, missen die kolommen → `OperationalError` bij upsert.

### 2.3 Wat deels werkt maar onbetrouwbaar is

**HOOG-1: `create_flow` roept ActivePieces aan vóór DB-opslaan**
- `src/domains/flows/service.py:43-72` roept AP aan in stap 2, DB-opslaan in stap 3.
- Als AP uitvalt tussen stap 2 en 3: de flow bestaat in AP maar niet in de DB → dangling state.
- De **oude** `src/core/focus_builder/service.py:49-60` doet het omgekeerde (DB eerst, dan AP) — de correcte volgorde.

**HOOG-2: Repository commit() in elke write-methode**
- `src/domains/flows/repository.py:61,77,89,147` roept `await self.db.commit()` aan na elke schrijfoperatie.
- `get_db()` (sessie-manager) commit ook bij succesvolle exit. Dubbele commit: benign in happy-path, maar maskeert fouten in de afhandelaar en verbreekt transactieatomiciteit bij gecombineerde operaties.

**HOOG-3: `update_flow` en `execute_flow` gooien `ValueError` als AP-sync nog niet heeft plaatsgevonden**
- `src/domains/flows/service.py:103-104`: `raise ValueError("Flow has not been synced to ActivePieces yet")`
- `flows_router.py:179-188` vangt `ValueError` als HTTP 400.
- Elke flow die is aangemaakt terwijl AP uitviel heeft `activepieces_flow_id = None` → update en execute retourneren misleidende 400-fout in plaats van 503/409.

**HOOG-4: `get()` + `expunge()` na elke leesoperatie**
- `src/domains/flows/repository.py:27,51` — `self.db.expunge(flow)` ontkoppelt het ORM-object van de sessie na lezen.
- `update()` (regel 69) roept eerst `self.get(flow_id)` aan, waarna het via `setattr` probeert te schrijven naar een losgekoppeld object — dit werkt alleen omdat `expire_on_commit=False` gezet is. Bij eventuele relatie-toegang of deferred columns volgt `DetachedInstanceError`.

**MIDDEL-1: `pieces_router.py:89` roept private methode aan via router**
- `await service._sync_pieces_catalog()` — roept een private methode rechtstreeks aan vanuit een router. Schending van de service-boundary.

---

## 3. Root Cause Analyse

### Fout bij GET /api/v1/focus-builder/flows

```
HTTP GET /api/v1/focus-builder/flows
  → FastAPI dependency resolution
  → get_focus_builder_service()
      → FocusBuilderService(db=db, tenant_id=tenant_id)
          → self.ap_client = ActivePiecesClient()   # src/domains/flows/service.py:22
              → config.activepieces_email is None or ''
              → raise ValueError(
                    "ActivePieces credentials not configured "
                    "(AP_SERVICE_EMAIL/AP_SERVICE_PASSWORD)"
                )                                   # src/core/activepieces/client.py:75-77
  → ValueError propagates, not caught by FastAPI default handler
  → HTTP 500 Internal Server Error
```

Als AP-credentials wel aanwezig zijn, verloopt de aanroep:
```
  → FocusBuilderService instantiatie slaagt
  → list_flows handler
  → service.repository.list(skip=0, limit=100)
      → await self.db.execute(select(Flow)...)
          → ProgrammingError: relation "flows" does not exist
  → Niet gevangen in list_flows (geen try/except om repository-aanroep)
  → HTTP 500 Internal Server Error
```

`list_flows` (regel 99) heeft geen `try/except` blok — onverwachte DB-fouten escaleert direct als 500.

### Oorzaak van de twee parallelle implementaties

De codebase bevat twee `FocusBuilderService`-klassen. De **oude** leeft in `src/core/focus_builder/service.py` en gebruikt `FocusBuilderFlow` (`__tablename__ = "focus_builder_flows"`). De **nieuwe** leeft in `src/domains/flows/service.py` en gebruikt `Flow` (`__tablename__ = "flows"`). De ADR-033-router is op een gegeven moment overgezet naar de nieuwe, maar:
1. Er zijn geen Alembic-migraties voor de nieuwe tabellen geschreven.
2. De oude modellen en service zijn nooit verwijderd.
3. Het `FocusBuilderPieceCache`-model uit de oude implementatie registreert zich op dezelfde tabelnaam als het `PiecesCacheMetadata`-model uit de nieuwe implementatie.

---

## 4. Impactanalyse (applicatiebreed)

| ID | Prioriteit | Beschrijving | Geraakt onderdeel |
|----|-----------|--------------|-------------------|
| C-1 | KRITIEK | Elke focus-builder endpoint → 500 als AP-credentials ontbreken | Alle 7 sub-routers; frontend `focusBuilderApi.*` |
| C-2 | KRITIEK | `flows`-tabel ontbreekt → 500 bij elke DB-aanroep | `GET /flows`, `GET /flows/{id}`, `DELETE`, `PUT` |
| C-3 | KRITIEK | Mapper-conflict `focus_builder_pieces_cache` → crash bij `_sync_pieces_catalog` | `POST /pieces/sync`, `GET /pieces` (lege cache) |
| H-1 | HOOG | AP-eerst volgorde in `create_flow` → dangling AP-state bij DB-fout | `POST /flows` |
| H-2 | HOOG | Dubbele commit in repository → transactie-onveiligheid | Alle schrijf-endpoints |
| H-3 | HOOG | `ValueError` bij niet-gesyncde flow → misleidende 400 | `PUT /flows/{id}`, `POST /flows/{id}/execute` |
| H-4 | HOOG | `expunge()` na leesoperatie → potentiële `DetachedInstanceError` | `GET /flows/{id}`, `PUT /flows/{id}` |
| M-1 | MIDDEL | Router roept private `_sync_pieces_catalog()` aan | `POST /pieces/sync` |
| M-2 | MIDDEL | Twee parallelle service-implementaties zonder deprecatieplan | Elk toekomstig onderhoud |
| M-3 | MIDDEL | Geen falende architecture-test voor ontbrekende migratie (CLAUDE.md schending) | CI — slaagt terwijl productie-DB kapot is |
| L-1 | LAAG | Legacy `src/core/api/focus_builder_endpoints.py` nooit verwijderd | Codebase overhead |
| L-2 | LAAG | Frontend `createFlow` gebruikt hardcoded pad i.p.v. `WAVE_A_PATHS` | `client.ts:404` |
| L-3 | LAAG | Pervasieve `Any`-annotaties in alle FocusBuilder-bestanden | mypy/pyright dekking |

---

## 5. Oplossingsplan

### 5.1 Directe fixes (kapotte dingen repareren)

#### Fix C-1: Lazy instantiatie van `ActivePiecesClient`

**Bestand:** `src/domains/flows/service.py`

```python
# VOOR (regel 18-23):
def __init__(self, db: AsyncSession, tenant_id: int) -> None:
    self.db = db
    self.tenant_id = tenant_id
    self.repository = FlowRepository(db, tenant_id)
    self.ap_client = ActivePiecesClient()

# NA:
def __init__(self, db: AsyncSession, tenant_id: int) -> None:
    self.db = db
    self.tenant_id = tenant_id
    self.repository = FlowRepository(db, tenant_id)
    self._ap_client: ActivePiecesClient | None = None

@property
def ap_client(self) -> ActivePiecesClient:
    """Lazy-initialised AP client — credentials only checked on first use."""
    if self._ap_client is None:
        self._ap_client = ActivePiecesClient()
    return self._ap_client
```

Na deze fix mislukt `GET /flows` (en andere read-endpoints die AP niet aanraken) niet langer vanwege ontbrekende credentials.

#### Fix C-2: Alembic-migratie voor `flows` en `focus_builder_pieces_cache`

Maak een nieuw migratiebestand aan:
**Bestand:** `alembic/versions/<timestamp>_add_focus_builder_tables.py`

```python
"""add focus_builder tables: flows and focus_builder_pieces_cache

Revision ID: <gegenereerd>
Revises: <vorige head>
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '<gegenereerd>'
down_revision = '<vorige head>'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'flows',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.Integer(),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('react_flow_graph',
                  postgresql.JSONB().with_variant(sa.JSON(), 'sqlite'),
                  nullable=False),
        sa.Column('ui_version', sa.String(20), nullable=True),
        sa.Column('activepieces_flow_id', sa.String(255),
                  unique=True, nullable=True),
        sa.Column('activepieces_project_id', sa.String(255), nullable=True),
        sa.Column('activepieces_version', sa.Integer(),
                  server_default='1', nullable=True),
        sa.Column('activepieces_flow_json',
                  postgresql.JSONB().with_variant(sa.JSON(), 'sqlite'),
                  nullable=True),
        sa.Column('is_published', sa.Boolean(),
                  server_default='false', nullable=True),
        sa.Column('last_executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('execution_count', sa.Integer(),
                  server_default='0', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('ix_flows_tenant_id', 'flows', ['tenant_id'])
    op.create_index('ix_flows_activepieces_flow_id', 'flows',
                    ['activepieces_flow_id'], unique=True)

    op.create_table(
        'focus_builder_pieces_cache',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('piece_name', sa.String(255), unique=True, nullable=False),
        sa.Column('piece_version', sa.String(50), nullable=True),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('logo_url', sa.String(500), nullable=True),
        sa.Column('actions',
                  postgresql.JSONB().with_variant(sa.JSON(), 'sqlite'),
                  nullable=True),
        sa.Column('triggers',
                  postgresql.JSONB().with_variant(sa.JSON(), 'sqlite'),
                  nullable=True),
        sa.Column('auth_config',
                  postgresql.JSONB().with_variant(sa.JSON(), 'sqlite'),
                  nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
    )
    op.create_index('ix_focus_builder_pieces_cache_piece_name',
                    'focus_builder_pieces_cache', ['piece_name'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_focus_builder_pieces_cache_piece_name',
                  table_name='focus_builder_pieces_cache')
    op.drop_table('focus_builder_pieces_cache')
    op.drop_index('ix_flows_activepieces_flow_id', table_name='flows')
    op.drop_index('ix_flows_tenant_id', table_name='flows')
    op.drop_table('flows')
```

Na aanmaken: controleer met `alembic -c src/alembic.ini heads` (moet precies 1 tonen).

#### Fix C-3: Verwijder `FocusBuilderPieceCache` uit de oude modellen

Het mapper-conflict oplossen door de oude klasse te verwijderen of te hernoemen.

**Bestand:** `src/core/focus_builder/models.py:51-76`

```python
# VOOR:
class FocusBuilderPieceCache(Base):
    __tablename__ = "focus_builder_pieces_cache"
    __table_args__ = {"extend_existing": True}
    ...

# NA: verwijder de hele klasse.
# De PiecesCacheMetadata in src/domains/flows/models.py is de authoritative definitie.
# Pas ook src/core/focus_builder/repositories.py aan als die FocusBuilderPieceCache importeert.
```

#### Fix H-1: DB-eerst volgorde in `create_flow`

**Bestand:** `src/domains/flows/service.py:35-86`

```python
# NA (herstructureer de methode):
async def create_flow(
    self, name: str, graph: ReactFlowGraph, created_by: int | None = None
) -> Any:
    # Stap 1: Compileer (geen side-effects)
    try:
        ap_flow_json = FlowTransformer.react_flow_to_activepieces(graph.dict())
    except Exception as e:
        raise ValueError(f"Invalid Flow Graph: {str(e)}")

    # Stap 2: Sla op in DB (primaire persistentie — moet first happen)
    flow_record = await self.repository.create(
        {
            "name": name,
            "react_flow_graph": graph.dict(),
            "activepieces_flow_json": ap_flow_json,
            "created_by": created_by,
            # activepieces_flow_id bewust None — wordt gevuld in stap 3
        }
    )

    # Stap 3: Sync naar ActivePieces (graceful degradation)
    try:
        project_id = await self._get_tenant_ap_project_id()
        flow_def = {
            "displayName": name,
            "projectId": project_id,
            "trigger": ap_flow_json.get("trigger"),
        }
        ap_response = await self.ap_client.create_flow(project_id, flow_def)
        ap_flow_id = cast(str | None, ap_response.get("id"))
        if ap_flow_id:
            if "nextAction" in ap_flow_json:
                await self.ap_client.update_flow(ap_flow_id, ap_flow_json)
            await self.repository.update(
                flow_record.id,
                {"activepieces_flow_id": ap_flow_id,
                 "activepieces_project_id": project_id},
            )
            flow_record.activepieces_flow_id = ap_flow_id
    except Exception as ap_error:
        logger.warning(
            "create_flow_ap_sync_failed: %s: %s",
            type(ap_error).__name__, ap_error, exc_info=True
        )
        # Flow is veilig opgeslagen in DB; AP-sync kan later opnieuw worden geprobeerd.

    return flow_record
```

#### Fix H-2: Verwijder `commit()` uit repository-methoden

**Bestand:** `src/domains/flows/repository.py` — vervang in `create`, `update`, `delete`, `upsert_piece`:

```python
# VOOR (voorbeeld in create, regel 61-63):
await self.db.commit()
await self.db.refresh(flow)
self.db.expunge(flow)

# NA:
await self.db.flush()
await self.db.refresh(flow)
# Verwijder expunge() — sessie-manager beheert lifecycle
```

Verwijder ook alle `self.db.expunge(...)` aanroepen in `get()` (regel 27) en `list()` (regel 51). De sessie-manager (`get_db` in `database.py`) commit bij succesvolle exit.

#### Fix H-4: Verwijder `expunge()` uit leesoperaties

**Bestand:** `src/domains/flows/repository.py:27,51`

```python
# VOOR (get, regel 25-28):
flow = result.scalars().first()
if flow:
    self.db.expunge(flow)
return flow

# NA:
return result.scalars().first()
```

```python
# VOOR (list, regel 49-51):
flows = list(result.scalars().all())
for flow in flows:
    self.db.expunge(flow)
return flows

# NA:
return list(result.scalars().all())
```

### 5.2 Verbeteringen (wat kan beter)

#### Verbetering 1: `list_flows` needs try/except around DB call

**Bestand:** `src/core/api/v1/focus_builder/flows_router.py:99`

```python
# VOOR:
flows = await service.repository.list(skip=skip, limit=limit)

# NA:
try:
    flows = await service.repository.list(skip=skip, limit=limit)
except Exception as e:
    logger.error("list_flows_db_error", user_id=current_user.id, error=str(e), exc_info=True)
    raise HTTPException(
        status_code=500,
        detail=create_error_response("INTERNAL_ERROR", "Failed to retrieve flows"),
    )
```

#### Verbetering 2: Maak `_sync_pieces_catalog` publiek

**Bestand:** `src/domains/flows/service.py:200` — hernoem naar `sync_pieces_catalog` (zonder leading underscore).
**Bestand:** `src/core/api/v1/focus_builder/pieces_router.py:89` — pas de aanroep aan.

#### Verbetering 3: Fix hardcoded pad in frontend `createFlow`

**Bestand:** `frontend/src/lib/api/client.ts:404`

```typescript
// VOOR:
createFlow: (data: { name: string; graph: unknown }) =>
  apiClient.post<unknown>('/focus-builder/flows', data),

// NA:
createFlow: (data: { name: string; graph: unknown }) =>
  apiClient.post<unknown>(WAVE_A_PATHS.focusFlows, data),
```

#### Verbetering 4: Voeg `503` toe als HTTP-status voor AP-onbeschikbaarheid bij update/execute

**Bestand:** `src/core/api/v1/focus_builder/flows_router.py:179-188` en `execution_router.py:128-137`

Verander de `except ValueError` handlers zodat "Flow has not been synced to ActivePieces yet" en AP-gerelateerde fouten een HTTP `503` teruggeven in plaats van `400`.

### 5.3 Architecturele aanbevelingen (lange termijn)

1. **Kies één service-implementatie en verwijder de andere.** `src/domains/flows/` is de actieve implementatie. `src/core/focus_builder/service.py`, `repositories.py`, `models.FocusBuilderFlow`, en `FocusBuilderPieceCache` kunnen worden verwijderd zodra de migratie en de nieuwe service stabiel zijn. Tot die tijd: laat de oude service-bestanden staan maar verwijder tenminste `FocusBuilderPieceCache` (Fix C-3).

2. **Voeg een background-job toe voor AP-synchronisatie.** De huidige aanpak (AP-sync inline in de HTTP-aanroep) maakt elke write-operatie afhankelijk van AP-beschikbaarheid. Een Dramatiq-task `sync_flow_to_ap.py` die bij DB-create wordt gepland, zou de HTTP-aanroep ontkoppelen van de AP-state.

3. **Voeg `activepieces_sync_status` kolom toe aan `flows` tabel.** Enum: `pending | synced | failed`. Dit maakt het mogelijk om flows te tonen waarvan de AP-sync nog loopt of mislukt is, zonder misleidende 400/503 fouten.

4. **Verwijder `src/core/api/focus_builder_endpoints.py`.** Dit legacy-bestand (L-1) is vervangen door de ADR-033 router maar nooit opgeruimd.

---

## 6. Implementatievolgorde

De volgorde is op basis van afhankelijkheden en minste kans op regressie:

1. **Fix C-1** — Lazy AP-client in `src/domains/flows/service.py` (1 regel toevoegen, `__init__` aanpassen). Geen migratieafhankelijkheid. Maakt onmiddellijk testen van de read-flow mogelijk zodra de DB-fix er is.

2. **Fix C-2** — Schrijf Alembic-migratie voor `flows` en `focus_builder_pieces_cache`. Draai `alembic upgrade head`. Verificatie: `\dt` in psql toont beide tabellen.

3. **Fix C-3** — Verwijder `FocusBuilderPieceCache` uit `src/core/focus_builder/models.py`. Controleer alle imports.

4. **Fix H-2 + H-4** — Verwijder `commit()` en `expunge()` uit `FlowRepository`. Dit moet in één commit om consistentie te garanderen.

5. **Fix H-1** — Herstructureer `create_flow` naar DB-eerst volgorde.

6. **Verbetering 1** — Voeg try/except toe in `list_flows`.

7. **Verbetering 2** — Hernoem `_sync_pieces_catalog` naar `sync_pieces_catalog`.

8. **Verbetering 3** — Fix hardcoded pad in `client.ts`.

9. **Verbetering 4** — Fix HTTP-statuscodes voor AP-onbeschikbaarheid.

10. **Architecturele aanbevelingen 1-4** — Plannen als aparte sprint-items.

---

## 7. Testplan

De volgende tests moeten groen zijn na de directe fixes (stap 1-6):

### Unit tests (nieuw toe te voegen)

```python
# tests/unit/domains/flows/test_service_lazy_client.py
async def test_list_flows_does_not_instantiate_ap_client(
    db_session, tenant_id
):
    """C-1: FocusBuilderService.__init__ mag ActivePiecesClient NIET aanroepen."""
    with patch.dict(os.environ, {}, clear=True):
        # Verwijder AP-env vars
        os.environ.pop("AP_SERVICE_EMAIL", None)
        os.environ.pop("AP_SERVICE_PASSWORD", None)
        # Instantiatie mag NIET crashen
        service = FocusBuilderService(db=db_session, tenant_id=tenant_id)
        assert service._ap_client is None

async def test_ap_client_property_raises_on_missing_credentials(
    db_session, tenant_id
):
    """C-1: ap_client property gooit ValueError als credentials ontbreken."""
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("AP_SERVICE_EMAIL", None)
        service = FocusBuilderService(db=db_session, tenant_id=tenant_id)
        with pytest.raises(ValueError, match="AP_SERVICE_EMAIL"):
            _ = service.ap_client


# tests/unit/domains/flows/test_repository_no_commit.py
async def test_repository_create_uses_flush_not_commit(db_session, tenant_id):
    """H-2: FlowRepository.create() mag GEEN commit aanroepen."""
    repo = FlowRepository(db_session, tenant_id)
    with patch.object(db_session, "commit", new_callable=AsyncMock) as mock_commit:
        await repo.create({"name": "test", "react_flow_graph": {"nodes": [], "edges": []}})
    mock_commit.assert_not_called()


# tests/architecture/test_flows_table_migration.py
def test_flows_table_has_alembic_migration():
    """C-2 TODO(SP-FB-001): flows tabel MOET een Alembic-migratie hebben."""
    import os, re
    versions_dir = "alembic/versions"
    tables: set[str] = set()
    for fname in os.listdir(versions_dir):
        if not fname.endswith(".py"):
            continue
        with open(os.path.join(versions_dir, fname)) as f:
            content = f.read()
        for m in re.finditer(r"op\.create_table\(\s*['\"](\w+)['\"]", content):
            tables.add(m.group(1))
    assert "flows" in tables, (
        "SP-FB-001: 'flows' ontbreekt in Alembic-migraties. "
        "src/domains/flows/models.py:17 vereist deze tabel."
    )
    assert "focus_builder_pieces_cache" in tables, (
        "SP-FB-001: 'focus_builder_pieces_cache' ontbreekt in Alembic-migraties."
    )
```

### Integratietests (endpoint smoke tests)

Na alle fixes moeten deze curl-commando's slagen:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8765/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@integration.test&password=AdminPass123!" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# C-2 fix verificatie: lijst flows — moet 200 retourneren (lege lijst)
curl -s -w "\nHTTP:%{http_code}" \
  http://127.0.0.1:8765/api/v1/focus-builder/flows \
  -H "Authorization: Bearer $TOKEN"
# Verwacht: HTTP:200 met []

# C-1 fix verificatie: als AP down is, moet lijst flows 200 retourneren
# (AP wordt niet aangeroepen bij list_flows na de lazy-init fix)

# Stukjes catalog — moet 200 retourneren (lege lijst)
curl -s -w "\nHTTP:%{http_code}" \
  http://127.0.0.1:8765/api/v1/focus-builder/pieces \
  -H "Authorization: Bearer $TOKEN"
# Verwacht: HTTP:200 met {"pieces": [], "total": 0}
```

### Regressietest: tenant-isolatie

```python
# tests/unit/domains/flows/test_repository_tenant_isolation.py
async def test_tenant_a_cannot_see_tenant_b_flows(db_session):
    """H-repository: tenant A ziet flows van tenant B NIET."""
    repo_a = FlowRepository(db_session, tenant_id=1)
    repo_b = FlowRepository(db_session, tenant_id=2)
    # Maak flow aan voor tenant B
    await repo_b.create({"name": "tenant_b_flow",
                          "react_flow_graph": {"nodes": [], "edges": []}})
    await db_session.flush()
    # Tenant A mag hem niet zien
    flows_a = await repo_a.list()
    assert not any(f.name == "tenant_b_flow" for f in flows_a)
```

---

*Audit afgesloten. Alle bevindingen zijn direct afgeleid uit broncode-analyse van de genoemde bestanden.*
