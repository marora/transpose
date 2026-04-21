// workbook.bicep — Deploys the Transpose Pipeline Operations workbook
// Links to Application Insights and scopes KQL queries to it.

@description('Name for the workbook resource')
param workbookName string = 'Transpose Pipeline Operations'

@description('Azure region')
param location string

@description('Resource ID of the Application Insights instance')
param appInsightsId string

@description('Resource tags')
param tags object = {}

// Deterministic GUID so re-deploys are idempotent
var workbookGuid = guid(resourceGroup().id, 'transpose-pipeline-dashboard')

resource workbook 'Microsoft.Insights/workbooks@2022-04-01' = {
  name: workbookGuid
  location: location
  tags: tags
  kind: 'shared'
  properties: {
    displayName: workbookName
    category: 'workbook'
    sourceId: appInsightsId
    serializedData: loadTextContent('../workbooks/pipeline-dashboard.json')
  }
}

output workbookId string = workbook.id
output workbookName string = workbook.properties.displayName
