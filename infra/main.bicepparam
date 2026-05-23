// main.bicepparam - Default parameters for Transpose infrastructure deployment

using './main.bicep'

// Environment configuration
param environmentName = 'dev'

// Network access (set to false for production)
param allowPublicPostgresAccess = true

// Container configuration (update after building the app image)
param containerImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
param containerRegistryServer = ''

// Cost guardrails: $25/month RG budget from dormant-cost lesson
param budgetAlertEmail = 'marora@gmail.com'
param monthlyBudgetAmount = 25

// Azure SRE Agent lifecycle — set deployAgent=false before walking away for >3 days
// to stop the ~$10/day idle billing (see dormant-cost lesson). Re-deploying
// with true re-creates the agent in <5 min.
// agentName/agentIdentityName adopt the pre-existing hand-provisioned resources
// into IaC without recreating them. Leave empty after a clean teardown to use the
// default ${namePrefix}-agent naming convention.
param deployAgent = true
param agentLocation = 'swedencentral'
param agentName = 'transpose-sc-agent'
param agentIdentityName = 'transpose-sc-agent-5h56rfksrqb24'

// Tags are set in main.bicep based on environmentName
