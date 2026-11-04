# Informatiebeveiligingsbeleid
## SanskritiSetu Enterprise AI Agent Operating System

---

| Eigenschap        | Waarde                                              |
|-------------------|-----------------------------------------------------|
| Versie            | 1.0                                                 |
| Datum             | 2026-05-26                                          |
| Eigenaar          | Rakesh Ramkhelawan (rakesh@sanskritisetu.org)        |
| Volgende review   | 2027-05-26                                          |
| Status            | Actief                                              |
| Classificatie     | INTERNAL                                            |

---

## 1. Doel

Dit beleid legt de minimum-beveiligingseisen vast voor alle systemen die betrokken zijn bij de verwerking, opslag en overdracht van informatie binnen het SanskritiSetu platform. Het doel is de vertrouwelijkheid, integriteit en beschikbaarheid van tenant-data te waarborgen en te voldoen aan toepasselijke wet- en regelgeving, waaronder de Algemene Verordening Gegevensbescherming (AVG/GDPR) en de voorbereidende eisen voor SOC 2 Type I certificering.

---

## 2. Scope

Dit beleid is van toepassing op alle systemen, processen en personen die toegang hebben tot of betrokken zijn bij het SanskritiSetu platform, inclusief:

- **Cloudinfrastructuur:** Azure Container Apps (West Europe - productie, North Europe - staging), Azure Container Registry (`sanskritisetuacr.azurecr.io`, UK South), Azure Key Vault, Azure Log Analytics
- **Databases en caching:** Azure PostgreSQL (met pgvector-extensie), Redis
- **CI/CD-platform:** GitHub Actions (repository `SanskritiSetu.org`)
- **Externe AI-providers:** Anthropic Claude, OpenAI, Google Gemini (via API-calls; geen data opgeslagen bij provider langer dan de transactieduur tenzij anders contractueel vastgelegd)
- **Alle code, configuratiebestanden en secrets** die onderdeel uitmaken van het platform

Uitgesloten van scope: eindgebruikers-apparaten van tenantsystemen, tenzij die direct verbinding maken met productie-API-endpoints.

---

## 3. Informatieclassificatie

Alle informatie die in het platform wordt verwerkt, wordt ingedeeld in een van de volgende vier niveaus. De classificatie bepaalt welke beveiligingsmaatregelen van toepassing zijn.

### 3.1 PUBLIC

Informatie die zonder beperking openbaar gedeeld mag worden.

Voorbeelden:
- Marketingteksten op de SanskritiSetu-website
- Gepubliceerde API-documentatie zonder authenticatie-details
- Open source code-componenten en hun licenties

Maatregelen: Geen bijzondere bescherming vereist.

### 3.2 INTERNAL

Informatie voor intern gebruik die niet bedoeld is voor externe partijen, maar waarvan openbaarmaking geen directe schade aan het platform of tenants veroorzaakt.

Voorbeelden:
- Architectuurdocumenten (ADRs), CLAUDE.md, SPRINT_PLANNING.md
- Interne runbooks en deployment-procedures
- Niet-productie log-uitvoer zonder persoonsgegevens

Maatregelen: Toegang beperkt tot geauthoriseerde medewerkers en tooling. Niet gedeeld via publieke kanalen.

### 3.3 CONFIDENTIAL

Informatie waarvan onbevoegde openbaarmaking schade kan veroorzaken aan het platform, tenants of betrokken personen.

Voorbeelden:
- Tenant-bedrijfsdata en workflowconfiguraties
- Gebruikersnamen, e-mailadressen en authenticatiedata van tenants
- Interne financiele informatie
- Cryptografische sleutels die niet in Key Vault zijn opgeslagen

Maatregelen: Versleuteld in rust en tijdens transport. Toegang op need-to-know basis. Logging van toegangsacties verplicht.

### 3.4 RESTRICTED

Maximale bescherming vereist. Openbaarmaking kan directe juridische, financiele of reputatieschade veroorzaken.

Voorbeelden:
- Productie-API-sleutels voor LLM-providers (Anthropic, OpenAI, Google)
- Azure service principal credentials
- GitHub Secrets en Azure Key Vault secrets
- Persoonsgegevens die vallen onder GDPR bijzondere categorien (Art. 9 AVG)
- Auditlogregels met persoonlijk identificeerbare informatie

Maatregelen: Uitsluitend opgeslagen in Azure Key Vault of GitHub Encrypted Secrets. Nooit in code, logs of e-mail. Rotatie bij vermoeden van compromittering. Toegang gelogd en gemonitord.

---

## 4. Toegangsbeheer

### 4.1 Authenticatievereisten

Alle toegang tot het SanskritiSetu platform vereist authenticatie. De volgende principes gelden:

- **API-toegang:** Alle API-endpoints (met uitzondering van expliciet publieke health-endpoints) vereisen een geldig JWT-token. Tokens worden uitsluitend geaccepteerd via de `Authorization: Bearer`-header of een httpOnly-cookie. Query-parameterterugval is uitsluitend toegestaan voor WebSocket-handshakes (ADR-003).
- **Tenant-isolatie:** Alle databasequery's worden automatisch gefilterd op `tenant_id` via de SQLAlchemy `do_orm_execute`-hook en Row Level Security (RLS) op PostgreSQL. Handmatige tenant-filtering is aanvullend vereist in alle repository-methoden (ADR-005).
- **Productie-infrastructuur:** Toegang tot Azure-productieomgevingen vereist een Azure-account met toewijzing aan de `sanskritisetu-github-actions` service principal (App ID: `34923a6f-3f24-47f1-bb56-ce8416bc850f`). Direct console-toegang zonder CI/CD is niet toegestaan voor deployment-acties.

### 4.2 Least Privilege

- Elke dienst ontvangt uitsluitend de minimaal benodigde rechten.
- De Azure Container Registry wordt benaderd via Managed Identity; wachtwoordgebaseerde ACR-toegang is uitgeschakeld.
- GitHub Actions-workflows ontvangen uitsluitend de benodigde OIDC-scopes voor de specifieke taak (push to ACR, deploy to Container Apps).
- Databasegebruikers per omgeving: productie-gebruiker heeft geen DDL-rechten; migraties worden uitgevoerd door een aparte migratiegebruiker.

### 4.3 Versiebeheer en branch-bescherming

- Branch protection is actief op `main` en `develop`.
- Directe pushes naar `main` zijn geblokkeerd; wijzigingen vereisen een pull request met goedkeuring.
- CODEOWNERS-review is verplicht voor wijzigingen in beveiligingskritieke bestanden (bijv. `.github/workflows/`, `src/core/auth/`, `src/core/middleware/`).
- Signing van commits: [TODO: Verplichte commit-signing instellen bij toevoeging tweede contributor]

### 4.4 Scheiding van omgevingen

| Omgeving  | Regio        | Doel                     | Status (2026-08-30)                     |
|-----------|--------------|--------------------------|-----------------------------------------|
| Staging   | North Europe | Testdeploys vanuit CI/CD | Ingericht, herbouwd op 2026-08-27       |
| Productie | West Europe  | Live tenant-verkeer      | **NIET INGERICHT** sinds 2026-05-11     |

Bron: `docs/infra/AZURE_OMGEVINGEN.md` -- de enige plek waar deze gegevens worden onderhouden. Neem ze hier niet opnieuw over (ADR-036 OP-116).

Productie- en staging-omgevingen maken gebruik van aparte databases, Redis-instanties en Key Vault-sleutels. Productiedata wordt nooit gekopieert naar staging.

---

## 5. Wachtwoordbeleid en authenticatie

### 5.1 JWT-tokenparameters

- Access token geldigheid: 60 minuten
- Refresh token geldigheid: 7 dagen, met rotatie bij gebruik
- JWT secret-sleutels: minimaal 32 tekens, uitsluitend opgeslagen in Azure Key Vault
- Ondersteund algoritme: HS256; meerdere verificatiepaden zijn niet toegestaan (één pad via `jwt_handler.verify_token()`)

### 5.2 Account lockout

- Na 5 opeenvolgende mislukte inlogpogingen wordt het account automatisch geblokkeerd voor 15 minuten.
- Blokkering wordt gelogd als beveiligingsgebeurtenis in de audit trail.

### 5.3 Meerfactorauthenticatie (MFA)

- MFA is verplicht op het GitHub-account van de repository-eigenaar.
- MFA is verplicht op het Azure Portal-account met productietoegang.
- [TODO: Screenshot-bewijs van actieve MFA-configuratie toevoegen aan `docs/compliance/soc2/evidence/` bij productielancering]

### 5.4 Cookiebeveiliging

Alle sessiecookies die door het platform worden ingesteld, voldoen aan de volgende eigenschappen:

```
httpOnly: true     -- JavaScript-toegang geblokkeerd
Secure: true       -- Uitsluitend over HTTPS
SameSite: Lax      -- CSRF-bescherming
max_age: 3600      -- Access token: 1 uur
```

---

## 6. Encryptie

### 6.1 Data in transit

- Alle externe verbindingen met het platform worden beveiligd met TLS 1.3, afgedwongen door Traefik als edge gateway (ADR-009).
- Interne service-to-service communicatie binnen Azure Container Apps maakt gebruik van Azure-beheerde encryptie op het netwerkniveau.
- TLS 1.0 en 1.1 zijn uitgeschakeld.

### 6.2 Data at rest

- Azure PostgreSQL, Redis Cache en Azure Blob Storage zijn versleuteld met AES-256 via Azure-beheerde sleutels (standaard Azure-encryptie).
- Azure Key Vault gebruikt HSM-backed sleutels voor RESTRICTED-classificeerde gegevens.
- [TODO: Customer Managed Keys (CMK) evalueren bij eerste enterprise klant met contractuele eis]

### 6.3 Secrets en sleutelbeheer

- Alle RESTRICTED-geclassificeerde sleutels worden uitsluitend opgeslagen in Azure Key Vault of als GitHub Encrypted Secrets.
- Secrets worden nooit geschreven naar logbestanden, broncode, Docker images of omgevingsvariabelen buiten de CI/CD-context.
- Gitleaks scant elke CI-run op per ongeluk ingecheckte secrets (geimplementeerd als eerste job in de pipeline).
- Rotation policy: handmatige rotatie bij vermoeden van compromise; [TODO: Automatische rotatie via Key Vault rotation policy instellen voor LLM API-sleutels]

---

## 7. Wijzigingsbeheer

### 7.1 Wijzigingsprocedure

Alle wijzigingen aan het SanskritiSetu platform verlopen via de volgende procedure:

1. Wijziging ingecheckt op `develop`-branch via commit (met beschrijvend bericht)
2. CI/CD-pipeline valideert automatisch: linting, type-checking, unittests, integratietests, security scanning (Trivy, pip-audit, npm audit, Gitleaks, Bandit)
3. Pull request naar `main` met verplichte review (CODEOWNERS)
4. Goedgekeurde merge triggert CD-pipeline voor staging-deploy
5. Productiedeploy via versietag (`v*.*.*`) op `develop`-branch, met 5-minuten wait timer en verplichte reviewer-approval in de GitHub Environment

### 7.2 Verboden

- Handmatige wijzigingen in productie buiten de CI/CD-pipeline zijn niet toegestaan.
- Het overslaan van de pipeline (`--no-verify`, directe Azure CLI-deploy zonder workflow) is uitsluitend toegestaan bij door P1-incident gedocumenteerde noodsituaties en vereist achteraf documentatie in het incidentlog.

### 7.3 Documentatieverplichtingen

Elke architectuurbeslissing wordt vastgelegd als Architecture Decision Record (ADR) in `docs/adr/`. Zie `docs/adr/000-adr-index.md` voor het overzicht.

Uitgebreide procedure: zie `docs/compliance/soc2/change-management-procedure.md`.

---

## 8. Kwetsbaarhedenbeheer

### 8.1 Container image scanning

- Trivy voert bij elke CI-run een scan uit op alle container images (backend API, frontend, worker).
- Een aparte Trivy-scan wordt uitgevoerd voorafgaand aan elke push naar Azure Container Registry.
- CRITICAL- en HIGH-kwetsbaarheden blokkeren de pipeline; de build faalt automatisch.
- SARIF-rapporten worden geupload naar GitHub Code Scanning voor audittrail.

### 8.2 Dependency scanning

- `pip-audit` controleert alle Python-afhankelijkheden bij elke CI-run.
- `npm audit` controleert alle frontend-afhankelijkheden bij elke CI-run.
- Afhankelijkheden worden bijgehouden via Renovate voor automatische updatepull requests.

### 8.3 Supply chain beveiliging

- Alle GitHub Actions-referenties zijn vastgepind op een specifieke commit-hash (geen versietags die kunnen worden overschreven).
- Artifact signing: container images worden gesigneerd via cosign met keyless signing op basis van GitHub OIDC-tokens.
- Het SLSA-provenance-niveau voor containerbouw is gedocumenteerd in de CI-workflow.

### 8.4 Statische analyse

- Bandit voert statische beveiligingsanalyse uit op Python-broncode bij elke CI-run.
- ESLint met security-regels is geconfigureerd voor TypeScript/React-code.
- Mypy controleert type-veiligheid voor alle Python-modules.

---

## 9. Incident response

De volledige procedure voor het detecteren, classificeren en afhandelen van beveiligingsincidenten is vastgelegd in:

`docs/compliance/soc2/incident-response-plan.md`

Beveiligingsincidenten worden gemeld aan de eigenaar van dit beleid: Rakesh Ramkhelawan (rakesh@sanskritisetu.org).

---

## 10. Logging en monitoring

### 10.1 Audit trail

- Alle authenticatie-events (inloggen, uitloggen, mislukte pogingen, token refresh), toegangsacties op tenant-data, en administrator-handelingen worden gelogd conform ADR-019.
- Auditlogregels worden beveiligd met een SHA-256 hash chain voor tamper-detectie. Elke logregel bevat de hash van de vorige rij. Verwijdering is sinds 2026-08-10 detecteerbaar via een anker per tenant (`audit_chain_anchors`) dat de rijtelling en de ketenkop met de vorige meting vergelijkt; de controle draait dagelijks en alarmeert.
  **Grens, toegevoegd 2026-08-11:** de hash is ongesleuteld, dus een aanvaller met schrijfrechten op de database kan de keten herberekenen (ADR-036 OP-120, in behandeling). De volledige afweging staat in ADR-019.
- Logdata wordt geclassificeerd per dataniveau (PUBLIC t/m RESTRICTED) en behandeld overeenkomstig.

### 10.2 Opslag en retentie

- ~~Logdata wordt weggeschreven naar Azure Log Analytics.~~ -- **onjuist, gecorrigeerd 2026-08-11.** De workspace bestaat in Bicep, maar niets stuurt er auditregels heen: geen `diagnosticSettings`, geen logexport, geen `azure-monitor`-pakket. Auditlogdata staat uitsluitend in PostgreSQL.
- Retentie: 365 dagen is geconfigureerd op de workspace, maar geldt feitelijk alleen voor de database zolang er niets naar Log Analytics stroomt.
- [TODO: Immutable log storage (Azure Blob met Write-Once policy) configureren voor RESTRICTED-logdata bij productielancering]

### 10.3 Alerting

- Prometheus-metrics worden gescraped door Azure Monitor.
- Grafana-dashboards zijn beschikbaar voor real-time inzicht in agentstatus, wachtrijdiepte en authenticatie-anomalieen.
- Kritieke alerts (P1/P2 conform het incidentresponsplan) genereren direct een notificatie via [TODO: Notificatiekanaal instellen - bijv. PagerDuty of Azure Monitor Action Group - voor productielancering].

---

## 11. Naleving en juridische grondslag

### 11.1 GDPR

- Verwerkingsbasis voor platform-operationele data: gerechtvaardigd belang (Art. 6(1)(f) AVG) voor fraudedetectie, beveiliging en platformintegriteit.
- Verwerkingsbasis voor door tenants aangeleverde persoonsgegevens: contractuele noodzaak (Art. 6(1)(b) AVG) of toestemming (Art. 6(1)(a) AVG), afhankelijk van de verwerkersovereenkomst.
- Een Data Protection Impact Assessment (DPIA) voor AI-verwerking is beschikbaar in `docs/compliance/DPIA_AI_PROCESSING.md`.
- Verwerkersovereenkomsten: [TODO: Standaard verwerkersovereenkomst opstellen voor tenant-onboarding]

### 11.2 SOC 2

Dit document ondersteunt de voorbereiding op SOC 2 Type I certificering. Het dekt de Trust Services Criteria Security (CC) als primaire categorie. De status van alle controledoelstellingen wordt bijgehouden in `docs/compliance/soc2/` en het risicoregister (`docs/compliance/soc2/risk-register.md`).

### 11.3 Hostinglocaties en datasoevereiniteit

- Productiedata wordt uitsluitend verwerkt binnen de Europese Unie (West Europe en North Europe Azure-regio's).
- Azure biedt EU Data Boundary-garanties voor deze regio's.
- Overdracht buiten de EU: niet van toepassing voor productie-opslag; externe AI-providers (Anthropic, OpenAI, Google) verwerken uitsluitend de transactieinhoud zonder langdurige opslag. [TODO: Verwerkersovereenkomsten met AI-providers documenteren in `docs/compliance/soc2/vendor-agreements/`]

---

## 12. Sancties

Schendingen van dit beleid - inclusief maar niet beperkt tot het omzeilen van beveiligingscontroles, het opslaan van credentials buiten goedgekeurde systemen, of het uitvoeren van niet-geautoriseerde productiewijzigingen - worden gedocumenteerd in het incidentlog en geescaleerd naar Rakesh Ramkhelawan als platformeigenaar.

Bij betrokkenheid van externe partijen of contractanten wordt schending behandeld conform de toepasselijke contractuele bepalingen.

---

## 13. Revisiehistorie

| Versie | Datum      | Auteur             | Wijziging                      |
|--------|------------|--------------------|-------------------------------|
| 1.0    | 2026-05-26 | Rakesh Ramkhelawan | Initieel document              |

---

*Dit document is onderdeel van het SanskritiSetu compliance-dossier. Bij tegenstrijdigheid met specifieke ADRs of runbooks prevaleert het specifieke document voor de technische implementatie; dit beleid prevaleert voor de nalevingsstatus.*

> **Gecorrigeerd 2026-08-11 (ADR-036 OP-118 t/m OP-121).** De volledige afweging, met wat de keten wel en niet detecteert, staat in ADR-019 onder "Wat tamper-evident hier WEL en NIET betekent". Correcties zijn doorgehaald in plaats van verwijderd, zodat zichtbaar blijft dat een claim is bijgesteld.
