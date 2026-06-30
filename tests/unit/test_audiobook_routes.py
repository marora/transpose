"""Tests for audiobook consumer routes (aiohttp)."""

import xml.etree.ElementTree as ET

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from transpose.api.audiobook_routes import AudiobookMeta, register_audiobook_routes

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


@pytest.fixture
def app():
    """Create an aiohttp app with audiobook routes."""
    application = web.Application()
    register_audiobook_routes(application)
    application["audiobook_store"]["book-1"] = SAMPLE
    return application


@pytest.fixture
async def client(app, aiohttp_client):
    return await aiohttp_client(app)


async def test_get_audiobook_meta_200(client):
    r = await client.get("/books/book-1/audiobook")
    assert r.status == 200
    data = await r.json()
    assert data["title"] == "Test Book"
    assert len(data["chapters"]) == 2
    assert data["total_duration_ms"] == 550000


async def test_get_audiobook_meta_404(client):
    r = await client.get("/books/unknown/audiobook")
    assert r.status == 404


async def test_feed_xml(client):
    r = await client.get("/books/book-1/audiobook/feed.xml")
    assert r.status == 200
    assert "application/rss+xml" in r.headers["content-type"]
    content = await r.read()
    root = ET.fromstring(content)
    assert root.tag == "rss"


async def test_chapter_redirect(client):
    r = await client.get("/books/book-1/audiobook/chapters/1", allow_redirects=False)
    assert r.status == 307
    assert r.headers["location"] == "https://blob.example.com/ch1.mp3"


async def test_listen_page_html(client):
    r = await client.get("/listen/book-1")
    assert r.status == 200
    assert "text/html" in r.headers["content-type"]
    text = await r.text()
    assert "Test Book" in text


async def test_listen_page_404(client):
    r = await client.get("/listen/unknown")
    assert r.status == 404
