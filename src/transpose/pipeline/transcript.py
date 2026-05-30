"""Read-along transcript generation from word boundary data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WordTiming:
    text: str
    start_ms: int
    end_ms: int


def _format_vtt_ts(ms: int) -> str:
    h = ms // 3_600_000
    m = (ms % 3_600_000) // 60_000
    s = (ms % 60_000) // 1000
    mil = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{mil:03d}"


def _format_srt_ts(ms: int) -> str:
    return _format_vtt_ts(ms).replace(".", ",")


def _group_into_cues(word_timings: list[WordTiming], words_per_cue: int) -> list[list[WordTiming]]:
    """Group words into paragraph-sized cues, breaking at sentence boundaries."""
    if not word_timings:
        return []
    cues: list[list[WordTiming]] = []
    current: list[WordTiming] = []
    for wt in word_timings:
        current.append(wt)
        at_sentence_end = wt.text.rstrip().endswith((".", "!", "?"))
        if at_sentence_end and len(current) >= (words_per_cue * 0.6):
            cues.append(current)
            current = []
        elif len(current) >= words_per_cue:
            cues.append(current)
            current = []
    if current:
        cues.append(current)
    return cues


def generate_vtt(
    word_timings: list[WordTiming],
    mode: str = "paragraph",
    words_per_cue: int = 25,
) -> str:
    """Generate WebVTT content from word timings."""
    lines = ["WEBVTT", ""]
    if not word_timings:
        return "WEBVTT\n\n"
    if mode == "word":
        for wt in word_timings:
            lines.append(f"{_format_vtt_ts(wt.start_ms)} --> {_format_vtt_ts(wt.end_ms)}")
            lines.append(wt.text)
            lines.append("")
    else:
        for cue in _group_into_cues(word_timings, words_per_cue):
            start = _format_vtt_ts(cue[0].start_ms)
            end = _format_vtt_ts(cue[-1].end_ms)
            text = " ".join(w.text for w in cue)
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")
    return "\n".join(lines)


def generate_srt(
    word_timings: list[WordTiming],
    words_per_cue: int = 25,
) -> str:
    """Generate SRT content from word timings (paragraph mode only)."""
    if not word_timings:
        return ""
    cues = _group_into_cues(word_timings, words_per_cue)
    lines: list[str] = []
    for i, cue in enumerate(cues, 1):
        start = _format_srt_ts(cue[0].start_ms)
        end = _format_srt_ts(cue[-1].end_ms)
        text = " ".join(w.text for w in cue)
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def estimate_paragraph_timings(
    text: str,
    total_duration_ms: int,
) -> list[WordTiming]:
    """Estimate word-level timings from plain text when no word boundaries available."""
    words = text.split()
    if not words:
        return []
    total_chars = sum(len(w) for w in words)
    timings: list[WordTiming] = []
    current_ms = 0
    for w in words:
        duration = int((len(w) / total_chars) * total_duration_ms) if total_chars else 0
        timings.append(WordTiming(text=w, start_ms=current_ms, end_ms=current_ms + duration))
        current_ms += duration
    # Adjust last word to exactly hit total_duration_ms
    if timings:
        timings[-1].end_ms = total_duration_ms
    return timings
