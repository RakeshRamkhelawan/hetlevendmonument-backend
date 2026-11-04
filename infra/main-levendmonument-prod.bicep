// Het Levend Monument -- productie in Azure Container Apps (northeurope).
//
// Draaiboek: docs/infra/LEVEND-MONUMENT-PRODUCTIE-DRAAIBOEK.md, stap 3 tot en met 6.
// Al handmatig ingericht en hier alleen GELEZEN (existing): Key Vault levendmonument-kv-prd
// en PostgreSQL Flexible Server levendmonument-db-prd.
//
// Ontwerp:
// - Een user-assigned identity leest de geheimen uit de Key Vault (rol Key Vault Secrets
//   User). User-assigned en niet system-assigned: de rol moet bestaan VOORDAT een app met
//   Key-Vault-verwijzingen wordt aangemaakt, anders faalt het aanmaken.
// - api: INTERNE ingress. De browser praat alleen met de portal; nginx in de portal stuurt
//   /api/ door naar https://<api>.internal.<omgevingsdomein> (portal/nginx.conf).
// - portal: externe ingress; het eigen domein wordt na de DNS-stap gekoppeld (param
//   portalCustomDomains), zodat een herhaalde uitrol die koppeling niet weghaalt.
// - worker: geen ingress.
// - migratiejob (eigenaar van de database) en een rollenjob die de applicatierol en de
//   bypassrol een wachtwoord geeft (docs/runbooks/applicatie-databaserol.md stap 5).
// - Images uit de gedeelde ACR via dezelfde identiteit (rol AcrPull), zonder admin-wachtwoord.
//   Het ophalen van dat wachtwoord (listCredentials) werd vanaf de beheer-pc steeds
//   afgebroken (gemeten 2026-11-02); een identiteit is bovendien de veiligere vorm.

targetScope = 'resourceGroup'

@description('Azure-regio. West Europe weigert nieuwe klanten voor deze subscription (gemeten 2026-11-01).')
param location string = 'northeurope'

@description('Image-tag voor api, worker en portal, vorm levendmonument-<git-sha>.')
param imageTag string

@description('Resourcegroep van de gedeelde ACR sanskritisetuacr (voor de AcrPull-rol).')
param acrResourceGroup string = 'sanskritisetu-staging'

@description('Publieke URL van de site.')
param frontendUrl string = 'https://hetlevendmonument.nl'

@description('Afzender van e-mail (moet in Brevo geverifieerd zijn).')
param emailFrom string = 'info@hetlevendmonument.nl'

@description('SMTP-login van Brevo (geen geheim; het wachtwoord staat in de Key Vault).')
param smtpUser string = ''

@description('Koppel hetlevendmonument.nl en www aan de portal met de managed certificates. Pas op true zetten NA scripts/azure/levendmonument_domein.ps1 (die maakt de certificaten aan); anders verwijst de koppeling naar certificaten die nog niet bestaan.')
param domeinenGekoppeld bool = true

@description('Fase 1 (false): basis, jobs en Redis. Fase 2 (true): ook api, worker en portal. De apps pas na migratie en rollenjob, anders starten ze tegen een lege database of een rol zonder inlogrecht.')
param deployApps bool = false

@description('Tags voor alle resources.')
param tags object = {
  project: 'levend-monument'
  omgeving: 'productie'
}

var acrServer = 'sanskritisetuacr.azurecr.io'
var kvName = 'levendmonument-kv-prd'
var kvUrl = 'https://${kvName}${environment().suffixes.keyvaultDns}/secrets'
var apiName = 'levendmonument-api'
var portalName = 'levendmonument-portal'
var workerName = 'levendmonument-worker'
var redisName = 'levendmonument-redis'
var redisUrl = 'redis://${redisName}:6379/0'

// Ingebouwde rol "Key Vault Secrets User".
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: kvName
}

resource identiteit 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'levendmonument-id'
  location: location
  tags: tags
}

resource kvLezen 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, identiteit.id, kvSecretsUserRoleId)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleId)
    principalId: identiteit.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

module acrPull 'modules/acr-pull.bicep' = {
  name: 'lm-acr-pull'
  scope: resourceGroup(acrResourceGroup)
  params: {
    acrName: 'sanskritisetuacr'
    principalId: identiteit.properties.principalId
  }
}

module logboek 'modules/log-analytics.bicep' = {
  name: 'lm-log-analytics'
  params: {
    name: 'levendmonument-logs'
    location: location
    retentionInDays: 30
    tags: tags
  }
}

resource werkruimte 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: 'levendmonument-logs'
}

module opslag 'modules/storage-account.bicep' = {
  name: 'lm-storage'
  params: {
    name: 'levendmonumentstprd'
    location: location
    containerName: 'foundation-uploads'
    tags: tags
  }
}

resource opslagAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: 'levendmonumentstprd'
}

// De connection string gaat server-side de Key Vault in: listKeys draait hier in Azure, dus
// de sleutel komt nooit langs de beheer-pc of in een deploymentparameter.
resource opslagGeheim 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'storage-connection-string'
  dependsOn: [
    opslag
  ]
  properties: {
    value: 'DefaultEndpointsProtocol=https;AccountName=${opslagAccount.name};AccountKey=${opslagAccount.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
  }
}

resource omgeving 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'levendmonument-env'
  location: location
  tags: tags
  dependsOn: [
    logboek
  ]
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logboek.outputs.workspaceCustomerId
        sharedKey: werkruimte.listKeys().primarySharedKey
      }
    }
  }
}

// Redis zoals infra/modules/redis-container.bicep (interne TCP-ingress, geen persistentie,
// een replica, noeviction), maar met de identiteit in plaats van het ACR-admin-wachtwoord.
resource redis 'Microsoft.App/containerApps@2024-03-01' = {
  name: redisName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identiteit.id}': {}
    }
  }
  dependsOn: [
    acrPull
  ]
  properties: {
    managedEnvironmentId: omgeving.id
    configuration: {
      ingress: {
        external: false
        transport: 'Tcp'
        targetPort: 6379
        exposedPort: 6379
      }
      registries: registry
    }
    template: {
      containers: [
        {
          name: 'redis'
          image: '${acrServer}/redis:7.4-alpine'
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
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Geheimen: elke naam is een Key-Vault-geheim met dezelfde naam.
// ---------------------------------------------------------------------------
var kvGeheimenApp = [
  'app-database-url'
  'bypass-database-url'
  'secret-key'
  'jwt-secret-key'
  'tool-payload-pseudonym-key'
  'master-encryption-key'
  'audit-chain-hmac-key'
  'mistral-api-key'
  'hcaptcha-secret-key'
  'brevo-api-key'
  'smtp-password'
  'default-admin-password'
  'storage-connection-string'
]

var geheimenKv = [for g in kvGeheimenApp: {
  name: g
  keyVaultUrl: '${kvUrl}/${g}'
  identity: identiteit.id
}]

var geheimenApp = geheimenKv

var registry = [
  {
    server: acrServer
    identity: identiteit.id
  }
]

var envGedeeld = [
  { name: 'ENVIRONMENT', value: 'production' }
  { name: 'LOG_LEVEL', value: 'INFO' }
  { name: 'PYTHONUNBUFFERED', value: '1' }
  { name: 'PGSSLMODE', value: 'require' }
  { name: 'DATABASE_URL', secretRef: 'app-database-url' }
  { name: 'BYPASS_DATABASE_URL', secretRef: 'bypass-database-url' }
  { name: 'REDIS_URL', value: redisUrl }
  { name: 'DRAMATIQ_BROKER_URL', value: redisUrl }
  { name: 'SECRET_KEY', secretRef: 'secret-key' }
  { name: 'JWT_SECRET_KEY', secretRef: 'jwt-secret-key' }
  { name: 'TOOL_PAYLOAD_PSEUDONYM_KEY', secretRef: 'tool-payload-pseudonym-key' }
  { name: 'MASTER_ENCRYPTION_KEY', secretRef: 'master-encryption-key' }
  { name: 'AUDIT_CHAIN_HMAC_KEY', secretRef: 'audit-chain-hmac-key' }
  { name: 'LLM_PROVIDER', value: 'mistral' }
  { name: 'LLM_MODEL', value: 'mistral-small-latest' }
  { name: 'MISTRAL_API_KEY', secretRef: 'mistral-api-key' }
  { name: 'FRONTEND_URL', value: frontendUrl }
  { name: 'API_BASE_URL', value: frontendUrl }
  { name: 'CORS_ORIGINS', value: frontendUrl }
  // Basis voor links in docentmails (inloglink, beheer, docentenportaal); standaard is localhost.
  { name: 'FOUNDATION_PORTAL_BASE_URL', value: frontendUrl }
  { name: 'HCAPTCHA_SECRET_KEY', secretRef: 'hcaptcha-secret-key' }
  { name: 'BREVO_API_KEY', secretRef: 'brevo-api-key' }
  { name: 'BREVO_SENDER_EMAIL', value: emailFrom }
  { name: 'BREVO_SENDER_NAME', value: 'Het Levend Monument' }
  { name: 'SMTP_HOST', value: 'smtp-relay.brevo.com' }
  { name: 'SMTP_PORT', value: '587' }
  { name: 'SMTP_USER', value: smtpUser }
  { name: 'SMTP_PASSWORD', secretRef: 'smtp-password' }
  { name: 'EMAIL_FROM', value: emailFrom }
  { name: 'DEFAULT_ADMIN_PASSWORD', secretRef: 'default-admin-password' }
  { name: 'STORAGE_BACKEND', value: 'azure' }
  { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'storage-connection-string' }
  { name: 'FOUNDATION_BLOB_CONTAINER', value: 'foundation-uploads' }
]

resource api 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: apiName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identiteit.id}': {}
    }
  }
  dependsOn: [
    kvLezen
    acrPull
  ]
  properties: {
    managedEnvironmentId: omgeving.id
    configuration: {
      activeRevisionsMode: 'Single'
      // Intern: alleen de portal (nginx) praat met de api.
      ingress: {
        external: false
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: registry
      secrets: geheimenApp
    }
    template: {
      containers: [
        {
          name: 'api'
          image: '${acrServer}/lm-api:${imageTag}'
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: concat(envGedeeld, [
            // De container-ingress staat voor gunicorn; zonder VNet is het adres van die
            // proxy niet vast. De api is alleen intern bereikbaar, dus elke directe
            // verbinding is de ingress (scripts/gunicorn_config.py).
            { name: 'FORWARDED_ALLOW_IPS', value: '*' }
            // Anders telt gunicorn de cpu's van de HOST (cpu_count * 2 + 1).
            { name: 'GUNICORN_WORKERS', value: '2' }
          ])
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 30
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health/ready'
                port: 8000
              }
              initialDelaySeconds: 20
              periodSeconds: 15
            }
          ]
        }
      ]
      // Een replica die blijft draaien: geen koude start tijdens de demo.
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
}

resource worker 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: workerName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identiteit.id}': {}
    }
  }
  dependsOn: [
    kvLezen
    acrPull
  ]
  properties: {
    managedEnvironmentId: omgeving.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registry
      secrets: geheimenApp
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: '${acrServer}/lm-worker:${imageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: envGedeeld
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

var portalDomeinen = [
  {
    name: 'hetlevendmonument.nl'
    bindingType: 'SniEnabled'
    certificateId: '${omgeving.id}/managedCertificates/hetlevendmonument-nl'
  }
  {
    name: 'www.hetlevendmonument.nl'
    bindingType: 'SniEnabled'
    certificateId: '${omgeving.id}/managedCertificates/www-hetlevendmonument-nl'
  }
]

resource portal 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: portalName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identiteit.id}': {}
    }
  }
  dependsOn: [
    acrPull
  ]
  properties: {
    managedEnvironmentId: omgeving.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 5174
        transport: 'auto'
        allowInsecure: false
        // Zonder deze lijst haalt elke herhaalde uitrol de domeinkoppeling weg.
        customDomains: domeinenGekoppeld ? portalDomeinen : []
      }
      registries: registry
    }
    template: {
      containers: [
        {
          name: 'portal'
          image: '${acrServer}/lm-portal:${imageTag}'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            // Volledige interne naam; zonder pad en zonder slash (portal/nginx.conf).
            { name: 'API_UPSTREAM', value: 'https://${apiName}.internal.${omgeving.properties.defaultDomain}' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Jobs (handmatig gestart door scripts/azure/levendmonument_uitrol.ps1).
// ---------------------------------------------------------------------------
resource migratie 'Microsoft.App/jobs@2024-03-01' = {
  name: 'levendmonument-migratie'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identiteit.id}': {}
    }
  }
  dependsOn: [
    kvLezen
    acrPull
  ]
  properties: {
    environmentId: omgeving.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registry
      secrets: [
        {
          name: 'db-owner-url'
          keyVaultUrl: '${kvUrl}/db-owner-url'
          identity: identiteit.id
        }
        {
          name: 'secret-key'
          keyVaultUrl: '${kvUrl}/secret-key'
          identity: identiteit.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'migratie'
          image: '${acrServer}/lm-api:${imageTag}'
          command: [
            'python3'
            '-m'
            'alembic'
            '-c'
            '/app/src/alembic.ini'
            'upgrade'
            'head'
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            // Migraties draaien als EIGENAAR, nooit als de applicatierol (runbook stap 6).
            { name: 'DATABASE_URL', secretRef: 'db-owner-url' }
            { name: 'SECRET_KEY', secretRef: 'secret-key' }
            { name: 'RUN_MIGRATIONS', value: 'true' }
            { name: 'PGSSLMODE', value: 'require' }
            { name: 'PYTHONUNBUFFERED', value: '1' }
          ]
        }
      ]
    }
  }
}

// Geeft sanskritisetu_app en sanskritisetu_bypass inlogrecht met het wachtwoord uit de Key
// Vault (runbook applicatie-databaserol.md stap 5, OP-154). De rollen zelf maken de
// migraties aan (NOLOGIN); dit is de bewuste, aparte stap per omgeving.
var rollenScript = '''
import asyncio, os, asyncpg
async def main():
    dsn = os.environ["DB_OWNER_URL"].replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(dsn, ssl="require")
    app_pw = os.environ["APP_DB_PASSWORD"].replace("'", "''")
    byp_pw = os.environ["BYPASS_DB_PASSWORD"].replace("'", "''")
    await con.execute(
        "ALTER ROLE sanskritisetu_app LOGIN PASSWORD '" + app_pw + "' "
        "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 100")
    await con.execute("ALTER ROLE sanskritisetu_bypass LOGIN PASSWORD '" + byp_pw + "'")
    rijen = await con.fetch(
        "SELECT rolname, rolcanlogin, rolsuper, rolbypassrls FROM pg_roles "
        "WHERE rolname IN ('sanskritisetu_app','sanskritisetu_bypass') ORDER BY 1")
    for r in rijen:
        print(dict(r))
    leden = await con.fetchval(
        "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member "
        "WHERE r.rolname = 'sanskritisetu_app'")
    print("sanskritisetu_app lid van andere rollen:", leden)
    assert leden == 0, "applicatierol mag geen lid zijn van een andere rol"
    await con.close()
asyncio.run(main())
'''

resource rollen 'Microsoft.App/jobs@2024-03-01' = {
  name: 'levendmonument-dbrollen'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identiteit.id}': {}
    }
  }
  dependsOn: [
    kvLezen
    acrPull
  ]
  properties: {
    environmentId: omgeving.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 300
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registry
      secrets: [
        {
          name: 'db-owner-url'
          keyVaultUrl: '${kvUrl}/db-owner-url'
          identity: identiteit.id
        }
        {
          name: 'app-db-password'
          keyVaultUrl: '${kvUrl}/app-db-password'
          identity: identiteit.id
        }
        {
          name: 'bypass-db-password'
          keyVaultUrl: '${kvUrl}/bypass-db-password'
          identity: identiteit.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'dbrollen'
          image: '${acrServer}/lm-api:${imageTag}'
          command: [
            'python3'
            '-c'
            rollenScript
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'DB_OWNER_URL', secretRef: 'db-owner-url' }
            { name: 'APP_DB_PASSWORD', secretRef: 'app-db-password' }
            { name: 'BYPASS_DB_PASSWORD', secretRef: 'bypass-db-password' }
          ]
        }
      ]
    }
  }
}

// Zet de tenant, de beheerder en de demoverhalen klaar (scripts/seed/publiceer_levend_monument.py).
// Het script gaat via loadTextContent mee in de template en draait met `python3 -c`; de
// verhalen zelf staan in de image (/app/scripts/seed/levend_monument_demo_verhalen.json).
@description('E-mailadres van de eerste beheerder van de portal.')
param beheerEmail string = 'rakesh@sanskritisetu.org'

resource publiceer 'Microsoft.App/jobs@2024-03-01' = {
  name: 'levendmonument-publiceer'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identiteit.id}': {}
    }
  }
  dependsOn: [
    kvLezen
    acrPull
  ]
  properties: {
    environmentId: omgeving.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 600
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registry
      secrets: [
        {
          name: 'db-owner-url'
          keyVaultUrl: '${kvUrl}/db-owner-url'
          identity: identiteit.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'publiceer'
          image: '${acrServer}/lm-api:${imageTag}'
          command: [
            'python3'
            '-c'
            loadTextContent('../scripts/seed/publiceer_levend_monument.py')
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'DATABASE_URL', secretRef: 'db-owner-url' }
            { name: 'BEHEER_EMAIL', value: beheerEmail }
            // Het importeren van de modellen bouwt de Dramatiq-broker en eist REDIS_URL.
            { name: 'REDIS_URL', value: redisUrl }
            { name: 'PORTAL_URL', value: frontendUrl }
            { name: 'PYTHONUNBUFFERED', value: '1' }
          ]
        }
      ]
    }
  }
}

// Verwijdert elke nacht leerlingantwoorden ouder dan 8 weken (BE-EP-055, privacy van
// minderjarigen). De API ruimt ook op bij elk lezen en schrijven; deze job zorgt dat het ook
// gebeurt als niemand de site bezoekt. Eigenaar-verbinding: de job werkt over alle tenants.
resource opschonen 'Microsoft.App/jobs@2024-03-01' = {
  name: 'levendmonument-opschonen'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identiteit.id}': {}
    }
  }
  dependsOn: [
    kvLezen
    acrPull
  ]
  properties: {
    environmentId: omgeving.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 600
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: '30 2 * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registry
      secrets: [
        {
          name: 'db-owner-url'
          keyVaultUrl: '${kvUrl}/db-owner-url'
          identity: identiteit.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'opschonen'
          image: '${acrServer}/lm-api:${imageTag}'
          command: [
            'python3'
            '-m'
            'src.core.services.foundation_leerlingantwoorden'
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'DATABASE_URL', secretRef: 'db-owner-url' }
            // Het importeren van de modellen bouwt de Dramatiq-broker en eist REDIS_URL.
            { name: 'REDIS_URL', value: redisUrl }
            { name: 'PYTHONUNBUFFERED', value: '1' }
          ]
        }
      ]
    }
  }
}

output portalFqdn string = deployApps ? portal.properties.configuration.ingress.fqdn : ''
output omgevingIp string = omgeving.properties.staticIp
output omgevingDomein string = omgeving.properties.defaultDomain
output verificatieId string = omgeving.properties.customDomainConfiguration.customDomainVerificationId
output opslagAccount string = opslag.outputs.storageAccountName
