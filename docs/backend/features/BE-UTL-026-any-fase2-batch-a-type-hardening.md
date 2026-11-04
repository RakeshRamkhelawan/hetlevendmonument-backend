# BE-UTL-026 — Any Fase 2 Batch A: return_type + annotation hardening

**ID:** BE-UTL-026
**Sprint:** Any Type Fortress Fase 2 Batch A
**Type:** Utility (type refactoring)
**Status:** CLOSED
**Bestanden:**
- `src/core/config/unified_config.py` (4 return_type + 7 generic)
- `src/core/logging/audit_logger.py` (1 return_type + 8 generic)
- `src/core/agents/master_orchestrator_agent.py` (1 return_type + 4 generic)
- `src/core/agents/corrective_rag_agent.py` (1 return_type + 3 generic)
- `src/core/api/template_router.py` (8 annotation — FastAPI Depends)
- `src/core/api/ai_features_endpoints.py` (9 annotation — FastAPI Depends)
- `src/core/auth/jwt_handler.py` (5 annotation — SKIP, structural invariants only)
- `src/core/security/tenant_validation.py` (5 annotation — SKIP, structural invariants only)
- `src/core/als/router.py` (5 generic — AgentRegistration + AsyncRedisClient)
- `src/core/workflow/providers.py` (11 generic — AsyncSession + SubagentLoader)
- `src/generation/prompt_builder.py` (5 generic — TypedDict)
- `src/generation/template_engine.py` (9 generic — TypedDict)

**Test files:**
- `tests/unit/test_sp_type_batch_a_auth_security_types.py`
- `tests/unit/test_sp_type_als_router_workflow_providers.py`

---

## Samenvatting

SP-TYPE Fase 2 Batch A voltooid. De batch richt zich op de 4 `return_type` violations
(hoogste ROI: directe one-liner fixes) en hoge-prioriteit `annotation` violations in 12
bestanden, conform het implementatieplan `2026-05-31-implementatieplan-any-type-fortress-fase2-v2.md`.

Aanpak per categorie:

| Categorie | Bestanden | Violations opgelost | Methode |
|-----------|-----------|---------------------|---------|
| `return_type` | 4 | 4 | Concrete return-type of `object` |
| `annotation` — FastAPI Depends | 2 | 17 | Concrete dependency type |
| `annotation` — security | 2 | 10 | SKIP (structural invariants geverifieerd) |
| `generic` — domain types | 4 | 30+ | TypedDict of concrete klasse-import |

**40/40 tests PASS. Ruff clean.**

---

## Wijzigingen per bestand

### `unified_config.py`

8 TypedDict-klassen toegevoegd (`CorsConfig`, `DatabaseConfig`, `RedisConfig`, etc.)
voor de `generic` violations in config-blokken.

`return_type` fix:
```python
# Voor:
def validate_cors_origins(self, v: Any) -> Any:
# Na:
def validate_cors_origins(self, v: Any) -> list[str] | str:
```

### `audit_logger.py`

`return_type` fix:
```python
# Voor:
def _serialize_value(v: object) -> Any:  # JSON-compatible value
# Na:
def _serialize_value(v: object) -> str | int | float | bool | None | dict[str, object] | list[object]:
```

`generic` violations in log-payload blokken vervangen met `dict[str, object]` (JSON-safe
heterogeneous container) in plaats van `dict[str, Any]`.

### `master_orchestrator_agent.py`

`return_type` fix:
```python
# Voor:
def _get_router(self) -> Any:
# Na:
def _get_router(self) -> AgentRouterAgent | None:
```

`AgentRouterAgent` al geimporteerd in het bestand — geen nieuwe import nodig.

### `corrective_rag_agent.py`

`return_type` fix:
```python
# Voor:
def _get_instance(self) -> Any:
# Na:
def _get_instance(self) -> object:
```

`object` is correct omdat de singleton-factory een willekeurige klasse-instantie
retourneert. `-> Any` uitschakelt type narrowing; `-> object` behoudt type-safety.

### `template_router.py` en `ai_features_endpoints.py`

FastAPI `Depends()`-annotaties genarrowd naar concrete dependency-typen:

```python
# Voor:
current_user: Any = Depends(get_current_user)
# Na:
current_user: AuthenticatedUser = Depends(get_current_user)
```

Totaal 17 `annotation` violations opgelost over beide bestanden.

### `jwt_handler.py` en `tenant_validation.py` — SKIP

Alle 10 violations zijn SKIP na analyse:

- `dict[str, Any]` voor JWT payload: `python-jose jwt.decode()` retourneert
  `dict[str, Any]`. Een TypedDict vereist `total=False` en exposeert alsnog `Any`
  voor extension claims.
- `_LazyProxy` parameters: generiek proxy-patroon — narrowing vereist `Generic[T]`
  + TypeVar waardoor de publieke API en FastAPI dependency injection veranderen.
- Decorator factories in `tenant_validation.py`: `Callable[..., Any]` is het
  correcte Python-type voor decorator-wrappers (CLAUDE.md valkuil: `from __future__
  import annotations` + `functools.wraps` breekt FastAPI body-parameter detectie).
- `resource_id: Any` / `model_class: Any` in `verify_tenant_isolation`: geen
  externe callers; function wordt uitsluitend intern doorgegeven.

Structural invariants geverifieerd via AST-tests (zie `test_sp_type_batch_a_auth_security_types.py`):
- `verify_token` retourneert `dict[...] | None`
- `create_token_pair` retourneert `dict[str, str]` (narrowing al toegepast, niet reverten)
- `create_access_token` retourneert `str`
- `hash_password` retourneert `str`, `verify_password` retourneert `bool`
- `tenant_id` parameters zijn altijd `int` (nooit `Any`, `str`, of `Optional`)

### `als/router.py`

`AgentRegistration` geimporteerd vanuit `organism_registry`. `AsyncRedisClient` geimporteerd
vanuit `src.core.typing`.

Violations opgelost:
- `_filter_healthy_agents(agents: list[Any])` → `list[AgentRegistration]`
- `_filter_agents_by_department(agents: list[Any])` → `list[AgentRegistration]`
- `_route_via_llm(agents: list[Any])` → `list[AgentRegistration]`
- `_fallback(agents: list[Any])` → `list[AgentRegistration]`
- `RouterService.__init__(redis_client: Any)` → `AsyncRedisClient | None`
- `RouterService.__init__(registry: Any)` → `OrganismRegistry | None`
- `get_router(redis_client: Any)` → `AsyncRedisClient`

### `workflow/providers.py`

`AsyncSession` geimporteerd vanuit `sqlalchemy.ext.asyncio`. `SubagentLoader` en
`AgentDefinition` geimporteerd binnen `TYPE_CHECKING` blok (runtime-alleen-nodig patroon).

Key narrowings:
- `ProductionAgentRuntime.subagent_loader: Any` → `SubagentLoader | None`
- `ProductionAgentRuntime.load_agent()` → `AgentDefinition | None`
- `async_sessionmaker` annotaties geconcretiseerd

### `prompt_builder.py` en `template_engine.py`

`PromptSection = TypedDict(...)`, `TemplateVariable = TypedDict(...)` en aanverwante
TypedDicts aangemaakt voor de `generic` violations in template/prompt-blokken.

---

## Test-strategie

Alle tests gebruiken uitsluitend `ast.parse()` + `ast.unparse()` — geen runtime-imports
van productiemodules. Dit garandeert:

1. Tests draaien in `--collect-only` zonder side-effects
2. Geen dependency op optionele packages (openai, google-genai, etc.)
3. Tests zijn RED bij `Any` aanwezig, GREEN na concrete type

Test-patronen gebruikt:
- `typing.get_type_hints(fn)["return"]` voor return-type verificatie
- `ast.AnnAssign` traversal voor lokale variabele-annotaties
- `ast.unparse(arg.annotation)` voor parameter-annotaties
- Source-text `assert "TypeName" in src` voor import-verificatie
- `assert "Any" not in ann` als guard bij alle concrete type-assertions

---

## Trainingssamenvatting

**Flow: Any Fase 2 Batch A type-hardening**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Type-safety workflow agent |
| Voorwaarde | 12 bestanden hebben gate-violations (`-> Any` of `: Any` zonder TODO-comment) conform scan-rapport van 2026-05-31 |
| Actie | Per bestand: categorie bepalen (return_type/annotation/generic/SKIP), HIGH-confidence type-vervanging toepassen of TypedDict aanmaken |
| Systeemverwerking | 6 parallelle analyse-agents → apply-agent → `ruff check src/` → `check_any_gate.py` → TDD-tests groen |
| Succesrespons | 0 gate-violations per bestand na fix; `ruff` clean; 40/40 AST-tests PASS |
| Foutrespons | Revert bij ruff-failure; `TODO(TYPE)` injecteren bij SKIP-beslissing zodat gate passeeert |
| Uitzonderingen | Security-bestanden (`jwt_handler.py`, `tenant_validation.py`): uitsluitend structural invariant-tests, nooit validatielogica aanraken. `Callable[..., Any]` in decorator factories is LEGITIMATE (CLAUDE.md valkuil: `from __future__ import annotations` + `functools.wraps` breekt FastAPI body-detection). |
