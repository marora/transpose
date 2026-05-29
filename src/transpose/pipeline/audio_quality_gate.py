"""Audio quality gate — validates mastered audio meets broadcast standards.

Checks loudness (LUFS), true peak, silence ratios, and file integrity.
Integrates with the existing gates.py pattern in Transpose.

Implements: #124 — Audio quality gate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Podcast standards (Spotify / Apple Podcasts / RSS best practices)
LUFS_TARGET = -16.0
LUFS_MIN = -18.0
LUFS_MAX = -14.0
TRUE_PEAK_MAX_DBFS = -1.0
MIN_DURATION_MS = 5000  # chapters should be at least 5s
MAX_SILENCE_RATIO = 0.30  # max 30% silence


@dataclass
class AudioQualityReport:
    """Quality measurements for a single audio file."""

    measured_lufs: float
    true_peak_dbfs: float
    duration_ms: int
    silence_ratio: float
    sample_rate: int
    bitrate_kbps: int
    passed: bool
    issues: list[str]


async def measure_audio(audio_bytes: bytes) -> AudioQualityReport:
    """Measure loudness, peak, silence ratio of an audio file.

    Uses ffmpeg's ebur128 and silencedetect filters.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found — required for audio quality gate")

    issues: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "input.mp3"
        input_path.write_bytes(audio_bytes)

        # Run ebur128 measurement
        cmd = [
            ffmpeg, "-i", str(input_path),
            "-af", "ebur128=peak=true",
            "-f", "null", "-",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        stderr_text = stderr.decode("utf-8", errors="replace")

        # Parse integrated loudness
        lufs_match = re.search(r"I:\s+(-?\d+\.?\d*)\s+LUFS", stderr_text)
        measured_lufs = float(lufs_match.group(1)) if lufs_match else -99.0

        # Parse true peak
        tp_match = re.search(r"Peak:\s+(-?\d+\.?\d*)\s+dBFS", stderr_text)
        true_peak = float(tp_match.group(1)) if tp_match else 0.0

        # Get duration, sample rate, bitrate from probe
        dur_match = re.search(r"Duration: (\d+):(\d+):(\d+)\.(\d+)", stderr_text)
        duration_ms = 0
        if dur_match:
            h, m, s, cs = [int(x) for x in dur_match.groups()]
            duration_ms = (h * 3600 + m * 60 + s) * 1000 + cs * 10

        sr_match = re.search(r"(\d+) Hz", stderr_text)
        sample_rate = int(sr_match.group(1)) if sr_match else 0

        br_match = re.search(r"(\d+) kb/s", stderr_text)
        bitrate_kbps = int(br_match.group(1)) if br_match else 0

        # Measure silence ratio using silencedetect
        silence_cmd = [
            ffmpeg, "-i", str(input_path),
            "-af", "silencedetect=n=-40dB:d=0.5",
            "-f", "null", "-",
        ]
        proc = await asyncio.create_subprocess_exec(
            *silence_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, silence_stderr = await proc.communicate()
        silence_text = silence_stderr.decode("utf-8", errors="replace")

        # Sum silence durations
        silence_durations = re.findall(
            r"silence_duration: (\d+\.?\d*)", silence_text
        )
        total_silence_ms = sum(float(d) * 1000 for d in silence_durations)
        silence_ratio = total_silence_ms / duration_ms if duration_ms > 0 else 0.0

    # Validate against standards
    if measured_lufs < LUFS_MIN:
        issues.append(
            f"Too quiet: {measured_lufs:.1f} LUFS (min {LUFS_MIN})"
        )
    elif measured_lufs > LUFS_MAX:
        issues.append(
            f"Too loud: {measured_lufs:.1f} LUFS (max {LUFS_MAX})"
        )

    if true_peak > TRUE_PEAK_MAX_DBFS:
        issues.append(
            f"True peak too high: {true_peak:.1f} dBFS (max {TRUE_PEAK_MAX_DBFS})"
        )

    if duration_ms < MIN_DURATION_MS:
        issues.append(
            f"Too short: {duration_ms}ms (min {MIN_DURATION_MS}ms)"
        )

    if silence_ratio > MAX_SILENCE_RATIO:
        issues.append(
            f"Too much silence: {silence_ratio:.0%} (max {MAX_SILENCE_RATIO:.0%})"
        )

    return AudioQualityReport(
        measured_lufs=measured_lufs,
        true_peak_dbfs=true_peak,
        duration_ms=duration_ms,
        silence_ratio=silence_ratio,
        sample_rate=sample_rate,
        bitrate_kbps=bitrate_kbps,
        passed=len(issues) == 0,
        issues=issues,
    )


async def validate_audiobook(
    chapter_audio_list: list[bytes],
) -> tuple[bool, list[AudioQualityReport]]:
    """Validate all chapters meet quality standards.

    Returns (all_passed, list_of_reports).
    """
    reports = []
    all_passed = True

    for i, audio_bytes in enumerate(chapter_audio_list):
        report = await measure_audio(audio_bytes)
        reports.append(report)
        if not report.passed:
            all_passed = False
            logger.warning(
                f"Chapter {i + 1} FAILED quality gate: {report.issues}"
            )
        else:
            logger.info(
                f"Chapter {i + 1} passed: {report.measured_lufs:.1f} LUFS, "
                f"peak {report.true_peak_dbfs:.1f} dBFS"
            )

    return all_passed, reports
