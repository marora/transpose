// sre-agent.bicep — Azure SRE Agent (Microsoft.App/agents)
//
// Brings the previously hand-provisioned `transpose-sc-agent` under IaC so its
// lifecycle (create / delete) is repeatable. See the dormant-cost lesson:
// idle Azure SRE Agents bill ~$10/day even with zero invocations, which made
// this the single largest dormant-cost contributor.
//
// Lifecycle pattern:
//   • Provision  → bicep deployment with deployAgent=true (default)
//   • Tear down  → `az resource delete -g <rg> -n <name> --resource-type Microsoft.App/agents`
//                  (followed by deleting the dedicated UAMI). Bicep incremental
//                  deployments do NOT delete resources by omission; the explicit
//                  `az resource delete` is the canonical teardown command until
//                  a complete-mode or stack deployment is introduced.

@description('Name prefix for agent and its dedicated managed identity')
param namePrefix string

@description('Override the agent resource name. Defaults to <namePrefix>-agent; set to adopt a pre-existing hand-provisioned agent into IaC without recreating it.')
param agentName string = ''

@description('Override the agent UAMI resource name. Defaults to <namePrefix>-agent-identity; set to adopt a pre-existing UAMI alongside the agent.')
param agentIdentityName string = ''

@description('Azure region for resource deployment (Azure SRE Agent is region-restricted)')
param location string = 'swedencentral'

@description('Resource tags')
param tags object = {}

@description('Application Insights resource ID for log forwarding')
param appInsightsId string

@description('Resource group ID the agent should reason over (knowledge graph scope)')
param managedResourceId string = resourceGroup().id

@description('Monthly cap on agent units (cost guardrail)')
param monthlyAgentUnitLimit int = 10000

@description('Upgrade channel for the agent runtime')
@allowed(['Stable', 'Preview'])
param upgradeChannel string = 'Stable'

@description('Default model provider')
param defaultModelProvider string = 'Anthropic'

@description('Default model name (Automatic lets the platform pick the best fit)')
param defaultModelName string = 'Automatic'

@description('Action-execution access level')
@allowed(['Low', 'Medium', 'High'])
param actionAccessLevel string = 'Low'

@description('Action execution mode (review = human-in-the-loop)')
@allowed(['review', 'autoApprove'])
param actionMode string = 'review'

var resolvedAgentName = empty(agentName) ? '${namePrefix}-agent' : agentName
var resolvedIdentityName = empty(agentIdentityName) ? '${namePrefix}-agent-identity' : agentIdentityName

// Dedicated user-assigned identity for the agent. Mirrors the existing
// `transpose-sc-agent-<suffix>` UAMI that the portal auto-creates.
resource agentIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: resolvedIdentityName
  location: location
  tags: tags
}

resource sreAgent 'Microsoft.App/agents@2025-05-01-preview' = {
  name: resolvedAgentName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${agentIdentity.id}': {}
    }
  }
  properties: {
    actionConfiguration: {
      accessLevel: actionAccessLevel
      identity: agentIdentity.id
      mode: actionMode
    }
    defaultModel: {
      name: defaultModelName
      provider: defaultModelProvider
    }
    experimentalSettings: {
      EnableV2AgentLoop: true
      EnableWorkspaceTools: true
    }
    knowledgeGraphConfiguration: {
      identity: agentIdentity.id
      managedResources: [
        managedResourceId
      ]
    }
    logConfiguration: {
      applicationInsightsConfiguration: {
        applicationInsightsResourceId: appInsightsId
      }
    }
    mcpServers: []
    monthlyAgentUnitLimit: monthlyAgentUnitLimit
    upgradeChannel: upgradeChannel
  }
}

output agentName string = sreAgent.name
output agentId string = sreAgent.id
output agentEndpoint string = sreAgent.properties.agentEndpoint
output agentIdentityName string = agentIdentity.name
output agentIdentityPrincipalId string = agentIdentity.properties.principalId
