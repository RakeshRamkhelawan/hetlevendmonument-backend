# BE-UTL-021 — SP-TYPE-05 Generation/Flows/Company Type Hardening
**ID:** BE-UTL-021
**Sprint:** SP-TYPE-05 Dag 2-5
**Type:** Utility (type refactoring)
**Status:** CLOSED
**Bestanden:** src/core/generation/, src/domains/flows/, src/core/company/, src/core/procedures/

## Samenvatting
Type hardening in generation templates, agentic flows, company services, and procedure registries.

## Wijzigingen
SP-TYPE-05 Group A: 9 files analysed. Changes are HIGH-confidence only.

**response_formatter.py** (src/core/generation/): Remove unused `Dict, List, Optional` from typing import. Narrow 5 local list accumulators (`yaml_lines`, `list_lines`, `html_parts`, `md_parts`, `lines` x2) from `list[Any]` to `list[str]` — all provably only receive str values.

**template_engine.py** (src/core/generation/): Remove unused `Dict, List, Optional, Set, Tuple` from typing import. Narrow `errors: list[Any]` → `list[str]` in `validate_syntax` and `validate_context`. Narrow `loop_result: list[Any]` → `list[str]` (_substitute_variables returns str). Narrow `arg_parts: list[Any]` → `list[str]` (accumulates char-stripped strings).

**prompt_builder.py** (src/core/generation/): Remove unused `Dict, List, Optional, Tuple`. Narrow `suggestions: list[Any]` → `list[str]` in all 3 optimization closures. Narrow `optimized_lines: list[Any]` → `list[str]`. Narrow `enhancements: list[Any]` → `list[str]`. Narrow `all_suggestions: list[Any]` → `list[str]`.

**agentic_service.py** (src/domains/flows/): Remove unused `Optional`. Narrow `selected_provider: Any | None` → `LLMProvider | None` in `_legacy_generate_flow` (loop only assigns LLMProvider enum values).

**pack_activation.py** (src/core/company/): Remove unused `Optional`. In `_execute_score`: narrow `scores: list[Any]` → `list[tuple[float, str]]` (all appends are `(float_weight, str_signal)` tuples), `reasons: list[Any]` → `list[str]`, `matched_signals: list[Any]` → `list[str]`.

**external_agent_service.py** (src/core/company/): Remove unused `Dict, List, Optional`. Narrow `stale_ids: list[Any]` → `list[uuid.UUID]` — the loop appends only `agent.id` which is `PG_UUID(as_uuid=True)`.

**external_agent_bridge.py** (src/core/company/): Remove unused `Dict, Optional`. Narrow `sla_seconds: Any` → `int | None` — fetched from dict.get (int or None) and immediately used with `or int` fallback.

**domain_pack_registry.py** (src/core/procedures/): Remove unused `Optional`. Narrow `tenant_id: Any` → `UUID | str` in `_normalize_tenant_id`, `get_active_packs`, and `find_candidates_by_tag` — the method body explicitly handles only UUID and str, raising TypeError for anything else.

**domain_pack_repository.py** (src/core/procedures/): Replace `from typing import Any` with `from uuid import UUID`. Narrow `pack_id: Any` → `pack_id: UUID` in `get_by_id`, `update`, and `archive` — `DomainPack.id` is `PG_UUID(as_uuid=True)` confirmed from models.py.

**Test file**: `tests/unit/test_sp_type05_group_a.py` — 9 `@pytest.mark.unit` tests, one per file, using the established `_import`/`_source` helper pattern, verifying both import cleanup and presence of narrowed type annotations in source text.

## Trainingssamenvatting
| Onderdeel | Inhoud |
|-----------|--------|
| Actor | SP-TYPE-05 workflow agent |
| Actie | HIGH-confidence Any replacements via parallel analysis |
| Succesrespons | TDD tests groen, ruff 0 errors |
| Uitzonderingen | *args/**kwargs, generic decorators, external SDK types als Any behouden |
