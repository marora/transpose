"""Custom metrics definitions for the Transpose pipeline."""

from __future__ import annotations

from opentelemetry import metrics

meter = metrics.get_meter("transpose")

# Pipeline stage duration
stage_duration = meter.create_histogram(
    name="transpose.pipeline.stage_duration",
    description="Duration of each pipeline stage in seconds",
    unit="s",
)

# Translation counters
chunks_translated = meter.create_counter(
    name="transpose.pipeline.chunks_translated",
    description="Number of chunks translated",
)

tokens_used = meter.create_counter(
    name="transpose.openai.tokens_used",
    description="Total tokens consumed (prompt + completion)",
)

# OCR counters
pages_processed = meter.create_counter(
    name="transpose.ocr.pages_processed",
    description="Number of pages processed by OCR",
)

low_confidence_pages = meter.create_counter(
    name="transpose.ocr.low_confidence_pages",
    description="Number of pages with confidence below threshold",
)

# Error counter
pipeline_errors = meter.create_counter(
    name="transpose.errors",
    description="Pipeline errors by stage and type",
)

# Content filter tracking
content_filter_blocks = meter.create_counter(
    name="transpose.translation.content_filter_blocks",
    description="Chunks blocked by Azure content filter",
)

content_filter_fallback_success = meter.create_counter(
    name="transpose.translation.content_filter_fallback_success",
    description="Content filter blocks recovered via academic reframing",
)

translation_errors = meter.create_counter(
    name="transpose.translation.errors",
    description="Translation errors by type",
)
