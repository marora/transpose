// main.bicep - Transpose Azure Infrastructure Orchestrator
// Provisions all Azure resources needed for the Transpose literary translation pipeline

targetScope = 'resourceGroup'

@description('Environment name (e.g., dev, staging, prod)')
@minLength(3)
@maxLength(10)
param environmentName string = 'dev'

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Resource tags')
param tags object = {
  environment: environmentName
  project: 'transpose'
  managedBy: 'bicep'
}

@description('Allow public network access to PostgreSQL (disable for production)')
param allowPublicPostgresAccess bool = true

@description('Container image for the application')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Container registry server (leave empty for public registries)')
param containerRegistryServer string = ''

@description('LaBSE sidecar image for Oracle Layer A embeddings (leave empty for placeholder)')
param labseImage string = ''

@description('Email address for Azure Monitor alert notifications')
param alertEmail string = ''

@description('Email address for budget notifications')
param budgetAlertEmail string = ''

@description('Monthly budget amount in USD')
param monthlyBudgetAmount int = 25

@description('SKU for Azure Container Registry')
@allowed(['Basic', 'Standard', 'Premium'])
param acrSku string = 'Basic'

// Naming convention: transpose-{env}-{service}
var namePrefix = 'transpose-${environmentName}'

// Get tenant ID
var tenantId = tenant().tenantId

// ============================================================================
// MODULE 1: Monitoring (Log Analytics + Application Insights)
// ============================================================================
module monitoring './modules/monitoring.bicep' = {
  name: 'monitoring-deployment'
  params: {
    namePrefix: namePrefix
    location: location
    tags: tags
  }
}

// ============================================================================
// MODULE 2: Storage (Blob Storage for PDFs and outputs)
// ============================================================================
module storage './modules/storage.bicep' = {
  name: 'storage-deployment'
  params: {
    namePrefix: namePrefix
    location: location
    tags: tags
  }
}

// ============================================================================
// MODULE 3: Cache (Removed — using PostgreSQL for pipeline state)
// ============================================================================
// Redis removed per serverless-first directive

// ============================================================================
// MODULE 4: Cognitive Services (Document Intelligence + OpenAI)
// ============================================================================
module cognitiveServices './modules/cognitive-services.bicep' = {
  name: 'cognitive-services-deployment'
  params: {
    namePrefix: namePrefix
    location: location
    tags: tags
  }
}

// ============================================================================
// MODULE 5: Identity (User-Assigned Managed Identity + RBAC)
// ============================================================================
module identity './modules/identity.bicep' = {
  name: 'identity-deployment'
  params: {
    namePrefix: namePrefix
    location: location
    tags: tags
    storageAccountId: storage.outputs.storageAccountId
    documentIntelligenceId: cognitiveServices.outputs.documentIntelligenceId
    openAIId: cognitiveServices.outputs.openAIId
    appInsightsId: monitoring.outputs.appInsightsId
  }
}

// ============================================================================
// MODULE 6: Key Vault (for future secrets if needed)
// ============================================================================
module keyVault './modules/keyvault.bicep' = {
  name: 'keyvault-deployment'
  params: {
    namePrefix: namePrefix
    location: location
    tags: tags
    tenantId: tenantId
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
  }
}

// ============================================================================
// MODULE 7: Database (PostgreSQL with Entra authentication)
// ============================================================================
module database './modules/database.bicep' = {
  name: 'database-deployment'
  params: {
    namePrefix: namePrefix
    location: location
    tags: tags
    tenantId: tenantId
    managedIdentityObjectId: identity.outputs.managedIdentityObjectId
    managedIdentityName: identity.outputs.managedIdentityName
    allowPublicAccess: allowPublicPostgresAccess
  }
}

// ============================================================================
// MODULE 8: Azure Container Registry
// ============================================================================
module acr './modules/acr.bicep' = {
  name: 'acr-deployment'
  params: {
    name: replace('${namePrefix}-acr', '-', '')
    location: location
    sku: acrSku
    tags: tags
    pullIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
  }
}

// ============================================================================
// MODULE 9: Azure Monitor Alert Rules
// ============================================================================
module alerts './modules/alerts.bicep' = if (!empty(alertEmail)) {
  name: 'alerts-deployment'
  params: {
    namePrefix: namePrefix
    location: location
    tags: tags
    appInsightsId: monitoring.outputs.appInsightsId
    alertEmail: alertEmail
  }
}

// ============================================================================
// MODULE 10: Budget Alerts
// ============================================================================
module budget './modules/budget.bicep' = if (!empty(budgetAlertEmail)) {
  name: 'budget-deployment'
  params: {
    namePrefix: namePrefix
    monthlyBudgetAmount: monthlyBudgetAmount
    alertEmail: budgetAlertEmail
  }
}

// ============================================================================
// MODULE 11: Container App (Compute runtime)
// ============================================================================
module containerApp './modules/container-app.bicep' = {
  name: 'container-app-deployment'
  params: {
    namePrefix: namePrefix
    location: location
    tags: tags
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
    managedIdentityId: identity.outputs.managedIdentityId
    managedIdentityClientId: identity.outputs.managedIdentityClientId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    documentIntelligenceEndpoint: cognitiveServices.outputs.documentIntelligenceEndpoint
    openAIEndpoint: cognitiveServices.outputs.openAIEndpoint
    openAIDeploymentName: cognitiveServices.outputs.gpt4oDeploymentName
    storageAccountBlobEndpoint: storage.outputs.blobEndpoint
    storageAccountStaticWebsiteEndpoint: storage.outputs.staticWebsiteEndpoint
    postgresFqdn: database.outputs.postgresFqdn
    postgresDatabaseName: database.outputs.postgresDatabaseName
    keyVaultUri: keyVault.outputs.keyVaultUri
    containerImage: containerImage
    containerRegistryServer: containerRegistryServer
    labseImage: labseImage
  }
}

// ============================================================================
// OUTPUTS
// ============================================================================

output resourceGroupName string = resourceGroup().name
output location string = location
output environmentName string = environmentName

// Monitoring
output logAnalyticsWorkspaceName string = monitoring.outputs.logAnalyticsWorkspaceName
output appInsightsName string = monitoring.outputs.appInsightsName
output appInsightsConnectionString string = monitoring.outputs.appInsightsConnectionString

// Storage
output storageAccountName string = storage.outputs.storageAccountName
output staticWebsiteEndpoint string = storage.outputs.staticWebsiteEndpoint
output sourcePdfsContainerName string = storage.outputs.sourcePdfsContainerName
output outputContainerName string = storage.outputs.outputContainerName
output bookWorkspacesContainerName string = storage.outputs.bookWorkspacesContainerName

// Cognitive Services
output documentIntelligenceName string = cognitiveServices.outputs.documentIntelligenceName
output documentIntelligenceEndpoint string = cognitiveServices.outputs.documentIntelligenceEndpoint
output openAIName string = cognitiveServices.outputs.openAIName
output openAIEndpoint string = cognitiveServices.outputs.openAIEndpoint
output gpt4oDeploymentName string = cognitiveServices.outputs.gpt4oDeploymentName

// Database
output postgresServerName string = database.outputs.postgresServerName
output postgresFqdn string = database.outputs.postgresFqdn
output postgresDatabaseName string = database.outputs.postgresDatabaseName

// Key Vault
output keyVaultName string = keyVault.outputs.keyVaultName
output keyVaultUri string = keyVault.outputs.keyVaultUri

// Identity
output managedIdentityName string = identity.outputs.managedIdentityName
output managedIdentityClientId string = identity.outputs.managedIdentityClientId

// Container Registry
output acrLoginServer string = acr.outputs.loginServer
output acrName string = acr.outputs.name

// Container App
output containerAppName string = containerApp.outputs.containerAppName
output containerAppFqdn string = containerApp.outputs.containerAppFqdn
