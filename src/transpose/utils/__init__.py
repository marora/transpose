"""Shared utility functions."""

from __future__ import annotations


def escape_html(text: str) -> str:
    """Basic HTML escaping — single canonical implementation."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
