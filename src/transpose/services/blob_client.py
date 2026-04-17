"""Azure Blob Storage client wrapper."""

from __future__ import annotations


class BlobClient:
    """Wraps Azure Blob Storage for source PDF and output file management.

    Pipeline stages call this interface — never the Azure SDK directly.
    """

    def __init__(self, account_url: str) -> None:
        self._account_url = account_url
        self._client = None

    async def _get_client(self):
        """Lazy-initialize the Blob Service client with Managed Identity."""
        if self._client is None:
            from azure.identity.aio import DefaultAzureCredential
            from azure.storage.blob.aio import BlobServiceClient

            credential = DefaultAzureCredential()
            self._client = BlobServiceClient(
                account_url=self._account_url, credential=credential
            )
        return self._client

    async def upload_pdf(self, container: str, blob_name: str, data: bytes) -> str:
        """Upload a PDF to blob storage. Returns the blob URI."""
        client = await self._get_client()
        blob_client = client.get_blob_client(container=container, blob=blob_name)

        # Upload with overwrite
        await blob_client.upload_blob(data, overwrite=True, content_type="application/pdf")

        # Return the full blob URI
        return blob_client.url

    async def download_blob(self, container: str, blob_name: str) -> bytes:
        """Download a blob's content."""
        client = await self._get_client()
        blob_client = client.get_blob_client(container=container, blob=blob_name)

        # Download blob content
        stream = await blob_client.download_blob()
        return await stream.readall()

    async def upload_output(self, container: str, blob_name: str, data: bytes) -> str:
        """Upload an output file (ePub/PDF) to blob storage. Returns the blob URI."""
        client = await self._get_client()
        blob_client = client.get_blob_client(container=container, blob=blob_name)

        # Detect content type from extension
        content_type = "application/octet-stream"
        if blob_name.endswith(".epub"):
            content_type = "application/epub+zip"
        elif blob_name.endswith(".pdf"):
            content_type = "application/pdf"

        # Upload with overwrite
        await blob_client.upload_blob(data, overwrite=True, content_type=content_type)

        # Return the full blob URI
        return blob_client.url

    async def close(self) -> None:
        """Release SDK resources."""
        if self._client is not None:
            await self._client.close()
