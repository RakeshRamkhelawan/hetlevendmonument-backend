# Incident Response Plan
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

## 1. Definities

### 1.1 Beveiligingsincident

Een beveiligingsincident is elke gebeurtenis die de vertrouwelijkheid, integriteit of beschikbaarheid van het SanskritiSetu platform of de daarin verwerkte data verstoort, of waarbij een redelijk vermoeden bestaat dat dit het geval is. Voorbeelden:

- Ongeautoriseerde toegang tot productiesystemen of tenant-data
- Compromittering van authenticatiecredentials (API-sleutels, JWT-secrets, Azure credentials)
- Detectie van malware of onverwachte code-uitvoering in de infrastructuur
- Succesvolle of gefaalde aanvalspogingen op de applicatielaag (bijv. SQL-injectie, prompt injection)

### 1.2 Datalek (GDPR Art. 4(12))

Een datalek in de zin van de AVG is een inbreuk op de beveiliging die per ongeluk of op onrechtmatige wijze leidt tot vernietiging, verlies, wijziging of ongeoorloofde verstrekking van of toegang tot doorgezonden, opgeslagen of anderszins verwerkte persoonsgegevens.

Een datalek omvat zowel opzettelijke aanvallen (ongeautoriseerde toegang) als accidentele incidenten (verkeerde configuratie waardoor data zichtbaar werd voor verkeerde tenant).

### 1.3 Beschikbaarheidsincident

Een beschikbaarheidsincident is elke geplande of ongeplande onderbreking van de dienstverlening van het platform. Dit omvat:

- Volledige uitval van de API (HTTP 503 voor alle requests)
- Degradatie waarbij meer dan 10% van requests faalt of een latentie >5 seconden heeft
- Uitval van een kritieke afhankelijkheid (PostgreSQL, Redis, Azure Container Apps)

Geplande maintenance met minimaal 24 uur voorafgaande kennisgeving aan tenants valt buiten de scope van dit plan.

---

## 2. Classificatie van incidenten

Elk incident wordt bij detectie direct geclassificeerd op ernstniveau. Bij twijfel: classificeer hoger en degradeer later.

### P1 - CRITICAL

Directe, significante schade aan het platform of tenants. Vereist onmiddellijke respons.

Voorbeelden:
- Bewezen datalek waarbij persoonsgegevens van tenants zijn blootgesteld of geexfiltreerd (activeert GDPR-meldplicht Art. 33)
- Ongeautoriseerde toegang tot de productiedatabase of Azure-omgeving
- Compromittering van productie-credentials (Azure service principal, Key Vault secrets, LLM API-sleutels)
- Actieve aanval met bewijs van code-uitvoering op productiesystemen
- Volledige platform-uitval > 60 minuten zonder herstelpad

### P2 - HIGH

Ernstige verstoring of aanzienlijk verhoogd risico. Vereist spoedige respons.

Voorbeelden:
- Service-uitval langer dan 30 minuten
- CVE met CVSS-score >= 9.0 gedetecteerd in een actief productie-container image waarvoor geen patch beschikbaar is in de huidige image-versie
- Verdachte toegangspatronen die op een actieve aanval kunnen duiden (bijv. systematisch scrapen van tenant-data, bruteforce boven drempelwaarde)
- Verlies van log-integriteit (hash chain gebroken in audit trail)

### P3 - MEDIUM

Beperkte impact, of situatie is automatisch afgehandeld maar vereist onderzoek.

Voorbeelden:
- Service-uitval korter dan 30 minuten die succesvol is afgehandeld door de auto-rollback (rollback.yml)
- CVE gedetecteerd tijdens CI-run die de build blokkeert (productie niet geraakt, maar actie vereist)
- Mislukte authenticatiepogingen boven 10 per minuut voor een enkel account of IP-adres
- Falende auditlog-writes die via `best_effort` stil zijn gefaald (data-integriteitsrisico)

### P4 - LOW

Laag risico, geen directe actie op systemen vereist, maar opvolging binnen de week.

Voorbeelden:
- Monitoring-alerts met bekende, niet-kritieke oorzaken
- Key Vault-sleutels of certificaten die binnen 30 dagen verlopen
- Renovate-pull requests voor dependency-updates met bekende non-critical CVEs
- Afwijkingen in resource-gebruik zonder beveiligingsimplicaties

---

## 3. Responstijdlijnen

| Ernst | Detectie naar eerste actie | GDPR-melding (indien datalek) | Statusupdate frequentie |
|-------|---------------------------|-------------------------------|-------------------------|
| P1    | < 1 uur                   | < 72 uur na ontdekking        | Elk uur                 |
| P2    | < 4 uur                   | N.v.t. (geen meldplicht)      | Elke 4 uur              |
| P3    | < 24 uur                  | N.v.t.                        | Dagelijks               |
| P4    | < 7 dagen                 | N.v.t.                        | Bij afsluiting          |

"Eerste actie" betekent: het incident is gedocumenteerd in het incidentlog EN een initieel onderzoek is gestart EN (voor P1/P2) de relevante isolatiestap is ingezet.

---

## 4. Responders en contacten

| Rol                    | Persoon             | Contact                        | Beschikbaarheid     |
|------------------------|---------------------|--------------------------------|---------------------|
| Security eigenaar      | Rakesh Ramkhelawan  | rakesh@sanskritisetu.org       | Primair aanspreekpunt |
| Azure-ondersteuning    | Microsoft Support   | portal.azure.com > Help + Support (Subscription `<azure-subscription-id>`) | Via support ticket |
| GitHub-ondersteuning   | GitHub Support      | support.github.com             | Via support ticket  |
| Autoriteit Persoonsgegevens | AP           | autoriteitpersoonsgegevens.nl  | Uitsluitend bij datalek |

[TODO: Tweede contactpersoon toevoegen zodra een tweede medewerker of contractant toegang heeft tot het platform]

---

## 5. Stap-voor-stap responseprocedures

### 5.1 Gecompromitteerde credentials

**Trigger:** Vermoeden of bewijs dat een API-sleutel, JWT-secret, Azure service principal of GitHub Secret is blootgesteld.

**Stap 1 - Detectie en classificatie**
Bepaal welk credential is gecompromitteerd. Raadpleeg:
- GitHub Security Alerts (Gitleaks-bevindingen in CI)
- Azure Key Vault-toegangslogboeken
- Azure Monitor-alerts op onverwachte authentication-events

**Stap 2 - Isolatie (uitvoeren binnen P1-tijdlijn)**

Voor Azure service principal credentials:
```bash
# Stap 2a: Controleer actieve credentials
az ad sp credential list --id 34923a6f-3f24-47f1-bb56-ce8416bc850f

# Stap 2b: Verwijder gecompromitteerde credential (vervang KEY_ID door de specifieke key ID)
az ad sp credential delete --id 34923a6f-3f24-47f1-bb56-ce8416bc850f --key-id <KEY_ID>

# Stap 2c: Maak nieuwe credential aan
az ad sp credential reset --id 34923a6f-3f24-47f1-bb56-ce8416bc850f --append
```

Voor GitHub Secrets:
```bash
# Stap 2a: Roteer het secret in de GitHub-repository-instellingen
# GitHub UI: Settings > Secrets and variables > Actions > [secret naam] > Update

# Stap 2b: Verifieer dat de CI-pipeline na rotatie slaagt
gh run list --limit 5
```

Voor LLM API-sleutels (Anthropic, OpenAI, Google):
1. Log in op de betreffende provider-console
2. Revoceer de gecompromitteerde sleutel onmiddellijk
3. Genereer een nieuwe sleutel
4. Werk de Azure Key Vault-waarde bij:
```bash
az keyvault secret set --vault-name <keyvault-naam> \
  --name <secret-naam> \
  --value "<nieuwe-sleutel>"
```
5. Trigger een nieuwe deployment zodat de Container Apps de bijgewerkte secret ophalen

**Stap 3 - Onderzoek**
- Controleer Azure Log Analytics op toegangspatronen met het gecompromitteerde credential
- Bepaal of er aanwijzingen zijn voor ongeautoriseerde API-calls of datadumps
- Leg de bevindingen vast in het incidentlog

**Stap 4 - Rapportage**
Indien het credential toegang had tot persoonsgegevens en er aanwijzingen zijn voor gebruik door een onbevoegde partij: escaleer naar GDPR Art. 33-procedure (zie sectie 7).

---

### 5.2 Service-uitval

**Trigger:** Health-monitoring detecteert een uitval (liveness-probe faalt, >10% error rate).

**Stap 1 - Beoordeel de status**

> **Resourcegroep.** De commando's hieronder gebruiken `$RESOURCE_GROUP`. Zet die eerst:
> `export RESOURCE_GROUP=sanskritisetu-staging` voor staging. Voor productie is er geen
> waarde: die resourcegroep is op 2026-05-11 verwijderd en nooit herbouwd, zie
> `docs/infra/AZURE_OMGEVINGEN.md`. Dit scenario beschrijft dus de gewenste toestand,
> niet een bestaande omgeving (ADR-036 OP-116).

```bash
# Controleer container-status in de productie-omgeving
az containerapp show --name sanskritisetu-api \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.latestRevisionName"

# Bekijk recente revision-geschiedenis
az containerapp revision list --name sanskritisetu-api \
  --resource-group "$RESOURCE_GROUP" \
  --query "[].{name:name,active:properties.active,created:properties.createdTime}"
```

**Stap 2 - Automatische rollback (P3-scenario)**
Als de CI/CD-pipeline al een rollback heeft uitgevoerd (rollback.yml), verifieer dat de vorige revisie actief en gezond is:
```bash
az containerapp ingress show --name sanskritisetu-api \
  --resource-group "$RESOURCE_GROUP"
```

Zie `docs/runbooks/deployment-rollback.md` voor de volledige rollback-procedure.

**Stap 3 - Handmatige rollback (P2-scenario)**
Als auto-rollback niet is opgetreden:
```bash
# Activeer de vorige revisie handmatig
az containerapp revision activate \
  --name sanskritisetu-api \
  --resource-group "$RESOURCE_GROUP" \
  --revision <vorige-revisie-naam>
```

**Stap 4 - Root cause analyse**
- Raadpleeg Azure Log Analytics voor application logs rondom het tijdstip van uitval
- Controleer of de uitval gekoppeld is aan een recente deployment
- Leg de oorzaak en herstelstap vast in het incidentlog

---

### 5.3 CVE in productie-container image

**Trigger:** Trivy-scan rapporteert een CRITICAL of HIGH CVE in een image dat momenteel in productie draait.

**Stap 1 - Beoordeel de ernst**
Raadpleeg het SARIF-rapport in GitHub Code Scanning. Bepaal:
- CVSS-score en exploitability
- Of de kwetsbare component daadwerkelijk bereikbaar is via de applicatiecode (false positive check)
- Of een patch beschikbaar is in een nieuwere versie van het basisimage of de afhankelijkheid

Zie `docs/runbooks/trivy-cve-handling.md` voor de volledige CVE-triage-procedure.

**Stap 2 - Mitigatie**

Als patch beschikbaar:
1. Werk de betreffende afhankelijkheid bij in `requirements.txt`, `requirements-base.txt` of `package.json`
2. Of werk het basisimage bij in de `Dockerfile` (bijv. van `python:3.12-slim-bookworm` naar de gepatchte variant)
3. Voer de CI-pipeline opnieuw uit
4. Verifieer dat Trivy de CVE niet meer rapporteert
5. Deploy naar staging, verifieer gezondheid, deploy naar productie

Als geen patch beschikbaar (P2-scenario):
1. Documenteer in het incidentlog: CVE-ID, component, CVSS-score, afwezigheid van patch
2. Beoordeel of een tijdelijke mitigatie mogelijk is (bijv. de kwetsbare feature uitschakelen via configuratie)
3. Stel een herbeoordelingsdatum in van maximaal 7 dagen
4. Abonneer op de CVE-tracker van de betreffende component voor patch-notificaties

---

### 5.4 Datalek (GDPR Art. 33)

**Trigger:** Bewijs of redelijk vermoeden dat persoonsgegevens van tenants ongeoorloofd zijn blootgesteld, gewijzigd of verloren.

**Stap 1 - Inperking**
Beperk de verdere blootstelling zo snel mogelijk:
- Sluit het kwetsbare toegangspunt af (bijv. blokkeer een specifiek endpoint, revoceer credentials)
- Zet de getroffen service in maintenance-modus indien noodzakelijk

**Stap 2 - Inventarisatie**
Beantwoord zo snel mogelijk de volgende vragen (voor de GDPR-melding):
1. Welke categorie persoonsgegevens zijn betrokken? (naam, e-mail, bedrijfsdata, bijzondere categorien)
2. Van hoeveel betrokken personen (geschat)?
3. Van welke tenants?
4. Wat is de vermoedelijke oorzaak?
5. Zijn de gegevens geexfiltreerd, of alleen toegankelijk geweest?

Raadpleeg de audit trail (hash chain in `council_decisions`-tabel) en Azure Log Analytics.

**Stap 3 - Risicobeoordeling**
Bepaal het risico voor de betrokken personen op basis van:
- Categorie van gegevens (gewone persoonsgegevens vs. bijzondere categorien uit Art. 9 AVG)
- Aard van de onbevoegde partij (intern/extern, gekend/onbekend)
- Mogelijkheid tot misbruik (identiteitsfraude, discriminatie, financieel nadeel)

Als het risico voor de betrokken personen niet te verwaarlozen is: meldplicht bij de AP is van toepassing (Art. 33 AVG).

**Stap 4 - Melding bij de Autoriteit Persoonsgegevens**

Deadline: binnen 72 uur na het moment van ontdekking.

Meldpunt: https://autoriteitpersoonsgegevens.nl/themas/beveiliging-van-persoonsgegevens/meldplicht-datalekken

De melding bevat minimaal:
- De aard van de inbreuk op de beveiliging
- De (geschatte) categorieen en aantallen betrokkenen
- De (geschatte) categorieen en aantallen persoonsgegevensrecords
- De naam en contactgegevens van de functionaris gegevensbescherming of ander contactpunt: Rakesh Ramkhelawan (rakesh@sanskritisetu.org)
- De vermoedelijke gevolgen van de inbreuk
- De maatregelen die zijn genomen of voorgesteld om de inbreuk aan te pakken

Als de melding niet binnen 72 uur volledig kan worden gedaan: dien een initiële melding in met de op dat moment bekende informatie, en geef aan dat aanvullende informatie volgt.

**Stap 5 - Kennisgeving aan betrokkenen (indien vereist)**
Als het datalek waarschijnlijk een hoog risico inhoudt voor de betrokken personen, moeten zij individueel worden geinformeerd (Art. 34 AVG). Beoordeel dit in overleg met de AP-melding.
[TODO: Standaard kennisgevingssjabloon opstellen in `docs/compliance/soc2/templates/breach-notification-template.md`]

---

## 6. Post-incident procedure

Na afsluiting van elk incident (P1 t/m P3) worden de volgende stappen uitgevoerd:

### 6.1 Incidentlog bijwerken

Vul het incidentlog in `docs/compliance/soc2/incident-log.md` aan met:
[TODO: `docs/compliance/soc2/incident-log.md` aanmaken na het eerste incident]

Vereiste velden per incident:
- Incident ID (formaat: INC-YYYY-###)
- Datum/tijd van detectie
- Datum/tijd van eerste actie
- Datum/tijd van afsluiting
- Ernst (P1/P2/P3/P4)
- Beschrijving
- Getroffen systemen
- Betrokken data (classificatieniveau)
- Oorzaak
- Genomen maatregelen
- Aanbevelingen voor herhaling-preventie
- Openstaande actiepunten

### 6.2 Root cause analyse

Voor P1 en P2 incidenten wordt binnen 5 werkdagen een root cause analyse uitgevoerd. De analyse beantwoordt:
- Wat was de technische oorzaak?
- Waarom werd dit niet eerder gedetecteerd?
- Welke bestaande controlemaatregel heeft gefaald of ontbrak?
- Wat zijn de concrete verbeteracties?

### 6.3 Beleidsupdate

Als het incident aantoont dat dit plan, het informatiebeveiligingsbeleid, of een runbook onvolledig of onjuist is: werk het betreffende document bij en noteer de versiewijziging in de revisiehistorie.

---

## 7. Aanvullende documentatie en runbooks

| Document                                      | Locatie                                              |
|-----------------------------------------------|------------------------------------------------------|
| Deployment rollback procedure                 | `docs/runbooks/deployment-rollback.md`               |
| Trivy CVE-triage procedure                    | `docs/runbooks/trivy-cve-handling.md`                |
| Informatiebeveiligingsbeleid                  | `docs/compliance/soc2/information-security-policy.md`|
| Risicoregister                                | `docs/compliance/soc2/risk-register.md`              |
| Incidentlog (aanmaken na eerste incident)     | `docs/compliance/soc2/incident-log.md`               |

---

## 8. Revisiehistorie

| Versie | Datum      | Auteur             | Wijziging                      |
|--------|------------|--------------------|-------------------------------|
| 1.0    | 2026-05-26 | Rakesh Ramkhelawan | Initieel document              |
