"""Azure Blob Storage client wrapper with optional repo-local fallback."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from transpose.services.azure_rbac_retry import (
    is_rbac_propagation_error,
    with_rbac_retry,
)

logger = logging.getLogger(__name__)


class BlobClient:
    """Wrap Azure Blob Storage with optional repo-local fallback.

    Pipeline stages call this interface — never the Azure SDK directly.
    Local fallback remains available for explicit dev/test flows, but publish
    paths can disable it so Azure errors fail loudly.
    """

    def __init__(
        self,
        account_url: str,
        *,
        allow_local_fallback: bool = True,
        on_rbac_retry: Callable[[str], None] | None = None,
    ) -> None:
        self._account_url = account_url.rstrip("/")
        self._client = None
        self._credential = None
        self._allow_local_fallback = allow_local_fallback
        self._on_rbac_retry = on_rbac_retry
        self._local_mode = not bool(self._account_url) and self._allow_local_fallback
        self._local_root = Path(
            os.environ.get("TRANSPOSE_LOCAL_BLOB_ROOT", "output/blob")
        ).resolve()

    @property
    def uses_local_storage(self) -> bool:
        return self._local_mode

    def _local_path(self, container: str, blob_name: str) -> Path:
        return self._local_root / container / Path(blob_name)

    def blob_uri(self, container: str, blob_name: str) -> str:
        if self._local_mode:
            return self._local_path(container, blob_name).resolve().as_uri()
        if not self._account_url:
            raise RuntimeError("Azure Blob storage account URL is not configured")
        return f"{self._account_url}/{quote(container)}/{quote(blob_name, safe='/')}"

    def _enable_local_mode(self, reason: str) -> None:
        if not self._local_mode:
            logger.warning(
                "Azure Blob unavailable (%s). Falling back to local artifact storage at %s",
                reason,
                self._local_root,
            )
        self._local_mode = True

    def _emit_rbac_retry(self, message: str) -> None:
        if self._on_rbac_retry is not None:
            self._on_rbac_retry(message)
            return
        logger.warning(message)

    def _should_fallback(self, exc: Exception) -> bool:
        if not self._allow_local_fallback:
            return False

        if is_rbac_propagation_error(exc):
            return True

        msg = str(exc)
        return any(token in msg for token in [
            "AuthorizationFailure",
            "AuthenticationFailed",
            "CredentialUnavailableError",
            "ManagedIdentity",
            "DefaultAzureCredential",
            "This request is not authorized",
        ])

    async def _get_client(self):
        """Lazy-initialize the Blob Service client with Managed Identity."""
        if self._local_mode:
            raise RuntimeError("Blob client is using local fallback storage")
        if not self._account_url:
            raise RuntimeError("Azure Blob storage account URL is not configured")
        if self._client is None:
            from azure.identity.aio import DefaultAzureCredential
            from azure.storage.blob.aio import BlobServiceClient

            self._credential = DefaultAzureCredential()
            self._client = BlobServiceClient(
                account_url=self._account_url, credential=self._credential
            )
        return self._client

    async def upload_bytes(
        self,
        container: str,
        blob_name: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload arbitrary bytes to blob or local fallback storage."""
        if self._local_mode:
            local_path = self._local_path(container, blob_name)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(data)
            return local_path.resolve().as_uri()

        async def _upload() -> str:
            client = await self._get_client()
            blob_client = client.get_blob_client(container=container, blob=blob_name)
            await blob_client.upload_blob(data, overwrite=True, content_type=content_type)
            return blob_client.url

        try:
            return await with_rbac_retry(_upload, on_retry=self._emit_rbac_retry)
        except Exception as exc:
            if not self._should_fallback(exc):
                raise
            self._enable_local_mode(type(exc).__name__)
            return await self.upload_bytes(
                container,
                blob_name,
                data,
                content_type=content_type,
            )

    async def upload_pdf(self, container: str, blob_name: str, data: bytes) -> str:
        """Upload a PDF to blob storage. Returns the blob URI."""
        return await self.upload_bytes(
            container,
            blob_name,
            data,
            content_type="application/pdf",
        )

    async def download_blob(self, container: str, blob_name: str) -> bytes:
        """Download a blob's content from Azure or the local fallback store."""
        if self._local_mode:
            return self._local_path(container, blob_name).read_bytes()

        async def _download() -> bytes:
            client = await self._get_client()
            blob_client = client.get_blob_client(container=container, blob=blob_name)
            stream = await blob_client.download_blob()
            return await stream.readall()

        try:
            return await with_rbac_retry(_download, on_retry=self._emit_rbac_retry)
        except Exception as exc:
            if not self._should_fallback(exc):
                raise
            self._enable_local_mode(type(exc).__name__)
            return await self.download_blob(container, blob_name)

    async def upload_output(self, container: str, blob_name: str, data: bytes) -> str:
        """Upload an output file (ePub/PDF/image). Returns the blob URI."""
        content_type = "application/octet-stream"
        if blob_name.endswith(".epub"):
            content_type = "application/epub+zip"
        elif blob_name.endswith(".pdf"):
            content_type = "application/pdf"
        elif blob_name.endswith(".png"):
            content_type = "image/png"
        elif blob_name.endswith(".html"):
            content_type = "text/html; charset=utf-8"
        elif blob_name.endswith(".json"):
            content_type = "application/json; charset=utf-8"

        return await self.upload_bytes(
            container,
            blob_name,
            data,
            content_type=content_type,
        )

    async def list_containers(self) -> list[str]:
        """Return a lightweight container listing for readiness checks."""
        if self._local_mode:
            if not self._local_root.exists():
                return []
            return sorted(p.name for p in self._local_root.iterdir() if p.is_dir())

        async def _list_containers() -> list[str]:
            client = await self._get_client()
            return [
                getattr(item, "name", item["name"])
                async for item in client.list_containers(results_per_page=20)
            ]

        try:
            return await with_rbac_retry(_list_containers, on_retry=self._emit_rbac_retry)
        except Exception as exc:
            if not self._should_fallback(exc):
                raise
            self._enable_local_mode(type(exc).__name__)
            return await self.list_containers()

    async def close(self) -> None:
        """Release SDK resources."""
        if self._client is not None:
            await self._client.close()
        if self._credential is not None:
            await self._credential.close()
