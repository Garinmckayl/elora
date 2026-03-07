"""
Multimodal Memory Ingestion for Elora.

Extracts structured text/facts from non-text content (images, audio, video, PDFs)
using Gemini's multimodal capabilities, then feeds the extracted information into
Elora's existing memory pipeline (MemU → Firestore → in-memory fallback).

This gives Elora the ability to *remember* what she sees, hears, and reads —
not just respond to it in the moment.

Supported modalities:
  - Images (JPEG, PNG, GIF, WebP): scene description, text extraction (OCR),
    objects, people, locations
  - Audio (MP3, WAV, OGG, FLAC): transcription + key facts extraction
  - Video (MP4, WebM, MOV): frame sampling + audio transcription + key facts
  - Documents (PDF): text extraction + summarization

Usage:
  from tools.multimodal_memory import ingest_to_memory

  # From raw bytes (e.g., camera frame, uploaded file)
  result = await ingest_to_memory(
      user_id="abc123",
      data=jpeg_bytes,
      mime_type="image/jpeg",
      source="camera during live call",
  )

  # From a GCS URI
  result = await ingest_to_memory_from_gcs(
      user_id="abc123",
      gcs_uri="gs://bucket/users/abc123/photo.jpg",
      mime_type="image/jpeg",
      source="uploaded photo",
  )

Inspired by Google's Always-On Memory Agent multimodal ingestion pipeline,
adapted to work within Elora's MemU + Firestore memory stack.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger("elora.multimodal_memory")

# ── Gemini client ────────────────────────────────────────────────────────────
_genai_client = None
try:
    from google import genai as _genai
    _genai_client = _genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))
except Exception as e:
    logger.warning(f"[MultimodalMemory] Gemini client unavailable: {e}")

# ── Supported MIME types ─────────────────────────────────────────────────────
IMAGE_MIMES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "image/bmp", "image/svg+xml",
}
AUDIO_MIMES = {
    "audio/mpeg", "audio/wav", "audio/ogg", "audio/flac",
    "audio/mp4", "audio/aac",
}
VIDEO_MIMES = {
    "video/mp4", "video/webm", "video/quicktime",
    "video/x-msvideo", "video/x-matroska",
}
DOCUMENT_MIMES = {
    "application/pdf",
}
ALL_SUPPORTED_MIMES = IMAGE_MIMES | AUDIO_MIMES | VIDEO_MIMES | DOCUMENT_MIMES

# ── Extension to MIME mapping ────────────────────────────────────────────────
EXT_TO_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
    ".flac": "audio/flac", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".avi": "video/x-msvideo", ".mkv": "video/x-matroska",
    ".pdf": "application/pdf",
}

# ── Size limits ──────────────────────────────────────────────────────────────
MAX_BYTES_IMAGE = 20 * 1024 * 1024     # 20 MB
MAX_BYTES_AUDIO = 25 * 1024 * 1024     # 25 MB
MAX_BYTES_VIDEO = 50 * 1024 * 1024     # 50 MB (Gemini supports up to ~2GB but we cap)
MAX_BYTES_DOC = 20 * 1024 * 1024       # 20 MB


# ── Extraction prompts ───────────────────────────────────────────────────────

IMAGE_EXTRACTION_PROMPT = """You are a memory extraction engine for a personal AI assistant.

Analyze this image and extract ALL information that would be useful to remember about the user's life.

Extract:
1. SCENE: What's happening? Where is this? What time of day does it seem like?
2. PEOPLE: Who is visible? Describe them (but don't guess names unless text/nametags are visible).
3. TEXT: Any text visible in the image (signs, screens, documents, labels, menus).
4. OBJECTS: Notable objects, food, products, brands.
5. EMOTIONAL CONTEXT: What mood or occasion does this suggest?
6. PERSONAL FACTS: Any facts about the user's life this reveals (location, activity, preferences).

Return a concise paragraph (3-5 sentences) of the most important, memorable facts.
Focus on what a personal AI should remember for future conversations.
Do NOT describe the image technically. Write as if noting down what happened."""

AUDIO_EXTRACTION_PROMPT = """You are a memory extraction engine for a personal AI assistant.

Listen to this audio and extract ALL information that would be useful to remember about the user's life.

Extract:
1. CONTENT: What is being said? Who is speaking?
2. KEY FACTS: Names, dates, numbers, plans, decisions mentioned.
3. EMOTIONAL TONE: How do the speakers sound? Stressed? Happy? Planning something?
4. ACTION ITEMS: Any tasks, reminders, or commitments mentioned.
5. PERSONAL DETAILS: Preferences, relationships, plans revealed.

Return a concise paragraph (3-5 sentences) of the most important, memorable facts.
Focus on what a personal AI should remember for future conversations."""

VIDEO_EXTRACTION_PROMPT = """You are a memory extraction engine for a personal AI assistant.

Watch this video and extract ALL information that would be useful to remember about the user's life.

Extract:
1. WHAT HAPPENED: Summarize the key events/content.
2. PEOPLE: Who appears? What are they doing?
3. SPOKEN CONTENT: Key things said (names, plans, facts, decisions).
4. VISUAL DETAILS: Location, objects, food, brands, text visible.
5. PERSONAL RELEVANCE: What does this reveal about the user's life, interests, or plans?

Return a concise paragraph (3-5 sentences) of the most important, memorable facts.
Focus on what a personal AI should remember for future conversations."""

DOCUMENT_EXTRACTION_PROMPT = """You are a memory extraction engine for a personal AI assistant.

Read this document and extract ALL information that would be useful to remember about the user's life.

Extract:
1. DOCUMENT TYPE: What kind of document is this? (receipt, letter, report, medical, legal, etc.)
2. KEY FACTS: Names, dates, amounts, addresses, reference numbers.
3. PERSONAL RELEVANCE: How does this relate to the user? What should their AI remember?
4. ACTION ITEMS: Any deadlines, follow-ups, or things to track.

Return a concise paragraph (3-5 sentences) of the most important, memorable facts.
Focus on what a personal AI should remember for future conversations.
Preserve exact names, dates, numbers, and reference codes verbatim."""


# ── Public API ───────────────────────────────────────────────────────────────

async def ingest_to_memory(
    user_id: str,
    data: bytes,
    mime_type: str,
    source: str = "",
    context: str = "",
) -> dict:
    """
    Extract structured information from multimodal content and store it in memory.

    Args:
        user_id: The user's uid.
        data: Raw bytes of the content (image, audio, video, PDF).
        mime_type: MIME type of the content.
        source: Description of where this came from (e.g., "camera", "uploaded file").
        context: Optional conversation context to help interpret the content.

    Returns:
        dict with status, extracted text, and memory storage result.
    """
    if not _genai_client:
        return {"status": "error", "error": "Gemini client not available"}

    if mime_type not in ALL_SUPPORTED_MIMES:
        return {"status": "error", "error": f"Unsupported MIME type: {mime_type}"}

    # Check size limits
    max_size = _get_max_size(mime_type)
    if len(data) > max_size:
        return {
            "status": "error",
            "error": f"File too large ({len(data)} bytes, max {max_size})",
        }

    try:
        # Extract text/facts using Gemini multimodal
        extracted = await asyncio.to_thread(
            _extract_from_content, data, mime_type, context
        )

        if not extracted or len(extracted) < 20:
            return {
                "status": "no_content",
                "note": "Could not extract meaningful information from this content.",
            }

        # Store the extracted facts in memory
        source_label = f" (from {source})" if source else ""
        memory_text = f"[Multimodal{source_label}] {extracted}"

        from tools.memory import save_memory
        save_result = save_memory(user_id, memory_text)

        logger.info(
            f"[MultimodalMemory] Ingested {mime_type} for user={user_id}: "
            f"'{extracted[:80]}...'"
        )

        return {
            "status": "success",
            "extracted": extracted,
            "memory_result": save_result,
            "mime_type": mime_type,
            "source": source,
        }

    except Exception as e:
        logger.error(f"[MultimodalMemory] Ingestion failed: {e}")
        return {"status": "error", "error": str(e)}


async def ingest_to_memory_from_gcs(
    user_id: str,
    gcs_uri: str,
    mime_type: str,
    source: str = "",
    context: str = "",
) -> dict:
    """
    Extract and memorize content from a GCS URI.
    Downloads the file from GCS first, then runs extraction.
    """
    try:
        from google.cloud import storage as gcs
        client = gcs.Client()

        # Parse gs://bucket/path
        if not gcs_uri.startswith("gs://"):
            return {"status": "error", "error": f"Invalid GCS URI: {gcs_uri}"}

        parts = gcs_uri[5:].split("/", 1)
        if len(parts) < 2:
            return {"status": "error", "error": f"Invalid GCS URI: {gcs_uri}"}

        bucket_name, blob_path = parts
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)

        if not blob.exists():
            return {"status": "error", "error": f"File not found: {gcs_uri}"}

        data = blob.download_as_bytes()
        return await ingest_to_memory(user_id, data, mime_type, source or gcs_uri, context)

    except ImportError:
        return {"status": "error", "error": "google-cloud-storage not available"}
    except Exception as e:
        logger.error(f"[MultimodalMemory] GCS ingestion failed: {e}")
        return {"status": "error", "error": str(e)}


async def extract_and_memorize_image(
    user_id: str,
    image_bytes: bytes,
    source: str = "camera",
    context: str = "",
) -> dict:
    """
    Convenience wrapper for image ingestion.
    Used by the live call vision loop and image message handler.
    """
    return await ingest_to_memory(
        user_id=user_id,
        data=image_bytes,
        mime_type="image/jpeg",
        source=source,
        context=context,
    )


def extract_and_memorize_image_sync(
    user_id: str,
    image_bytes: bytes,
    source: str = "camera",
    context: str = "",
) -> dict:
    """Synchronous wrapper for image ingestion (fire-and-forget calls)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Can't use run_until_complete in a running loop; schedule it
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    extract_and_memorize_image(user_id, image_bytes, source, context),
                )
                return future.result(timeout=30)
        return loop.run_until_complete(
            extract_and_memorize_image(user_id, image_bytes, source, context)
        )
    except Exception as e:
        logger.debug(f"[MultimodalMemory] Sync wrapper failed: {e}")
        return {"status": "error", "error": str(e)}


# ── Internal extraction ──────────────────────────────────────────────────────

def _extract_from_content(
    data: bytes,
    mime_type: str,
    context: str = "",
) -> str:
    """
    Use Gemini to extract structured information from multimodal content.
    Returns a text string of extracted facts.
    """
    from google.genai import types

    # Select the appropriate extraction prompt
    prompt = _get_extraction_prompt(mime_type)
    if context:
        prompt += f"\n\nADDITIONAL CONTEXT: {context}"

    # Build the multimodal content
    parts = [
        types.Part.from_bytes(data=data, mime_type=mime_type),
        types.Part.from_text(text=prompt),
    ]

    resp = _genai_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[types.Content(role="user", parts=parts)],
    )

    return (resp.text or "").strip()


def _get_extraction_prompt(mime_type: str) -> str:
    """Return the appropriate extraction prompt for the given MIME type."""
    if mime_type in IMAGE_MIMES:
        return IMAGE_EXTRACTION_PROMPT
    elif mime_type in AUDIO_MIMES:
        return AUDIO_EXTRACTION_PROMPT
    elif mime_type in VIDEO_MIMES:
        return VIDEO_EXTRACTION_PROMPT
    elif mime_type in DOCUMENT_MIMES:
        return DOCUMENT_EXTRACTION_PROMPT
    else:
        return IMAGE_EXTRACTION_PROMPT  # fallback


def _get_max_size(mime_type: str) -> int:
    """Return the max allowed bytes for a given MIME type."""
    if mime_type in IMAGE_MIMES:
        return MAX_BYTES_IMAGE
    elif mime_type in AUDIO_MIMES:
        return MAX_BYTES_AUDIO
    elif mime_type in VIDEO_MIMES:
        return MAX_BYTES_VIDEO
    elif mime_type in DOCUMENT_MIMES:
        return MAX_BYTES_DOC
    return MAX_BYTES_IMAGE  # fallback
