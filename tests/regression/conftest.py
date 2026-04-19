"""Fixtures for regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"


@pytest.fixture
def golden_structure() -> dict:
    """Load the golden expected-structure reference."""
    with open(GOLDEN_DIR / "expected-structure.json") as f:
        return json.load(f)


@pytest.fixture
def golden_glossary() -> list[dict]:
    """Load the golden expected-glossary reference."""
    with open(GOLDEN_DIR / "expected-glossary.json") as f:
        return json.load(f)


@pytest.fixture
def golden_gates() -> dict:
    """Load the golden gate-expectations reference."""
    with open(GOLDEN_DIR / "gate-expectations.json") as f:
        return json.load(f)
