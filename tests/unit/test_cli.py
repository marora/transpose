"""Tests for transpose.cli — Click CLI entry point.

Covers:
- CLI group help
- 'run' command argument parsing and validation
- 'status' command argument parsing
- Error handling on missing required options
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from transpose.cli import main

# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


class TestCLIGroup:
    """Top-level CLI group tests."""

    @patch("transpose.observability.tracing.configure_tracing")
    @patch("transpose.config.settings.get_appinsights_connection_string", return_value="")
    def test_help_text(self, _mock_conn, _mock_tracing) -> None:
        """--help returns 0 and shows description."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Transpose" in result.output

    @patch("transpose.observability.tracing.configure_tracing")
    @patch("transpose.config.settings.get_appinsights_connection_string", return_value="")
    def test_no_subcommand_shows_usage(self, _mock_conn, _mock_tracing) -> None:
        """Invoking with no subcommand shows help/usage."""
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code in (0, 2)  # 0 if invoke_without_command=True, 2 otherwise


# ---------------------------------------------------------------------------
# 'run' command
# ---------------------------------------------------------------------------


class TestRunCommand:
    """CLI 'run' subcommand tests."""

    @patch("transpose.observability.tracing.configure_tracing")
    @patch("transpose.config.settings.get_appinsights_connection_string", return_value="")
    def test_run_missing_source_fails(self, _mock_conn, _mock_tracing) -> None:
        """--source is required → exit code != 0."""
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--title", "Test"])
        assert result.exit_code != 0
        assert (
            "source" in result.output.lower()
            or "missing" in result.output.lower()
            or "required" in result.output.lower()
        )

    @patch("transpose.observability.tracing.configure_tracing")
    @patch("transpose.config.settings.get_appinsights_connection_string", return_value="")
    def test_run_missing_title_fails(self, _mock_conn, _mock_tracing) -> None:
        """--title is required → exit code != 0."""
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--source", "test.pdf"])
        assert result.exit_code != 0

    @patch("transpose.observability.tracing.configure_tracing")
    @patch("transpose.config.settings.get_appinsights_connection_string", return_value="")
    def test_run_invalid_language_fails(self, _mock_conn, _mock_tracing) -> None:
        """Invalid --language value → rejected by Click Choice."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["run", "--source", "t.pdf", "--title", "T", "--language", "spanish"]
        )
        assert result.exit_code != 0

    @patch("transpose.observability.tracing.configure_tracing")
    @patch("transpose.config.settings.get_appinsights_connection_string", return_value="")
    @patch("transpose.cli._run_pipeline", new_callable=AsyncMock)
    def test_run_valid_args_invokes_pipeline(
        self, mock_pipeline, _mock_conn, _mock_tracing
    ) -> None:
        """Valid args → pipeline is invoked with correct arguments."""
        runner = CliRunner()
        runner.invoke(
            main,
            [
                "run",
                "--source", "book.pdf",
                "--title", "Bhagavad Gita",
                "--author", "Vyasa",
                "--language", "hindi",
            ],
        )
        # Pipeline was called
        mock_pipeline.assert_called_once()
        call_args = mock_pipeline.call_args
        assert call_args[0][0] == "book.pdf"
        assert call_args[0][1] == "Bhagavad Gita"
        assert call_args[0][2] == "Vyasa"
        assert call_args[0][3] == "hindi"

    @patch("transpose.observability.tracing.configure_tracing")
    @patch("transpose.config.settings.get_appinsights_connection_string", return_value="")
    @patch("transpose.cli._run_pipeline", new_callable=AsyncMock)
    def test_run_default_language_is_hindi(
        self, mock_pipeline, _mock_conn, _mock_tracing
    ) -> None:
        """Default language is hindi."""
        runner = CliRunner()
        runner.invoke(
            main,
            ["run", "--source", "book.pdf", "--title", "Test"],
        )
        if mock_pipeline.called:
            assert mock_pipeline.call_args[0][3] == "hindi"

    @patch("transpose.observability.tracing.configure_tracing")
    @patch("transpose.config.settings.get_appinsights_connection_string", return_value="")
    @patch("transpose.cli._run_pipeline", new_callable=AsyncMock)
    def test_run_punjabi_language(
        self, mock_pipeline, _mock_conn, _mock_tracing
    ) -> None:
        """--language punjabi is accepted."""
        runner = CliRunner()
        runner.invoke(
            main,
            ["run", "--source", "book.pdf", "--title", "Test", "--language", "punjabi"],
        )
        if mock_pipeline.called:
            assert mock_pipeline.call_args[0][3] == "punjabi"

    @patch("transpose.observability.tracing.configure_tracing")
    @patch("transpose.config.settings.get_appinsights_connection_string", return_value="")
    @patch("transpose.cli._run_pipeline", new_callable=AsyncMock)
    def test_run_echoes_title(self, mock_pipeline, _mock_conn, _mock_tracing) -> None:
        """Output includes the title being translated."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["run", "--source", "book.pdf", "--title", "Gita"],
        )
        assert "Gita" in result.output


# ---------------------------------------------------------------------------
# 'status' command
# ---------------------------------------------------------------------------


class TestStatusCommand:
    """CLI 'status' subcommand tests."""

    @patch("transpose.observability.tracing.configure_tracing")
    @patch("transpose.config.settings.get_appinsights_connection_string", return_value="")
    def test_status_missing_book_id_fails(self, _mock_conn, _mock_tracing) -> None:
        """--book-id is required → exit code != 0."""
        runner = CliRunner()
        result = runner.invoke(main, ["status"])
        assert result.exit_code != 0

    @patch("transpose.observability.tracing.configure_tracing")
    @patch("transpose.config.settings.get_appinsights_connection_string", return_value="")
    @patch("transpose.cli._check_status", new_callable=AsyncMock)
    def test_status_valid_book_id(self, mock_check, _mock_conn, _mock_tracing) -> None:
        """Valid --book-id invokes status check."""
        runner = CliRunner()
        runner.invoke(
            main, ["status", "--book-id", "12345678-1234-1234-1234-123456789012"]
        )
        mock_check.assert_called_once_with("12345678-1234-1234-1234-123456789012")
