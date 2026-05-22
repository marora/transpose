#!/usr/bin/env python3
"""Wrapper CLI for Stage 8 workspace backfills."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


if __name__ == "__main__":
    import_module("transpose.backfill_workspace").main()
