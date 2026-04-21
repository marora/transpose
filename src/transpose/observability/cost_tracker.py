"""Per-book cost tracking across all Azure services.

Accumulates token usage, OCR pages, and blob operations during a
pipeline run, then persists a cost breakdown to PostgreSQL and emits
OpenTelemetry metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from transpose.observability.cost_rates import DEFAULT_RATES, CostRates

logger = logging.getLogger(__name__)


@dataclass
class ServiceUsage:
    """Accumulated usage for a single Azure service."""

    input_tokens: int = 0
    output_tokens: int = 0
    pages: int = 0
    blob_reads: int = 0
    blob_writes: int = 0


@dataclass
class CostSummary:
    """Final cost breakdown for a book."""

    book_id: UUID
    openai_input_tokens: int
    openai_output_tokens: int
    openai_cost_usd: float
    ocr_pages: int
    ocr_cost_usd: float
    blob_read_ops: int
    blob_write_ops: int
    blob_cost_usd: float
    total_cost_usd: float


class CostTracker:
    """Tracks resource usage per book and computes estimated costs.

    Usage:
        tracker = CostTracker(book_id)
        tracker.record_llm_usage(prompt_tokens=500, completion_tokens=200)
        tracker.record_ocr_pages(18)
        tracker.record_blob_operation("write")
        summary = tracker.summary()
        await tracker.persist(db)
    """

    def __init__(
        self,
        book_id: UUID,
        rates: CostRates | None = None,
    ) -> None:
        self._book_id = book_id
        self._rates = rates or DEFAULT_RATES
        self._usage = ServiceUsage()

    @property
    def book_id(self) -> UUID:
        return self._book_id

    def record_llm_usage(
        self, prompt_tokens: int, completion_tokens: int
    ) -> None:
        """Record token usage from a single LLM call."""
        self._usage.input_tokens += prompt_tokens
        self._usage.output_tokens += completion_tokens

    def record_ocr_pages(self, page_count: int) -> None:
        """Record pages processed by Document Intelligence."""
        self._usage.pages += page_count

    def record_blob_operation(self, op_type: str) -> None:
        """Record a blob storage operation ('read' or 'write')."""
        if op_type == "read":
            self._usage.blob_reads += 1
        elif op_type == "write":
            self._usage.blob_writes += 1

    def summary(self) -> CostSummary:
        """Compute the cost breakdown from accumulated usage."""
        openai_cost = self._rates.estimate_openai_cost(
            self._usage.input_tokens, self._usage.output_tokens
        )
        ocr_cost = self._rates.estimate_ocr_cost(self._usage.pages)
        blob_cost = self._rates.estimate_blob_cost(
            write_ops=self._usage.blob_writes,
            read_ops=self._usage.blob_reads,
        )

        return CostSummary(
            book_id=self._book_id,
            openai_input_tokens=self._usage.input_tokens,
            openai_output_tokens=self._usage.output_tokens,
            openai_cost_usd=openai_cost,
            ocr_pages=self._usage.pages,
            ocr_cost_usd=ocr_cost,
            blob_read_ops=self._usage.blob_reads,
            blob_write_ops=self._usage.blob_writes,
            blob_cost_usd=blob_cost,
            total_cost_usd=openai_cost + ocr_cost + blob_cost,
        )

    async def persist(self, db) -> None:
        """Write cost rows to the book_costs table and emit OTel metrics."""
        summary = self.summary()

        rows: list[tuple[str, str, int, float]] = []

        if summary.openai_input_tokens > 0:
            rows.append((
                "openai", "input_tokens",
                summary.openai_input_tokens,
                (summary.openai_input_tokens / 1000) * self._rates.openai_input_per_1k,
            ))
        if summary.openai_output_tokens > 0:
            rows.append((
                "openai", "output_tokens",
                summary.openai_output_tokens,
                (summary.openai_output_tokens / 1000) * self._rates.openai_output_per_1k,
            ))
        if summary.ocr_pages > 0:
            rows.append((
                "doc_intelligence", "pages",
                summary.ocr_pages,
                summary.ocr_cost_usd,
            ))
        if summary.blob_write_ops > 0:
            rows.append((
                "blob_storage", "write_operations",
                summary.blob_write_ops,
                (summary.blob_write_ops / 10_000) * self._rates.blob_write_per_10k,
            ))
        if summary.blob_read_ops > 0:
            rows.append((
                "blob_storage", "read_operations",
                summary.blob_read_ops,
                (summary.blob_read_ops / 10_000) * self._rates.blob_read_per_10k,
            ))

        if rows:
            await db.save_book_costs(self._book_id, rows)

        # Emit OTel metrics
        self._emit_metrics(summary)

        logger.info(
            "💰 Cost summary for book_id=%s: "
            "OpenAI=$%.4f (%d in / %d out tokens) | "
            "OCR=$%.4f (%d pages) | "
            "Blob=$%.6f (%d read / %d write ops) | "
            "Total=$%.4f",
            self._book_id,
            summary.openai_cost_usd,
            summary.openai_input_tokens,
            summary.openai_output_tokens,
            summary.ocr_cost_usd,
            summary.ocr_pages,
            summary.blob_cost_usd,
            summary.blob_read_ops,
            summary.blob_write_ops,
            summary.total_cost_usd,
        )

    def _emit_metrics(self, summary: CostSummary) -> None:
        """Emit cost data as OpenTelemetry metrics."""
        from transpose.observability.metrics import (
            estimated_cost,
            pages_processed,
            tokens_used,
        )

        attrs = {"book_id": str(self._book_id)}

        tokens_used.add(
            summary.openai_input_tokens + summary.openai_output_tokens,
            {**attrs, "type": "total"},
        )
        tokens_used.add(
            summary.openai_input_tokens,
            {**attrs, "type": "input"},
        )
        tokens_used.add(
            summary.openai_output_tokens,
            {**attrs, "type": "output"},
        )

        estimated_cost.add(summary.total_cost_usd, attrs)

        if summary.ocr_pages > 0:
            pages_processed.add(summary.ocr_pages, attrs)
