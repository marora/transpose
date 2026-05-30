"""End-to-end integration test: audiobook pipeline → RSS feed → transcript → share page.

Validates the full consumer experience chain without real Azure/blob calls.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from transpose.pipeline.rss_feed import generate_feed
from transpose.pipeline.transcript import (
    WordTiming,
    generate_vtt,
    generate_srt,
    estimate_paragraph_timings,
)
from transpose.api.audiobook_routes import AudiobookMeta, create_audiobook_router


# Simulate a completed audiobook pipeline output
BOOK_ID = "e2e-test-book-001"
CHAPTERS = [
    {
        "number": 1,
        "title": "Chapter 1: The Beginning",
        "duration_ms": 180_000,  # 3 min
        "file_size_bytes": 2_880_000,
        "audio_url": "https://storage.blob.core.windows.net/audio/ch1.mp3",
        "transcript_url": "https://storage.blob.core.windows.net/transcripts/ch1.vtt",
    },
    {
        "number": 2,
        "title": "Chapter 2: The Journey",
        "duration_ms": 300_000,  # 5 min
        "file_size_bytes": 4_800_000,
        "audio_url": "https://storage.blob.core.windows.net/audio/ch2.mp3",
        "transcript_url": "https://storage.blob.core.windows.net/transcripts/ch2.vtt",
    },
    {
        "number": 3,
        "title": "Chapter 3: The Return",
        "duration_ms": 240_000,  # 4 min
        "file_size_bytes": 3_840_000,
        "audio_url": "https://storage.blob.core.windows.net/audio/ch3.mp3",
        "transcript_url": "https://storage.blob.core.windows.net/transcripts/ch3.vtt",
    },
]

META: AudiobookMeta = {
    "book_id": BOOK_ID,
    "title": "The Great Translation",
    "author": "Test Author",
    "description": "A test book translated from Hindi to English.",
    "language": "en",
    "cover_art_url": "https://storage.blob.core.windows.net/covers/cover.jpg",
    "base_url": "https://storage.blob.core.windows.net/feeds",
    "chapters": CHAPTERS,
}


class TestE2EAudiobookFlow:
    """Tests the full flow: data → RSS → transcript → consumer page."""

    def test_rss_feed_generation_from_pipeline_output(self):
        """Pipeline output → valid RSS feed with all chapters."""
        xml_str = generate_feed(
            book_id=BOOK_ID,
            title=META["title"],
            author=META["author"],
            description=META["description"],
            language=META["language"],
            cover_art_url=META["cover_art_url"],
            base_url=META["base_url"],
            chapters=CHAPTERS,
        )

        # Must be valid XML
        root = ET.fromstring(xml_str)
        assert root.tag == "rss"
        assert root.get("version") == "2.0"

        channel = root.find("channel")
        assert channel is not None
        assert channel.find("title").text == "The Great Translation"

        # 3 items (chapters)
        items = channel.findall("item")
        assert len(items) == 3

        # First item has correct enclosure
        enc = items[0].find("enclosure")
        assert enc is not None
        assert enc.get("url") == CHAPTERS[0]["audio_url"]
        assert enc.get("type") == "audio/mpeg"
        assert enc.get("length") == str(CHAPTERS[0]["file_size_bytes"])

        # Chapters ordered by number
        guids = [item.find("guid").text for item in items]
        assert guids == [
            f"{BOOK_ID}-chapter-1",
            f"{BOOK_ID}-chapter-2",
            f"{BOOK_ID}-chapter-3",
        ]

    def test_transcript_vtt_from_word_boundaries(self):
        """Word boundaries → VTT transcript (paragraph mode)."""
        # Simulate word boundaries from Azure TTS
        words = [
            WordTiming(text="The", start_ms=0, end_ms=200),
            WordTiming(text="sun", start_ms=200, end_ms=500),
            WordTiming(text="rose", start_ms=500, end_ms=900),
            WordTiming(text="over", start_ms=900, end_ms=1200),
            WordTiming(text="the", start_ms=1200, end_ms=1400),
            WordTiming(text="mountains.", start_ms=1400, end_ms=2000),
            WordTiming(text="Birds", start_ms=2200, end_ms=2500),
            WordTiming(text="sang", start_ms=2500, end_ms=2800),
            WordTiming(text="loudly.", start_ms=2800, end_ms=3200),
        ]

        vtt = generate_vtt(words, mode="paragraph", words_per_cue=6)
        assert vtt.startswith("WEBVTT")
        assert "The sun rose over the mountains." in vtt
        assert "-->" in vtt  # Has timestamps

    def test_transcript_word_level_for_karaoke(self):
        """Word boundaries → word-level VTT (karaoke mode)."""
        words = [
            WordTiming(text="Hello", start_ms=0, end_ms=500),
            WordTiming(text="world", start_ms=500, end_ms=1000),
        ]
        vtt = generate_vtt(words, mode="word")
        lines = vtt.strip().split("\n")
        # WEBVTT header + blank line + 2 cues (each: timestamp + text + blank)
        assert "Hello" in vtt
        assert "world" in vtt
        # Should have 2 timestamp lines
        assert vtt.count("-->") == 2

    def test_transcript_estimation_without_word_boundaries(self):
        """When no word boundaries exist, estimate from text + duration."""
        text = "The sun rose over the mountains. Birds sang loudly in the trees."
        timings = estimate_paragraph_timings(text, total_duration_ms=5000)
        assert len(timings) > 0
        # First word starts at 0
        assert timings[0].start_ms == 0
        # Last word ends at total duration
        assert timings[-1].end_ms == 5000

    def test_srt_fallback_format(self):
        """SRT generation for apps that don't support VTT."""
        words = [
            WordTiming(text="Hello", start_ms=0, end_ms=500),
            WordTiming(text="world.", start_ms=500, end_ms=1000),
            WordTiming(text="Goodbye", start_ms=1200, end_ms=1700),
            WordTiming(text="earth.", start_ms=1700, end_ms=2200),
        ]
        srt = generate_srt(words, words_per_cue=2)
        # SRT uses commas in timestamps
        assert "," in srt
        # Numbered cues
        assert srt.strip().startswith("1")

    def test_consumer_share_page_full_flow(self):
        """Share page renders with all chapters and subscribe link."""
        from fastapi import FastAPI

        app = FastAPI()
        store = {BOOK_ID: META}
        router = create_audiobook_router(store)
        app.include_router(router)
        client = TestClient(app)

        # GET metadata
        r = client.get(f"/books/{BOOK_ID}/audiobook")
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "The Great Translation"
        assert len(data["chapters"]) == 3
        assert data["total_duration_ms"] == 720_000  # 12 min total

        # GET feed XML
        r = client.get(f"/books/{BOOK_ID}/audiobook/feed.xml")
        assert r.status_code == 200
        assert "application/rss+xml" in r.headers.get("content-type", "")
        # Valid XML
        root = ET.fromstring(r.content)
        assert root.tag == "rss"

        # GET chapter redirect
        r = client.get(
            f"/books/{BOOK_ID}/audiobook/chapters/1", follow_redirects=False
        )
        assert r.status_code == 307
        assert r.headers["location"] == CHAPTERS[0]["audio_url"]

        # GET share page
        r = client.get(f"/listen/{BOOK_ID}")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        html = r.text
        assert "The Great Translation" in html
        assert "Chapter 1" in html
        assert "Chapter 3" in html
        # Has podcast subscribe link
        assert "podcast://" in html

    def test_full_chain_rss_links_match_routes(self):
        """RSS feed enclosure URLs match what the route would redirect to."""
        xml_str = generate_feed(
            book_id=BOOK_ID,
            title=META["title"],
            author=META["author"],
            description=META["description"],
            language=META["language"],
            cover_art_url=META["cover_art_url"],
            base_url=META["base_url"],
            chapters=CHAPTERS,
        )
        root = ET.fromstring(xml_str)
        items = root.find("channel").findall("item")

        # Each enclosure URL should point to the blob storage URL
        for i, item in enumerate(items):
            enc_url = item.find("enclosure").get("url")
            assert enc_url == CHAPTERS[i]["audio_url"]

    def test_transcript_integrates_with_rss(self):
        """RSS podcast:transcript tag URLs match transcript generation output format."""
        xml_str = generate_feed(
            book_id=BOOK_ID,
            title=META["title"],
            author=META["author"],
            description=META["description"],
            language=META["language"],
            cover_art_url=META["cover_art_url"],
            base_url=META["base_url"],
            chapters=CHAPTERS,
        )
        root = ET.fromstring(xml_str)
        items = root.find("channel").findall("item")

        # Check podcast:transcript tags exist
        ns = {"podcast": "https://podcastindex.org/namespace/1.0"}
        for i, item in enumerate(items):
            transcript = item.find("podcast:transcript", ns)
            assert transcript is not None
            assert transcript.get("url") == CHAPTERS[i]["transcript_url"]
