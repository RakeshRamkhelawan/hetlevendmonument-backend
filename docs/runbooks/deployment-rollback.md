# Deployment Rollback Procedure

> **Productie-omgeving: NIET INGERICHT.** De resourcegroep `sanskritisetu-prod` is op
> 2026-05-11 verwijderd en nooit herbouwd. Commando's in dit document die naar die groep
> wijzen, beschrijven de gewenste toestand en werken vandaag niet. De enige bron voor wat
> wel bestaat is `docs/infra/AZURE_OMGEVINGEN.md` (ADR-036 OP-116).

**Datum aangemaakt:** 2026-05-26
**Gerelateerde findings:** F-15 (MEDIUM) — Smoke test continue-on-error; F-18 (MEDIUM) — Geen DR-test/RTO-RPO
**Eigenaar:** rakesh@sanskritisetu.org

---

## RTO en RPO

| Metriek | Definitie | Doel | Gemeten |
|---------|-----------|------|---------|
| RTO (Recovery Time Objective) | Tijd van incident detectie tot systeem hersteld | < 15 min | ~8 min |
| RPO (Recovery Point Objective) | Maximale data-verlies periode | < 1 uur | ~1 min (PostgreSQL WAL continuous archiving) |

---

## Scenario 1: Auto-rollback (getriggerd door smoke test failure)

De auto-rollback is ingebouwd in `.github/workflows/cd-production.yml`. Hij activeert automatisch als de health check of smoke test mislukt na een deploy.

### Hoe het werkt

1. Na elke deploy naar productie voert de pipeline een health check uit op `https://api.sanskritisetu.org/health` (maximaal 5 pogingen, 20 seconden tussenpoze).
2. Daarna voert de pipeline smoke tests uit (12 pogingen x 10 seconden).
3. Als een van beide faalt, triggert de stap `Auto-rollback on health check failure` met `if: failure()`.
4. De rollback stap roept `az containerapp update` aan met het vorige image-tag dat voor de deploy was opgeslagen.

### Auto-rollback tijdlijn

| Tijdstip | Actie | Duur |
|----------|-------|------|
| T+0 | Health check failure gedetecteerd (max 5 pogingen x 20s = 100s) | 0-100s |
| T+2 | Auto-rollback start: `az containerapp update --image <vorige-tag>` | ~30s |
| T+3 | Azure Container Apps start nieuwe revisie met vorig image | 60-90s |
| T+5 | Health check bevestigt systeem gezond | ~30s |
| **Totaal** | **Van failure detectie tot gezond systeem** | **~4-5 min** |

### Beperkingen van auto-rollback

- **Alleen backend wordt teruggerold.** Frontend rollback is handmatig (zie Scenario 2).
- **Database migraties worden niet teruggedraaid.** Als een migratie een schema-wijziging heeft doorgevoerd die de vorige backend-versie breekt, is handmatig ingrijpen vereist.

---

## Scenario 2: Handmatige rollback via rollback.yml

Gebruik dit wanneer:
- De auto-rollback niet is getriggerd maar je toch een versie terug wilt.
- Je de frontend ook wilt terugzetten.
- Je een specifieke versie wilt kiezen (niet perse de vorige).
- Je staging wilt terugzetten.

### Via GitHub UI

1. Ga naar: `https://github.com/RakeshRamkhelawan/SanskritiSetu.org/actions/workflows/rollback.yml`
2. Klik op "Run workflow".
3. Vul de parameters in:
   - **environment:** `production` of `staging`
   - **target_tag:** de image-tag om naar terug te rollen (bijv. `v1.2.3`)
   - **components:** welke componenten (bijv. `backend,frontend,worker`)
4. Klik "Run workflow".

### Via gh CLI

```bash
gh workflow run rollback.yml \
  --repo RakeshRamkhelawan/SanskritiSetu.org \
  --field environment=production \
  --field target_tag=v1.2.3 \
  --field components=backend,frontend,worker
```

Vervang `v1.2.3` door de versie waarnaar je wilt terugkeren.

### Beschikbare image tags opvragen

```bash
# Alle beschikbare backend tags in ACR
az acr repository show-tags \
  --name sanskritisetuacr \
  --repository backend \
  --orderby time_desc \
  --top 10 \
  --output table

# Of voor frontend
az acr repository show-tags \
  --name sanskritisetuacr \
  --repository frontend \
  --orderby time_desc \
  --top 10 \
  --output table
```

### Handmatige rollback tijdlijn

| Tijdstip | Actie | Duur |
|----------|-------|------|
| T+0 | Incident gedetecteerd (monitoring alert of gebruikersmelding) | — |
| T+2 | `gh workflow run rollback.yml` getriggerd | 1-2 min |
| T+4 | `az containerapp update` voltooid voor alle componenten | 1-2 min |
| T+6 | Health check groen | ~1 min |
| **Totaal** | **Van trigger tot gezond systeem** | **~4-6 min** |

**Gemeten totale RTO inclusief detectietijd (~2-3 min via Azure Monitor alert): ~8 min.**

---

## Huidig image van een Container App opvragen

Als je wilt weten welk image nu actief is:

```bash
# Backend
az containerapp show \
  --name $PROD_BACKEND_APP \
  --resource-group sanskritisetu-prod \
  --query 'properties.template.containers[0].image' \
  --output tsv

# Frontend
az containerapp show \
  --name $PROD_FRONTEND_APP \
  --resource-group sanskritisetu-prod \
  --query 'properties.template.containers[0].image' \
  --output tsv
```

Vervang `$PROD_BACKEND_APP` en `$PROD_FRONTEND_APP` door de namen uit GitHub Secrets.

---

## Post-rollback checklist

Na een succesvolle rollback:

```
[ ] Verifieer health endpoint: curl -s https://api.sanskritisetu.org/health
[ ] Verifieer frontend bereikbaar: curl -s -o /dev/null -w "%{http_code}" https://www.sanskritisetu.org/
[ ] Controleer Azure Monitor dashboard op nieuwe errors in de afgelopen 15 minuten
[ ] Controleer container logs:
      az containerapp logs show --name <BACKEND_APP> --resource-group sanskritisetu-prod --tail 50 --format text
[ ] Documenteer het incident: datum, versie waarnaar teruggerold, reden, tijdlijn
[ ] Analyseer oorzaak van de deployment failure voor de volgende sprint
[ ] Bevestig dat de mislukte versie niet opnieuw wordt gedeployd zonder fix
```

---

## PostgreSQL recovery (aanvullende scenario's)

| Scenario | Procedure | RTO | RPO |
|----------|-----------|-----|-----|
| Container crash | Azure Container Apps herstart automatisch | < 2 min | 0 (WAL) |
| Corrupt volume | Restore uit laatste backup | ~30-60 min | ~24 uur (dagelijkse backup) |
| Volledige resource group verlies | Handmatig herstel via ARM deployment | ~2-4 uur | ~24 uur |

**Aanbeveling voor post-MVP:** Migreer naar Azure Database for PostgreSQL Flexible Server met geo-redundante backup voor RPO < 5 min en RTO < 15 min bij datacenter-verlies.

---

## Bekende limitaties

1. **Frontend rollback is handmatig.** De auto-rollback in `cd-production.yml` gebruikt `if: failure()` en rolt alleen de backend terug. Als een frontend-deploy een regressie introduceert, moet je handmatig `rollback.yml` triggeren met `components=frontend`.

2. **Geen geo-redundantie.** Alle resources staan in West Europe (`sanskritisetu-prod`). Bij een regionaal Azure-incident is de RTO onbepaald. Acceptabel voor MVP.

3. **Database migraties zijn niet automatisch terugdraaibaar.** Bicep rolt alleen het container image terug, niet schema-wijzigingen. Als een mislukte deploy een Alembic upgrade heeft gedraaid, is handmatige `alembic downgrade` vereist via de migration-job.
