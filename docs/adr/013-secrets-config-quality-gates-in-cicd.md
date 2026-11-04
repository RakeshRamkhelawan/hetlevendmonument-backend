# ADR-013: Secrets & Config Quality Gates in CI/CD

## Status

Accepted - Implemented (2026-05-26)

### Statushistorie

- Initieel Accepted: theoriefase (Pydantic schema-validatie, Gitleaks concept)
- 2026-05-22: Gitleaks geimplementeerd als eerste CI-job (P0 sprint, commit `37503142`-reeks)
- 2026-05-26: Volledig geimplementeerd na build-stack security programma (ADR-030);
  alle gates actief in ci-feature.yml, cd-staging.yml en cd-prod.yml

## Context

Configuratiefouten (zoals een missende `DATABASE_URL` of een verkeerde `TENANT_SECRET`)
zijn de meest voorkomende oorzaak van falende deployments. Daarnaast is het lekken van
API keys in de codebase een onacceptabel risico. Het enterprise security audit (mei 2026)
identificeerde aanvullend: ontbrekende container CVE-scanning, geen SCA-gate voor
Python- en npm-pakketten, geen artifact signing, geen SBOM, en geen gestandaardiseerde
secret rotation procedure.

## Decision

Wij implementeren de volgende quality gates als harde CI-stappen (geen `continue-on-error`).

### 1. Secret scanning (Gitleaks)

**Tooling:** `gitleaks/gitleaks-action` als eerste CI-job, zodat een secret-lek de
pipeline stopt voor verdere stappen worden uitgevoerd.

**Gate:** Pipeline faalt onmiddellijk bij detectie van patronen voor API keys
(Google, Redis, JWT secrets, Azure credentials). Test-keys zijn opgenomen in
`.gitleaks.toml` als allowlist.

```toml
# .gitleaks.toml (fragment)
[[rules.allowlist]]
description = "Test API keys in test fixtures"
regexes = ["test_key_[a-z0-9]{16}"]
```

### 2. Container CVE-scanning (Trivy)

**Tooling:** `aquasecurity/trivy-action` met `format: sarif`; resultaten worden
geupload naar de GitHub Security tab via `codeql-action/upload-sarif`.

**Gate:** 9 Trivy-scans per workflow-combinatie (backend, frontend, worker per
ci-feature, cd-staging, cd-prod). Severity `CRITICAL,HIGH` faalt de pipeline.

```yaml
- uses: aquasecurity/trivy-action@a20de5420d57c4102486cdd9349b532415b29ccc
  with:
    image-ref: ${{ env.IMAGE_REF }}
    format: sarif
    output: trivy-results.sarif
    severity: CRITICAL,HIGH
- uses: github/codeql-action/upload-sarif@03e4368b24d93d4cccc62c9f1f8d4ea44afa3b72
  with:
    sarif_file: trivy-results.sarif
```

**Opmerking:** Worker-images vereisen `--load` vlag bij build-stap zodat Trivy
de lokale Docker-daemon kan scannen (niet vanuit een registry).

### 3. Software Composition Analysis (pip-audit + npm audit)

**Tooling:** `pip-audit` voor Python-pakketten, `npm audit` voor de frontend.
Beide draaien als aparte CI-job stap.

**Gate:** Pipeline faalt bij bekende kwetsbaarheden. Exit-code patroon:

```bash
# FOUT — --strict flag bestaat niet bij pip-audit
pip-audit --strict

# GOED — exit-code bewaken
pip-audit || AUDIT_EXIT=$?
if [ "${AUDIT_EXIT:-0}" -ne 0 ]; then exit $AUDIT_EXIT; fi
```

### 4. Python dependency lockfile (pip-compile)

**Tooling:** `pip-tools` met `pip-compile --generate-hashes --platform linux/amd64`.

**Gate:** CI verifieert dat `requirements.txt` up-to-date is met `requirements.in`
via `pip-compile --dry-run --check`. Hashes in requirements.txt beschermen tegen
supply chain aanvallen (dependency confusion, PyPI package substitution).

### 5. Artifact signing (cosign keyless)

**Tooling:** `sigstore/cosign-installer` + `cosign sign` na elke ACR-push.

**Gate:** Productie-images worden na elke push naar ACR ondertekend met cosign
keyless (GitHub OIDC als identiteitsbron). Ondertekening is verifieerbaar via
`cosign verify` en de Rekor transparency log. GitHub Actions workflow vereist
`id-token: write` permission.

```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: sigstore/cosign-installer@v3
  - run: cosign sign ${{ env.IMAGE_REF }}
```

### 6. SBOM-generatie (syft)

**Tooling:** `anchore/sbom-action` met CycloneDX JSON output.

**Gate:** SBOM wordt bijgevoegd aan elke GitHub Release als artifact (`sbom-*.json`).
De SBOM biedt aantoonbare herkomst voor license-compliance audits en verwerkersinventaris
onder GDPR.

### 7. Code ownership review-enforcement (CODEOWNERS)

**Bestand:** `.github/CODEOWNERS`

**Gate:** Pull requests die security-kritische paden raken, vereisen review van
de aangewezen eigenaar (GitHub branch-protection enforcement). Gedekte paden
omvatten o.a. `Dockerfile*`, `.github/workflows/`, `requirements*.txt`,
`requirements*.in`, `infra/bicep/`, `src/core/auth/`, `src/core/governance/`.

**Letop:** CODEOWNERS gebruikt last-match-wins logica. `/.github/workflows/` moet
na `/.github/` worden gedefinieerd om de juiste eigenaar te krijgen. Bestanden
in `.git/info/exclude` vereisen `git add -f` om trackable te maken.

### 8. Key Vault secret rotation (MetricAlerts)

**Tooling:** Azure Key Vault expiry policies + Azure Monitor MetricAlerts op de
`DaysUntilExpiry`-metric.

**Gate:** MetricAlert vuurt 30 dagen vóór vervaldatum van elk secret. Alert-scope
is het Key Vault resource-id (niet `resourceGroup().id` — dat geeft een ARM
deployment-fout). ActivityLogAlerts zijn bewust NIET gekozen: zij detecteren
uitsluitend events (aanmaken/verwijderen), niet het naderen van een vervaldatum.

```bicep
resource secretExpiryAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'secret-expiry-alert'
  properties: {
    criteria: {
      metricName: 'DaysUntilExpiry'
      operator: 'LessThanOrEqual'
      threshold: 30
    }
    scopes: [keyVault.id]  // resource-id, niet resourceGroup().id
  }
}
```

### 9. Smoke test gate

**Gate:** Na deployment naar staging of productie voert de pipeline een smoke
test uit met 12 pogingen (10s interval) via `curl -o /dev/null -w "%{http_code}"`.
`continue-on-error: true` is verwijderd — een falende smoke test blokkeert
de pipeline en voorkomt dat een kapotte deployment onopgemerkt blijft.

### 10. Environment schema validation (Pydantic)

Ongewijzigd ten opzichte van de initiële versie. Pydantic `BaseSettings` dwingt
de aanwezigheid van verplichte variabelen af bij container-start.

```python
class Settings(BaseSettings):
    tenant_secret: str = Field(..., env="TENANT_SECRET")
    database_url: PostgresDsn
```

### Secret management (rotation)

| Secret Type | Opslag | Rotatie Policy | Notificatie |
|-------------|--------|----------------|-------------|
| **JWT Secrets** | Azure Key Vault | Elke 90 dagen | MetricAlert <= 30 dagen |
| **LLM API Keys** | GitHub Secrets | Bij vermoeden van lek | Handmatig |
| **DB Credentials** | Azure Key Vault | Elke 180 dagen | MetricAlert <= 30 dagen |
| **BREVO_API_KEY** | GitHub Secrets / Key Vault | Elk jaar | MetricAlert <= 30 dagen |
| **HCAPTCHA_SECRET** | GitHub Secrets | Elk jaar | Handmatig |
| **AZURE_BLOB_CONNECTION_STRING** | Key Vault | Elk jaar | MetricAlert <= 30 dagen |

**Ophalen van `workspacePrimarySharedKey`:**

```bash
# GOED — via CLI, nooit als Bicep output (ARM history is plaintext)
az monitor log-analytics workspace get-shared-keys \
  --resource-group <rg> \
  --workspace-name sanskriti-logs-prd \
  --query primarySharedKey -o tsv
```

## Consequences

### Positief

- Drastische vermindering van "broken deploys" door vroegtijdige schema-validatie
- Geen secrets in git-history (Gitleaks als eerste CI-job)
- Container CVE-scanning zichtbaar in GitHub Security tab zonder extra tooling
- pip-compile met `--generate-hashes` beschermt tegen dependency confusion aanvallen
- cosign signing biedt onweerlegbare bouw-herkomst (Rekor transparency log)
- SBOM faciliteert license-compliance en GDPR-verwerkersinventaris
- CODEOWNERS garandeert vier-ogen-principe op security-kritische paden
- MetricAlerts op Key Vault garanderen tijdige secret rotation

### Negatief

- Langere CI-tijden door extra scan-stappen (Trivy + pip-audit + npm audit)
- "Frictie" bij het toevoegen van nieuwe variabelen: schema bijwerken vereist
- `workspacePrimarySharedKey` nooit als Bicep-output exporteren (ARM deployment
  history is plaintext) — ophalen via CLI bij elke rotatie
- CODEOWNERS vereist dat geschikte reviewers beschikbaar zijn; bij solo-developer
  context is dit een known limitation (zie ADR-030 F-07)

### Notes

- `.env.example` blijft gesynchroniseerd met de Pydantic `Settings` class
- Zie ADR-030 voor de volledige toolkeuze-onderbouwing en alternatieven per categorie

## Bekende implementatiebug (P0-8) — vastgesteld 2026-05-28

**Bestanden:**
- `src/core/config/production_config.py:22` — `secret_key or "dev-secret-change-in-production"`
- `src/core/shared/interfaces.py:393` — `secret_key: str = "dev-secret-change-in-production"` als dataclass default

**Probleem:** Als `SECRET_KEY` of `JWT_SECRET_KEY` env var niet gezet zijn bij deployment,
tekent de applicatie live JWTs met een publiek bekende string. Elke aanvaller kan dan geldige
tokens voor elke tenant fabriceren — de geheime sleutel is geen geheim.

Dit is een directe omzeiling van gate 1 (Gitleaks) en gate 10 (Pydantic Settings) die
in dit ADR zijn gedefinieerd. Gitleaks detecteert secrets die te zien zijn in code; dit
patroon gebruikt een fallback-default in plaats van een hardcoded waarde, en ontglipt
daarmee de scanner.

**Vereiste fix:**

```python
# src/core/config/production_config.py
KNOWN_INSECURE_DEFAULTS = {
    "dev-secret-change-in-production",
    "dev-secret-key-change-in-production",
    "change-me",
    "secret",
}

secret_key = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET_KEY")
if not secret_key:
    raise ConfigurationError(
        "SECRET_KEY env var is required. Generate: openssl rand -hex 32"
    )
if secret_key in KNOWN_INSECURE_DEFAULTS:
    raise ConfigurationError(
        "SECRET_KEY is a known insecure default. Generate: openssl rand -hex 32"
    )
```

Voeg `_check_secret_key()` toe aan `config_validator.py` als startup-check, zodat de
applicatie bij elke start faalt als de key ontbreekt of een bekende waarde heeft.

**Aanvullend patroon:** `src/core/shared/interfaces.py:393` bevat dezelfde bekende string
als dataclass-default. Verwijder de default; lees de waarde uit env bij constructie.

**Prioriteit:** P0 — JWT-forgery mogelijk bij ontbrekende of standaard `SECRET_KEY`.
Volledig fix-plan: `docs/frontend/pages/22-platform-p0-blockers-scope.md` (P0-8).

---

## Changelog

- **2026-05-28** — P0-8 bug gedocumenteerd: secret key fallback naar bekende string omzeilt
  gate 1+10; fix-patroon vastgelegd met `KNOWN_INSECURE_DEFAULTS` en startup-check
- **2026-05-26** — Volledig geimplementeerd na 3-sprint security programma;
  gates 2-9 toegevoegd; status bijgewerkt naar Implemented; F-07 Known Limitation
  gedocumenteerd
