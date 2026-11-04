// Redis als Container App -- ADR-006 (Dramatiq met Redis-broker), ADR-036 OP-111/OP-117.
//
// WAAROM GEEN Microsoft.Cache/redis (zie infra/modules/redis.bicep):
// Microsoft heeft aangekondigd dat Azure Cache for Redis Basic/Standard/Premium op
// 30-09-2028 wordt uitgezet EN dat nieuwe instanties vanaf 01-10-2026 niet meer
// aangemaakt kunnen worden. Een cache die we vandaag aanmaken is dus een gegarandeerde
// migratie binnen twee jaar, voor ongeveer EUR 15/maand plat, zonder SLA en zonder
// replicatie op Basic C0.
//
// Deze variant draait in de bestaande Container Apps-omgeving en kost bij een stille
// staging grotendeels het idle-tarief. Belangrijker: de ingress is INTERN, dus er is
// geen publiek endpoint. Daarmee vervalt OP-117 (de cache stond open naar het internet)
// in plaats van dat het besluit wordt uitgesteld.
//
// WAT DIT NIET IS: er is geen persistentie, geen SLA en geen beheerde backup. Dat is een
// bewuste keuze voor STAGING en volgt docs/AZURE_TEARDOWN_2026_05_11.md, dat Redis-data
// expliciet als vluchtig aanmerkt ("transient, OK to discard"). Voor productie is dit
// besluit NIET automatisch overdraagbaar.

@description('Naam van de container app.')
param name string

@description('Azure-regio.')
param location string = resourceGroup().location

@description('Resource-id van de bestaande Container Apps-omgeving.')
param containerAppEnvironmentId string

@description('Redis-image. Via ACR en niet rechtstreeks van Docker Hub: anonieme pulls daar zijn per IP begrensd en Container Apps deelt uitgaande adressen.')
param containerImage string = 'sanskritisetuacr.azurecr.io/redis:7.4-alpine'

@description('Login-server van de registry.')
param registryServer string = 'sanskritisetuacr.azurecr.io'

@description('Gebruikersnaam van de registry (ACR admin-user).')
param registryUsername string = 'sanskritisetuacr'

@description('Wachtwoord van de registry. Nooit een default: dit hoort uit een pipeline-secret of Key Vault te komen.')
@secure()
param registryPassword string

@description('Tags voor alle resources.')
param tags object = {}

resource redis 'Microsoft.App/containerApps@2023-05-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    managedEnvironmentId: containerAppEnvironmentId
    configuration: {
      // INTERN: alleen bereikbaar binnen de omgeving, als `<naam>:6379`. Externe TCP-ingress
      // zou een VNet vereisen en zou precies het publieke endpoint terugbrengen dat we hier
      // juist vermijden.
      ingress: {
        external: false
        transport: 'Tcp'
        targetPort: 6379
        exposedPort: 6379
      }
      registries: [
        {
          server: registryServer
          username: registryUsername
          passwordSecretRef: 'registry-password'
        }
      ]
      secrets: [
        {
          name: 'registry-password'
          value: registryPassword
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'redis'
          image: containerImage
          // --save "" zet RDB-snapshots uit: er is geen persistent volume, dus schrijven naar
          // schijf levert alleen I/O op en geen duurzaamheid.
          // noeviction spiegelt redis.bicep: een wachtrij mag geen taken weggooien onder druk;
          // volraken hoort een luide fout te zijn, geen stil verlies van opdrachten.
          command: [
            'redis-server'
          ]
          args: [
            '--save'
            ''
            '--appendonly'
            'no'
            '--maxmemory'
            '350mb'
            '--maxmemory-policy'
            'noeviction'
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      // Exact een replica. Meer dan een zou losse, niet-gedeelde caches opleveren: elke replica
      // heeft zijn eigen geheugen, dus een broker die over twee replicas verdeeld wordt raakt
      // opdrachten kwijt.
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

@description('Adres binnen de omgeving. Vorm voor REDIS_URL: redis://<naam>:6379/0')
output redisHost string = name

@description('Resource-id van de container app.')
output redisId string = redis.id
