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
    """Synthesize a chapter to MP3 using Azure Speech REST API with AAD token."""
    import requests
    
    # Build SSML
    ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
    <voice name="{VOICE}">
        <prosody rate="-5%">
            <break time="1500ms"/>
            {_escape_ssml(chapter_title)}
            <break time="2000ms"/>
            {_escape_ssml(text)}
        </prosody>
    </voice>
</speak>"""
    
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
        audio_data = resp.content
        # Estimate duration from data size (16kHz, 32kbps mono MP3)
        duration_ms = len(audio_data) * 8 * 1000 // 32000
        return audio_data, duration_ms
    elif resp.status_code == 401:
        raise RuntimeError(f"Unauthorized (401): token may have expired")
    else:
        raise RuntimeError(f"TTS failed ({resp.status_code}): {resp.text[:200]}")


def _escape_ssml(text: str) -> str:
    """Escape text for SSML (basic XML escaping + paragraph breaks)."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
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
    
    for ch in chapters:
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
        
        # Upload to blob
        blob_name = f"audiobooks/{book_slug}/chapter-{ch['number']:03d}.mp3"
        blob_url = f"{STORAGE_URL}/output/{blob_name}"
        
        output_container.upload_blob(
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
    
    manifest_blob = f"audiobooks/{book_slug}/manifest.json"
    output_container.upload_blob(
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
