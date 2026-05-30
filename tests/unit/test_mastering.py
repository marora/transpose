"""Tests for mastering and audio quality gate modules."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from transpose.pipeline.mastering import (
    MasteringResult,
    master_chapter_audio,
    _TARGET_LUFS,
)
from transpose.pipeline.audio_quality_gate import (
    AudioQualityReport,
    audio_quality_gate,
    measure_audio,
    validate_audiobook,
    LUFS_MIN,
    LUFS_MAX,
    TRUE_PEAK_MAX_DBFS,
)


# --- Mastering tests ---


class TestMastering:
    """Tests for the mastering pipeline."""

    def test_mastering_result_dataclass(self):
        r = MasteringResult(
            audio_bytes=b"fake",
            duration_ms=5000,
            lufs=-16.0,
            peak_dbfs=-1.5,
            file_size_bytes=1024,
        )
        assert r.lufs == -16.0
        assert r.duration_ms == 5000

    @pytest.mark.asyncio
    async def test_master_chapter_raises_without_ffmpeg(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="ffmpeg not found"):
                await master_chapter_audio(b"fake audio")

    @pytest.mark.asyncio
    async def test_master_chapter_success(self):
        """Mock ffmpeg subprocess calls and verify mastering pipeline."""
        fake_output = b"mastered audio bytes"

        async def mock_exec(*args, **kwargs):
            proc = AsyncMock()
            cmd = args[0] if args else ""
            # Check if this is the measurement pass (output to null)
            if "-f" in args and "null" in args:
                proc.communicate.return_value = (
                    b"",
                    b'{\n"input_i": "-24.0",\n"input_tp": "-1.5",\n'
                    b'"input_lra": "7.0",\n"input_thresh": "-34.0"\n}\n'
                    b"Duration: 00:01:30.50",
                )
            else:
                proc.communicate.return_value = (b"", b"")
            proc.returncode = 0
            return proc

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch(
                "asyncio.create_subprocess_exec", side_effect=mock_exec
            ):
                with patch("pathlib.Path.write_bytes"):
                    with patch("pathlib.Path.read_bytes", return_value=fake_output):
                        with patch("pathlib.Path.exists", return_value=True):
                            result = await master_chapter_audio(b"raw tts audio")

        assert result.audio_bytes == fake_output
        assert result.lufs == _TARGET_LUFS


# --- Audio Quality Gate tests ---


class TestAudioQualityGate:
    """Tests for the audio quality gate."""

    def test_report_dataclass(self):
        r = AudioQualityReport(
            measured_lufs=-16.0,
            true_peak_dbfs=-2.0,
            duration_ms=60000,
            silence_ratio=0.05,
            sample_rate=44100,
            bitrate_kbps=192,
            passed=True,
            issues=[],
        )
        assert r.passed is True

    @pytest.mark.asyncio
    async def test_measure_raises_without_ffmpeg(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="ffmpeg not found"):
                await measure_audio(b"fake")

    @pytest.mark.asyncio
    async def test_measure_audio_passing(self):
        """Audio within spec passes."""

        async def mock_exec(*args, **kwargs):
            proc = AsyncMock()
            if any("ebur128" in str(a) for a in args):
                proc.communicate.return_value = (
                    b"",
                    b"I:        -16.0 LUFS\n"
                    b"Peak:     -2.0 dBFS\n"
                    b"Duration: 00:02:30.00\n"
                    b"44100 Hz\n192 kb/s\n",
                )
            else:
                # silencedetect pass
                proc.communicate.return_value = (
                    b"",
                    b"silence_duration: 1.5\nsilence_duration: 0.8\n"
                    b"Duration: 00:02:30.00\n",
                )
            proc.returncode = 0
            return proc

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
                with patch("pathlib.Path.write_bytes"):
                    report = await measure_audio(b"good audio")

        assert report.passed is True
        assert report.measured_lufs == -16.0
        assert report.issues == []

    @pytest.mark.asyncio
    async def test_measure_audio_too_quiet(self):
        """Audio below -18 LUFS fails."""

        async def mock_exec(*args, **kwargs):
            proc = AsyncMock()
            if any("ebur128" in str(a) for a in args):
                proc.communicate.return_value = (
                    b"",
                    b"I:        -22.0 LUFS\nPeak:     -3.0 dBFS\n"
                    b"Duration: 00:01:00.00\n44100 Hz\n192 kb/s\n",
                )
            else:
                proc.communicate.return_value = (
                    b"",
                    b"Duration: 00:01:00.00\n",
                )
            proc.returncode = 0
            return proc

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
                with patch("pathlib.Path.write_bytes"):
                    report = await measure_audio(b"quiet audio")

        assert report.passed is False
        assert any("Too quiet" in i for i in report.issues)

    @pytest.mark.asyncio
    async def test_measure_audio_peak_too_high(self):
        """True peak above -1 dBFS fails."""

        async def mock_exec(*args, **kwargs):
            proc = AsyncMock()
            if any("ebur128" in str(a) for a in args):
                proc.communicate.return_value = (
                    b"",
                    b"I:        -16.0 LUFS\nPeak:     -0.5 dBFS\n"
                    b"Duration: 00:01:00.00\n44100 Hz\n192 kb/s\n",
                )
            else:
                proc.communicate.return_value = (
                    b"",
                    b"Duration: 00:01:00.00\n",
                )
            proc.returncode = 0
            return proc

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
                with patch("pathlib.Path.write_bytes"):
                    report = await measure_audio(b"clipped audio")

        assert report.passed is False
        assert any("True peak too high" in i for i in report.issues)

    @pytest.mark.asyncio
    async def test_validate_audiobook_all_pass(self):
        """All chapters passing returns True."""

        async def mock_exec(*args, **kwargs):
            proc = AsyncMock()
            if any("ebur128" in str(a) for a in args):
                proc.communicate.return_value = (
                    b"",
                    b"I:        -16.0 LUFS\nPeak:     -2.0 dBFS\n"
                    b"Duration: 00:02:00.00\n44100 Hz\n192 kb/s\n",
                )
            else:
                proc.communicate.return_value = (
                    b"",
                    b"Duration: 00:02:00.00\n",
                )
            proc.returncode = 0
            return proc

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
                with patch("pathlib.Path.write_bytes"):
                    passed, reports = await validate_audiobook(
                        [b"ch1", b"ch2", b"ch3"]
                    )

        assert passed is True
        assert len(reports) == 3


# --- audio_quality_gate (GateResult adapter) tests ---


class TestAudioQualityGateAdapter:
    """Tests for the audio_quality_gate function that integrates with the runner."""

    def test_gate_passes_with_valid_chapters(self):
        from transpose.pipeline.audiobook import AudiobookOutput, ChapterAudio
        from uuid import uuid4

        output = AudiobookOutput(
            book_id=uuid4(),
            chapters=[
                ChapterAudio(
                    chapter_number=1, title="Intro",
                    blob_uri="https://blob/ch1.mp3",
                    duration_ms=120000, file_size_bytes=500_000,
                ),
                ChapterAudio(
                    chapter_number=2, title="The Path",
                    blob_uri="https://blob/ch2.mp3",
                    duration_ms=600000, file_size_bytes=2_000_000,
                ),
            ],
            total_duration_ms=720000,
            total_cost=0.50,
        )
        result = audio_quality_gate(output)
        assert result.passed is True
        assert result.gate_name == "audio_quality"
        assert result.details["chapter_count"] == 2

    def test_gate_fails_empty_chapters(self):
        from transpose.pipeline.audiobook import AudiobookOutput
        from uuid import uuid4

        output = AudiobookOutput(book_id=uuid4(), chapters=[], total_duration_ms=0)
        result = audio_quality_gate(output)
        assert result.passed is False
        assert "No audio chapters produced" in result.failures[0]

    def test_gate_fails_too_small_file(self):
        from transpose.pipeline.audiobook import AudiobookOutput, ChapterAudio
        from uuid import uuid4

        output = AudiobookOutput(
            book_id=uuid4(),
            chapters=[
                ChapterAudio(
                    chapter_number=1, title="Empty",
                    blob_uri="https://blob/ch1.mp3",
                    duration_ms=60000, file_size_bytes=100,  # < 1024
                ),
            ],
            total_duration_ms=60000,
        )
        result = audio_quality_gate(output)
        assert result.passed is False
        assert "too small" in result.failures[0]

    def test_gate_fails_too_short_chapter(self):
        from transpose.pipeline.audiobook import AudiobookOutput, ChapterAudio
        from uuid import uuid4

        output = AudiobookOutput(
            book_id=uuid4(),
            chapters=[
                ChapterAudio(
                    chapter_number=1, title="Tiny",
                    blob_uri="https://blob/ch1.mp3",
                    duration_ms=2000, file_size_bytes=50_000,  # 2s < 5s min
                ),
            ],
            total_duration_ms=2000,
        )
        result = audio_quality_gate(output)
        assert result.passed is False
        assert "too short" in result.failures[0]

    def test_gate_fails_too_long_chapter(self):
        from transpose.pipeline.audiobook import AudiobookOutput, ChapterAudio
        from uuid import uuid4

        output = AudiobookOutput(
            book_id=uuid4(),
            chapters=[
                ChapterAudio(
                    chapter_number=1, title="Epic",
                    blob_uri="https://blob/ch1.mp3",
                    duration_ms=35 * 60 * 1000,  # 35 min > 30 max
                    file_size_bytes=10_000_000,
                ),
            ],
            total_duration_ms=35 * 60 * 1000,
        )
        result = audio_quality_gate(output)
        assert result.passed is False
        assert "too long" in result.failures[0]
