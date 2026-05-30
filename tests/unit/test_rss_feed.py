"""Tests for RSS feed generation."""

import xml.etree.ElementTree as ET

from transpose.pipeline.rss_feed import generate_feed, ITUNES_NS, PODCAST_NS


SAMPLE_CHAPTERS = [
    {
        "number": 2,
        "title": "Chapter 2",
        "duration_ms": 360000,
        "file_size_bytes": 5760000,
        "audio_url": "https://storage.blob.core.windows.net/audio/ch2.mp3",
        "transcript_url": "https://storage.blob.core.windows.net/transcripts/ch2.srt",
    },
    {
        "number": 1,
        "title": "Chapter 1",
        "duration_ms": 300000,
        "file_size_bytes": 4800000,
        "audio_url": "https://storage.blob.core.windows.net/audio/ch1.mp3",
        "transcript_url": "https://storage.blob.core.windows.net/transcripts/ch1.srt",
    },
]


def _generate(**kwargs):
    defaults = dict(
        book_id="book-42",
        title="Test Book",
        author="Jane Doe",
        description="A test audiobook",
        language="en",
        cover_art_url="https://example.com/cover.jpg",
        base_url="https://storage.blob.core.windows.net/feeds",
        chapters=SAMPLE_CHAPTERS,
    )
    defaults.update(kwargs)
    return generate_feed(**defaults)


def test_valid_xml():
    xml_str = _generate()
    assert xml_str.startswith("<?xml")
    root = ET.fromstring(xml_str)
    assert root.tag == "rss"


def test_itunes_tags_present():
    xml_str = _generate()
    root = ET.fromstring(xml_str)
    channel = root.find("channel")
    assert channel.find(f"{{{ITUNES_NS}}}author").text == "Jane Doe"
    assert channel.find(f"{{{ITUNES_NS}}}image").get("href") == "https://example.com/cover.jpg"
    assert channel.find(f"{{{ITUNES_NS}}}category").get("text") == "Books"
    # itunes:duration on items
    items = channel.findall("item")
    assert len(items) == 2
    for item in items:
        assert item.find(f"{{{ITUNES_NS}}}duration") is not None


def test_podcast_transcript_tags():
    xml_str = _generate()
    root = ET.fromstring(xml_str)
    items = root.find("channel").findall("item")
    for item in items:
        t = item.find(f"{{{PODCAST_NS}}}transcript")
        assert t is not None
        assert t.get("url").endswith(".srt")
        assert t.get("type") == "application/srt"


def test_enclosure_tags():
    xml_str = _generate()
    root = ET.fromstring(xml_str)
    items = root.find("channel").findall("item")
    for item in items:
        enc = item.find("enclosure")
        assert enc is not None
        assert enc.get("type") == "audio/mpeg"
        assert int(enc.get("length")) > 0


def test_chapter_ordering():
    xml_str = _generate()
    root = ET.fromstring(xml_str)
    items = root.find("channel").findall("item")
    guids = [item.find("guid").text for item in items]
    assert guids == ["book-42-chapter-1", "book-42-chapter-2"]


def test_empty_chapters():
    xml_str = _generate(chapters=[])
    root = ET.fromstring(xml_str)
    items = root.find("channel").findall("item")
    assert len(items) == 0
