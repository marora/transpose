// Azure Container Registry module for Transpose
// Provides container image storage with Managed Identity-based pull access

@description('Name of the Azure Container Registry')
param name string

@description('Azure region for the resource')
param location string = resourceGroup().location

@description('SKU for the container registry')
@allowed(['Basic', 'Standard', 'Premium'])
param sku string = 'Basic'

@description('Tags to apply to the resource')
param tags object = {}

@description('Principal ID of the managed identity that needs AcrPull access')
param pullIdentityPrincipalId string = ''

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
    dataEndpointEnabled: false
    policies: {
      retentionPolicy: {
        days: 7
        status: 'disabled'
      }
    }
  }
}

// AcrPull role assignment for the managed identity
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(pullIdentityPrincipalId)) {
  name: guid(acr.id, pullIdentityPrincipalId, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: pullIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

@description('Container registry login server')
output loginServer string = acr.properties.loginServer

@description('Container registry resource ID')
output id string = acr.id

@description('Container registry name')
output name string = acr.name
