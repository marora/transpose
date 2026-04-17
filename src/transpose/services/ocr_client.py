"""Azure AI Document Intelligence client wrapper."""

from __future__ import annotations

from uuid import UUID

from transpose.models.book import Page


class OcrClient:
    """Wraps Azure AI Document Intelligence for text extraction.

    All Azure SDK interactions are isolated here. Pipeline stages
    call this interface — never the SDK directly.
    """

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint
        # Initialized lazily on first use
        self._client = None

    async def _get_client(self):
        """Lazy-initialize the Document Intelligence client with Managed Identity."""
        if self._client is None:
            from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
            from azure.identity.aio import DefaultAzureCredential

            credential = DefaultAzureCredential()
            self._client = DocumentIntelligenceClient(
                endpoint=self._endpoint, credential=credential
            )
        return self._client

    async def extract_pages(self, blob_uri: str, book_id: UUID) -> list[Page]:
        """Extract text from all pages of a PDF using the prebuilt-read model.

        Args:
            blob_uri: Azure Blob Storage URI of the source PDF.
            book_id: ID of the book being processed.

        Returns:
            List of Page objects with extracted text and confidence scores.
        """
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

        client = await self._get_client()

        # Start the analysis job with prebuilt-read model
        poller = await client.begin_analyze_document(
            model_id="prebuilt-read",
            analyze_request=AnalyzeDocumentRequest(url_source=blob_uri),
        )

        # Wait for completion
        result = await poller.result()

        # Parse pages from the result
        pages: list[Page] = []

        if result.pages:
            for page_num, page in enumerate(result.pages, start=1):
                # Extract text from the page
                # The prebuilt-read model gives us lines
                page_text = ""
                page_confidence_sum = 0.0
                line_count = 0

                if page.lines:
                    for line in page.lines:
                        page_text += line.content + "\n"
                        # Aggregate confidence from words if available
                        if page.words:
                            for word in page.words:
                                if (
                                    word.span.offset >= line.span.offset
                                    and word.span.offset
                                    < (line.span.offset + line.span.length)
                                    and word.confidence is not None
                                ):
                                    page_confidence_sum += word.confidence
                                    line_count += 1

                # Calculate average confidence
                avg_confidence = (
                    page_confidence_sum / line_count if line_count > 0 else 1.0
                )

                # Build OCR metadata
                ocr_metadata = {
                    "page_width": page.width if hasattr(page, "width") else 0,
                    "page_height": page.height if hasattr(page, "height") else 0,
                    "unit": page.unit if hasattr(page, "unit") else "pixel",
                    "line_count": len(page.lines) if page.lines else 0,
                    "word_count": len(page.words) if page.words else 0,
                }

                pages.append(
                    Page(
                        book_id=book_id,
                        page_number=page_num,
                        raw_text=page_text.strip(),
                        confidence=avg_confidence,
                        needs_review=avg_confidence < 0.7,
                        ocr_metadata=ocr_metadata,
                    )
                )

        return pages

    async def close(self) -> None:
        """Release SDK resources."""
        if self._client is not None:
            await self._client.close()
