# Runbook: Tenant deprovisioning

> **Productie-omgeving: NIET INGERICHT.** De resourcegroep `sanskritisetu-prod` is op
> 2026-05-11 verwijderd en nooit herbouwd. Commando's in dit document die naar die groep
> wijzen, beschrijven de gewenste toestand en werken vandaag niet. De enige bron voor wat
> wel bestaat is `docs/infra/AZURE_OMGEVINGEN.md` (ADR-036 OP-116).

**Doel**: tenant offboarden bij contractbeeindiging met AVG-export en data-retentie.
**Doorlooptijd**: 90 dagen grace + 1 jaar cold storage = 15 maanden total.
**Eigenaar**: Platform-admin.

## Aanleiding
- Contract beeindigd
- Stichting opgeheven (KVK-uitschrijving)
- Wanbetaling > 90 dagen na sommering
- Verzoek stichting

## Stappen

### Dag 0: opzeggingsbevestiging

1. Schriftelijke opzegging per e-mail bevestigen
2. Eind-datum vastleggen in `Tenant.settings.deprovision_at` (ISO 8601)
3. Banner op portal aanzetten: "Dit platform sluit op {datum}. Download je data."

```bash
# Via admin dashboard
PATCH /api/v1/admin/tenants/<id>
{
  "settings": {
    "deprovision_at": "2026-09-01T00:00:00Z",
    "show_closure_banner": true
  }
}
```

### Dag 0-90: grace period

- Portal blijft volledig functioneel
- E-mail naar curator + bestuur op dag 0, 30, 60, 80
- Maandelijkse herinnering naar uploaders (PortalUser) via admin

### Dag 30: AVG-export aanbieden

```bash
# Genereer ZIP met:
# - alle FoundationContent rijen (JSON)
# - alle bestanden uit Azure Blob (origineel)
# - FoundationPortalSettings (JSON)
# - PortalUser lijst (geanonimiseerd indien gewenst)
# - Audit-log uittreksel (alleen acties van deze tenant)

python scripts/avg_tenant_export.py --tenant-slug <slug> --output ./exports/<slug>.zip
```

Versturen via secure transfer (e-mail link met TTL 7 dagen).

### Dag 90: soft-delete

```python
# In transactie
await db.execute(
    update(Tenant)
    .where(Tenant.id == tenant_id)
    .values(is_active=False, settings={"deprovisioned_at": utc_now()})
)
```

Effect:
- Portal toont 410 Gone op alle public URLs
- Admin kan nog wel data bekijken (read-only)
- DNS-record blijft 30 dagen (voor cache-flush)

### Dag 120: DNS-record verwijderen

```bash
az network dns record-set a delete \
  --resource-group sanskritisetu-prod \
  --zone-name levend-monument.nl \
  --name <slug>
```

### Dag 90 + 1 jaar: hard-delete

Cron job (zie `scripts/cron/hard_delete_inactive_tenants.py`):
```sql
DELETE FROM tenants
WHERE is_active = false
  AND (settings->>'deprovisioned_at')::timestamptz < now() - interval '1 year';
-- CASCADE deletes alle gekoppelde data
```

Blob storage:
```bash
az storage blob delete-batch \
  --source foundation-content \
  --pattern "tenant-<id>/*"
```

Audit-log: bewaard 7 jaar conform subsidieverantwoording. Wel anonimiseren: `email`, `display_name` velden vervangen door `[deleted-user-<id>]`.

### Dag 90 + 1 jaar + 1 dag: bevestiging

E-mail naar (laatst bekende) bestuur: "Alle data verwijderd op {datum}. Audit-log bewaard tot {datum + 7j}."

## Edge cases

| Scenario | Actie |
| --- | --- |
| Stichting komt terug binnen grace | `is_active=true`, banner uit, geen data-loss |
| Audit-log toont kritieke incidenten | Verlengen retentie, juridisch advies inwinnen |
| Subsidieverantwoording UVB nog open | Wachten met hard-delete tot UVB-akkoord rapportage |
| KVK-uitschrijving zonder opvolger | Bestuur achterhalen via KVK; bij geen contact: na 6 mnd opheffen |

## Audit
Elke fase loggen in `docs/operations/tenant-deprovisionings.md`.
