"""Tests for transpose.services.blob_client — Azure Blob Storage wrapper.

All Azure SDK calls are mocked. Tests verify:
- Lazy client initialization
- upload_pdf content type and overwrite behavior
- download_blob returns bytes
- upload_output detects content type from extension
- close() releases resources
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from transpose.services.blob_client import BlobClient


@pytest.fixture
def blob_client() -> BlobClient:
    return BlobClient(account_url="https://teststorage.blob.core.windows.net")


@pytest.fixture
def mock_blob_service():
    """Mock BlobServiceClient with chained get_blob_client."""
    service = AsyncMock()
    inner_blob = AsyncMock()
    inner_blob.url = "https://teststorage.blob.core.windows.net/container/test.pdf"
    inner_blob.upload_blob = AsyncMock()

    download_stream = AsyncMock()
    download_stream.readall = AsyncMock(return_value=b"pdf-bytes")
    inner_blob.download_blob = AsyncMock(return_value=download_stream)

    service.get_blob_client = MagicMock(return_value=inner_blob)
    service.close = AsyncMock()
    return service, inner_blob


# ---------------------------------------------------------------------------
# Lazy initialization
# ---------------------------------------------------------------------------


class TestBlobClientInit:
    def test_client_starts_none(self, blob_client: BlobClient) -> None:
        assert blob_client._client is None

    @pytest.mark.asyncio
    async def test_lazy_init_creates_client(self, blob_client: BlobClient) -> None:
        """_get_client() initializes SDK client on first call."""
        with (
            patch("azure.identity.aio.DefaultAzureCredential"),
            patch("azure.storage.blob.aio.BlobServiceClient") as mock_bsc,
        ):
            mock_bsc.return_value = AsyncMock()
            client = await blob_client._get_client()
            assert client is not None
            assert blob_client._client is not None

    @pytest.mark.asyncio
    async def test_lazy_init_reuses_client(self, blob_client: BlobClient) -> None:
        """Second call reuses the same client."""
        with (
            patch("azure.identity.aio.DefaultAzureCredential"),
            patch("azure.storage.blob.aio.BlobServiceClient") as mock_bsc,
        ):
            mock_bsc.return_value = AsyncMock()
            client1 = await blob_client._get_client()
            client2 = await blob_client._get_client()
            assert client1 is client2
            assert mock_bsc.call_count == 1


# ---------------------------------------------------------------------------
# upload_pdf
# ---------------------------------------------------------------------------


class TestUploadPdf:
    @pytest.mark.asyncio
    async def test_upload_returns_url(
        self, blob_client: BlobClient, mock_blob_service
    ) -> None:
        service, inner = mock_blob_service
        blob_client._client = service

        url = await blob_client.upload_pdf("source-pdfs", "test.pdf", b"data")
        assert "test.pdf" in url or url == inner.url

    @pytest.mark.asyncio
    async def test_upload_calls_with_overwrite(
        self, blob_client: BlobClient, mock_blob_service
    ) -> None:
        service, inner = mock_blob_service
        blob_client._client = service

        await blob_client.upload_pdf("source-pdfs", "test.pdf", b"data")
        inner.upload_blob.assert_called_once()
        call_kwargs = inner.upload_blob.call_args
        assert call_kwargs[1]["overwrite"] is True
        assert call_kwargs[1]["content_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_upload_pdf_container_and_blob_name(
        self, blob_client: BlobClient, mock_blob_service
    ) -> None:
        service, _ = mock_blob_service
        blob_client._client = service

        await blob_client.upload_pdf("my-container", "path/to/book.pdf", b"x")
        service.get_blob_client.assert_called_with(
            container="my-container", blob="path/to/book.pdf"
        )


# ---------------------------------------------------------------------------
# download_blob
# ---------------------------------------------------------------------------


class TestDownloadBlob:
    @pytest.mark.asyncio
    async def test_download_returns_bytes(
        self, blob_client: BlobClient, mock_blob_service
    ) -> None:
        service, _ = mock_blob_service
        blob_client._client = service

        result = await blob_client.download_blob("source-pdfs", "test.pdf")
        assert result == b"pdf-bytes"

    @pytest.mark.asyncio
    async def test_download_uses_correct_container(
        self, blob_client: BlobClient, mock_blob_service
    ) -> None:
        service, _ = mock_blob_service
        blob_client._client = service

        await blob_client.download_blob("my-container", "file.pdf")
        service.get_blob_client.assert_called_with(
            container="my-container", blob="file.pdf"
        )


# ---------------------------------------------------------------------------
# upload_output — content type detection
# ---------------------------------------------------------------------------


class TestUploadOutput:
    @pytest.mark.asyncio
    async def test_epub_content_type(
        self, blob_client: BlobClient, mock_blob_service
    ) -> None:
        service, inner = mock_blob_service
        blob_client._client = service

        await blob_client.upload_output("output", "book.epub", b"epub-data")
        call_kwargs = inner.upload_blob.call_args
        assert call_kwargs[1]["content_type"] == "application/epub+zip"

    @pytest.mark.asyncio
    async def test_pdf_content_type(
        self, blob_client: BlobClient, mock_blob_service
    ) -> None:
        service, inner = mock_blob_service
        blob_client._client = service

        await blob_client.upload_output("output", "book.pdf", b"pdf-data")
        call_kwargs = inner.upload_blob.call_args
        assert call_kwargs[1]["content_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_unknown_extension_content_type(
        self, blob_client: BlobClient, mock_blob_service
    ) -> None:
        service, inner = mock_blob_service
        blob_client._client = service

        await blob_client.upload_output("output", "book.xyz", b"data")
        call_kwargs = inner.upload_blob.call_args
        assert call_kwargs[1]["content_type"] == "application/octet-stream"

    @pytest.mark.asyncio
    async def test_upload_output_returns_url(
        self, blob_client: BlobClient, mock_blob_service
    ) -> None:
        service, inner = mock_blob_service
        blob_client._client = service

        url = await blob_client.upload_output("output", "book.epub", b"data")
        assert url == inner.url


# ---------------------------------------------------------------------------
# local fallback + readiness helpers
# ---------------------------------------------------------------------------


class TestBlobClientFallback:
    @pytest.mark.asyncio
    async def test_upload_falls_back_to_repo_local_storage_on_auth_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        local_root = Path("output/test-blob-fallback").resolve()
        if local_root.exists():
            for child in sorted(local_root.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            local_root.rmdir()
        monkeypatch.setenv("TRANSPOSE_LOCAL_BLOB_ROOT", str(local_root))

        client = BlobClient(
            account_url="https://teststorage.blob.core.windows.net",
            allow_local_fallback=True,
        )
        failing_blob = AsyncMock()
        failing_blob.upload_blob = AsyncMock(side_effect=RuntimeError("AuthorizationFailure"))
        service = AsyncMock()
        service.get_blob_client = MagicMock(return_value=failing_blob)
        client._client = service

        try:
            uri = await client.upload_pdf("source-pdfs", "test.pdf", b"pdf-data")
            assert client.uses_local_storage is True
            assert uri == (local_root / "source-pdfs" / "test.pdf").as_uri()
            assert (local_root / "source-pdfs" / "test.pdf").read_bytes() == b"pdf-data"
        finally:
            if local_root.exists():
                for child in sorted(local_root.rglob("*"), reverse=True):
                    if child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                local_root.rmdir()

    @pytest.mark.asyncio
    async def test_list_containers_reads_repo_local_directories(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        local_root = Path("output/test-blob-list").resolve()
        if local_root.exists():
            for child in sorted(local_root.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            local_root.rmdir()
        (local_root / "source-pdfs").mkdir(parents=True)
        (local_root / "output").mkdir(parents=True)
        monkeypatch.setenv("TRANSPOSE_LOCAL_BLOB_ROOT", str(local_root))

        client = BlobClient(account_url="", allow_local_fallback=True)

        try:
            assert await client.list_containers() == ["output", "source-pdfs"]
        finally:
            for child in sorted(local_root.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            local_root.rmdir()


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestBlobClientClose:
    @pytest.mark.asyncio
    async def test_close_when_initialized(
        self, blob_client: BlobClient, mock_blob_service
    ) -> None:
        service, _ = mock_blob_service
        blob_client._client = service

        await blob_client.close()
        service.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_when_not_initialized(self, blob_client: BlobClient) -> None:
        """close() is safe to call before init."""
        await blob_client.close()  # should not raise
