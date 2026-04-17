"""Tests for settings configuration."""

import os

from transpose.config.settings import Settings


class TestSettings:
    def test_defaults(self) -> None:
        settings = Settings()
        assert settings.postgres_host == "localhost"
        assert settings.postgres_port == 5432
        assert settings.chunk_target_tokens == 1500
        assert settings.low_confidence_threshold == 0.7

    def test_env_prefix(self) -> None:
        os.environ["TRANSPOSE_POSTGRES_HOST"] = "testhost"
        try:
            settings = Settings()
            assert settings.postgres_host == "testhost"
        finally:
            del os.environ["TRANSPOSE_POSTGRES_HOST"]
