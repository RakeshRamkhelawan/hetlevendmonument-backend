// Azure Cache for Redis — ADR-036 OP-111.
//
// Waarom deze module bestaat terwijl er nog geen cache is: op 2026-08-09 is gemeten dat er in
// het hele abonnement GEEN enkele Microsoft.Cache/Redis staat, terwijl cd-staging.yml en
// cd-production.yml er allebei van uitgaan. De worker start zonder REDIS_URL niet eens
// (RuntimeError bij het importeren van workflow_worker), en het entrypoint is dramatiq, dus dat
// wordt een stille crash-loop in plaats van een luide deploy-fout.
//
// Rakesh heeft op 2026-08-10 gekozen voor een beheerde Azure Cache for Redis boven een
// Redis-container. Deze module maakt van die keuze een reviewbare diff in plaats van een
// handeling in de portal. Hij wordt aangeroepen achter een `deployRedis`-vlag die standaard
// UIT staat, dus hij kost niets tot iemand hem bewust aanzet.
//
// Na het aanzetten is er GEEN nieuw secret nodig: de deploy leidt de verbindingsstring zelf af
// uit `STAGING_REDIS_HOST` via `az redis list-keys` (cd-staging.yml, stap "Resolve Redis
// connection string"). Alleen dat ene secret moet gezet worden — de hostnaam, niet de sleutel.

@description('Name of the Redis cache. Becomes <name>.redis.cache.windows.net.')
param name string

@description('Azure region')
param location string = resourceGroup().location

@description('SKU family. C = Basic/Standard, P = Premium.')
@allowed(['C', 'P'])
param skuFamily string = 'C'

@description('SKU name. Basic has no SLA and no replication — acceptable for staging.')
@allowed(['Basic', 'Standard', 'Premium'])
param skuName string = 'Basic'

@description('Cache size. C0 = 250 MB, the smallest and cheapest tier.')
@minValue(0)
@maxValue(6)
param skuCapacity int = 0

@description('''Netwerktoegang. 'Disabled' is veiliger maar vraagt een private endpoint EN een
Container Apps-omgeving met VNet-integratie -- zonder die twee is de cache voor NIEMAND
bereikbaar, ook niet voor de worker. Zet dit pas op 'Disabled' als beide aantoonbaar bestaan
(ADR-036 OP-117).''')
@allowed(['Enabled', 'Disabled'])
param publicNetworkAccess string = 'Enabled'

@description('Tags')
param tags object = {}

resource redisCache 'Microsoft.Cache/redis@2023-08-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      family: skuFamily
      name: skuName
      capacity: skuCapacity
    }
    // TLS-only. De worker verbindt op 6380 met `rediss://`; poort 6379 zonder TLS mag niet open
    // staan. cd-staging.yml stelt de URL ook expliciet op 6380 samen.
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    // OPEN NAAR HET INTERNET, en dat is een bewuste, geregistreerde afweging (ADR-036 OP-117).
    //
    // Een blinde securityreview merkte terecht op dat de cache zo alleen door de access key
    // wordt beschermd, naast de Traefik-rand uit ADR-009 in plaats van erachter. `Disabled` is
    // het veilige antwoord, MAAR dat vraagt een private endpoint EN een Container
    // Apps-omgeving met VNet-integratie. Of die er is, is niet vanuit deze repo vast te
    // stellen. `Disabled` zetten zonder dat te weten levert een cache op die voor NIEMAND
    // bereikbaar is -- inclusief de worker -- en dat faalt op een manier die moeilijk te
    // herleiden is.
    //
    // Daarom een parameter met de werkende waarde als default, en het dichtzetten als een
    // eigen, gemeten stap.
    publicNetworkAccess: publicNetworkAccess
    // Pinnen: zonder dit krijg je wat Azure die maand default vindt.
    redisVersion: '6'
    redisConfiguration: {
      // Dramatiq-wachtrijen mogen niet stil worden weggegooid als het geheugen vol loopt:
      // dan verdwijnen opruimtaken zonder foutmelding. Liever een luide schrijffout.
      'maxmemory-policy': 'noeviction'
    }
  }
}

@description('Hostname — dit is de waarde voor het GitHub-secret STAGING_REDIS_HOST.')
output hostName string = redisCache.properties.hostName

@description('SSL-poort. Altijd 6380; de deploy stelt rediss://...:6380/0 samen.')
output sslPort int = redisCache.properties.sslPort

@description('Resource-id, voor eventuele diagnostische instellingen.')
output id string = redisCache.id
