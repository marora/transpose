"""Service context — holds all initialized service clients for the pipeline."""

from __future__ import annotations

from transpose.config.settings import Settings, get_settings
from transpose.services.blob_client import BlobClient
from transpose.services.cache import PipelineState
from transpose.services.database import Database
from transpose.services.llm_client import LlmClient
from transpose.services.ocr_client import OcrClient


class ServiceContext:
    """Container for all service clients used by pipeline stages.

    Initializes and holds references to:
    - Database (PostgreSQL)
    - PipelineState (PostgreSQL-backed state tracking)
    - BlobClient (Azure Blob Storage)
    - OcrClient (Azure AI Document Intelligence)
    - LlmClient (Azure OpenAI)

    All services are initialized lazily on first use.
    Call connect() to initialize connections, close() to clean up.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

        # Initialize service clients
        self.db = Database(
            self._build_dsn(),
            pool_min_size=self.settings.pool_min_size,
            pool_max_size=self.settings.pool_max_size,
        )
        self.state = PipelineState(self.db)
        self.blob = BlobClient(self.settings.blob_storage_account_url)
        self.ocr = OcrClient(
            self.settings.doc_intelligence_endpoint,
            low_confidence_threshold=self.settings.low_confidence_threshold,
            ocr_concurrency=self.settings.ocr_concurrency,
        )
        self.llm = LlmClient(
            endpoint=self.settings.openai_endpoint,
            deployment=self.settings.openai_deployment,
            api_version=self.settings.openai_api_version,
            max_retries=self.settings.max_retries,
            retry_base_delay=self.settings.retry_base_delay,
        )

    def _build_dsn(self) -> str:
        """Build PostgreSQL connection string."""
        if self.settings.postgres_password:
            return (
                f"postgresql://{self.settings.postgres_user}:"
                f"{self.settings.postgres_password}@"
                f"{self.settings.postgres_host}:{self.settings.postgres_port}/"
                f"{self.settings.postgres_db}"
            )
        return (
            f"postgresql://{self.settings.postgres_user}@"
            f"{self.settings.postgres_host}:{self.settings.postgres_port}/"
            f"{self.settings.postgres_db}"
        )

    @property
    def _requires_ssl(self) -> bool:
        """Azure PostgreSQL always requires SSL."""
        return self.settings.postgres_host.endswith(".database.azure.com")

    async def connect(self) -> None:
        """Initialize all service connections."""
        ssl_mode = "require" if self._requires_ssl else None
        await self.db.connect(ssl=ssl_mode)
        # Ensure required tables exist
        await self.state.ensure_lock_table()

    async def close(self) -> None:
        """Close all service connections."""
        await self.db.close()
        await self.blob.close()
        await self.ocr.close()
        await self.llm.close()
