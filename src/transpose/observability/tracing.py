"""OpenTelemetry trace configuration for Azure Monitor."""

from __future__ import annotations


def configure_tracing(connection_string: str) -> None:
    """Initialize OpenTelemetry tracing with Azure Monitor exporter.

    Args:
        connection_string: Application Insights connection string.
    """
    if not connection_string:
        return

    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(connection_string=connection_string)
