// identity.bicep - User-Assigned Managed Identity with RBAC role assignments

@description('Name prefix for managed identity')
param namePrefix string

@description('Azure region for resource deployment')
param location string

@description('Resource tags')
param tags object = {}

@description('Storage account ID for role assignment')
param storageAccountId string

@description('Document Intelligence account ID for role assignment')
param documentIntelligenceId string

@description('OpenAI account ID for role assignment')
param openAIId string

@description('Application Insights ID for role assignment')
param appInsightsId string

// User-Assigned Managed Identity
resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-identity'
  location: location
  tags: tags
}

// Reference existing resources for role assignments
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: last(split(storageAccountId, '/'))
}

resource documentIntelligence 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' existing = {
  name: last(split(documentIntelligenceId, '/'))
}

resource openAI 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' existing = {
  name: last(split(openAIId, '/'))
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: last(split(appInsightsId, '/'))
}

// Storage Blob Data Contributor role
resource storageBlobContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, managedIdentity.id, 'Storage Blob Data Contributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services User on Document Intelligence
resource docIntelUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(documentIntelligenceId, managedIdentity.id, 'Cognitive Services User')
  scope: documentIntelligence
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908') // Cognitive Services User
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services OpenAI User
resource openAIUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAIId, managedIdentity.id, 'Cognitive Services OpenAI User')
  scope: openAI
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd') // Cognitive Services OpenAI User
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Monitoring Metrics Publisher (for Application Insights)
resource metricsPublisherRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appInsightsId, managedIdentity.id, 'Monitoring Metrics Publisher')
  scope: appInsights
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '3913510d-42f4-4e42-8a64-420c390055eb') // Monitoring Metrics Publisher
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

output managedIdentityId string = managedIdentity.id
output managedIdentityName string = managedIdentity.name
output managedIdentityPrincipalId string = managedIdentity.properties.principalId
output managedIdentityClientId string = managedIdentity.properties.clientId
output managedIdentityObjectId string = managedIdentity.properties.principalId
