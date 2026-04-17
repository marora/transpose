// main.bicepparam - Default parameters for Transpose infrastructure deployment

using './main.bicep'

// Environment configuration
param environmentName = 'dev'

// Network access (set to false for production)
param allowPublicPostgresAccess = true

// Container configuration (update after building the app image)
param containerImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
param containerRegistryServer = ''

// Tags are set in main.bicep based on environmentName
