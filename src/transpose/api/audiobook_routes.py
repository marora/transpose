"""Consumer download/share page routes for audiobooks (GitHub issue #128)."""

from __future__ import annotations

from typing import TypedDict
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response


class AudiobookMeta(TypedDict):
    book_id: str
    title: str
    author: str
    description: str
    language: str
    cover_art_url: str
    base_url: str
    chapters: list[dict]  # {number, title, duration_ms, file_size_bytes, audio_url, transcript_url}


def _fmt_duration(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _build_feed_xml(meta: AudiobookMeta, feed_url: str) -> bytes:
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = meta["title"]
    SubElement(channel, "description").text = meta["description"]
    SubElement(channel, "language").text = meta["language"]
    SubElement(channel, "link").text = feed_url
    SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author").text = meta["author"]
    if meta.get("cover_art_url"):
        SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}image", href=meta["cover_art_url"])
    for ch in meta["chapters"]:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = ch["title"]
        SubElement(item, "enclosure", url=ch["audio_url"], type="audio/mpeg", length=str(ch["file_size_bytes"]))
        SubElement(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration").text = _fmt_duration(ch["duration_ms"])
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(rss, encoding="unicode").encode()


def _build_html(meta: AudiobookMeta, feed_url: str) -> str:
    total_ms = sum(ch["duration_ms"] for ch in meta["chapters"])
    chapters_html = ""
    for ch in meta["chapters"]:
        dur = _fmt_duration(ch["duration_ms"])
        chapters_html += f"""<li>
<span class="ch-title">{ch['title']}</span><span class="ch-dur">{dur}</span>
<a href="{ch['audio_url']}" class="btn">&#9654; Play</a>
<a href="{ch['audio_url']}" download class="btn">&#11015; Download</a>
</li>"""
    podcast_link = "podcast://" + feed_url.replace("https://", "").replace("http://", "")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{meta['title']} - Audiobook</title>
<style>
*{{box-sizing:border-box}}body{{font-family:-apple-system,system-ui,sans-serif;max-width:600px;margin:0 auto;padding:1rem;background:#fafafa}}
h1{{font-size:1.4rem;margin-bottom:0}}p.author{{color:#555;margin-top:.2rem}}
.btn{{display:inline-block;padding:.3rem .6rem;margin:.2rem;background:#2563eb;color:#fff;text-decoration:none;border-radius:4px;font-size:.85rem}}
.btn:hover{{background:#1d4ed8}}
ul{{list-style:none;padding:0}}li{{padding:.6rem 0;border-bottom:1px solid #e5e7eb;display:flex;flex-wrap:wrap;align-items:center;gap:.4rem}}
.ch-title{{flex:1;min-width:120px}}.ch-dur{{color:#666;font-size:.85rem;width:60px}}
.subscribe{{margin:1rem 0;text-align:center}}
.qr{{margin:1rem auto;padding:1rem;background:#fff;border:1px solid #ddd;text-align:center;max-width:200px;font-size:.75rem;color:#888}}
</style></head><body>
<h1>{meta['title']}</h1><p class="author">by {meta['author']}</p>
<p>{meta['description']}</p>
<p>Total duration: {_fmt_duration(total_ms)} &middot; {len(meta['chapters'])} chapters</p>
<div class="subscribe"><a href="{podcast_link}" class="btn">&#127911; Subscribe in Podcast App</a></div>
<div class="qr"><div>QR Code</div><small>{feed_url}</small></div>
<ul>{chapters_html}</ul>
</body></html>"""


def create_audiobook_router(audiobook_store: dict[str, AudiobookMeta]) -> APIRouter:
    router = APIRouter()

    def _get(book_id: str) -> AudiobookMeta:
        meta = audiobook_store.get(book_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Audiobook not found")
        return meta

    @router.get("/books/{book_id}/audiobook")
    def get_audiobook_meta(book_id: str, request: Request):
        meta = _get(book_id)
        feed_url = str(request.url_for("get_audiobook_feed", book_id=book_id))
        total_ms = sum(ch["duration_ms"] for ch in meta["chapters"])
        return {
            "book_id": meta["book_id"],
            "title": meta["title"],
            "author": meta["author"],
            "total_duration_ms": total_ms,
            "feed_url": feed_url,
            "chapters": meta["chapters"],
        }

    @router.get("/books/{book_id}/audiobook/feed.xml", name="get_audiobook_feed")
    def get_audiobook_feed(book_id: str, request: Request):
        meta = _get(book_id)
        feed_url = str(request.url)
        xml = _build_feed_xml(meta, feed_url)
        return Response(content=xml, media_type="application/rss+xml")

    @router.get("/books/{book_id}/audiobook/chapters/{chapter_number}")
    def get_chapter_redirect(book_id: str, chapter_number: int):
        meta = _get(book_id)
        for ch in meta["chapters"]:
            if ch["number"] == chapter_number:
                return RedirectResponse(url=ch["audio_url"], status_code=307)
        raise HTTPException(status_code=404, detail="Chapter not found")

    @router.get("/listen/{book_id}")
    def listen_page(book_id: str, request: Request):
        meta = _get(book_id)
        feed_url = str(request.url_for("get_audiobook_feed", book_id=book_id))
        html = _build_html(meta, feed_url)
        return HTMLResponse(content=html)

    return router
