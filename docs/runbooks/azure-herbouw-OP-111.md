# Runbook: Azure opnieuw opbouwen (OP-111)

> **Productie-omgeving: NIET INGERICHT.** De resourcegroep `sanskritisetu-prod` is op
> 2026-05-11 verwijderd en nooit herbouwd. Commando's in dit document die naar die groep
> wijzen, beschrijven de gewenste toestand en werken vandaag niet. De enige bron voor wat
> wel bestaat is `docs/infra/AZURE_OMGEVINGEN.md` (ADR-036 OP-116).

> Voor Rakesh. Geschreven om te kopieren en plakken, niet om te interpreteren.
> Je hoeft geen engineer te zijn om dit te doen, maar lees stap 0 wel echt.

---

## Waarom dit nodig is

Op 2026-05-11 zijn beide Azure-resourcegroepen EN de container registry verwijderd
(`docs/AZURE_TEARDOWN_2026_05_11.md`). De herbouw is nooit afgemaakt. Gemeten op 2026-08-09:

| Wat | Stand |
| --- | --- |
| Resourcegroep `sanskritisetu-prod` | Bestaat niet |
| Redis-cache | Bestaat nergens in het abonnement |
| `worker-staging` | Draait, maar met NUL omgevingsvariabelen |
| `staging-api` | Vier variabelen, geen `DATABASE_URL` |

De repo staat klaar. **Na deze stappen hoeft er niets meer in de code.**

---

## Stap 0 -- lees dit eerst

- **Alles hieronder kost geld.** De Redis-cache is ongeveer 15 euro per maand, de
  scheduler-app ongeveer 12. Dat zijn terugkerende kosten.
- **Doe staging eerst, productie pas als staging werkt.** Staging is goedkoper en kapotmaken
  is daar niet erg.
- **Als een commando faalt: stop en plak de foutmelding.** Doorgaan met een half aangemaakte
  omgeving is lastiger te repareren dan opnieuw beginnen.
- Je hebt de Azure CLI nodig. Controleer met `az --version`. Inloggen: `az login`.

Controleer eerst waar je bent:

```bash
az account show --query "{abonnement:name, id:id}" -o table
```

Klopt dat abonnement niet, dan: `az account set --subscription "<naam>"`.

---

## Stap 1 -- staging: de Redis-cache

Dit is het enige wat staging blokkeert. De worker start zonder Redis niet eens.

```bash
az redis create \
  --name sanskritisetu-cache-stg \
  --resource-group sanskritisetu-staging \
  --location northeurope \
  --sku Basic \
  --vm-size c0 \
  --minimum-tls-version 1.2
```

**Dit duurt 15 tot 20 minuten.** Dat is normaal; Azure doet daar lang over.

Als het klaar is, haal de hostnaam op:

```bash
az redis show \
  --name sanskritisetu-cache-stg \
  --resource-group sanskritisetu-staging \
  --query hostName -o tsv
```

Je krijgt iets als `sanskritisetu-cache-stg.redis.cache.windows.net`. **Bewaar die regel.**

---

## Stap 2 -- staging: het secret zetten

Ga naar GitHub -> je repo -> Settings -> Secrets and variables -> Actions -> New repository secret.

| Naam | Waarde |
| --- | --- |
| `STAGING_REDIS_HOST` | de hostnaam uit stap 1 |

**Alleen de hostnaam. Geen wachtwoord, geen sleutel.** De deploy haalt de sleutel zelf op. Dat
is bewust zo gebouwd: een sleutel in een secret veroudert zodra iemand hem roteert.

Of met de CLI:

```bash
gh secret set STAGING_REDIS_HOST --body "sanskritisetu-cache-stg.redis.cache.windows.net"
```

---

## Stap 3 -- staging: controleren of de service principal de sleutel mag ophalen

De deploy heeft het recht `Microsoft.Cache/redis/listKeys/action` nodig. Testen:

```bash
az redis list-keys \
  --name sanskritisetu-cache-stg \
  --resource-group sanskritisetu-staging \
  --query primaryKey -o tsv
```

- **Krijg je een lange sleutel terug:** goed, klaar met stap 3.
- **Krijg je een foutmelding over rechten:** dan mist de service principal dat recht. De deploy
  meldt dat dan zelf ook expliciet. Twee opties: het recht toekennen, of het secret
  `STAGING_REDIS_URL` met de volledige verbindingsstring zetten. Vraag me om de eerste optie;
  dat is de nette.

---

## Stap 4 -- staging deployen en kijken of het werkt

**Eerst de trigger terugzetten.** `cd-staging.yml` staat sinds 2026-08-12 op `workflow_dispatch`
(handmatig), omdat hij bij elke push naar develop omviel op de ontbrekende Redis en daarmee
permanent rood stond. Haal in dat bestand de regel `workflow_dispatch:` weg en zet het
`push`-blok eronder weer aan:

```yaml
on:
  push:
    branches: [develop]
    paths-ignore:
      - 'docs/**'
      - '**/*.md'
      - '.github/workflows/archive/**'
```

Daarna push je naar `develop` (of draai je de workflow een keer met de hand). Kijk vervolgens:

```bash
az containerapp revision list \
  --name worker-staging \
  --resource-group sanskritisetu-staging \
  --query "[0].{revisie:name, draait:properties.runningState}" -o table
```

Je wilt `Running` zien. Staat er `Failed`, plak dan dit:

```bash
az containerapp logs show \
  --name worker-staging \
  --resource-group sanskritisetu-staging \
  --tail 50
```

---

## Stap 5 -- productie: de resourcegroep

**Pas doen als staging draait.**

```bash
az group create --name sanskritisetu-prod --location westeurope
```

Zet daarna het secret:

```bash
gh secret set PROD_RESOURCE_GROUP --body "sanskritisetu-prod"
```

Dit secret is nieuw. Tot vandaag stond de naam hardgecodeerd in de workflow; nu komt hij hier
vandaan. **Zonder dit secret stopt de deploy meteen** met een duidelijke melding -- dat is
expres, zodat je het niet pas achttien stappen verderop merkt.

---

## Stap 6 -- productie: de rest

Productie heeft meer nodig dan alleen een resourcegroep: een Container Apps-omgeving, een
Key Vault, de container registry, en de apps zelf. `cd-production.yml` heeft voor backend,
frontend en worker **alleen een update-tak** -- het kan die apps niet zelf aanmaken.

**Dit is geen kopieer-en-plak-stap.** Vraag me om het als aparte klus op te pakken; dan meet ik
eerst wat er precies moet en schrijf ik het net zo uit als hierboven.

---

## Als je Redis wilt via de bicep-template

Er staat een template klaar die hetzelfde doet als stap 1, maar dan als reviewbare wijziging:

```bash
az deployment group create \
  --resource-group sanskritisetu-staging \
  --template-file infra/main-staging.bicep \
  --parameters deployRedis=true
```

De vlag `deployRedis` staat standaard op `false`, dus zonder die parameter gebeurt er niets.
De template zet TLS-only en poort 6380 goed. Twee dingen die er bewust NIET in staan, met de
reden erbij in het bestand: de cache staat open naar het internet (dichtzetten vraagt een
private endpoint plus VNet-integratie, en of die er zijn is niet vanuit de repo te zien), en er
zijn geen firewallregels. Dat staat als OP-117 geregistreerd.

---

## Wat je NIET moet doen

- **Niet de twee pseudonimiseringssecrets opnieuw zetten.** `STAGING_TOOL_PAYLOAD_PSEUDONYM_KEY`
  en `PROD_TOOL_PAYLOAD_PSEUDONYM_KEY` bestaan al. Ze opnieuw zetten maakt al het eerdere
  auditbewijs onbruikbaar en er is geen weg terug. Zie `.claude/WORKING-CONTEXT.md`.
- **Niet de resourcegroep een andere naam geven zonder het secret bij te werken.** De deploy
  controleert alleen dat het secret niet leeg is, niet dat het naar de juiste omgeving wijst.
  Een verkeerde groep levert een groene deploy op die niets aan productie doet -- dat is
  geregistreerd, maar nog niet afgevangen.

---

*Hoort bij ADR-036 OP-111. Laatst gemeten: 2026-08-09.*

## De auditsleutel aanzetten (optioneel, ADR-036 OP-120)

De auditketen kan gesleuteld worden. Dat beschermt tegen iemand die de database kan schrijven
maar niet bij de applicatie kan -- een gestolen verbindingsstring, een backup, een databasedump.
Het beschermt NIET tegen iemand die code in de applicatie kan draaien; die heeft de sleutel ook.

**Zonder deze stap werkt alles gewoon.** De keten draait dan op SHA-256, precies zoals nu. Er
gaat niets stuk als je dit overslaat of uitstelt.

### Wat je doet

Twee GitHub-secrets aanmaken, elk minstens 32 tekens, en verschillend per omgeving:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # genereer er een
gh secret set STAGING_AUDIT_CHAIN_HMAC_KEY --repo <repo>
gh secret set PROD_AUDIT_CHAIN_HMAC_KEY --repo <repo>
```

De eerstvolgende deploy pikt ze op. Vanaf dan krijgen NIEUWE auditregels een gesleutelde hash;
bestaande regels blijven op SHA-256 en blijven gewoon verifieren -- er wordt niets omgehasht,
want dat zou juist de bewijswaarde vernietigen.

### Anders dan de pseudonimiseringssleutel

`TOOL_PAYLOAD_PSEUDONYM_KEY` mag NOOIT wijzigen. Deze wel: de auditketen legt per tenant een
knippunt vast (`audit_chain_anchors.chain_epoch_id`), dus een rotatie is mogelijk zolang er een
nieuw knippunt bij komt. Doe dat niet lichtvaardig -- het is een besluit, geen onderhoudstaak --
maar het is geen doodlopende weg zoals bij die andere sleutel.

### Wat je NIET moet doen

**Niet handmatig een `secretref` in Azure zetten zonder het bijbehorende secret.** Dan resolveert
de omgevingsvariabele naar de letterlijke tekst `secretref:audit-chain-hmac-key`. Die is lang
genoeg om als sleutel geaccepteerd te worden, en dan is je "sleutel" een publiek bekende
constante. De workflows doen dit goed en er staat een test op
(`tests/architecture/test_audit_chain_key_is_wired_per_app.py`), maar met de hand kan het mis.

---

# Addendum 2026-08-28 -- wat dit runbook niet vertelde

Bij het daadwerkelijk uitvoeren bleek de lijst hierboven onvolledig. Onderstaande punten zijn
gemeten op de echte omgeving, niet afgeleid uit de repo. Vier ervan waren onzichtbaar zolang
de omgeving niet startte.

## 1. Er ontbrak een DATABASE, niet alleen een cache

Dit runbook noemde PostgreSQL geen enkele keer, terwijl `docs/AZURE_TEARDOWN_2026_05_11.md`
vastlegt dat de Postgres-servers van beide groepen op 2026-05-11 zijn verwijderd. Het secret
`STAGING_DATABASE_URL` wees naar `sanskritisetu-db.postgres.database.azure.com`; die naam
bestaat niet meer (NXDOMAIN). Je kon dit runbook dus van begin tot eind afwerken en daarna nog
steeds een omgeving hebben die op `[WAIT] PostgreSQL...` bleef hangen.

Aangemaakt op 2026-08-28: `sanskritisetu-db-stg`, PostgreSQL 16, Burstable Standard_B1ms,
32 GB, backup 7 dagen, `--public-access 0.0.0.0` (= alleen Azure-diensten; een IP-allowlist is
onhoudbaar omdat de Container Apps-omgeving geen VNet heeft en 160+ wisselende uitgaande
adressen gebruikt).

**`azure.extensions` moet op `VECTOR,UUID-OSSP` staan.** Migratie
`20260330_futureproof_baseline.py:35-36` maakt beide extensies aan; alleen `VECTOR`
allowlisten laat de allereerste migratie omvallen op een foutmelding die niets met vectoren
te maken heeft.

## 2. De verbindingsstring: geen ssl-parameter

Zet er GEEN `?sslmode=require` achter. Dat faalt op de meest misleidende manier die er is:
**de migraties worden groen en de applicatie gaat daarna dood.** Alembic draait op psycopg2
(dat `sslmode` kent), de applicatie op asyncpg (dat het niet kent -- SQLAlchemy geeft
queryparameters door als keyword-argument aan `asyncpg.connect()`). `?ssl=require` is precies
andersom fout. Zonder parameter valt asyncpg terug op `PGSSLMODE` en anders op `prefer`, en de
server staat op `require_secure_transport=on`, dus TLS is hoe dan ook verplicht. De CD-workflow
zet daarnaast `PGSSLMODE=require` als losse variabele; die lezen beide drivers.

## 3. Redis is een Container App geworden, geen Azure Cache

Microsoft blokkeert nieuwe Azure Cache for Redis-instanties vanaf **01-10-2026** en zet de
dienst **30-09-2028** uit. Een cache die je vandaag aanmaakt is een gegarandeerde migratie
binnen twee jaar, voor ongeveer EUR 15/maand plat en zonder SLA op Basic C0.

Staging draait daarom op `redis-staging`: een container app met INTERNE TCP-ingress op 6379,
bereikbaar als `redis://redis-staging:6379/0`. Geen publiek endpoint, geen retirement-klok,
en grotendeels idle-tarief. Daarmee vervalt OP-117 in plaats van dat het besluit wordt
uitgesteld. Kosten van die keuze, eerlijk: geen persistentie, geen SLA, geen beheerde backup --
aanvaardbaar omdat het teardown-document Redis-data expliciet als vluchtig aanmerkt.
Stap 1 en 2 hierboven (`az redis create` + `STAGING_REDIS_HOST`) zijn daarmee vervallen.

## 4. Vier dingen die pas zichtbaar werden toen de omgeving eenmaal startte

| Wat | Waarom het niemand opviel |
| --- | --- |
| `staging-api` draaide de image **`nginx`** | De revisie stond sinds 5 juni op `Healthy`, dus alles leek in orde. Het was een placeholder; de applicatie heeft in deze omgeving nooit gedraaid. |
| Ingress `targetPort` stond op **80**, de app luistert op **8000** | De workflow zet alleen image en env-vars, nooit de poort. Ook een geslaagde deploy had dit niet gerepareerd. |
| Gunicorn forkte **9 workers** in 0,5 GiB | `scripts/gunicorn_config.py:26` rekent met `multiprocessing.cpu_count()`, en dat is de CPU van de HOST, niet de limiet van de container. Opgelost met `GUNICORN_WORKERS=2` en 0,5 vCPU / 1 GiB. |
| `DEFAULT_ADMIN_PASSWORD` werd nergens gezet | `seed.py:80` weigert te seeden zonder die variabele en `app_lifespan.py:241` maakt daar een RuntimeError van. Geen enkel deploy-pad zette hem, en `config_validator.py` kent hem niet, dus de boot-check die hier juist voor bestaat liet hem door. |

## 5. Key Vault-verwijzingen worden gecachet

Een bijgewerkte waarde in de Key Vault komt NIET meteen in een draaiende container app of job
terecht. De eerste migratieloop na het zetten van de nieuwe `database-url` gebruikte nog de
oude hostnaam en faalde daarop. Forceer een verversing door de resource aan te raken, of wacht
het verversingsinterval af.

## 6. Controleer migraties ECHT

In `cd-staging.yml` staat de stap `Run migrations` op `continue-on-error: true` en eindigt elk
faalpad met `exit 0`. Een mislukte migratie maakt de deploy dus niet rood. Los van de pipeline
controleren:

```bash
az containerapp job start -n migration-job -g sanskritisetu-staging
az containerapp job execution list -n migration-job -g sanskritisetu-staging \
  --query "[0].{naam:name, status:properties.status}" -o table
```

Op 2026-08-28 liepen zo 95 migraties door zonder fouten tegen de nieuwe database.

