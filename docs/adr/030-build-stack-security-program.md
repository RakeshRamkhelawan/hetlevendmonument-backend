# ADR-030: Build-Stack Security Programma

## Status

Accepted — 2026-05-26

### Statushistorie

- 2026-05-22: Programma gestart na enterprise audit (score 2.3/5 — 18 findings, 4 CRITICAL, 8 HIGH)
- 2026-05-26: Accepted na voltooiing van 3 sprints; alle CRITICAL en HIGH findings opgelost
  (F-07 separation of duties is een Known Limitation voor een solo-developer project)

## Context

Een enterprise security audit leverde in mei 2026 een gemiddelde score van 2.3/5 op voor de
SanskritiSetu build-stack. De audit beoordeelde vijf domeinen:

| Domein | Score voor | Score na |
| ------ | ---------- | -------- |
| CI/CD security | 3.0/5 | 4.2/5 |
| Supply chain beveiliging | 1.0/5 | 3.7/5 |
| Build reproducibility | 2.0/5 | 4.0/5 |
| Infrastructuur-as-Code | 1.0/5 | 2.5/5 |
| Gemiddeld | 2.3/5 | ~3.4/5 |

De 18 findings (F-01 t/m F-18) vielen uiteen in vier categorieën:

1. **Supply chain** — geen container CVE-scanning, geen SBOM, geen artifact signing,
   geen dependency lockfile met hashes, base images niet digest-gepind (F-01, F-02, F-03,
   F-05, F-06)
2. **CI/CD hardening** — GitHub Actions actions niet op commit-hash gepind, geen
   SCA-gate, geen pre-push hook, geen smoke test gate, ACR gebruikt wachtwoord
   in plaats van Managed Identity, Activepieces sandbox uitgeschakeld (F-08, F-09,
   F-10, F-11, F-13, F-15)
3. **IaC & governance** — geen Bicep IaC, geen CODEOWNERS, geen secret rotation
   policies, geen gecentraliseerde logging (F-04, F-07, F-14, F-16, F-18)
4. **Kwaliteitsborging** — geen integratie-tests in CI, geen coverage gate (F-12, F-17)

Dit ADR legt de definitieve toolkeuzes vast die in de drie sprints zijn gemaakt.

### Alternatieven per tool-categorie

#### Container CVE-scanning

| Tool | Voordeel | Nadeel | Besluit |
| ---- | -------- | ------ | ------- |
| **Trivy** (Aqua Security) | Open source, SARIF-output, native GitHub Security tab integratie, ondersteunt OS + Python + npm | Community-gedreven, commercieel support optioneel | **Gekozen** |
| Snyk | Sterk commercieel platform, developer-experience | Betaald voor hoge volumes, vendor lock-in | Afgewezen |
| Grype (Anchore) | Open source, CycloneDX output | Minder actief onderhouden, minder GitHub integratie | Afgewezen |

**Implementatie:** 9 Trivy-scans per workflow (backend, frontend, worker x ci + cd-staging + cd-prod)
met `format: sarif` en upload naar GitHub Security tab via `codeql-action/upload-sarif`.

#### Artifact signing

| Tool | Voordeel | Nadeel | Besluit |
| ---- | -------- | ------ | ------- |
| **cosign keyless** (Sigstore) | Geen sleutelbeheer, GitHub OIDC als identiteitsbron, SLSA-compatibel | Relatief nieuw ecosysteem | **Gekozen** |
| GPG signing | Bewezen, breed ondersteund | Sleutelbeheer vereist (rotatie, revocatie, veilige opslag) | Afgewezen |
| Notary v2 | Docker-native | Complexe infrastructure (Notary server), weinig tooling-integratie | Afgewezen |

**Implementatie:** `cosign sign` na elke ACR-push; verifieerbaar via `cosign verify`.
GitHub Actions vereist `id-token: write` permission voor OIDC-flow.

#### SBOM-generatie

| Tool | Voordeel | Nadeel | Besluit |
| ---- | -------- | ------ | ------- |
| **syft** (Anchore) | CycloneDX formaat, GitHub Actions ondersteuning, actief project | — | **Gekozen** |
| cdxgen | CycloneDX formaat, breed taal-support | Trager, meer afhankelijkheden | Afgewezen |
| Docker buildx SBOM | Ingebouwd | Alleen image-niveau, geen applicatie-niveau | Afgewezen |

**Implementatie:** `anchore/sbom-action` als stap in cd-*.yml; SBOM bijgevoegd aan
GitHub Release als artifact (`sbom-*.json`). Formaat: CycloneDX JSON.

#### Python dependency lockfile

| Tool | Voordeel | Nadeel | Besluit |
| ---- | -------- | ------ | ------- |
| **pip-compile** (pip-tools) | Integreert met bestaande requirements.txt workflow, `--generate-hashes` voor integriteitscontrole, `--platform linux/amd64` voor deterministische cross-platform builds | Geen ingebouwde venv-beheer | **Gekozen** |
| Poetry | Geintegreerde lockfile + venv + build | Vereist migratie van requirements.txt; conflicteert met bestaande CI-patronen | Afgewezen |
| uv | Extreem snel, Rust-based | Nog experimenteel (mei 2026); lockfile formaat niet stabiel | Afgewezen |

**Implementatie:** `pip-compile requirements.in --generate-hashes --platform linux/amd64
--output-file requirements.txt`. CI verifieert dat requirements.txt up-to-date is
(`pip-compile --dry-run --check`).

#### Base image pinning

Alle `FROM` instructies in Dockerfiles gebruiken digest-pinning:

```dockerfile
FROM python:3.11-slim-bookworm@sha256:<digest>
```

Renovate bot beheert automatische digest-updates via `digest: { enabled: true }` in
`renovate.json`. Dit garandeert reproducible builds terwijl security-patches
geautomatiseerd worden.

#### IaC toolkeuze

| Tool | Voordeel | Nadeel | Besluit |
| ---- | -------- | ------ | ------- |
| **Azure Bicep** | Native Azure, geen state file, gratis, directe ARM-integratie, modulair | Azure-specifiek, geen multi-cloud | **Gekozen** |
| Terraform | Multi-cloud, groot ecosysteem | State file management, state lock, licensing wijziging (BSL) in 2023 | Afgewezen |
| Pulumi | Code-based (TypeScript/Python), sterke type-safety | Extra SDK-laag, state backend vereist | Afgewezen |

**Implementatie:** `infra/bicep/` met modules per resource-type: `container-app.bicep`,
`acr.bicep`, `key-vault.bicep`, `log-analytics.bicep`. Fase 1 omvat CI-validatie
(`az bicep build --file`); Fase 2 voegt deployment-stap toe aan cd-*.yml
(Incremental mode, wacht op staging-test — zie Follow-up items).

#### Gecentraliseerde logging

| Tool | Voordeel | Nadeel | Besluit |
| ---- | -------- | ------ | ------- |
| **Azure Log Analytics** | Native Azure, geen extra infra, ingebouwde retentie-policies, KQL | Vendor lock-in, workspacePrimarySharedKey nooit in Bicep output exposen | **Gekozen** |
| ELK Stack (Elasticsearch + Logstash + Kibana) | Open source, krachtige queries | Hoge operationele overhead (3 services), storage-kosten | Afgewezen |
| Grafana Loki | Open source, Prometheus-integratie, lage kosten | State management, geen managed Azure optie | Afgewezen |

**Implementatie:** twee Log Analytics workspaces — `sanskriti-logs-prd` (West Europe)
en `sanskriti-logs-stg` (North Europe). Zie ADR-014 voor details over retentie,
GDPR-grondslag en KQL-querypatronen.

#### Secret rotation

Azure Key Vault expiry policies gecombineerd met **MetricAlerts** op de
`DaysUntilExpiry`-metric (drempel: <= 30 dagen). Bewuste keuze voor MetricAlerts
boven ActivityLogAlerts: ActivityLogAlerts kunnen uitsluitend reageren op events
(aanmaken/verwijderen) — zij kunnen niet detecteren wanneer een secret de
vervaldatum nadert. Scope van de MetricAlert is het Key Vault resource-id
(niet `resourceGroup().id` — dat geeft een ARM deployment-fout).

## Decision

Wij implementeren het build-stack security programma als drie opeenvolgende sprints:

- **Sprint 1** — Container scanning (F-01), Actions pinning (F-08), SCA (F-13),
  ACR Managed Identity (F-10), Activepieces sandboxing (F-09)
- **Sprint 2** — Python lockfile (F-05), Base image pinning (F-06), SBOM (F-03),
  cosign signing (F-02), Integratie-tests in CI (F-12), Coverage gate (F-17),
  Pre-push hook herstel (F-11)
- **Sprint 3** — Bicep IaC (F-04), CODEOWNERS (F-14), Key Vault expiry (F-16),
  Log Analytics (F-18), Smoke test gate (F-15), Separation of duties (F-07)

### Gehanteerde architectuurprincipes

1. **Supply chain integriteit is een CI-gate, geen opt-in** — Trivy, pip-audit en
   npm audit falen de pipeline; ze lopen niet met `continue-on-error: true`.
2. **Geen secrets in build-artefacten** — cosign keyless elimineert signing keys;
   `workspacePrimarySharedKey` wordt opgehaald via `az monitor log-analytics
   workspace get-shared-keys` en nooit in Bicep output gezet.
3. **Reproducible builds** — digest-pinning op base images garandeert dat
   dezelfde commit altijd dezelfde image produceert.
4. **Managed Identity boven wachtwoorden** — ACR-authenticatie via Azure Managed
   Identity (`"identity":"system"` in ARM, `--registry-server` only in CLI)
   verwijdert `ACR_PASSWORD` als GitHub Secret.
5. **Audit trail op release-artefacten** — cosign transparency log (Rekor) plus
   SBOM als GitHub Release-attachment bieden aantoonbare herkomst.

### SLSA-niveau voortgang

Het programma brengt SanskritiSetu naar de richting van **SLSA Level 2**:

| SLSA eis | Status |
| -------- | ------ |
| Versiebeheer | ✅ (git) |
| Geauthenticeerde builds | ✅ (GitHub Actions + Managed Identity) |
| Artifact signing | ✅ (cosign keyless) |
| Herkomst (provenance) | Gedeeltelijk (SBOM aanwezig; SLSA provenance attestation = post-MVP) |
| Isolated builds | ✅ (GitHub-hosted runners) |
| Two-person review | Beperkt (F-07 Known Limitation, solo-developer) |

## Consequences

### Positief

- Audit score gemiddeld gestegen van 2.3/5 naar ~3.4/5; CI/CD van 3.0 naar 4.2,
  supply chain van 1.0 naar 3.7
- Alle 4 CRITICAL findings gesloten; alle 8 HIGH findings gesloten (F-07 Known Limitation)
- Container CVE-scanning met SARIF in GitHub Security tab geeft visueel inzicht
  in kwetsbaarheden per image-laag
- cosign keyless verwijdert signing key management volledig; Rekor transparency log
  biedt onweerlegbare bouw-herkomst
- SBOM per release maakt license-compliance audits en GDPR-verwerkersinventaris eenvoudiger
- pip-compile met `--generate-hashes` voorkomt supply chain aanvallen via gemanipuleerde
  PyPI-pakketten (bijv. dependency confusion)
- Bicep IaC maakt infrastructuur reviewbaar in pull requests (geen handmatige Azure Portal-wijzigingen)
- CODEOWNERS op 15 security-kritische paden garandeert vier-ogen-principe voor
  Dockerfiles, workflows, requirements.txt en infra-modules

### Negatief

- **ACR Basic SKU limiteringen** — Basic SKU ondersteunt geen `retentionPolicy` en
  `exportPolicy` in Bicep. Deze Bicep-attributen zijn weggelaten; upgrade naar
  Premium SKU is nodig voor private endpoints en beleidsbeheer.
- **F-07 solo-developer beperking** — Separation of duties is een known limitation.
  De 5-minuten-timer in cd-*.yml is een procedurele controle; GitHub staat
  self-approval toe voor repository-admins. Structurele fix zodra een tweede
  contributor beschikbaar is.
- **Log Analytics 1 GB/dag cap** — bij productieverkeer zullen logs boven 1 GB/dag
  worden afgekapt. Dit is een GDPR Artikel 33-risico (gemiste incidenten). Verhogen
  naar 5 GB/dag zodra productieverkeer bekend is.
- **Bicep deployment fase 2 nog niet actief** — Fase 1 omvat uitsluitend CI-validatie.
  De deployment-stap naar Azure (Incremental mode) wordt in een volgende sprint
  toegevoegd na validatie op staging.

### Follow-up items (niet-blokkerend voor MVP)

1. **F-04 Fase 2** — Bicep deployment-stap in cd-staging.yml en cd-prod.yml
   (Incremental mode, wacht op staging-test van volledige module-suite)
2. **F-07** — Structurele separation of duties zodra tweede contributor beschikbaar
3. **ACR Basic → Premium** — nodig voor private endpoints en `exportPolicy`
4. **Log Analytics capacity** — verhoging van 1 GB naar 5 GB/dag bij productieverkeer
5. **PostgreSQL geo-redundante backup** — RPO verbeteren van 24h naar < 5 minuten
6. **SLSA provenance attestation** — voegt formele `slsa-provenance` attestation
   toe aan GitHub Releases (brengt SLSA Level 2 compleet)

## Geraakte ADRs

| ADR | Hoe geraakt |
| --- | ----------- |
| ADR-013 | Uitgebreid met Trivy, pip-audit, npm audit, cosign, syft, CODEOWNERS en Key Vault expiry |
| ADR-014 | Uitgebreid met Azure Log Analytics implementatie (dual workspace, retentie, KQL) |
| ADR-009 | Traefik TLS — niet gewijzigd, maar ACR private endpoints (post-MVP) raken de egress-configuratie |
| ADR-005 | RLS-policies blijven de primaire data-isolatielaag; Log Analytics verwerkt geen row-level data |

## Changelog

- **2026-05-26 v1.0** — Initial Accepted na voltooiing 3-sprint programma (Rakesh)

## SOC 2 Mapping

Dit ADR levert aantoonbaar bewijs voor de volgende SOC 2 Security Criteria:

| Criterium | Subcriteria | Hoe dit ADR voldoet |
| --------- | ----------- | ------------------- |
| CC8.1 | Changes authorized before implementation | Alle code-wijzigingen vereisen PR review via CODEOWNERS (F-14); production deploys hebben een 5-minuten wait timer en required reviewer (F-07 GitHub Environment); directe pushes naar main zijn geblokkeerd via branch protection |
| CC8.1 | Changes tested before implementation | CI gates voor elke PR: Gitleaks, Trivy CVE scan, pip-audit, npm audit, unit tests en integratietests met coverage gate van minimaal 80%; cosign signing na succesvolle CI run als bewijs van integriteit |
| CC8.1 | Changes documented | Git history, CODEOWNERS audit trail en GitHub Environment deployment log zijn auditeerbare wijzigingsrecords raadpleegbaar door auditors |
| CC6.8 | Protection against malicious software in supply chain | Trivy (container CVEs), pip-audit en npm audit (dependency CVEs), cosign keyless signing (artifact integriteit), syft SBOM (complete dependency inventaris), digest-gepinde base images |
| CC7.5 | Disaster recovery | Auto-rollback op smoke test failure (F-15); gedocumenteerde RTO van circa 8 minuten en RPO van circa 1 minuut; DR test rapport aanwezig (F-18) |
| CC9.2 | Vendor risk management | Azure (SOC 2 gecertificeerd als cloud provider), GitHub (SOC 2 gecertificeerd), cosign/Sigstore (open source, geen vendor dependency voor signing keys) |

### Open gaps richting volledige SOC 2 Type I readiness

- Geen formeel informatiebeveiligingsbeleid document (CC1.2 — organisatorisch); beleid is impliciet in ADRs maar niet als ondertekend document aanwezig
- Geen incident response plan als ondertekend document (CC7.3); procedures staan in runbooks maar zijn niet als formeel beleid geformaliseerd
- Geen kwartaallijks access review proces (CC6.1); toegangsrechten worden ad-hoc beheerd zonder periodieke herbevestiging
- Geen formeel risicoregister (CC3.1); risicos zijn gedocumenteerd per ADR maar niet gecentraliseerd bijgehouden
- Geen vendor security assessment documenten voor Anthropic, OpenAI en DeepSeek (CC9.2); deze LLM-aanbieders verwerken potentieel bedrijfsdata maar hebben geen formele beoordeling ondergaan
- Externe penetration test vereist voor Type I certificering (CC7.1 — jaarlijks); nog niet uitgevoerd
