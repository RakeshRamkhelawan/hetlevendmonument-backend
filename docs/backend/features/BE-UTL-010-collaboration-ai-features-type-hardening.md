# BE-UTL-010 — collaboration_endpoints + ai_features Type Hardening

**ID:** BE-UTL-010
**Sprint:** SP-TYPE-01 Dag 6
**Type:** Utility (type refactoring + null-safety)
**Status:** CLOSED — commit `9e285838`
**Bestanden:** `src/core/api/collaboration_endpoints_complex.py`, `src/core/api/ai_features_endpoints.py`

---

## Samenvatting

Type-annotatie verbetering in twee API bestanden. Bijzonder: de DI-type-wijziging onthulde een pre-existing null-safety bug.

---

## Wijzigingen

### collaboration_endpoints_complex.py
- `capabilities: list[Any]` → `list[str]` (loop-analyse bewees dat alleen strings worden toegevoegd)
- `processed_messages: list[Any]` → `list[dict[str, Any]]` (structuur was bekend)
- Legacy imports `Dict, List, Optional, Set` verwijderd

### ai_features_endpoints.py
- `router_instance: Any = Depends(Provide[Container.intelligent_router])` → `IntelligentRouter`
- Null-safety fix toegevoegd: `if decision is None: raise HTTPException(503)` — `IntelligentRouter.route()` retourneert `Optional[RoutingDecision]`, de code crashte eerder met `AttributeError` bij `None`
- `Optional` import verwijderd

---

## Trainingssamenvatting

**Flow: list[Any] → concreet type via code-analyse**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Type-safety sprint agent |
| Voorwaarde | `capabilities: list[Any]` in `register_agent` |
| Actie | AST-analyse bewijst dat alle `append()`-aanroepen strings produceren (`str(cap)` fallback) |
| Systeemverwerking | `list[str]` annotatie gezet; TDD test (rood → groen) |
| Succesrespons | 3/3 TDD tests groen |
| Foutrespons | N.v.t. |
| Uitzonderingen | DI-type wijziging `Any` → `IntelligentRouter` onthulde null-safety bug — direct gefixed |
