"""Application settings — loaded from environment variables."""

import os

from pydantic import AliasChoices, Field
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
    openai_timeout_seconds: float = 120.0

    # Anthropic API (for Oracle Layer C quality judge)
    # Pulled from Key Vault in production; .env file in local dev
    anthropic_api_key: str = ""

    # Azure Blob Storage
    blob_storage_account_url: str = ""
    blob_container_source: str = "source-pdfs"
    blob_container_output: str = "output"
    blob_workspace_container: str = "book-workspaces"

    # Azure Static Website — base URL for per-book landing pages.
    # Example: https://transposebooks.z6.web.core.windows.net
    # Set TRANSPOSE_BLOB_STATIC_WEBSITE_URL after running Tank's T-1 setup.
    blob_static_website_url: str = ""

    # Published site URL — Azure Static Web App for consumer-facing content.
    # This is policy-immune (not subject to storage account publicNetworkAccess).
    # Example: https://mango-forest-0563d4203.7.azurestaticapps.net
    # Falls back to blob_static_website_url if not set.
    published_site_url: str = ""

    # Workspace settings
    # Translator note prepended to all landing pages when not specified per-book.
    # Set TRANSPOSE_WORKSPACE_TRANSLATOR_NOTE in environment or .env.
    workspace_translator_note: str = ""

    # Application Insights
    applicationinsights_connection_string: str = ""

    # Entra ID admin dashboard auth
    entra_tenant_id: str = Field(
        default="",
        validation_alias=AliasChoices("TRANSPOSE_ENTRA_TENANT_ID", "ENTRA_TENANT_ID"),
    )
    entra_admin_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("TRANSPOSE_ENTRA_ADMIN_CLIENT_ID", "ENTRA_ADMIN_CLIENT_ID"),
    )
    entra_admin_audience: str = Field(
        default="",
        validation_alias=AliasChoices("TRANSPOSE_ENTRA_ADMIN_AUDIENCE", "ENTRA_ADMIN_AUDIENCE"),
    )
    entra_issuer: str = Field(
        default="",
        validation_alias=AliasChoices("TRANSPOSE_ENTRA_ISSUER", "ENTRA_ISSUER"),
    )
    entra_jwks_uri: str = Field(
        default="",
        validation_alias=AliasChoices("TRANSPOSE_ENTRA_JWKS_URI", "ENTRA_JWKS_URI"),
    )
    entra_jwks_cache_ttl_seconds: int = Field(
        default=300,
        validation_alias=AliasChoices(
            "TRANSPOSE_ENTRA_JWKS_CACHE_TTL_SECONDS",
            "ENTRA_JWKS_CACHE_TTL_SECONDS",
        ),
    )

    # Pipeline tuning
    ocr_concurrency: int = 5
    ocr_batch_size: int = 10
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

    # TTS / Audiobook
    tts_provider: str = "azure"  # azure | elevenlabs | openai
    tts_voice: str = "en-US-AndrewMultilingualNeural"
    tts_speech_key: str = ""
    tts_speech_region: str = ""
    tts_speech_endpoint: str = ""  # Alternative to region-based auth

    # API authentication (empty = permissive mode for local dev)
    api_key: str = ""

    @property
    def entra_admin_auth_configured(self) -> bool:
        """Return True when the admin dashboard auth inputs are configured."""
        return bool(
            self.entra_tenant_id
            and self.entra_admin_client_id
            and self.entra_admin_audience
        )

    def get_entra_authority_url(self) -> str:
        """Return the tenant authority base URL used in WWW-Authenticate challenges."""
        if not self.entra_tenant_id:
            return "https://login.microsoftonline.com"
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}"

    def get_entra_discovery_url(self) -> str:
        """Return the OpenID discovery endpoint for the configured tenant."""
        if not self.entra_tenant_id:
            return ""
        return f"{self.get_entra_authority_url()}/v2.0/.well-known/openid-configuration"

    def get_entra_issuer(self) -> str:
        """Return the expected token issuer for the configured tenant."""
        if self.entra_issuer:
            return self.entra_issuer
        if not self.entra_tenant_id:
            return ""
        return f"{self.get_entra_authority_url()}/v2.0"

    def get_entra_jwks_uri(self) -> str:
        """Return the configured or derived JWKS URI for the tenant."""
        if self.entra_jwks_uri:
            return self.entra_jwks_uri
        if not self.entra_tenant_id:
            return ""
        return f"{self.get_entra_authority_url()}/discovery/v2.0/keys"

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
