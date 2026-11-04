@description('Name of the Log Analytics workspace')
param name string

@description('Azure region')
param location string = resourceGroup().location

@description('Retention period in days. Minimum 30, maximum 730. F-18 requires >=365.')
@minValue(30)
@maxValue(730)
param retentionInDays int = 365

@description('Daily ingestion cap in GB. -1 = no cap. Set to 1 as cost guard for MVP.')
param dailyQuotaGb int = 1

@description('SKU')
@allowed(['PerGB2018', 'Free'])
param sku string = 'PerGB2018'

@description('Tags')
param tags object = {}

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      name: sku
    }
    retentionInDays: retentionInDays
    workspaceCapping: {
      dailyQuotaGb: dailyQuotaGb
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

output workspaceId string = logAnalyticsWorkspace.id
output workspaceCustomerId string = logAnalyticsWorkspace.properties.customerId
// Workspace key is intentionally not exposed as an output — retrieve on demand via
// listKeys() in the calling context to avoid storage in plaintext deployment history.
