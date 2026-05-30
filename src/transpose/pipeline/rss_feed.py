"""RSS feed generation for Transpose audiobook pipeline."""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone


ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
PODCAST_NS = "https://podcastindex.org/namespace/1.0"

BASE_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _duration_str(ms: int) -> str:
    """Convert milliseconds to HH:MM:SS."""
    total_seconds = ms // 1000
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _rfc2822(dt: datetime) -> str:
    """Format datetime as RFC 2822."""
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def generate_feed(
    book_id: str,
    title: str,
    author: str,
    description: str,
    language: str,
    cover_art_url: str,
    base_url: str,
    chapters: list[dict],
) -> str:
    """Generate a Podcast 2.0-compliant RSS feed for an audiobook."""
    ET.register_namespace("itunes", ITUNES_NS)
    ET.register_namespace("podcast", PODCAST_NS)

    rss = ET.Element("rss", version="2.0")

    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "description").text = description
    ET.SubElement(channel, "language").text = language
    ET.SubElement(channel, "link").text = base_url

    # iTunes channel tags
    ET.SubElement(channel, f"{{{ITUNES_NS}}}author").text = author
    img = ET.SubElement(channel, f"{{{ITUNES_NS}}}image")
    img.set("href", cover_art_url)
    cat = ET.SubElement(channel, f"{{{ITUNES_NS}}}category")
    cat.set("text", "Books")

    # Podcast 2.0 medium
    ET.SubElement(channel, f"{{{PODCAST_NS}}}medium").text = "audiobook"

    # Items (chapters ordered by number)
    sorted_chapters = sorted(chapters, key=lambda c: c["number"])

    for i, ch in enumerate(sorted_chapters):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = ch["title"]
        guid = ET.SubElement(item, "guid", isPermaLink="false")
        guid.text = f"{book_id}-chapter-{ch['number']}"

        pub_date = BASE_DATE + timedelta(minutes=i)
        ET.SubElement(item, "pubDate").text = _rfc2822(pub_date)

        enc = ET.SubElement(item, "enclosure")
        enc.set("url", ch["audio_url"])
        enc.set("type", "audio/mpeg")
        enc.set("length", str(ch["file_size_bytes"]))

        ET.SubElement(item, f"{{{ITUNES_NS}}}duration").text = _duration_str(ch["duration_ms"])
        ET.SubElement(item, f"{{{ITUNES_NS}}}author").text = author

        transcript = ET.SubElement(item, f"{{{PODCAST_NS}}}transcript")
        transcript.set("url", ch["transcript_url"])
        transcript.set("type", "application/srt")

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    xml_str = ET.tostring(rss, encoding="unicode", xml_declaration=True)
    return xml_str
