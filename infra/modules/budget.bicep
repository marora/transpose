// budget.bicep - Azure Budget Alert for Transpose
// Monitors monthly spend with configurable threshold and email alerts

targetScope = 'resourceGroup'

@description('Name prefix for budget resources')
param namePrefix string

@description('Monthly budget amount in USD')
param monthlyBudgetAmount int = 25

@description('Email address for budget notifications')
param alertEmail string

@description('Budget start date (YYYY-MM-01 format, defaults to current month)')
param startDate string = '${utcNow('yyyy-MM')}-01'

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: '${namePrefix}-monthly-budget'
  properties: {
    category: 'Cost'
    amount: monthlyBudgetAmount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: startDate
    }
    notifications: {
      atFiftyPercent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        contactEmails: [
          alertEmail
        ]
        thresholdType: 'Actual'
      }
      atEightyPercent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        contactEmails: [
          alertEmail
        ]
        thresholdType: 'Actual'
      }
      atOneHundredPercent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        contactEmails: [
          alertEmail
        ]
        thresholdType: 'Actual'
      }
    }
  }
}

output budgetName string = budget.name
