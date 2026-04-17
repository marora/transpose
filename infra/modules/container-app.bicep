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

@description('Storage Account Name')
param storageAccountName string

@description('PostgreSQL Server FQDN')
param postgresFqdn string

@description('PostgreSQL Database Name')
param postgresDatabaseName string

@description('Redis Host Name')
param redisHostName string

@description('Redis SSL Port')
param redisSslPort int

@description('Key Vault URI')
param keyVaultUri string

@description('Redis Password Secret URI from Key Vault')
param redisPasswordSecretUri string

@description('Container image (defaults to placeholder)')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Container registry server (leave empty for public registries)')
param containerRegistryServer string = ''

// Extract Log Analytics customer ID and shared key
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
        {
          name: 'redis-password'
          keyVaultUrl: redisPasswordSecretUri
          identity: managedIdentityId
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
            {
              name: 'AZURE_CLIENT_ID'
              value: managedIdentityClientId
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'appinsights-connection-string'
            }
            {
              name: 'DOCUMENT_INTELLIGENCE_ENDPOINT'
              value: documentIntelligenceEndpoint
            }
            {
              name: 'OPENAI_ENDPOINT'
              value: openAIEndpoint
            }
            {
              name: 'OPENAI_DEPLOYMENT_NAME'
              value: openAIDeploymentName
            }
            {
              name: 'STORAGE_ACCOUNT_BLOB_ENDPOINT'
              value: storageAccountBlobEndpoint
            }
            {
              name: 'STORAGE_ACCOUNT_NAME'
              value: storageAccountName
            }
            {
              name: 'POSTGRES_HOST'
              value: postgresFqdn
            }
            {
              name: 'POSTGRES_DATABASE'
              value: postgresDatabaseName
            }
            {
              name: 'POSTGRES_USER'
              value: managedIdentityClientId
            }
            {
              name: 'REDIS_HOST'
              value: redisHostName
            }
            {
              name: 'REDIS_PORT'
              value: string(redisSslPort)
            }
            {
              name: 'REDIS_PASSWORD'
              secretRef: 'redis-password'
            }
            {
              name: 'KEY_VAULT_URI'
              value: keyVaultUri
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
        minReplicas: 0
        maxReplicas: 3
        rules: []
      }
    }
  }
}

output containerAppEnvId string = containerAppEnv.id
output containerAppEnvName string = containerAppEnv.name
output containerAppId string = containerApp.id
output containerAppName string = containerApp.name
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
