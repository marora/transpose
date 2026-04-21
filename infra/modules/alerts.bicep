// alerts.bicep - Azure Monitor Alert Rules for Transpose pipeline
// Covers error rate, latency, and pipeline failure alerting

@description('Name prefix for alert resources')
param namePrefix string

@description('Azure region for resource deployment')
param location string

@description('Resource tags')
param tags object = {}

@description('Application Insights resource ID')
param appInsightsId string

@description('Email address for alert notifications')
param alertEmail string

@description('Error rate threshold (percentage of 5xx responses)')
param errorRateThreshold int = 5

@description('P95 latency threshold in seconds')
param latencyThresholdSeconds int = 30

// Action Group for email notifications
resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: '${namePrefix}-alerts-ag'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'TransposeAG'
    enabled: true
    emailReceivers: [
      {
        name: 'PrimaryEmail'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

// Alert 1: Error rate — >5% of requests return 5xx over 5-minute window
resource errorRateAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: '${namePrefix}-error-rate-alert'
  location: location
  tags: tags
  properties: {
    displayName: 'High Error Rate (5xx)'
    description: 'Fires when more than ${errorRateThreshold}% of requests return 5xx status codes over a 5-minute window.'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    scopes: [
      appInsightsId
    ]
    criteria: {
      allOf: [
        {
          query: '''
            requests
            | where timestamp > ago(5m)
            | summarize totalRequests = count(), failedRequests = countif(toint(resultCode) >= 500)
            | extend errorRate = iff(totalRequests == 0, 0.0, (toreal(failedRequests) / toreal(totalRequests)) * 100)
            | project errorRate
          '''
          timeAggregation: 'Maximum'
          metricMeasureColumn: 'errorRate'
          operator: 'GreaterThan'
          threshold: errorRateThreshold
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [
        actionGroup.id
      ]
    }
  }
}

// Alert 2: Latency — P95 response time >30s over 5-minute window
resource latencyAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: '${namePrefix}-latency-alert'
  location: location
  tags: tags
  properties: {
    displayName: 'High P95 Latency'
    description: 'Fires when P95 response time exceeds ${latencyThresholdSeconds}s over a 5-minute window.'
    severity: 3
    enabled: true
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    scopes: [
      appInsightsId
    ]
    criteria: {
      allOf: [
        {
          query: '''
            requests
            | where timestamp > ago(5m)
            | summarize p95_duration_s = percentile(duration, 95) / 1000
            | project p95_duration_s
          '''
          timeAggregation: 'Maximum'
          metricMeasureColumn: 'p95_duration_s'
          operator: 'GreaterThan'
          threshold: latencyThresholdSeconds
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [
        actionGroup.id
      ]
    }
  }
}

// Alert 3: Pipeline failures — custom metric pipeline_failures > 0
resource pipelineFailureAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: '${namePrefix}-pipeline-failure-alert'
  location: location
  tags: tags
  properties: {
    displayName: 'Pipeline Failure Detected'
    description: 'Fires when any pipeline failure is recorded (pipeline_failures custom metric > 0).'
    severity: 1
    enabled: true
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    scopes: [
      appInsightsId
    ]
    criteria: {
      allOf: [
        {
          query: '''
            customMetrics
            | where timestamp > ago(5m)
            | where name == 'pipeline_failures'
            | summarize totalFailures = sum(value)
            | project totalFailures
          '''
          timeAggregation: 'Maximum'
          metricMeasureColumn: 'totalFailures'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [
        actionGroup.id
      ]
    }
  }
}

output actionGroupId string = actionGroup.id
output actionGroupName string = actionGroup.name
