// container-app.bicep - Azure Container Apps Environment and Container App

@description('Name prefix for container app resources')
param namePrefix string

@description('Azure region for resource deployment')
param location string

@description('Resource tags')
param tags object = {}

@description('Log Analytics Workspace ID')
param logAnalyticsWorkspaceId string

@description('Managed Identity ID')
param managedIdentityId string

@description('Managed Identity Client ID')
param managedIdentityClientId string

@description('Application Insights Connection String')
@secure()
param appInsightsConnectionString string

@description('Document Intelligence Endpoint')
param documentIntelligenceEndpoint string

@description('OpenAI Endpoint')
param openAIEndpoint string

@description('OpenAI Deployment Name')
param openAIDeploymentName string

@description('Storage Account Blob Endpoint')
param storageAccountBlobEndpoint string

@description('Storage Account Static Website Endpoint')
param storageAccountStaticWebsiteEndpoint string

@description('PostgreSQL Server FQDN')
param postgresFqdn string

@description('PostgreSQL Database Name')
param postgresDatabaseName string

@description('Key Vault URI')
param keyVaultUri string

@description('Container image (defaults to placeholder)')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Minimum number of replicas (0 = scale to zero)')
param minReplicas int = 1

@description('Maximum number of replicas')
param maxReplicas int = 5

@description('HTTP concurrent requests threshold for scaling')
param httpScaleConcurrency int = 10

@description('Container registry server (leave empty for public registries)')
param containerRegistryServer string = ''
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: last(split(logAnalyticsWorkspaceId, '/'))
}

// Container Apps Environment
resource containerAppEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: '${namePrefix}-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

// Container App
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${namePrefix}-app'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: empty(containerRegistryServer) ? [] : [
        {
          server: containerRegistryServer
          identity: managedIdentityId
        }
      ]
      secrets: [
        {
          name: 'appinsights-connection-string'
          value: appInsightsConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'transpose'
          image: containerImage
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            // Azure Identity SDK needs this to select the correct Managed Identity
            {
              name: 'AZURE_CLIENT_ID'
              value: managedIdentityClientId
            }
            // All TRANSPOSE_* env vars match pydantic Settings fields (env_prefix = "TRANSPOSE_")
            {
              name: 'TRANSPOSE_POSTGRES_HOST'
              value: postgresFqdn
            }
            {
              name: 'TRANSPOSE_POSTGRES_DB'
              value: postgresDatabaseName
            }
            {
              name: 'TRANSPOSE_POSTGRES_USER'
              value: managedIdentityClientId
            }
            // No TRANSPOSE_POSTGRES_PASSWORD — Managed Identity auth, no password needed
            {
              name: 'TRANSPOSE_OPENAI_ENDPOINT'
              value: openAIEndpoint
            }
            {
              name: 'TRANSPOSE_OPENAI_DEPLOYMENT'
              value: openAIDeploymentName
            }
            {
              name: 'TRANSPOSE_DOC_INTELLIGENCE_ENDPOINT'
              value: documentIntelligenceEndpoint
            }
            {
              name: 'TRANSPOSE_BLOB_STORAGE_ACCOUNT_URL'
              value: storageAccountBlobEndpoint
            }
            {
              name: 'TRANSPOSE_BLOB_STATIC_WEBSITE_URL'
              value: storageAccountStaticWebsiteEndpoint
            }
            {
              name: 'TRANSPOSE_KEYVAULT_URL'
              value: keyVaultUri
            }
            {
              name: 'TRANSPOSE_APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'appinsights-connection-string'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 30
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 15
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '${httpScaleConcurrency}'
              }
            }
          }
        ]
      }
    }
  }
}

output containerAppEnvId string = containerAppEnv.id
output containerAppEnvName string = containerAppEnv.name
output containerAppId string = containerApp.id
output containerAppName string = containerApp.name
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
