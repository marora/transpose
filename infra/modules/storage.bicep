// storage.bicep - Azure Blob Storage for source PDFs and outputs

@description('Name prefix for storage account')
param namePrefix string

@description('Azure region for resource deployment')
param location string

@description('Resource tags')
param tags object = {}

// Storage account name must be globally unique and lowercase alphanumeric only
var storageAccountName = replace('${namePrefix}st', '-', '')

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    encryption: {
      services: {
        blob: {
          enabled: true
        }
      }
      keySource: 'Microsoft.Storage'
    }
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// Blob service with versioning
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    isVersioningEnabled: true
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

// Container for source PDFs
resource sourcePdfsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'source-pdfs'
  properties: {
    publicAccess: 'None'
  }
}

// Container for output files (ePub, PDF)
resource outputContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'output'
  properties: {
    publicAccess: 'None'
  }
}

output storageAccountId string = storageAccount.id
output storageAccountName string = storageAccount.name
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
output sourcePdfsContainerName string = sourcePdfsContainer.name
output outputContainerName string = outputContainer.name
