# SOC 2 Readiness Tracker — SanskritiSetu

**Status:** SOC 2 Type I READINESS IN VOORBEREIDING — niet gecertificeerd
**Peildatum:** 2026-05-26
**Eigenaar:** Rakesh Ramkhelawan (<rakesh@sanskritisetu.org>)
**Doel:** Type I gereed zijn voor eerste enterprise klant onboarding

---

## Leeswijzer voor een auditor

Dit document is het centrale overzicht van alle SOC 2 Trust Services Criteria (TSC) controls voor SanskritiSetu. Elke rij in de mastertabel geeft aan:

- of het control **GEREED**, **GEDEELTELIJK** of **PENDING** is
- welk bewijs beschikbaar is
- waar het bewijsdocument staat

PENDING controls zijn bewust uitgesteld vanwege ontbrekende randvoorwaarden (geen productieverkeer, geen team, geen enterprise klanten). De exacte trigger-conditie per control staat in `pending/README.md`. Elk PENDING control heeft een volledig ingevuld template klaarstaan; uitvoering vereist alleen de trigger-data invullen.

De basisarchitectuur is gedocumenteerd in 28 Architecture Decision Records (ADRs) in `docs/adr/`. ADRs zijn definitief en dienen als primair technisch bewijs voor control-implementaties.

---

## Master control tabel

| Criterium | Naam | Status | Bewijs aanwezig | Bewijsdocument |
|-----------|------|--------|----------------|----------------|
| CC1.1 | Control environment: eigenaarschap en verantwoordelijkheid | GEREED | CLAUDE.md, 28 ADRs, runbooks documenteren alle beslissingen en regels | `information-security-policy.md` |
| CC1.2 | Informatiebeveiligingsbeleid | GEREED | Formeel beleidsdocument aanwezig, versie 1.0, eigenaar en reviewdatum vastgelegd | `information-security-policy.md` |
| CC1.4 | Security awareness training | PENDING | Solo developer; beleid is geborgd via CLAUDE.md en ADRs; formeel trainingsprogramma wacht op eerste medewerker | `pending/security-awareness-training.md` |
| CC2.1 | Communicatie van beleid naar betrokkenen | GEREED | CLAUDE.md en ADRs beschikbaar in repository; runbooks beschikbaar in `docs/runbooks/` | `information-security-policy.md`, `docs/adr/` |
| CC3.1 | Risicoregister | GEREED | Centraal risicoregister aangemaakt, versie 1.0, eigenaar en reviewdatum vastgelegd | `risk-register.md` |
| CC3.2 | Risicobeheerprocedure | GEREED | Kwartaallijkse reviewcyclus gedocumenteerd in risicoregister | `risk-register.md` |
| CC4.1 | Monitoring en detectie van afwijkingen | GEREED | Prometheus + Grafana voor metrics; dagelijkse ketenverificatie met `audit_chain_*`-tellers en alertregels (`infra/prometheus/alerts/audit-chain.yml`). **Gecorrigeerd 2026-08-11:** ~~Azure Log Analytics voor audit-logs~~ -- die stream bestaat niet (ADR-036 OP-119) | ADR-019 (audit logging), ADR-014 (observability) |
| CC5.1 | Control activities: beleids- en proceduredocumentatie | GEREED | CLAUDE.md + 28 ADRs documenteren alle verplichte patronen en procedures | `information-security-policy.md`, `docs/adr/` |
| CC5.2 | Control activities: Human-in-the-Loop gate voor hoog-risico acties | GEREED | HITL gate geblokkeerd voor high-risk agent tools; ToolBroker allowlist actief | ADR-015 (agent safety), ADR-016 (Shadow CEO veto) |
| CC6.1 | Logical access controls | GEREED | JWT-claim als tenant identity (ADR-003), RLS op kernbedrijven (ADR-005), toegangsreview-procedure gedocumenteerd | `access-review-procedure.md`, ADR-003, ADR-005 |
| CC6.1 | Kwartaallijks access review — uitvoering | PENDING | Procedure klaar; uitvoering wacht op actieve productiegebruikers | `pending/README.md`, `access-review-procedure.md` |
| CC6.2 | Credential management en sleutelbeheer | GEREED | Azure Key Vault voor alle geheimen; Managed Identity voor service-authenticatie; rotatieprocedure gedocumenteerd | ADR-013 (secret scanning), `docs/runbooks/secret-rotation.md` |
| CC6.3 | Toegang uitsluitend op basis van autorisatie | GEREED | RBAC via JWT-claims; PermissionGate in frontend; CODEOWNERS voor repository-toegang; least privilege principle gedocumenteerd | ADR-003, ADR-015, `information-security-policy.md` |
| CC6.6 | Encryptie van data in transit | GEREED | TLS 1.3 via Traefik op alle publieke endpoints (ADR-009); httpOnly + Secure cookies voor sessies | ADR-009 (Traefik), `information-security-policy.md` |
| CC6.7 | Bescherming tegen ongeautoriseerde toegang en tenant-isolatie | GEREED | Tenant-isolatie via JWT ContextVar (ADR-003); automatische WHERE-filter via ORM hook (ADR-004); RLS op database-niveau (ADR-005); spoofing-preventie gedocumenteerd in CLAUDE.md | ADR-003, ADR-004, ADR-005 |
| CC6.8 | Supply chain beveiliging (containers en afhankelijkheden) | GEREED | Trivy scans (backend + frontend + worker) in CI/CD; cosign image signing; SBOM generatie; digest-pinning in workflows; Gitleaks secret scanning | ADR-013, ADR-030, `vulnerability-management.md` |
| CC7.1 | Kwetsbaarheden detecteren en monitoren | GEREED | Trivy, pip-audit, npm audit in elke CI-run; SARIF uploads naar GitHub Security; CVE-handling procedure gedocumenteerd | `vulnerability-management.md`, ADR-013 |
| CC7.1 | Externe penetration test | PENDING | Geen publieke productie-endpoints; pentest scope is gedocumenteerd en wacht op trigger | `pending/penetration-test-scope.md` |
| CC7.2 | Monitoring tools en health checks | GEREED | 3-tier health checks (liveness, readiness, diagnostics); Prometheus metrics; Grafana dashboards; Azure Log Analytics | ADR-012 (health checks), ADR-014 (observability) |
| CC7.3 | Incident response plan | GEREED | Plan gedocumenteerd met escalatieprocedure, classificatie-niveaus en herstelstappen | `incident-response-plan.md` |
| CC7.5 | Disaster recovery en business continuity | GEDEELTELIJK | RTO ca. 8 minuten en RPO ca. 1 minuut gemeten en getest; BCP-template aangemaakt; business impact analyse wacht op productieverkeer | `docs/runbooks/deployment-rollback.md`, `pending/business-continuity-plan.md` |
| CC8.1 | Change management | GEREED | CI/CD pipeline via GitHub Actions; CODEOWNERS voor verplichte reviews; branch protection op main; alle wijzigingen via pull requests | `change-management-procedure.md`, `docs/adr/` |
| CC9.2 | Vendor risk management — Azure en GitHub | GEREED | Risicobeoordeling gedocumenteerd; DPA aanwezig; jaarlijkse reviewdatum vastgelegd | `vendor-assessments/azure.md`, `vendor-assessments/github.md` |
| CC9.2 | Vendor DPA Anthropic — formele acceptatie | PENDING | Assessment aangemaakt; DPA-verificatie en training-opt-out vereisen actief productie-account met tenant-data | `vendor-assessments/anthropic.md` |
| CC9.2 | Vendor DPA OpenAI — formele acceptatie | PENDING | Assessment aangemaakt; DPA moet formeel geaccepteerd worden in OpenAI Platform-dashboard voor productie-gebruik | `vendor-assessments/openai.md` |
| CC9.2 | DeepSeek PII-filter en EU residency | PENDING | Assessment aangemaakt; PII-blokkering en per-tenant uitschakeloptie vereist implementatie; blokkeerbaar bij enterprise EU-klant | `vendor-assessments/deepseek.md`, `pending/README.md` |

---

## Openstaande acties voor Type I audit-gereedheid

De volgende items moeten gesloten zijn voordat een externe auditor ingeschakeld kan worden. Items zijn gerangschikt op prioriteit.

| # | Actie | SOC 2 Criterium | Trigger-conditie | Eigenaar |
|---|-------|-----------------|-----------------|---------|
| 1 | Vendor DPA Anthropic formeel accepteren en vastleggen | CC9.2 | Voor eerste productiegebruik met tenant-data | Rakesh |
| 2 | Vendor DPA OpenAI formeel accepteren in Platform-dashboard | CC9.2 | Voor eerste productiegebruik met tenant-data | Rakesh |
| 3 | MFA-bewijs screenshots verzamelen en toevoegen aan `mfa-enforcement.md` | CC6.1 | Productielancering (D-7 checklist) | Rakesh |
| 4 | DeepSeek PII-filter implementeren en per-tenant uitschakeloptie toevoegen | CC9.2 | Eerste enterprise klant met EU data-residency eis | Rakesh |
| 5 | Externe penetration test uitvoeren conform `pending/penetration-test-scope.md` | CC7.1 | 30 dagen voor eerste enterprise klant onboarding | Rakesh |
| 6 | Kwartaallijks access review uitvoeren en loggen | CC6.1 | Eerste tenant onboarding in productie | Rakesh |
| 7 | Business continuity plan voltooien (business impact analyse) | CC7.5 | 3 maanden productieverkeer beschikbaar | Rakesh |
| 8 | Security awareness training programma uitvoeren | CC1.4 | Eerste medewerker aangenomen | Rakesh |
| 9 | Cyber insurance evalueren en documenteren | CC9 | Eerste enterprise contract groter dan 50.000 euro ARR | Rakesh |
| 10 | SOC 2 Type I externe audit inhuren en inplannen | — | Alle bovenstaande acties gesloten + 1 maand stabiele productie | Rakesh |

---

## Bewijs verzamelen per criterium — instructies voor auditor

De volgende commando's en locaties leveren het primaire bewijs per criterium. Voer commando's uit vanuit de root van de repository.

### CC1.1 / CC1.2 / CC2.1 — Beleid en communicatie

```bash
# Controleer of beleidsbestanden aanwezig zijn en een reviewdatum hebben
ls docs/compliance/soc2/*.md

# Controleer of CLAUDE.md aanwezig en niet leeg is
wc -l CLAUDE.md
```

Bewijs: `docs/compliance/soc2/information-security-policy.md` (versie, datum, eigenaar), `CLAUDE.md` (regels geborgd in code-workflow), `docs/adr/` (28 ADRs met beslissings-rationale).

### CC3.1 / CC3.2 — Risicoregister

```bash
# Controleer of risicoregister aanwezig is
ls docs/compliance/soc2/risk-register.md
```

[TODO: aanmaken — zie actie 1 in bovenstaande tabel]

### CC4.1 — Monitoring

```bash
# Controleer of Prometheus metrics endpoint bereikbaar is
curl https://api.sanskritisetu.org/metrics

# Controleer of health endpoints reageren
curl https://api.sanskritisetu.org/health/live
curl https://api.sanskritisetu.org/health/ready
curl https://api.sanskritisetu.org/health/diagnostics
```

Bewijs: Grafana dashboards (login credentials in Azure Key Vault), Azure Log Analytics workspace, ADR-014 en ADR-012.

### CC6.1 / CC6.3 — Toegangscontrole en access review

```bash
# Controleer aanwezigheid van toegangsreview-procedure
cat docs/compliance/soc2/access-review-procedure.md

# Controleer GitHub organisatie-leden (vereist gh CLI ingelogd)
gh api orgs/RakeshRamkhelawan/members --jq '.[].login'

# Controleer Azure rol-toewijzingen
az role assignment list --subscription <azure-subscription-id> --output table
```

### CC6.2 — Credential management

```bash
# Controleer aanwezigheid van Key Vault geheimen (lijst, geen waarden)
az keyvault secret list --vault-name sanskriti-kv-prd --output table

# Controleer secret-rotatieprocedure
cat docs/runbooks/secret-rotation.md
```

### CC6.6 / CC6.7 — Encryptie en tenant-isolatie

Bewijs: ADR-009 (Traefik TLS 1.3), ADR-003 (JWT ContextVar tenant identity), ADR-004 (ORM auto-WHERE), ADR-005 (RLS + tenant_id NOT NULL). Technisch te verifiëren via:

```bash
# Controleer of de Traefik-configuratie TLS 1.3 afdwingt
grep -r "tls" docker/traefik/ --include="*.yml"

# Controleer of RLS-migraties aanwezig zijn
ls src/alembic/versions/ | grep rls
```

### CC6.8 / CC7.1 — Supply chain en kwetsbaarheden

```bash
# Bekijk meest recente Trivy SARIF-resultaten
gh run list --workflow ci.yml --limit 5
gh run view <run-id> --log

# Controleer of Gitleaks geconfigureerd is
cat .gitleaks.toml
```

Bewijs: GitHub Actions workflow `ci.yml` (Trivy scans bij elke push), SARIF uploads in GitHub Security tab, `vulnerability-management.md`.

### CC7.3 — Incident response

```bash
cat docs/compliance/soc2/incident-response-plan.md
```

### CC7.5 — Disaster recovery

```bash
# Controleer rollback-runbook
cat docs/runbooks/deployment-rollback.md

# Controleer DR-test bewijs (Sprint 3 testresultaten)
git log --oneline --grep="disaster recovery\|DR test\|rollback" | head -10
```

### CC8.1 — Change management

```bash
# Controleer branch protection regels
gh api repos/RakeshRamkhelawan/SanskritiSetu.org/branches/main/protection

# Controleer CODEOWNERS
cat .github/CODEOWNERS

# Bekijk recente pull requests (bewijs van review-proces)
gh pr list --state merged --limit 10
```

### CC9.2 — Vendor assessments

```bash
# Controleer aanwezigheid van alle vendor-assessments
ls docs/compliance/soc2/vendor-assessments/

# Controleer DPA-status per vendor
grep -h "DPA\|status" docs/compliance/soc2/vendor-assessments/*.md | head -20
```

---

## Document index

| Document | Status | Criterium |
|---------|--------|----------|
| `information-security-policy.md` | GEREED | CC1.1, CC1.2, CC5.1 |
| `access-review-procedure.md` | PROCEDURE GEREED — uitvoering pending | CC6.1 |
| `change-management-procedure.md` | GEREED | CC8.1 |
| `incident-response-plan.md` | GEREED | CC7.3 |
| `mfa-enforcement.md` | BELEID GEREED — bewijs pending | CC6.1 |
| `vulnerability-management.md` | GEREED | CC7.1, CC6.8 |
| `vendor-assessments/azure.md` | GEREED | CC9.2 |
| `vendor-assessments/github.md` | GEREED | CC9.2 |
| `vendor-assessments/anthropic.md` | ASSESSMENT GEREED — DPA pending | CC9.2 |
| `vendor-assessments/openai.md` | ASSESSMENT GEREED — DPA pending | CC9.2 |
| `vendor-assessments/deepseek.md` | ASSESSMENT GEREED — PII-filter pending | CC9.2 |
| `risk-register.md` | GEREED | CC3.1, CC3.2 |
| `pending/README.md` | ACTIEF | — |
| `pending/penetration-test-scope.md` | PENDING — trigger: 30 dagen voor enterprise onboarding | CC7.1 |
| `pending/business-continuity-plan.md` | GEDEELTELIJK — trigger: 3 maanden productieverkeer | CC7.5 |
| `pending/security-awareness-training.md` | PENDING — trigger: eerste medewerker | CC1.4 |

---

## Versiegeschiedenis

| Versie | Datum | Wijziging |
|--------|-------|----------|
| 1.0 | 2026-05-26 | Initieel overzicht aangemaakt; alle bekende controls gedocumenteerd |

> **Gecorrigeerd 2026-08-11 (ADR-036 OP-118 t/m OP-121).** De volledige afweging, met wat de keten wel en niet detecteert, staat in ADR-019 onder "Wat tamper-evident hier WEL en NIET betekent". Correcties zijn doorgehaald in plaats van verwijderd, zodat zichtbaar blijft dat een claim is bijgesteld.
