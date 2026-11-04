# Azure Teardown — 2026-05-11

**Status:** ✅ COMPLETE  
**Authorization:** Explicit user confirmation (Rakesh Ramkhelawan)  
**Reason:** Cost savings during 2-month implementation sprint  
**Savings:** ~$300 (2 months × $150/month)

## What Was Deleted

### Resource Groups (deleted via `az group delete`)
- ✗ `sanskritisetu-prod` (West Europe)
  - PostgreSQL server (19 Alembic migrations, all data)
  - Redis cache (transient data)
  - App Service Plan + API app
  - App Service + Frontend app
  - Storage accounts, network resources
  - **Status:** Async deletion in progress (10-15 min)

- ✗ `sanskritisetu-staging` (North Europe)
  - PostgreSQL server (staging data)
  - Redis cache (transient)
  - App Service Plan + staging services
  - Storage + network resources
  - **Status:** Async deletion in progress (10-15 min)

### Container Registry (deleted via `az acr delete`)
- ✗ `sanskritisetuacr.azurecr.io` (UK South)
  - All container images (API, frontend, workers)
  - **Status:** ✅ Immediately deleted

## What Was Preserved

Source code in Git:
- ✓ All 1,700 Python files
- ✓ All 1,043 TypeScript/TSX files
- ✓ All 19 Alembic migrations (`src/alembic/versions/`)
- ✓ Docker build configs (Dockerfile, frontend/)
- ✓ Traefik configuration templates

Documentation:
- ✓ CLAUDE.md (Azure specs, credentials format)
- ✓ AZURE_REBUILD_GUIDE.txt (step-by-step rebuild)
- ✓ This record (AZURE_TEARDOWN_2026_05_11.md)

PostgreSQL Data (May 2026):
- ✗ NOT preserved (intentional)
- Can be exported before deletion if needed (see guide)

Redis Data:
- ✗ NOT preserved (transient, OK to discard)

## Next Steps

### Immediate (2026-05-11)
1. ✓ Resource groups deletion initiated
2. ⏳ Wait 10-15 minutes for async completion
3. Optional: Remove GitHub Actions secret `AZURE_CREDENTIALS`
   ```bash
   gh secret delete AZURE_CREDENTIALS
   ```
4. Optional: Disable GitHub Actions CI/CD during 2-month sprint
   (No deployments planned, saves build minutes)

### June 2026
- Implementation sprint (no Azure needed)
- Develop new features
- Refactor existing code
- No live testing

### July 2026 (Rebuild)
- **July 1:** Start infrastructure rebuild (use AZURE_REBUILD_GUIDE.txt)
- **July 5:** Deploy rebuilt application
- **July 6:** Resume live testing

## Rebuild Timeline (July 2026)

Following `AZURE_REBUILD_GUIDE.txt`:

| Phase | Task | Duration |
|---|---|---|
| 1 | Infrastructure (RG, PostgreSQL, Redis, ACR, App Services) | 2 days |
| 2 | Credentials & service principal | 1 day |
| 3 | Environment variables | 1 day |
| 4 | Alembic migrations | 1 day |
| 5 | Container images & deployments | 1 day |
| 6 | Traefik & TLS | 1 day |
| **Total** | **Complete rebuild** | **~5 days** |

## Critical Reminders for July Rebuild

1. **pgvector extension:** Required before migrations
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

2. **All migrations stable:** 19 migrations in `src/alembic/versions/` will auto-apply

3. **JWT_SECRET:** Generate fresh (previous discarded)

4. **AZURE_CREDENTIALS:** 4 fields required (see CLAUDE.md format)

5. **Rebuild from source:** All Docker images rebuild from code (no image salvage)

## Costs

| Period | Cost | Notes |
|---|---|---|
| May 2026 (prod infra) | ~$150 | Before teardown |
| June 2026 (no infra) | $0 | Savings period |
| July 2026 (rebuild) | $0 (first week) → ~$150 | After July 5 deploy |
| **Total Savings** | **~$300** | For 2-month sprint |

## Authorization Record

- **User:** Rakesh Ramkhelawan (wiraj@sanskritisetu.org)
- **Date:** 2026-05-11
- **Confirmation:** Explicit "ja" via Claude Code
- **Scope:** Delete all Azure resources (prod + staging + registry)
- **Reason:** Cost reduction during implementation sprint
- **Urgency:** Non-critical (no live testing planned for 2 months)

## Irreversibility Statement

**This action is intentional and irreversible.**

- ✗ No backup strategy (data discarded by design)
- ✗ No rollback plan (not needed)
- ✗ Cannot recover deleted databases (OK, data ephemeral)
- ✓ Can perfectly rebuild from documented infrastructure
- ✓ Source code unchanged (can rebuild images anytime)

If early rebuild needed before July, follow `AZURE_REBUILD_GUIDE.txt` at any time.

---

**Teardown completed:** 2026-05-11 (async deletion in progress)  
**Documentation:** Complete and preserved in Git  
**Next review:** July 2026 for rebuild start
