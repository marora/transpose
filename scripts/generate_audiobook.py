"""Generate audiobook from translated epub in Azure Blob Storage.

Usage: python scripts/generate_audiobook.py [--book Test_Hindi_Book|Vigyan_Bhairav_Tantra_Volume_1]

Reads the epub from the 'output' container, extracts chapters,
synthesizes audio via Azure Speech (AAD token auth), and uploads
MP3 files back to blob storage under audiobooks/<book_slug>/.
"""

import argparse
import asyncio
import io
import logging
import os
import re
import subprocess
import sys
import time
import ebooklib
from azure.identity import AzureCliCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from bs4 import BeautifulSoup
from ebooklib import epub

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

STORAGE_URL = "https://transposedevst.blob.core.windows.net"
SPEECH_REGION = "eastus"
SPEECH_RESOURCE_ID = "/subscriptions/8fe7b2f7-3f2f-47c0-9cc2-f653b2e312ab/resourceGroups/transpose-sc/providers/Microsoft.CognitiveServices/accounts/transpose-speech"
SPEECH_ENDPOINT = "https://transpose-speech.cognitiveservices.azure.com/"
VOICE = "en-US-AndrewMultilingualNeural"  # Multilingual Neural HD voice

# Azure AD resource for Cognitive Services
COGNITIVE_RESOURCE = "https://cognitiveservices.azure.com"


def get_speech_token() -> str:
    """Get AAD token for Azure Speech."""
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", COGNITIVE_RESOURCE, "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def extract_chapters_from_epub(epub_path: str) -> list[dict]:
    """Extract chapter text from epub file."""
    book = epub.read_epub(epub_path)
    
    title_meta = book.get_metadata("DC", "title")
    title = title_meta[0][0] if title_meta else "Unknown"
    
    chapters = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        name = item.get_name()
        # Skip nav and non-chapter content
        if "nav" in name.lower():
            continue
            
        soup = BeautifulSoup(item.get_body_content(), "html.parser")
        text = soup.get_text(separator="\n\n", strip=True)
        
        if text and len(text) > 50:
            # Try to extract chapter title from first heading
            heading = soup.find(["h1", "h2", "h3"])
            ch_title = heading.get_text(strip=True) if heading else name.replace(".xhtml", "").replace("_", " ").title()
            
            chapters.append({
                "number": len(chapters) + 1,
                "title": ch_title,
                "text": text,
                "source_file": name,
            })
    
    return {"title": title, "chapters": chapters}


def synthesize_chapter(text: str, chapter_title: str, token: str) -> tuple[bytes, int]:
    """Synthesize a chapter to MP3 using Azure Speech REST API with AAD token.
    
    Splits text into chunks of ~4000 chars at paragraph boundaries to avoid
    connection timeouts on long chapters.
    """
    import requests
    
    # Split into chunks at paragraph boundaries (~1500 chars each)
    MAX_CHUNK_CHARS = 1500
    chunks = _split_text_into_chunks(text, MAX_CHUNK_CHARS)
    
    all_audio = bytearray()
    
    for i, chunk in enumerate(chunks):
        # Only add title intro on first chunk
        title_ssml = f'{_escape_ssml(chapter_title)}<break time="2000ms"/>' if i == 0 else ""
        
        ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
    <voice name="{VOICE}">
        <prosody rate="-5%">
            <break time="1500ms"/>
            {title_ssml}
            {_escape_ssml(chunk)}
        </prosody>
    </voice>
</speak>"""
        
        for attempt in range(3):
            try:
                resp = requests.post(
                    f"{SPEECH_ENDPOINT}tts/cognitiveservices/v1",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
                    },
                    data=ssml.encode("utf-8"),
                    timeout=180,
                    stream=True,
                )
                # Read streamed response to avoid chunked encoding errors
                audio_chunk = b"".join(resp.iter_content(chunk_size=8192))
                resp._content = audio_chunk
                break
            except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError) as e:
                if attempt < 2:
                    import time as t
                    logger.warning(f"    Connection error on chunk {i+1}/{len(chunks)}, retry {attempt+1}...")
                    t.sleep(10 * (attempt + 1))
                    token = get_speech_token()
                else:
                    raise RuntimeError(f"TTS connection failed after 3 retries: {e}")
        
        if resp.status_code == 200:
            all_audio.extend(resp._content)
        elif resp.status_code == 401:
            raise RuntimeError(f"Unauthorized (401): token may have expired")
        elif resp.status_code == 429:
            # Rate limited — wait and retry
            import time as t
            logger.warning(f"    Rate limited on chunk {i+1}/{len(chunks)}, waiting 10s...")
            t.sleep(10)
            token = get_speech_token()  # Refresh token
            resp = requests.post(
                f"{SPEECH_ENDPOINT}tts/cognitiveservices/v1",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
                },
                data=ssml.encode("utf-8"),
                timeout=120,
            )
            if resp.status_code == 200:
                all_audio.extend(resp.content)
            else:
                raise RuntimeError(f"TTS failed after retry ({resp.status_code}): {resp.text[:200]}")
        else:
            raise RuntimeError(f"TTS failed ({resp.status_code}): {resp.text[:200]}")
    
    audio_data = bytes(all_audio)
    # Estimate duration from data size (16kHz, 32kbps mono MP3)
    duration_ms = len(audio_data) * 8 * 1000 // 32000
    return audio_data, duration_ms


def _split_text_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split text into chunks at paragraph boundaries.
    If a single paragraph exceeds max_chars, split it at sentence boundaries."""
    if len(text) <= max_chars:
        return [text]
    
    paragraphs = text.split("\n\n")
    chunks = []
    current = []
    current_len = 0
    
    for para in paragraphs:
        # If a single paragraph is too long, split at sentence boundaries
        if len(para) > max_chars:
            # Flush current buffer first
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            # Split long paragraph into sentences
            sentences = re.split(r'(?<=[।.!?])\s+', para)
            sent_buf = []
            sent_len = 0
            for sent in sentences:
                if sent_len + len(sent) > max_chars and sent_buf:
                    chunks.append(" ".join(sent_buf))
                    sent_buf = [sent]
                    sent_len = len(sent)
                else:
                    sent_buf.append(sent)
                    sent_len += len(sent) + 1
            if sent_buf:
                chunks.append(" ".join(sent_buf))
        elif current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para) + 2
    
    if current:
        chunks.append("\n\n".join(current))
    
    return chunks


def _escape_ssml(text: str) -> str:
    """Escape text for SSML (basic XML escaping + paragraph breaks).
    Wraps Devanagari (Hindi) runs in <lang xml:lang='hi-IN'> tags
    so the multilingual voice switches correctly."""
    # XML escape first (before adding SSML tags)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    # Wrap Devanagari runs in Hindi language tags
    text = re.sub(
        r"([\u0900-\u097F][\u0900-\u097F\s\.\,\!\?\;\:\-\u0964\u0965]*[\u0900-\u097F\.\u0964\u0965])",
        r'<lang xml:lang="hi-IN">\1</lang>',
        text,
    )
    # Convert paragraph breaks to SSML breaks
    text = re.sub(r"\n\n+", '\n<break time="600ms"/>\n', text)
    return text


def main():
    parser = argparse.ArgumentParser(description="Generate audiobook from translated epub")
    parser.add_argument("--book", default="Test_Hindi_Book", help="Book name (without extension)")
    args = parser.parse_args()
    
    book_name = args.book
    epub_blob = f"{book_name}.epub"
    
    logger.info(f"Starting audiobook generation for: {book_name}")
    
    # Connect to blob storage
    cred = AzureCliCredential()
    blob_client = BlobServiceClient(STORAGE_URL, credential=cred)
    output_container = blob_client.get_container_client("output")
    audiobooks_container = blob_client.get_container_client("audiobooks")
    
    # Download epub
    logger.info(f"Downloading {epub_blob} from blob storage...")
    epub_data = output_container.download_blob(epub_blob).readall()
    epub_path = f"/tmp/{book_name}.epub"
    with open(epub_path, "wb") as f:
        f.write(epub_data)
    
    # Extract chapters
    logger.info("Extracting chapters from epub...")
    book_data = extract_chapters_from_epub(epub_path)
    chapters = book_data["chapters"]
    title = book_data["title"]
    
    logger.info(f"Book: {title}, Chapters: {len(chapters)}")
    total_chars = sum(len(ch["text"]) for ch in chapters)
    logger.info(f"Total characters to synthesize: {total_chars:,}")
    
    # Estimate cost (Azure Neural TTS: $16/1M chars)
    est_cost = total_chars * 16 / 1_000_000
    logger.info(f"Estimated cost: ${est_cost:.4f}")
    
    # Get speech token
    logger.info("Acquiring Azure AD token for Speech...")
    token = get_speech_token()
    
    # Synthesize each chapter
    book_slug = book_name.lower().replace(" ", "_")
    audio_manifest = []
    
    # Check which chapters already exist (resume support)
    existing_chapters = set()
    try:
        for blob in audiobooks_container.list_blobs(name_starts_with=f"{book_slug}/chapter-"):
            # Extract chapter number from blob name like "book_slug/chapter-001.mp3"
            import re as _re
            m = _re.search(r"chapter-(\d+)\.mp3", blob.name)
            if m:
                existing_chapters.add(int(m.group(1)))
    except Exception:
        pass
    
    if existing_chapters:
        logger.info(f"Resuming: {len(existing_chapters)} chapters already uploaded, skipping them")

    for ch in chapters:
        # Skip already uploaded chapters (resume)
        if ch["number"] in existing_chapters:
            logger.info(f"  Skipping Chapter {ch['number']}: {ch['title']} (already uploaded)")
            # Still add to manifest from blob metadata
            blob_name = f"{book_slug}/chapter-{ch['number']:03d}.mp3"
            blob_props = audiobooks_container.get_blob_client(blob_name).get_blob_properties()
            audio_manifest.append({
                "number": ch["number"],
                "title": ch["title"],
                "blob_name": blob_name,
                "duration_ms": blob_props.size * 8 * 1000 // 32000,
                "file_size_bytes": blob_props.size,
                "chars": len(ch["text"]),
            })
            continue
        
        logger.info(f"  Synthesizing Chapter {ch['number']}: {ch['title']} ({len(ch['text'])} chars)...")
        
        try:
            audio_bytes, duration_ms = synthesize_chapter(ch["text"], ch["title"], token)
        except RuntimeError as e:
            logger.error(f"    FAILED: {e}")
            # Token might have expired — refresh
            if "Unauthorized" in str(e) or "401" in str(e):
                logger.info("    Refreshing token...")
                token = get_speech_token()
                audio_bytes, duration_ms = synthesize_chapter(ch["text"], ch["title"], token)
            else:
                raise
        
        # Upload to blob (dedicated audiobooks container)
        blob_name = f"{book_slug}/chapter-{ch['number']:03d}.mp3"
        
        audiobooks_container.upload_blob(
            blob_name,
            audio_bytes,
            content_settings=ContentSettings(content_type="audio/mpeg"),
            overwrite=True,
        )
        
        audio_manifest.append({
            "number": ch["number"],
            "title": ch["title"],
            "blob_name": blob_name,
            "duration_ms": duration_ms,
            "file_size_bytes": len(audio_bytes),
            "chars": len(ch["text"]),
        })
        
        logger.info(
            f"    ✓ Chapter {ch['number']}: {duration_ms/1000:.1f}s, "
            f"{len(audio_bytes)/1024:.0f} KB"
        )
    
    # Write manifest
    import json
    manifest = {
        "book_id": book_slug,
        "title": title,
        "chapters": audio_manifest,
        "total_duration_ms": sum(ch["duration_ms"] for ch in audio_manifest),
        "total_size_bytes": sum(ch["file_size_bytes"] for ch in audio_manifest),
        "voice": VOICE,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    
    manifest_blob = f"{book_slug}/manifest.json"
    audiobooks_container.upload_blob(
        manifest_blob,
        json.dumps(manifest, indent=2).encode(),
        content_settings=ContentSettings(content_type="application/json"),
        overwrite=True,
    )
    
    total_duration = manifest["total_duration_ms"]
    total_size = manifest["total_size_bytes"]
    logger.info(f"\n{'='*60}")
    logger.info(f"AUDIOBOOK COMPLETE: {title}")
    logger.info(f"  Chapters: {len(audio_manifest)}")
    logger.info(f"  Total duration: {total_duration/1000/60:.1f} minutes")
    logger.info(f"  Total size: {total_size/1024/1024:.1f} MB")
    logger.info(f"  Manifest: {manifest_blob}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
