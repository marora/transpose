# Observability Guide — Transpose Pipeline

This document covers monitoring, alerting, and troubleshooting for the Transpose translation pipeline running on Azure.

## Architecture

The pipeline emits telemetry via [azure-monitor-opentelemetry](https://pypi.org/project/azure-monitor-opentelemetry/) which sends traces, metrics, and logs to Application Insights backed by a Log Analytics workspace.

| Component | Resource Name | Purpose |
|-----------|--------------|---------|
| Application Insights | `{namePrefix}-appinsights` | Traces, custom metrics, dependency tracking |
| Log Analytics | `{namePrefix}-logs` | KQL query engine, log retention |
| Custom Metrics | `src/transpose/observability/metrics.py` | Pipeline-specific counters and histograms |
| Tracing | `src/transpose/observability/tracing.py` | Distributed trace configuration |

### Custom Metrics Emitted

| Metric | Type | Description |
|--------|------|-------------|
| `transpose.pipeline.stage_duration` | Histogram | Duration of each pipeline stage (seconds) |
| `transpose.pipeline.chunks_translated` | Counter | Number of text chunks translated |
| `transpose.openai.tokens_used` | Counter | Total OpenAI GPT-4o tokens consumed |
| `transpose.ocr.pages_processed` | Counter | Pages processed by Document Intelligence |
| `transpose.ocr.low_confidence_pages` | Counter | Pages below OCR confidence threshold |
| `transpose.errors` | Counter | Errors by `stage` and `error_type` dimensions |

---

## Azure Portal Navigation (2026 UI)

The Azure Portal's Application Insights layout has changed. Here's how to find what you need:

### Finding Application Insights

1. **Azure Portal** → search for your resource name (e.g., `transpose-dev-appinsights`)
2. Or: **Resource Group** → click the Application Insights resource

### Key Menu Sections

| What You Want | Portal Path |
|---------------|-------------|
| **Live metrics / overview** | App Insights → Overview (top-level dashboard) |
| **Distributed traces** | App Insights → **Investigate** → **Transaction search** |
| **Performance & latency** | App Insights → **Investigate** → **Performance** |
| **Dependency calls** | App Insights → **Investigate** → **Performance** → **Dependencies** tab (top of page) |
| **Failures & exceptions** | App Insights → **Investigate** → **Failures** |
| **Custom metrics explorer** | App Insights → **Monitoring** → **Metrics** |
| **Log queries (KQL)** | App Insights → **Monitoring** → **Logs** |
| **Workbooks / dashboards** | App Insights → **Monitoring** → **Workbooks** |
| **Alerts** | App Insights → **Monitoring** → **Alerts** |
| **Live metrics stream** | App Insights → **Investigate** → **Live metrics** |

> **Note:** The old "Performance" blade at the top level has moved under **Investigate** in the 2026 Portal UI. If you don't see "Dependencies" as a separate menu item, click **Performance** → then switch between the **Operations** and **Dependencies** tabs at the top of the blade.

### Finding Custom Metrics

1. Go to App Insights → **Monitoring** → **Metrics**
2. In the **Metric Namespace** dropdown, select **Log-based metrics** or **azure.applicationinsights**
3. For OpenTelemetry custom metrics, select **Custom Metric Namespace: transpose**
4. Choose the metric (e.g., `transpose.pipeline.stage_duration`)
5. Apply splitting by dimension (e.g., `stage`)

### Finding the Transpose Workbook

After deploying with `deploy-workbook.sh`:

1. App Insights → **Monitoring** → **Workbooks**
2. Look under **Recently modified** or **All**
3. Click **Transpose Pipeline Dashboard**

Or find it directly in the Resource Group as an **Azure Workbook** resource.

---

## Workbook Dashboard

### Deploying the Workbook

```bash
cd infra/workbooks

# Deploy to your resource group
./deploy-workbook.sh -g transpose-dev

# With explicit subscription
./deploy-workbook.sh -g transpose-dev -s "My Subscription"

# Custom name
./deploy-workbook.sh -g transpose-dev -n "My Custom Dashboard Name"
```

The workbook template is at `infra/workbooks/transpose-dashboard.json`. It provides five tabs:

| Tab | What It Shows |
|-----|---------------|
| **Pipeline Overview** | Stage duration over time, throughput counters, error rate by stage, active runs |
| **Translation Performance** | Token usage, chunks/hour, latency distribution (P50/P90/P99), cost estimation |
| **OCR & Quality** | Pages processed, low-confidence ratio, OCR stage duration, OCR failures |
| **Infrastructure Health** | Container App process metrics, PostgreSQL query perf, dependency summary, HTTP success rate |
| **Errors & Alerts** | Exception timeline, top errors by stage/type, failed dependencies, alert rule recommendations |

### Importing Manually

If you prefer not to use the script, import the workbook JSON directly:

1. Go to **Azure Monitor** → **Workbooks** → **New**
2. Click the **Advanced Editor** (`</>` button)
3. Paste the contents of `infra/workbooks/transpose-dashboard.json`
4. Click **Apply** → **Done Editing** → **Save**

---

## KQL Queries

All queries below can be run directly in **App Insights → Monitoring → Logs**.

### Pipeline Stage Duration

```kusto
customMetrics
| where name == "transpose.pipeline.stage_duration"
| extend stage = tostring(customDimensions.stage)
| summarize
    avg_seconds = round(avg(value), 2),
    p95_seconds = round(percentile(value, 95), 2),
    max_seconds = round(max(value), 2),
    invocations = count()
  by stage
| order by avg_seconds desc
```

### OpenAI Token Usage by Hour

```kusto
customMetrics
| where name == "transpose.openai.tokens_used"
| summarize total_tokens = sum(value) by bin(timestamp, 1h)
| order by timestamp asc
| render timechart
```

### Token Cost Estimation

```kusto
// GPT-4o pricing: $2.50/1M input, $10.00/1M output
let input_tokens = customMetrics
| where name == "transpose.openai.tokens_used"
| where tostring(customDimensions.type) in ("prompt", "input")
| summarize total = sum(value);
let output_tokens = customMetrics
| where name == "transpose.openai.tokens_used"
| where tostring(customDimensions.type) in ("completion", "output")
| summarize total = sum(value);
input_tokens | extend d=1
| join (output_tokens | extend d=1) on d
| project
    input_tokens = total,
    output_tokens = total1,
    input_cost_usd = round(total / 1000000.0 * 2.50, 4),
    output_cost_usd = round(total1 / 1000000.0 * 10.00, 4),
    total_cost_usd = round(total / 1000000.0 * 2.50 + total1 / 1000000.0 * 10.00, 4)
```

### Error Rate by Stage

```kusto
customMetrics
| where name == "transpose.errors"
| extend stage = tostring(customDimensions.stage),
         error_type = tostring(customDimensions.error_type)
| summarize error_count = sum(value) by stage, error_type, bin(timestamp, 1h)
| order by timestamp asc
| render barchart
```

### OCR Confidence Analysis

```kusto
let total = customMetrics | where name == "transpose.ocr.pages_processed" | summarize sum(value);
let low = customMetrics | where name == "transpose.ocr.low_confidence_pages" | summarize sum(value);
total | extend d=1 | join (low | extend d=1) on d
| project total_pages = sum_value, low_conf_pages = sum_value1,
    ratio_pct = round(sum_value1 / sum_value * 100, 1)
```

### Dependency Performance (External Services)

```kusto
dependencies
| summarize
    calls = count(),
    avg_ms = round(avg(duration), 1),
    p95_ms = round(percentile(duration, 95), 1),
    failures = countif(success == false)
  by type, target
| extend failure_rate_pct = round(100.0 * failures / calls, 1)
| order by calls desc
```

### End-to-End Pipeline Trace

```kusto
// Find all operations for a specific book/pipeline run
requests
| where operation_Id == "<your-operation-id>"
| union dependencies, traces, exceptions
| where operation_Id == "<your-operation-id>"
| order by timestamp asc
| project timestamp, itemType, name, duration, success, message
```

---

## Alerts

### Recommended Alert Rules

Set up in **App Insights → Monitoring → Alerts → Create alert rule**.

#### 1. High Error Rate

- **Signal type:** Custom log search
- **KQL:**
  ```kusto
  customMetrics
  | where name == "transpose.errors"
  | where timestamp > ago(15m)
  | summarize total_errors = sum(value)
  | where total_errors > 10
  ```
- **Frequency:** Every 5 minutes
- **Action:** Email + Teams notification

#### 2. OCR Low Confidence Spike

- **Signal type:** Custom log search
- **KQL:**
  ```kusto
  let total = customMetrics
  | where name == "transpose.ocr.pages_processed"
  | where timestamp > ago(1h)
  | summarize t = sum(value);
  let low = customMetrics
  | where name == "transpose.ocr.low_confidence_pages"
  | where timestamp > ago(1h)
  | summarize l = sum(value);
  total | extend d=1 | join (low | extend d=1) on d
  | where t > 0 and (l / t) > 0.2
  ```
- **Frequency:** Every 15 minutes
- **Meaning:** More than 20% of pages have low OCR confidence — likely a scan quality issue

#### 3. Token Usage Spike

- **Signal type:** Custom log search
- **KQL:**
  ```kusto
  customMetrics
  | where name == "transpose.openai.tokens_used"
  | where timestamp > ago(1h)
  | summarize total_tokens = sum(value)
  | where total_tokens > 500000
  ```
- **Frequency:** Every 15 minutes
- **Meaning:** Unusually high token consumption — check for infinite retry loops or chunk explosion

#### 4. Stage Duration Regression

- **Signal type:** Custom log search
- **KQL:**
  ```kusto
  customMetrics
  | where name == "transpose.pipeline.stage_duration"
  | where timestamp > ago(15m)
  | summarize avg_duration = avg(value) by tostring(customDimensions.stage)
  | where avg_duration > 300
  ```
- **Frequency:** Every 5 minutes
- **Meaning:** A pipeline stage is averaging over 5 minutes — performance regression or upstream throttling

---

## Troubleshooting

### Pipeline appears stuck (no progress)

1. Check **App Insights → Investigate → Live metrics** — is the app receiving requests?
2. Check container status:
   ```bash
   az containerapp show --resource-group transpose-dev --name transpose-dev-app \
     --query "properties.runningStatus"
   ```
3. Check container logs:
   ```bash
   az containerapp logs show --resource-group transpose-dev --name transpose-dev-app --follow
   ```
4. Look for database lock contention:
   ```kusto
   dependencies
   | where target has "postgres"
   | where duration > 30000
   | order by timestamp desc
   | take 10
   ```

### High latency on translation stage

1. Check OpenAI dependency call durations:
   ```kusto
   dependencies
   | where target has "openai"
   | summarize avg(duration), percentile(duration, 95) by bin(timestamp, 5m)
   | render timechart
   ```
2. Check if Azure OpenAI is throttling (HTTP 429):
   ```kusto
   dependencies
   | where target has "openai"
   | where resultCode == "429"
   | summarize count() by bin(timestamp, 5m)
   ```
3. Review chunk sizes — excessively large chunks increase latency

### Out of memory (OOM) / Container restarts

1. Check container restart count:
   ```bash
   az containerapp revision list --resource-group transpose-dev --name transpose-dev-app \
     --query "[].{name:name, replicas:properties.replicas, active:properties.active}" -o table
   ```
2. Check memory consumption in the workbook **Infrastructure Health** tab
3. Common cause: loading full PDF into memory. The pipeline should stream pages via Document Intelligence.

### OCR producing garbage text

1. Check the **OCR & Quality** tab — is `Low_Confidence_Ratio` above 20%?
2. Examine specific low-confidence pages:
   ```kusto
   customMetrics
   | where name == "transpose.ocr.low_confidence_pages"
   | extend page = tostring(customDimensions.page_number),
            confidence = todouble(customDimensions.confidence)
   | order by confidence asc
   | take 20
   ```
3. Common causes: poor scan quality, handwritten text, ornate fonts, mixed scripts

### Database connection failures

1. Check PostgreSQL dependency health:
   ```kusto
   dependencies
   | where target has "postgres"
   | where success == false
   | summarize count() by resultCode, bin(timestamp, 5m)
   ```
2. Verify firewall rules allow the Container App's outbound IP
3. If using auto-pause, the first connection after idle may timeout — the pipeline's retry logic (tenacity) handles this

---

## Container App Metrics (Azure Monitor)

For infrastructure-level metrics (CPU, memory, network) that aren't in Application Insights, query Azure Monitor directly:

```bash
# Container App CPU usage
az monitor metrics list \
  --resource "/subscriptions/{sub}/resourceGroups/transpose-dev/providers/Microsoft.App/containerApps/transpose-dev-app" \
  --metric "UsageNanoCores" \
  --interval PT5M

# Container App memory usage
az monitor metrics list \
  --resource "/subscriptions/{sub}/resourceGroups/transpose-dev/providers/Microsoft.App/containerApps/transpose-dev-app" \
  --metric "WorkingSetBytes" \
  --interval PT5M
```

Or in the Azure Portal: **Container App → Monitoring → Metrics** → select `UsageNanoCores` or `WorkingSetBytes`.

---

**Owner:** Idaho (Cloud/Infrastructure Developer)
**Last Updated:** 2026
