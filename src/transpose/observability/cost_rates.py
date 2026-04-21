"""Default Azure service pricing rates for cost estimation.

Rates are per-unit (tokens per 1K, pages, operations) and can be
overridden via Settings for different pricing tiers or regions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostRates:
    """Configurable pricing rates for Azure services.

    All costs in USD. Token rates are per 1K tokens.
    """

    # Azure OpenAI GPT-4o (per 1K tokens)
    openai_input_per_1k: float = 0.005
    openai_output_per_1k: float = 0.015

    # Azure AI Document Intelligence — prebuilt-read (per page)
    doc_intelligence_per_page: float = 0.01

    # Azure Blob Storage — Standard LRS (per 10K operations)
    blob_write_per_10k: float = 0.05
    blob_read_per_10k: float = 0.004

    def estimate_openai_cost(
        self, prompt_tokens: int, completion_tokens: int
    ) -> float:
        """Estimate cost for an OpenAI call."""
        return (
            (prompt_tokens / 1000) * self.openai_input_per_1k
            + (completion_tokens / 1000) * self.openai_output_per_1k
        )

    def estimate_ocr_cost(self, page_count: int) -> float:
        """Estimate cost for Document Intelligence OCR."""
        return page_count * self.doc_intelligence_per_page

    def estimate_blob_cost(
        self, write_ops: int = 0, read_ops: int = 0
    ) -> float:
        """Estimate cost for Blob Storage operations."""
        return (
            (write_ops / 10_000) * self.blob_write_per_10k
            + (read_ops / 10_000) * self.blob_read_per_10k
        )


DEFAULT_RATES = CostRates()
