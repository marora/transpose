"""Tests for settings configuration."""

import os

from transpose.config.settings import Settings


def _clean_settings(**overrides) -> Settings:
    """Create Settings without reading the repo .env file."""
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


class TestSettings:
    def test_defaults(self) -> None:
        """Verify code defaults without .env file leaking in."""
        # Strip any TRANSPOSE_ env vars that might interfere
        saved = {}
        for key in list(os.environ):
            if key.startswith("TRANSPOSE_"):
                saved[key] = os.environ.pop(key)
        try:
            settings = _clean_settings()
            assert settings.postgres_host == "localhost"
            assert settings.postgres_port == 5432
            assert settings.chunk_target_tokens == 1500
            assert settings.low_confidence_threshold == 0.7
        finally:
            os.environ.update(saved)

    def test_env_prefix(self) -> None:
        os.environ["TRANSPOSE_POSTGRES_HOST"] = "testhost"
        try:
            settings = _clean_settings()
            assert settings.postgres_host == "testhost"
        finally:
            del os.environ["TRANSPOSE_POSTGRES_HOST"]
