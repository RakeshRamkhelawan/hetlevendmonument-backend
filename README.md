# Het Levend Monument

**Een digitaal monument waar nazaten van tot slaaf gemaakten hun verhalen, kunst en kennis delen, bewaren en doorgeven.**

[hetlevendmonument.nl](https://hetlevendmonument.nl) · een initiatief van Stichting Ketikotivlaardingen.NL

> *English summary: Het Levend Monument ("The Living Monument") is a Dutch digital heritage platform where descendants of enslaved people share and preserve stories, art and knowledge. It combines a curated public archive, an interactive map, and a classroom environment for schools.*

---

## Waarom

Het slavernijverleden van Nederland leeft door in families, in Nederland, Suriname, op Curaçao en daarbuiten. Veel van die verhalen zijn nooit opgeschreven. Ze worden verteld aan de keukentafel, bij herdenkingen en tijdens Keti Koti. Een stenen monument herinnert, maar luistert niet.

Het Levend Monument is een monument dat groeit. Iedereen die een verhaal, foto, gedicht of herinnering heeft, kan het hier veilig delen. Curatoren van de stichting kijken elke inzending na voordat die openbaar wordt. Zo ontstaat een betrouwbaar, levend archief: voor de gemeenschap zelf, voor het onderwijs en voor wie wil leren.

## Voor wie

| Wie | Wat het platform hen biedt |
|---|---|
| **Vertellers**: nazaten en gemeenschapsleden | Een verhaal, beeld of geluidsfragment delen, ook anoniem. Ze houden zelf zicht op hun inzendingen. |
| **Publiek** | Verhalen ontdekken op thema en op een kaart van Nederland, Suriname en Curaçao. |
| **Leerlingen** | Lessen en werkbladen openen met een klascode van de docent. Antwoorden invullen zonder account. |
| **Docenten** | Klassen en klascodes maken, lessen kiezen, antwoorden lezen en feedback geven, lesmateriaal als PDF downloaden. |
| **Curatoren en beheerders van de stichting** | Inzendingen beoordelen, meldingen afhandelen, docenten goedkeuren, statistieken bekijken, het archief exporteren. |
| **Erfgoedinstellingen en onderzoekers** | Openbare collectiegegevens ophalen via open standaarden (OAI-PMH, Dublin Core, EDM). |

## Wat het platform kan

**Ontdekken en delen**
- Verhalenoverzicht met categorieën (persoonlijk, herdenking, Keti Koti, kunst, educatie, archief en meer).
- Interactieve kaart (MapLibre) met de plek van elk verhaal.
- *Deel je verhaal*: tekst, beeld of media insturen, met expliciete toestemming en de keuze om anoniem te publiceren.
- *Mijn inzendingen*: vertellers zien de status van wat ze hebben ingestuurd.

**Onderwijs**
- Lespakket *Vijf verhalen over vrijheid*: twee docentenhandleidingen (openbaar) en tien werkbladen voor groep 7-8 en onderbouw VO.
- Leerlingen werken met een klascode van acht tekens. Ze vullen alleen een voornaam of bijnaam in. Hun antwoorden worden na acht weken automatisch verwijderd.
- Docentenportaal: een docentaccount aanvragen, klassen en codes beheren, lessen per klas open- of dichtzetten, antwoorden lezen en feedback geven, werkbladen als PDF.

**Curatie en beheer**
- Niets wordt openbaar zonder goedkeuring van een curator.
- Notice-and-takedown (NTD): iedereen kan een melding doen over een publicatie. Beheerders handelen die af volgens een vaste procedure.
- Beheeromgeving met tabbladen voor curatie, statistieken, archief, instellingen, meldingen en docenten.
- Archiefexport in BagIt-formaat voor duurzame opslag.

**Open data**
- OAI-PMH-endpoint (`oai_dc` en EDM) voor erfgoedaggregators, plus `sitemap.xml` en een kaart-API.

**Contact en betrokkenheid**
- Contactformulier en nieuwsbrief met dubbele bevestiging (double opt-in).
- Aanmelden zonder wachtwoord via een eenmalige inloglink per e-mail.

## Privacy, veiligheid en toegankelijkheid

- **AVG**: dataminimalisatie, anoniem publiceren, vaste bewaartermijnen en een privacyverklaring op [/privacy](https://hetlevendmonument.nl/privacy).
- **Hosting in de EU**: Microsoft Azure, regio Noord-Europa. E-mail via Brevo (EU).
- **Scheiding van gegevens**: elke organisatie op het platform heeft een eigen *tenant*. PostgreSQL row-level security dwingt die scheiding af in de database zelf. De applicatie draait met een databaserol zonder beheerrechten.
- **Bescherming tegen misbruik**: hCaptcha op openbare formulieren, rate limiting en beveiligingsheaders (CSP en HSTS).
- **Geheimen** staan in Azure Key Vault, nooit in de code.
- **Toegankelijkheid**: gebouwd met WCAG 2.1 AA als doel. De componenten worden automatisch getest met axe. Zie de [toegankelijkheidsverklaring](https://hetlevendmonument.nl/toegankelijkheid).

## Stand van zaken

Het platform draait sinds november 2026 als **pilot** op [hetlevendmonument.nl](https://hetlevendmonument.nl), met vijf fictieve voorbeeldverhalen (zo gelabeld) en het eerste lespakket.

| Onderdeel | Stand |
|---|---|
| Verhalen, kaart, inzenden, curatie, NTD | Live |
| Educatie: klascodes, werkbladen, docentenportaal | Live |
| Contactformulier, nieuwsbrief, e-mail | Live |
| Open data (OAI-PMH, sitemap) | Live |
| Online doneren (Stripe) | Gebouwd, nog niet geactiveerd |

## Architectuur

```
  Bezoeker ──HTTPS──▶  portal  (React + Vite, nginx)            Azure Container Apps
                          │  /api                               regio Noord-Europa
                          ▼
                        api  (FastAPI, Python 3.11) ──▶ PostgreSQL (row-level security)
                          │                         ──▶ Blob Storage (media)
                          ▼
                        worker (Dramatiq) ◀──▶ Redis
                          │
                          └──▶ Brevo (e-mail) · hCaptcha · Key Vault (geheimen)
```

| Laag | Techniek |
|---|---|
| Portaal | React 18, TypeScript, Vite, Tailwind CSS, MapLibre GL, geserveerd door nginx |
| API | FastAPI, SQLAlchemy (async), Alembic-migraties |
| Achtergrondtaken | Dramatiq met Redis; dagelijkse opschoonjob voor leerlingantwoorden |
| Data | Azure Database for PostgreSQL (Flexible Server), Azure Blob Storage |
| Infrastructuur | Azure Container Apps, Key Vault, Log Analytics, beheerde identiteit; volledig in Bicep |

**Over de backend.** De API draait op het multi-tenant platform van SanskritiSetu. Het Levend Monument is daarop de tenant `hetlevendmonument`. Daarom bevat `src/` ook platformmodules die het portaal niet gebruikt. Die worden in een volgende fase uit deze repository gehaald.

## Repository

| Map | Inhoud |
|---|---|
| `portal/` | Het publieke portaal (frontend), met Dockerfile en nginx-configuratie. Open source (MIT) |
| `src/` | De backend: API, modellen, services, workers en migraties (`src/alembic`) |
| `src/core/api/v1/foundation/` | De API-routes van het portaal: content, kaart, upload, educatie, docenten, beheer, open data |
| `tests/` | Unit-, integratie- en architectuurtests van de backend |
| `infra/` | Bicep-definitie van de productieomgeving (`main-levendmonument-prod.bicep`) |
| `scripts/azure/` | Uitrol- en domeinscripts voor Azure |
| `scripts/seed/` | Voorbeeldverhalen, lesmateriaal en het publicatiescript |
| `docs/` | Architectuurbesluiten (`docs/adr`), featuredocumentatie, draaiboeken (`docs/infra`, `docs/runbooks/foundation-portal`) |
| `config/` | Applicatieconfiguratie |

## Lokaal ontwikkelen

**Vereisten:** Python 3.11, Node.js 20, Docker.

```bash
# Backend en databases (Docker)
make up                      # start de ontwikkelstack, API op http://localhost:8000

# Portaal
cd portal
npm ci
npm run dev                  # http://localhost:5174, /api gaat naar localhost:8000
```

Kopieer `.env.example` naar `.env` en vul de waarden in. Zet `FOUNDATION_PORTAL_BASE_URL=http://localhost:5174` zodat links in e-mails naar je lokale portaal wijzen.

## Testen

```bash
# Backend (vanuit een Python 3.11-omgeving)
pytest tests/unit -q
pytest tests/architecture -q

# Portaal
cd portal && npm test
```

Bij elke commit draaien pre-commit hooks: formattering, linting, een controle op geheimen, typecontroles en de tests die bij de gewijzigde code horen. Installeer ze met `bash scripts/install-hooks.sh`.

## Uitrollen

De productieomgeving staat volledig in `infra/main-levendmonument-prod.bicep`. Een uitrol gaat in fasen:

```powershell
scripts\azure\levendmonument_uitrol.ps1 -Fase geheimen
scripts\azure\levendmonument_uitrol.ps1 -Fase db   -ImageTag levendmonument-<sha>
scripts\azure\levendmonument_uitrol.ps1 -Fase apps -ImageTag levendmonument-<sha>
```

Bouw en push eerst de images (`lm-api`, `lm-worker`, `lm-portal`). De volledige procedure, inclusief DNS, e-mail en herstel, staat in [docs/infra/LEVEND-MONUMENT-PRODUCTIE-DRAAIBOEK.md](docs/infra/LEVEND-MONUMENT-PRODUCTIE-DRAAIBOEK.md).

## Documentatie

- [ADR-029: architectuur van het portaal](docs/adr/029-foundation-portal-architecture.md)
- [Draaiboek productie](docs/infra/LEVEND-MONUMENT-PRODUCTIE-DRAAIBOEK.md)
- [Runbooks portaal](docs/runbooks/foundation-portal/README.md): incidenten, takedown, back-up en herstel, releasechecklist
- [Docentenomgeving (BE-EP-055)](docs/backend/features/BE-EP-055-docentenomgeving.md)

## Contact

Stichting Ketikotivlaardingen.NL · KvK 95265104
[info@hetlevendmonument.nl](mailto:info@hetlevendmonument.nl)

Een beveiligingsprobleem gevonden? Zie [SECURITY.md](SECURITY.md).

## Licentie

- **Backend en overige software:** [Business Source License 1.1](LICENSE), © 2026 SanskritiSetu.org. Stichtingen, verenigingen en andere organisaties zonder winstoogmerk mogen de software gebruiken voor hun eigen activiteiten; ook niet-commercieel onderzoek en onderwijs zijn toegestaan. De software als dienst of commercieel product aanbieden aan anderen mag alleen met een aparte licentie. Op 4 november 2030 gaat deze versie over naar de Apache License 2.0.
- **Portaal (`portal/`):** [MIT-licentie](portal/LICENSE); ook als aparte repository: [hetlevendmonument-portaal](https://github.com/RakeshRamkhelawan/hetlevendmonument-portaal).
- **Inhoud en merk:** naam, beeldmerk, teksten, lesmateriaal en afbeeldingen zijn van Stichting Ketikotivlaardingen.NL of de makers. Zie [NOTICE](NOTICE).
