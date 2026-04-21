"""Application settings — loaded from environment variables."""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Transpose pipeline configuration.

    All values are read from environment variables with the TRANSPOSE_ prefix.
    Example: TRANSPOSE_POSTGRES_HOST=localhost
    """

    model_config = {"env_prefix": "TRANSPOSE_", "env_file": ".env", "env_file_encoding": "utf-8"}

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "transpose"
    postgres_user: str = "transpose"
    postgres_password: str = ""  # Empty when using Managed Identity / Entra auth

    # Azure AI Document Intelligence
    doc_intelligence_endpoint: str = ""

    # Azure OpenAI
    openai_endpoint: str = ""
    openai_deployment: str = "gpt-4o"
    openai_api_version: str = "2024-10-21"

    # Azure Blob Storage
    blob_storage_account_url: str = ""
    blob_container_source: str = "source-pdfs"
    blob_container_output: str = "output"

    # Application Insights
    applicationinsights_connection_string: str = ""

    # Pipeline tuning
    ocr_concurrency: int = 5
    translate_concurrency: int = 5
    chunk_target_tokens: int = 1500
    chunk_overlap_tokens: int = 150
    low_confidence_threshold: float = 0.7

    # Database pool sizing
    # Rationale: translate_concurrency workers each hold a connection, plus
    # overhead for API requests, job tracker, and pipeline bookkeeping.
    # Default max = translate_concurrency + 15 overhead ≈ 20.
    pool_min_size: int = 5
    pool_max_size: int = 20

    # Retry policy
    max_retries: int = 3
    retry_base_delay: float = 1.0

    # API authentication (empty = permissive mode for local dev)
    api_key: str = ""

    def validate_for_pipeline(self) -> list[str]:
        """Validate that required settings are configured for pipeline execution.

        Returns list of validation errors (empty if all OK).
        """
        errors = []

        if not self.openai_endpoint:
            errors.append("TRANSPOSE_OPENAI_ENDPOINT is required")
        if not self.doc_intelligence_endpoint:
            errors.append("TRANSPOSE_DOC_INTELLIGENCE_ENDPOINT is required")
        if not self.blob_storage_account_url:
            errors.append("TRANSPOSE_BLOB_STORAGE_ACCOUNT_URL is required")

        return errors


def get_settings() -> Settings:
    """Load settings from environment."""
    return Settings()


def validate_settings() -> None:
    """Validate settings and log warnings for missing configuration."""
    import logging

    _logger = logging.getLogger(__name__)
    settings = get_settings()
    errors = settings.validate_for_pipeline()
    if errors:
        for err in errors:
            _logger.warning("⚠️  Configuration: %s", err)


def get_appinsights_connection_string() -> str:
    """Return the Application Insights connection string.

    Checks the prefixed ``TRANSPOSE_APPLICATIONINSIGHTS_CONNECTION_STRING``
    env var (via Pydantic settings) first, then falls back to the standard
    ``APPLICATIONINSIGHTS_CONNECTION_STRING`` env var (set by Key Vault in
    the Container App).
    """
    settings = get_settings()
    conn = settings.applicationinsights_connection_string
    if not conn:
        conn = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
    return conn
