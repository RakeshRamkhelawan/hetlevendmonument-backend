# Runbook: Onboard nieuwe tenant (stichting)

> **Productie-omgeving: NIET INGERICHT.** De resourcegroep `sanskritisetu-prod` is op
> 2026-05-11 verwijderd en nooit herbouwd. Commando's in dit document die naar die groep
> wijzen, beschrijven de gewenste toestand en werken vandaag niet. De enige bron voor wat
> wel bestaat is `docs/infra/AZURE_OMGEVINGEN.md` (ADR-036 OP-116).

**Doel**: nieuwe stichting toevoegen aan Levend Monument multi-tenant portal.
**Doorlooptijd**: 1 werkdag.
**Eigenaar**: Platform-admin (Ketikoti dienstverlener).

## Voorwaarden
- Dienstverleningsovereenkomst getekend (template `docs/legal/dienstverlening-template.md`)
- Stichting heeft KVK-inschrijving en contactpersoon aangewezen
- Pakket gekozen (Basis / Standaard / Premium — zie spec §14.2)

## Stappen

### 1. Tenant aanmaken in SanskritiSetu

```bash
# Via admin dashboard (productie)
# https://admin.sanskritisetu.org/tenants/new
```

Velden:
- `name`: officiele stichtingsnaam
- `slug`: lowercase, hyphens, 3-30 chars, niet in RESERVED_SLUGS (zie `src/core/models/rbac_models.py`)
- `domain`: leeg laten in fase 1; optioneel custom domein in fase 2
- `is_active`: `true`
- `settings`: `{"newsletter_provider": "brevo", "newsletter_list_id": "..."}` (na Brevo-setup)

Verificatie:
```sql
SELECT id, name, slug, is_active FROM tenants WHERE slug = '<nieuwe-slug>';
```

### 2. FoundationPortalSettings aanmaken

Via admin dashboard `/admin/foundation/portal-settings/new`:

| Veld | Waarde |
| --- | --- |
| `tenant_id` | (auto) |
| `platform_name_nl` | "Levend Monument {stichtingsnaam}" |
| `platform_name_en` | engelstalige variant |
| `primary_color` | hex, default `#1a2f45` |
| `accent_color` | hex, default `#e8b86d` |
| `logo_url` | upload via admin Blob-uploader |
| `favicon_url` | optioneel |
| `guidelines_nl` / `guidelines_en` | markdown, hergebruik Ketikoti-template |
| `about_nl` / `about_en` | korte stichtingsbeschrijving |
| `contact_email` | bestuurs-mailadres |

### 3. Eerste curator-account aanmaken

Via admin dashboard `/admin/users/new`:
- `tenant_id`: nieuwe tenant
- `email`: contactpersoon stichting
- `role`: `curator` (RBAC)
- Wachtwoord-reset link versturen

### 4. DNS configureren

**Wildcard al actief?** Verifieer:
```bash
dig +short *.levend-monument.nl
# Moet Azure-IP retourneren
```

Indien wildcard niet actief:
```
A-record: <slug>.levend-monument.nl  ->  <Azure Container App IP>
```

Via Azure DNS:
```bash
az network dns record-set a add-record \
  --resource-group sanskritisetu-prod \
  --zone-name levend-monument.nl \
  --record-set-name <slug> \
  --ipv4-address <ip>
```

### 5. Traefik TLS-certificaat

Traefik haalt automatisch een cert via httpChallenge op de eerste request naar `https://<slug>.levend-monument.nl`. Verifieer 5 minuten na DNS-propagation:
```bash
curl -I https://<slug>.levend-monument.nl
# Verwacht: HTTP/2 200 (of 404 indien content nog leeg)
```

### 6. Smoke test

| Test | Verwacht resultaat |
| --- | --- |
| `GET https://<slug>.levend-monument.nl/` | Magazine homepage met platform_name |
| `GET /api/v1/public/<slug>/settings` | JSON met branding |
| `GET /api/v1/public/<slug>/content?limit=5` | Lege array (geen content yet) |
| Curator login op `https://admin.sanskritisetu.org` | Toegang tot tenant-scoped admin |

### 6b. SPF / DKIM / DMARC voor portal-domain

Vereist voor magic-link e-mail deliverability via Brevo. Zonder correcte records komt mail in spam of bouncet helemaal.

**SPF** (TXT record op `levend-monument.nl` of custom-domain):
```
v=spf1 include:spf.brevo.com -all
```

**DKIM** (Brevo geeft 2 CNAMEs in dashboard):
```
mail._domainkey.<domain>  CNAME  mail.dkim.<brevo-cname>
mail2._domainkey.<domain> CNAME  mail2.dkim.<brevo-cname>
```

**DMARC** (TXT record op `_dmarc.<domain>`):
```
v=DMARC1; p=quarantine; rua=mailto:dmarc@<domain>; pct=100
```

Verificatie:
```bash
dig +short TXT <domain> | grep spf1
dig +short CNAME mail._domainkey.<domain>
dig +short TXT _dmarc.<domain>
```

In Brevo dashboard: "Senders & Domains" -> "Authenticate" tot status `Verified`.

### 7. Brevo nieuwsbrief koppelen (optioneel)

1. Brevo-account: nieuwe lijst aanmaken `levend-monument-<slug>`
2. List-ID kopieren naar `Tenant.settings.newsletter_list_id`
3. Double opt-in template configureren (NL + EN)

### 8. Welkomst-e-mail naar curator

Template `docs/templates/onboarding-welcome.md`. Bevat:
- Login-URL admin dashboard
- Link naar curator-handleiding (`docs/handleiding-curator.md`)
- Link naar guidelines
- Support-mail + responstijd (per pakket)

### 9. Bevestigen aan stichting

Stuur per e-mail:
- Portal-URL
- Curator-credentials (separaat kanaal)
- Eerste training-afspraak (1 uur, online)
- Factuur eenmalige implementatie-fee

## Rollback
Bij annulering binnen 30 dagen:
1. `Tenant.is_active = false`
2. DNS-record verwijderen
3. Brevo-lijst archiveren
4. Implementatie-fee terugstorten conform overeenkomst

## Audit
Elke stap loggen in `docs/operations/tenant-onboardings.md` met datum, uitvoerder, screenshot van smoke-test.
