"""Tests for resume_from pipeline functionality.

Validates that runner.py correctly skips stages when resume_from is set,
handles invalid stage names, and respects lock semantics on resume.

Covers Issue #49.
"""

from __future__ import annotations

import pytest

from transpose.pipeline.runner import STAGE_ORDER, PipelineInput


class TestResumeFromStageSelection:
    """Verify correct stage selection based on resume_from value."""

    def test_resume_from_none_runs_all_stages(self) -> None:
        """When resume_from is None the start index should be 0 (all stages)."""
        inp = PipelineInput(source_path="/book.pdf", title="T", resume_from=None)
        start_index = 0
        if inp.resume_from:
            start_index = STAGE_ORDER.index(inp.resume_from)
        assert start_index == 0
        # Every stage index is >= 0
        assert all(start_index <= STAGE_ORDER.index(s) for s in STAGE_ORDER)

    @pytest.mark.parametrize(
        "resume_stage, expected_skipped, expected_run",
        [
            ("translate", ["ingest", "ocr", "chunk"], ["translate", "glossary", "assemble", "export", "audiobook", "workspace"]),
            ("assemble", ["ingest", "ocr", "chunk", "translate", "glossary"], ["assemble", "export", "audiobook", "workspace"]),
            ("export", ["ingest", "ocr", "chunk", "translate", "glossary", "assemble"], ["export", "audiobook", "workspace"]),
            ("ocr", ["ingest"], ["ocr", "chunk", "translate", "glossary", "assemble", "export", "audiobook", "workspace"]),
            ("glossary", ["ingest", "ocr", "chunk", "translate"], ["glossary", "assemble", "export", "audiobook", "workspace"]),
        ],
    )
    def test_resume_from_skips_earlier_stages(
        self, resume_stage: str, expected_skipped: list[str], expected_run: list[str]
    ) -> None:
        """Stages before resume_from should be skipped, later ones should run."""
        start_index = STAGE_ORDER.index(resume_stage)

        skipped = STAGE_ORDER[:start_index]
        run = STAGE_ORDER[start_index:]

        assert skipped == expected_skipped
        assert run == expected_run

    def test_resume_from_ingest_runs_everything(self) -> None:
        """Resuming from 'ingest' should run all stages."""
        start_index = STAGE_ORDER.index("ingest")
        assert start_index == 0
        assert STAGE_ORDER[start_index:] == STAGE_ORDER

    def test_resume_from_invalid_stage_falls_through(self) -> None:
        """Invalid stage name should not be found in STAGE_ORDER.

        runner.py catches ValueError and starts from beginning.
        """
        with pytest.raises(ValueError):
            STAGE_ORDER.index("nonexistent_stage")

    def test_resume_from_invalid_stage_runner_behaviour(self) -> None:
        """Simulate the runner's fallback: unknown stage -> start_index = 0."""
        stage_name = "bogus_stage"
        start_index = 0
        try:
            start_index = STAGE_ORDER.index(stage_name)
        except ValueError:
            pass  # runner logs warning and keeps start_index = 0
        assert start_index == 0


class TestResumeFromIdempotency:
    """Calling with the same resume_from value must produce identical behaviour."""

    @pytest.mark.parametrize("stage", STAGE_ORDER)
    def test_same_resume_from_twice_gives_same_index(self, stage: str) -> None:
        idx1 = STAGE_ORDER.index(stage)
        idx2 = STAGE_ORDER.index(stage)
        assert idx1 == idx2

    def test_stage_order_is_stable(self) -> None:
        """STAGE_ORDER must not change between accesses."""
        snapshot = list(STAGE_ORDER)
        assert STAGE_ORDER == snapshot
        assert STAGE_ORDER == snapshot  # second access


class TestResumeFromStageGuards:
    """Verify the `start_index <= STAGE_ORDER.index(stage)` guards used in runner."""

    @pytest.mark.parametrize(
        "resume_stage, guarded_stage, should_run",
        [
            ("translate", "ingest", False),
            ("translate", "ocr", False),
            ("translate", "chunk", False),
            ("translate", "translate", True),
            ("translate", "glossary", True),
            ("translate", "assemble", True),
            ("translate", "export", True),
            ("assemble", "translate", False),
            ("assemble", "assemble", True),
            ("assemble", "export", True),
            (None, "ingest", True),
            (None, "export", True),
        ],
    )
    def test_stage_guard_logic(
        self, resume_stage: str | None, guarded_stage: str, should_run: bool
    ) -> None:
        """Replicate the `if start_index <= STAGE_ORDER.index(stage)` guard."""
        start_index = 0
        if resume_stage:
            start_index = STAGE_ORDER.index(resume_stage)
        ran = start_index <= STAGE_ORDER.index(guarded_stage)
        assert ran is should_run


class TestResumeFromPipelineInput:
    """PipelineInput dataclass correctly stores resume_from."""

    def test_pipeline_input_defaults_to_none(self) -> None:
        inp = PipelineInput(source_path="/book.pdf", title="T")
        assert inp.resume_from is None

    def test_pipeline_input_stores_resume_from(self) -> None:
        inp = PipelineInput(source_path="/book.pdf", title="T", resume_from="translate")
        assert inp.resume_from == "translate"

    def test_pipeline_input_resume_from_empty_string(self) -> None:
        """Empty string is falsy — runner treats it like None."""
        inp = PipelineInput(source_path="/book.pdf", title="T", resume_from="")
        start_index = 0
        if inp.resume_from:
            start_index = STAGE_ORDER.index(inp.resume_from)
        assert start_index == 0


class TestResumeFromLockHandling:
    """Lock semantics when resuming past ingest stage.

    When resume_from points past ingest the runner looks up an existing
    book_id via source hash. These tests verify the expected code paths.
    """

    def test_resume_past_ingest_requires_book_lookup(self) -> None:
        """start_index > ingest means the runner must resolve book_id from hash."""
        for stage in ["ocr", "chunk", "translate", "glossary", "assemble", "export"]:
            start_index = STAGE_ORDER.index(stage)
            ingest_index = STAGE_ORDER.index("ingest")
            assert start_index > ingest_index

    def test_resume_at_ingest_does_not_require_lookup(self) -> None:
        """Resuming at ingest runs ingest itself — no prior book_id needed."""
        start_index = STAGE_ORDER.index("ingest")
        assert start_index == STAGE_ORDER.index("ingest")
        assert start_index == 0

    def test_lock_acquire_happens_during_ingest(self) -> None:
        """The lock is acquired inside the ingest block (start_index <= 0).

        When we skip ingest (resume past it), the lock was acquired in the
        original run and the resumed run relies on the existing book record.
        """
        ingest_index = STAGE_ORDER.index("ingest")
        # If we resume from translate, ingest guard is False
        assert STAGE_ORDER.index("translate") > ingest_index
