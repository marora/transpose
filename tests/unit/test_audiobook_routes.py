"""Tests for audiobook consumer routes."""

import xml.etree.ElementTree as ET

from fastapi import FastAPI
from fastapi.testclient import TestClient

from transpose.api.audiobook_routes import AudiobookMeta, create_audiobook_router

SAMPLE: AudiobookMeta = {
    "book_id": "book-1",
    "title": "Test Book",
    "author": "Jane Author",
    "description": "A test audiobook.",
    "language": "en",
    "cover_art_url": "https://example.com/cover.jpg",
    "base_url": "https://example.com",
    "chapters": [
        {"number": 1, "title": "Chapter 1", "duration_ms": 300000, "file_size_bytes": 4800000, "audio_url": "https://blob.example.com/ch1.mp3", "transcript_url": "https://blob.example.com/ch1.vtt"},
        {"number": 2, "title": "Chapter 2", "duration_ms": 250000, "file_size_bytes": 4000000, "audio_url": "https://blob.example.com/ch2.mp3", "transcript_url": "https://blob.example.com/ch2.vtt"},
    ],
}

store = {"book-1": SAMPLE}
app = FastAPI()
app.include_router(create_audiobook_router(store))
client = TestClient(app)


def test_get_audiobook_meta_200():
    r = client.get("/books/book-1/audiobook")
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Test Book"
    assert len(data["chapters"]) == 2
    assert data["total_duration_ms"] == 550000


def test_get_audiobook_meta_404():
    r = client.get("/books/unknown/audiobook")
    assert r.status_code == 404


def test_feed_xml():
    r = client.get("/books/book-1/audiobook/feed.xml")
    assert r.status_code == 200
    assert "application/rss+xml" in r.headers["content-type"]
    root = ET.fromstring(r.content)
    assert root.tag == "rss"


def test_chapter_redirect():
    r = client.get("/books/book-1/audiobook/chapters/1", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "https://blob.example.com/ch1.mp3"


def test_listen_page_html():
    r = client.get("/listen/book-1")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Test Book" in r.text


def test_listen_page_404():
    r = client.get("/listen/unknown")
    assert r.status_code == 404
