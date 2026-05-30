"""Tests for transcript generation module."""

from transpose.pipeline.transcript import (
    WordTiming,
    generate_srt,
    generate_vtt,
    estimate_paragraph_timings,
)


def _make_timings(n: int, sentence_ends=None) -> list[WordTiming]:
    """Helper: create n word timings, optionally ending some with '.'"""
    sentence_ends = sentence_ends or set()
    timings = []
    for i in range(n):
        text = f"word{i}." if i in sentence_ends else f"word{i}"
        timings.append(WordTiming(text=text, start_ms=i * 100, end_ms=(i + 1) * 100))
    return timings


class TestVttParagraphMode:
    def test_groups_words(self):
        timings = _make_timings(50, sentence_ends={24})
        vtt = generate_vtt(timings, mode="paragraph", words_per_cue=25)
        assert vtt.startswith("WEBVTT\n\n")
        cues = [b for b in vtt.split("\n\n") if "-->" in b]
        assert len(cues) >= 2

    def test_sentence_boundary_detection(self):
        # 20 words with sentence end at word 17 (>= 60% of 25)
        timings = _make_timings(30, sentence_ends={17})
        vtt = generate_vtt(timings, mode="paragraph", words_per_cue=25)
        cues = [b for b in vtt.split("\n\n") if "-->" in b]
        # Should break at word 17
        assert len(cues) >= 2
        first_cue_text = cues[0].split("\n")[1]
        assert "word17." in first_cue_text


class TestVttWordMode:
    def test_one_cue_per_word(self):
        timings = _make_timings(5)
        vtt = generate_vtt(timings, mode="word")
        cues = [b for b in vtt.split("\n\n") if "-->" in b]
        assert len(cues) == 5


class TestSrtFormat:
    def test_comma_timestamps(self):
        timings = _make_timings(3)
        srt = generate_srt(timings)
        assert "," in srt
        assert "." not in srt.split("-->")[0].split("\n")[-1]  # no dot in timestamp
        # Numbered starting at 1
        assert srt.startswith("1\n")

    def test_correct_format(self):
        timings = [WordTiming("hello", 0, 1500), WordTiming("world.", 1500, 3000)]
        srt = generate_srt(timings)
        assert "00:00:00,000 --> 00:00:03,000" in srt


class TestEstimateParagraphTimings:
    def test_distributes_proportionally(self):
        timings = estimate_paragraph_timings("hi world", 1000)
        assert len(timings) == 2
        # "hi" is 2 chars, "world" is 5 chars -> ratio 2:5
        assert timings[0].start_ms == 0
        assert timings[-1].end_ms == 1000
        # First word shorter than second
        dur0 = timings[0].end_ms - timings[0].start_ms
        dur1 = timings[1].end_ms - timings[1].start_ms
        assert dur1 > dur0


class TestEmptyInput:
    def test_empty_vtt(self):
        assert generate_vtt([]) == "WEBVTT\n\n"

    def test_empty_srt(self):
        assert generate_srt([]) == ""

    def test_empty_estimate(self):
        assert estimate_paragraph_timings("", 1000) == []
