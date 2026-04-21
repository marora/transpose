"""Tests for gate telemetry and performance metrics (Issues #29 & #44).

Validates that _run_gate emits OpenTelemetry spans and records
gate_executions / gate_duration_seconds metrics.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from transpose.pipeline.gates import GateResult, QualityGateError
from transpose.pipeline.runner import _run_gate


def _make_gate_result(name: str = "test_gate", passed: bool = True, failures: list[str] | None = None) -> GateResult:
    return GateResult(gate_name=name, passed=passed, failures=failures or [])


class TestRunGateTelemetry:
    """Verify _run_gate emits spans and metrics."""

    def test_passing_gate_records_metrics(self) -> None:
        """A passing gate should record execution count and duration."""
        result = _make_gate_result("ocr_sanity", passed=True)
        gate_fn = MagicMock(return_value=result)
        collected: list[GateResult] = []

        with patch("transpose.observability.metrics.gate_executions") as mock_counter, \
             patch("transpose.observability.metrics.gate_duration_seconds") as mock_hist:
            _run_gate(gate_fn, None, collected)

            mock_counter.add.assert_called_once()
            args, kwargs = mock_counter.add.call_args
            assert args[0] == 1
            assert args[1]["gate_name"] == "ocr_sanity"
            assert args[1]["result"] == "pass"

            mock_hist.record.assert_called_once()
            hist_args = mock_hist.record.call_args[0]
            assert hist_args[0] >= 0  # duration >= 0
            assert mock_hist.record.call_args[0][1]["gate_name"] == "ocr_sanity"

    def test_failing_gate_records_fail_metric(self) -> None:
        """A failing gate should record result='fail' and raise QualityGateError."""
        result = _make_gate_result("translation_completeness", passed=False, failures=["too many failures"])
        gate_fn = MagicMock(return_value=result)
        collected: list[GateResult] = []

        with patch("transpose.observability.metrics.gate_executions") as mock_counter, \
             patch("transpose.observability.metrics.gate_duration_seconds"):
            with pytest.raises(QualityGateError):
                _run_gate(gate_fn, None, collected)

            args, kwargs = mock_counter.add.call_args
            assert args[1]["result"] == "fail"

    def test_gate_result_appended_on_pass(self) -> None:
        result = _make_gate_result("glossary_integrity", passed=True)
        gate_fn = MagicMock(return_value=result)
        collected: list[GateResult] = []

        _run_gate(gate_fn, None, collected)
        assert len(collected) == 1
        assert collected[0].gate_name == "glossary_integrity"

    def test_gate_result_appended_on_fail(self) -> None:
        """Even on failure the result is appended before raising."""
        result = _make_gate_result("export_rendering", passed=False, failures=["bad render"])
        gate_fn = MagicMock(return_value=result)
        collected: list[GateResult] = []

        with pytest.raises(QualityGateError):
            _run_gate(gate_fn, None, collected)
        assert len(collected) == 1

    def test_span_attributes_on_pass(self) -> None:
        """Span should carry gate.name, gate.passed, gate.duration_ms."""
        result = _make_gate_result("ocr_sanity", passed=True)
        gate_fn = MagicMock(return_value=result)
        collected: list[GateResult] = []

        with patch("opentelemetry.trace.get_tracer") as mock_get_tracer:
            mock_span = MagicMock()
            mock_tracer = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)
            mock_get_tracer.return_value = mock_tracer

            _run_gate(gate_fn, None, collected)

            attrs = {call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list}
            assert attrs["gate.name"] == "ocr_sanity"
            assert attrs["gate.passed"] is True
            assert "gate.duration_ms" in attrs

    def test_span_failure_reason_on_fail(self) -> None:
        """Failing gates should set gate.failure_reason on the span."""
        result = _make_gate_result("document_structure", passed=False, failures=["no chapters", "empty body"])
        gate_fn = MagicMock(return_value=result)
        collected: list[GateResult] = []

        with patch("opentelemetry.trace.get_tracer") as mock_get_tracer:
            mock_span = MagicMock()
            mock_tracer = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)
            mock_get_tracer.return_value = mock_tracer

            with pytest.raises(QualityGateError):
                _run_gate(gate_fn, None, collected)

            attrs = {call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list}
            assert "gate.failure_reason" in attrs
            assert "no chapters" in attrs["gate.failure_reason"]


class TestGateMetricsExist:
    """Verify gate metrics are defined in the metrics module."""

    def test_gate_executions_counter_exists(self) -> None:
        from transpose.observability.metrics import gate_executions
        assert gate_executions is not None

    def test_gate_duration_histogram_exists(self) -> None:
        from transpose.observability.metrics import gate_duration_seconds
        assert gate_duration_seconds is not None
