// cognitive-services.bicep - Azure AI Document Intelligence and Azure OpenAI

@description('Name prefix for cognitive services')
param namePrefix string

@description('Azure region for resource deployment')
param location string

@description('Resource tags')
param tags object = {}

// Azure AI Document Intelligence
resource documentIntelligence 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: '${namePrefix}-docintel'
  location: location
  tags: tags
  kind: 'FormRecognizer'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: '${namePrefix}-docintel'
    networkAcls: {
      defaultAction: 'Allow'
    }
    publicNetworkAccess: 'Enabled'
  }
  identity: {
    type: 'SystemAssigned'
  }
}

// Azure OpenAI
resource openAI 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: '${namePrefix}-openai'
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: '${namePrefix}-openai'
    networkAcls: {
      defaultAction: 'Allow'
    }
    publicNetworkAccess: 'Enabled'
  }
  identity: {
    type: 'SystemAssigned'
  }
}

// GPT-4o deployment
resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openAI
  name: 'gpt-4o'
  sku: {
    name: 'Standard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-11-20'
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
    raiPolicyName: 'Microsoft.Default'
  }
}

output documentIntelligenceId string = documentIntelligence.id
output documentIntelligenceName string = documentIntelligence.name
output documentIntelligenceEndpoint string = documentIntelligence.properties.endpoint
output openAIId string = openAI.id
output openAIName string = openAI.name
output openAIEndpoint string = openAI.properties.endpoint
output gpt4oDeploymentName string = gpt4oDeployment.name
