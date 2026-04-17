// database.bicep - PostgreSQL Flexible Server with Entra authentication

@description('Name prefix for PostgreSQL server')
param namePrefix string

@description('Azure region for resource deployment')
param location string

@description('Resource tags')
param tags object = {}

@description('Tenant ID for Entra authentication')
param tenantId string

@description('Object ID of the managed identity to set as Entra admin (same as principal ID)')
param managedIdentityObjectId string

@description('Name of the managed identity')
param managedIdentityName string

@description('Allow public network access (set to false for production)')
param allowPublicAccess bool = true

// NOTE: PostgreSQL Flexible Server auto-stop (auto-pause) for cost savings
// is configured post-deployment via Azure CLI or Portal, not directly in Bicep.
// To enable auto-stop after deployment, run:
//   az postgres flexible-server update --resource-group <rg> --name <server> --auto-grow Disabled
// This will auto-pause the server when inactive, reducing costs to near-zero during idle periods.
// The server will auto-resume when accessed.

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-03-01-preview' = {
  name: '${namePrefix}-psql'
  location: location
  tags: tags
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '15'
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Disabled'
      tenantId: tenantId
    }
  }
}

// NOTE: Entra admin is configured post-deployment via Azure CLI
// because of a timing issue where the server isn't fully accessible
// during the ARM deployment. See infra/README.md for the CLI command.
// resource entraAdmin removed — handled post-deploy

// Allow Azure services firewall rule
resource firewallRuleAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-03-01-preview' = if (allowPublicAccess) {
  parent: postgresServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// Create transpose database
resource transposeDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-03-01-preview' = {
  parent: postgresServer
  name: 'transpose'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

output postgresServerId string = postgresServer.id
output postgresServerName string = postgresServer.name
output postgresFqdn string = postgresServer.properties.fullyQualifiedDomainName
output postgresDatabaseName string = transposeDb.name
