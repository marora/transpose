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

// Tags are set in main.bicep based on environmentName
