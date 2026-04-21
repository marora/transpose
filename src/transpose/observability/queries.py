"""Reusable KQL query templates for Transpose pipeline observability.

Use from CLI scripts, notebooks, or any tool that can execute KQL against
Log Analytics / Application Insights.

Each function returns a KQL string. Pass an optional ``book_id`` to scope
queries to a single pipeline run, or leave it ``None`` to query all runs.

Example (Azure Monitor Query SDK)::

    from azure.monitor.query import LogsQueryClient
    from transpose.observability.queries import stage_duration_breakdown

    client = LogsQueryClient(credential)
    result = client.query_workspace(workspace_id, stage_duration_breakdown(), timespan="PT1H")
"""

from __future__ import annotations


def _book_filter(book_id: str | None) -> str:
    """Return a KQL ``where`` clause that filters by book_id, if provided."""
    if book_id:
        return f"| where tostring(customDimensions.book_id) == '{book_id}'"
    return ""


# ---------------------------------------------------------------------------
# Pipeline stage queries
# ---------------------------------------------------------------------------


def stage_duration_breakdown(book_id: str | None = None) -> str:
    """Per-stage avg / P50 / P95 / max duration."""
    return f"""\
customMetrics
| where name == 'transpose.pipeline.stage_duration'
{_book_filter(book_id)}
| extend stage = tostring(customDimensions.stage)
| where stage != 'total'
| summarize
    avg_s   = round(avg(value), 1),
    p50_s   = round(percentile(value, 50), 1),
    p95_s   = round(percentile(value, 95), 1),
    max_s   = round(max(value), 1),
    runs    = count()
  by stage
| extend stage_order = case(
    stage == 'ingest', 1, stage == 'ocr', 2, stage == 'chunk', 3,
    stage == 'translate', 4, stage == 'glossary', 5,
    stage == 'assemble', 6, stage == 'export', 7, 99)
| order by stage_order asc
| project stage, avg_s, p50_s, p95_s, max_s, runs"""


def stage_timeline(book_id: str | None = None) -> str:
    """Gantt-style stage start/end times for each pipeline run."""
    return f"""\
customMetrics
| where name == 'transpose.pipeline.stage_duration'
{_book_filter(book_id)}
| extend stage = tostring(customDimensions.stage),
         book_id = tostring(customDimensions.book_id)
| where stage != 'total'
| summarize stage_end = max(timestamp), duration_s = avg(value) by book_id, stage
| extend stage_start = datetime_add('second', -toint(duration_s), stage_end)
| project book_id, stage, stage_start, stage_end, duration_s = round(duration_s, 1)
| order by book_id asc, stage_start asc"""


def pipeline_total_duration(book_id: str | None = None) -> str:
    """End-to-end pipeline duration summary."""
    return f"""\
customMetrics
| where name == 'transpose.pipeline.stage_duration'
{_book_filter(book_id)}
| extend stage = tostring(customDimensions.stage)
| where stage == 'total'
| summarize
    avg_s = round(avg(value), 1),
    min_s = round(min(value), 1),
    max_s = round(max(value), 1),
    runs  = count()"""


# ---------------------------------------------------------------------------
# Translation progress
# ---------------------------------------------------------------------------


def translation_progress(book_id: str | None = None) -> str:
    """Chunks translated, failed, tokens used, and estimated cost."""
    return f"""\
let translated = customMetrics
| where name == 'transpose.pipeline.chunks_translated'
{_book_filter(book_id)}
| summarize Translated = sum(value);
let failed = customMetrics
| where name == 'transpose.translation.errors'
{_book_filter(book_id)}
| summarize Failed = sum(value);
let tokens = customMetrics
| where name == 'transpose.openai.tokens_used'
{_book_filter(book_id)}
| summarize Tokens = sum(value);
let cost = customMetrics
| where name == 'transpose.translation.estimated_cost_usd'
{_book_filter(book_id)}
| summarize Cost_USD = round(sum(value), 2);
translated | extend d=1
| join (failed | extend d=1) on d
| join (tokens | extend d=1) on d
| join (cost | extend d=1) on d
| project Translated, Failed, Tokens, Cost_USD"""


def translation_throughput(book_id: str | None = None, bin_minutes: int = 5) -> str:
    """Chunks translated per time bucket."""
    return f"""\
customMetrics
| where name == 'transpose.pipeline.chunks_translated'
{_book_filter(book_id)}
| summarize chunks = sum(value) by bin(timestamp, {bin_minutes}m)
| order by timestamp asc"""


# ---------------------------------------------------------------------------
# Error queries
# ---------------------------------------------------------------------------


def error_rate_by_stage(book_id: str | None = None) -> str:
    """Error count grouped by pipeline stage and error type."""
    return f"""\
customMetrics
| where name == 'transpose.errors'
{_book_filter(book_id)}
| extend stage      = tostring(customDimensions.stage),
         error_type = tostring(customDimensions.error_type)
| summarize error_count = sum(value) by stage, error_type
| order by error_count desc"""


def error_timeline(book_id: str | None = None, bin_minutes: int = 5) -> str:
    """Error count over time, grouped by stage."""
    return f"""\
customMetrics
| where name == 'transpose.errors'
{_book_filter(book_id)}
| extend stage = tostring(customDimensions.stage)
| summarize errors = sum(value) by stage, bin(timestamp, {bin_minutes}m)
| order by timestamp asc"""


# ---------------------------------------------------------------------------
# Content filter
# ---------------------------------------------------------------------------


def content_filter_summary(book_id: str | None = None) -> str:
    """Content filter blocks vs. successful fallback recoveries."""
    return f"""\
let blocks = customMetrics
| where name == 'transpose.translation.content_filter_blocks'
{_book_filter(book_id)}
| summarize Blocked = sum(value);
let recovered = customMetrics
| where name == 'transpose.translation.content_filter_fallback_success'
{_book_filter(book_id)}
| summarize Recovered = sum(value);
blocks | extend d=1
| join (recovered | extend d=1) on d
| project Blocked, Recovered,
    Unrecoverable = Blocked - Recovered,
    Recovery_Rate_Pct = iff(Blocked > 0, round(Recovered / Blocked * 100, 1), 0.0)"""


def content_filter_timeline(book_id: str | None = None, bin_minutes: int = 10) -> str:
    """Content filter block and recovery events over time."""
    return f"""\
customMetrics
| where name in (
    'transpose.translation.content_filter_blocks',
    'transpose.translation.content_filter_fallback_success')
{_book_filter(book_id)}
| extend metric = case(
    name == 'transpose.translation.content_filter_blocks', 'Blocked',
    name == 'transpose.translation.content_filter_fallback_success', 'Recovered',
    name)
| summarize count = sum(value) by metric, bin(timestamp, {bin_minutes}m)
| order by timestamp asc"""


# ---------------------------------------------------------------------------
# OCR quality
# ---------------------------------------------------------------------------


def ocr_quality(book_id: str | None = None) -> str:
    """Pages processed, low-confidence count, and quality percentage."""
    return f"""\
let total = customMetrics
| where name == 'transpose.ocr.pages_processed'
{_book_filter(book_id)}
| summarize pages = sum(value);
let low = customMetrics
| where name == 'transpose.ocr.low_confidence_pages'
{_book_filter(book_id)}
| summarize low_conf = sum(value);
total | extend d=1
| join (low | extend d=1) on d
| project pages, low_conf,
    quality_pct = iff(pages > 0, round((pages - low_conf) * 100.0 / pages, 1), 0.0)"""


# ---------------------------------------------------------------------------
# Dependency / infrastructure
# ---------------------------------------------------------------------------


def dependency_health() -> str:
    """Azure service dependency call stats and failure rates."""
    return """\
dependencies
| summarize
    calls      = count(),
    avg_ms     = round(avg(duration), 1),
    p95_ms     = round(percentile(duration, 95), 1),
    failures   = countif(success == false)
  by type, target
| extend failure_rate_pct = round(100.0 * failures / calls, 1)
| order by calls desc"""


def openai_throttling(bin_minutes: int = 5) -> str:
    """Azure OpenAI HTTP 429 (rate-limit) events over time."""
    return f"""\
dependencies
| where target has 'openai'
| where resultCode == '429'
| summarize throttle_count = count() by bin(timestamp, {bin_minutes}m)
| order by timestamp asc"""


# ---------------------------------------------------------------------------
# End-to-end trace
# ---------------------------------------------------------------------------


def pipeline_trace(operation_id: str) -> str:
    """Full distributed trace for a single pipeline execution."""
    return f"""\
requests
| where operation_Id == '{operation_id}'
| union dependencies, traces, exceptions
| where operation_Id == '{operation_id}'
| order by timestamp asc
| project timestamp, itemType, name, duration, success, message"""
