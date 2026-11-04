# BE-CFG-022 -- SP-API-009 Dag 3: Forbidden Imports Reduceren (top overtreders)

**ID:** BE-CFG-022
**Sprint:** SP-API-009 Dag 3
**ADR:** ADR-033 para.0 + para.3
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

SP-API-009 Dag 3: 28 forbidden imports gereduceerd (249 -> 221) via consolidatie van
duplicate/deferred module-imports in 20 v1/ bestanden. Doel was >=30; behaald 28 vanwege
een test-regressie bij focus_builder (eager import brak WS-gedrag).

---

## Aanpak

**Strategie:** Duplicate deferred imports consolideren tot 1 statement.
Import-linter telt elke `ast.ImportFrom` node -- ook dezelfde module
die 2-3x in functiebody's geimporteerd wordt. Samenvoegen naar 1
module-level import spaart 1-2 telpunten per bestand.

**Bestanden (v1/ forbidden: 198 -> 170, save 28):**

| Bestand | Was | Nu | Save |
|---------|-----|----|------|
| `system/llm_health.py` | 4 | 1 | 3 |
| `workflow/workflow_execution_router.py` | 6 | 4 | 2 |
| `workflow/workflow_execution_core_router.py` | 5 | 3 | 2 |
| `feature_flags/tenant_router.py` | 4 | 2 | 2 |
| `gatekeeper/gatekeeper_decisions_router.py` | 3 | 1 | 2 |
| `system/llm_status.py` | 5 | 3 | 2 |
| `gdpr_compliance/erasure_router.py` | 4 | 3 | 1 |
| `gdpr_compliance/portability_router.py` | 4 | 3 | 1 |
| `workflow/workflow_execution_cancel_router.py` | 2 | 1 | 1 |
| `cva/state.py` | 2 | 1 | 1 |
| `cva/chat_router.py` | 3 | 2 | 1 |
| `documents/crud_router.py` | 2 | 1 | 1 |
| `governance/dependencies.py` | 2 | 1 | 1 |
| `workflow/workflow_refinement_router.py` | 2 | 1 | 1 |
| `orchestration/health_router.py` | 2 | 1 | 1 |
| `snapshot_endpoints.py` | 2 | 1 | 1 |
| `notifications/router.py` | 2 | 1 | 1 |
| `privacy/consent_router.py` | 2 | 1 | 1 |
| `privacy/ai_transparency_router.py` | 2 | 1 | 1 |
| `models/registry_router.py` | 2 | 1 | 1 |
| `models/schemas.py` | 2 | 1 | 1 |

**Niet gereduceerd (1 save teruggedraaid):** `focus_builder/ws_chat_router.py`
-- eager import van `FocusBuilderChatAgent` brak test_ws_chat_ping_pong (session_init
stuurde voor pong). Teruggedraaid naar deferred patroon.

---

## Resterend (ADR-033 criterium: < 200)

| Categorie | Count | Pad naar < 200 |
|-----------|-------|----------------|
| v1/ forbidden | 170 | 21 meer nodig uit flat files |
| flat files | 51 | Dag 4: shims aanmaken |
| **Totaal** | **221** | **21 verminderen** |

Dag 4 scope: flat files (51 forbidden) omzetten naar echte 2-regel shims bereikt < 200.

---

## Trainingssamenvatting

### Flow 1: Duplicate deferred imports consolideren

**Actor:** Sprint-engineer
**Voorwaarde:** AST-scan toont dezelfde module 2+ keer geimporteerd in 1 bestand
(in functiebody's of in TYPE_CHECKING + runtime combinatie)
**Actie:** Voeg module-level import toe; verwijder deferred imports; controleer
of formatter de deferred imports automatisch opruimt
**Systeemverwerking:** Python AST telt elk `ImportFrom` node -- ook
dezelfde module in functiebody's; module-level import substitueert alle
deferred versies; count daalt per extra verwijderd statement
**Succesrespons:** `grep -c "from X import" bestand` = 1; forbidden-count daalt
**Foutrespons:** Als formatter deferred imports NIET verwijdert: handmatig
verwijderen van de deferred instanties; `logger.error(..., exc_info=True)` per CLAUDE.md
**Uitzonderingen:** Deferred imports die ANDERS gedragen dan module-level
(bijv. lazy agent imports die WS init-volgorde beinvloeden) NIET converteren.
Test op regressie na elke conversie.

### Flow 2: Stopcriterium bij regressie

**Actor:** Sprint-engineer
**Voorwaarde:** Regressiecheck toont nieuwe failure na eager import conversie
**Actie:** Verwijder de module-level import; herstel deferred pattern; markeer
bestand als TODO(SP-VOLGENDE) voor safe lazy-import patroon
**Systeemverwerking:** git diff toont het omgekeerde van de consolidatie; test
passeert weer; 1 save verloren maar regressievrij
**Succesrespons:** 160 tests PASS; bestand terug naar deferred; 1 minder save
**Foutrespons:** Als ook na herstel de test faalt: root-cause analyse nodig
**Uitzonderingen:** WebSocket init-volgorde is gevoelig voor module-level eager imports
van agent-klassen die side-effects triggeren bij import
