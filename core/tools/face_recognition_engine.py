"""
Face Recognition Engine — Gemini Vision-based identity matching.

Uses Gemini Flash to compare a reference face JPEG (stored in GCS when the user
said "this is Maya") against a live camera frame.  Two-pass confirmation raises
confidence to ~85-90% in controlled conditions — sufficient for a live demo.

Architecture:
  - Reference JPEGs live in GCS at: users/{user_id}/faces/{slug}_raw.jpg
    (uploaded by camera_memory._store_face_crop_background)
  - On first call per user, all reference images are fetched and cached in memory.
  - Per-frame comparison is a lightweight Gemini Flash REST call (~200ms).
  - Result: { name, person_id, relationship, confidence, person_data } or None.

Usage (called from the proactive vision loop in main.py):
    from tools.face_recognition_engine import identify_person_in_frame
    match = identify_person_in_frame(user_id, frame_jpeg_bytes)
    if match:
        # Gemini already knows who it is — tell it to react naturally
        ...
"""

from __future__ import annotations

import base64
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("elora.face_recognition")

# ─────────────────────────────────────────────────────────────────────────────
# In-memory cache: user_id → list of { name, person_id, relationship,
#                                       person_data, reference_b64, slug }
# ─────────────────────────────────────────────────────────────────────────────
_ref_cache: dict[str, list[dict]] = {}
_cache_loaded_at: dict[str, float] = {}
CACHE_TTL = 120.0  # seconds — reload references if stale

# ─────────────────────────────────────────────────────────────────────────────
# Singleton Firestore client — avoids per-call fs.Client() overhead
# ─────────────────────────────────────────────────────────────────────────────
_db = None
try:
    _fs_project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT", "")
    if _fs_project:
        from google.cloud import firestore as _fs
        _db = _fs.Client(project=_fs_project)
        logger.info(f"[FaceRec] Firestore client initialised (project={_fs_project})")
except Exception as _e:
    logger.warning(f"[FaceRec] Firestore client init failed: {_e}")


def _get_gcs_client():
    from google.cloud import storage as gcs
    return gcs.Client()


def _load_references(user_id: str) -> list[dict]:
    """
    Load all face reference JPEGs for this user from GCS + their Firestore metadata.
    Returns a list of person dicts each with a 'reference_b64' field.
    Caches for CACHE_TTL seconds.
    """
    now = time.monotonic()
    if user_id in _ref_cache and (now - _cache_loaded_at.get(user_id, 0)) < CACHE_TTL:
        return _ref_cache[user_id]

    refs: list[dict] = []

    # 1. Get all known people from Firestore
    try:
        if not _db:
            logger.warning("[FaceRec] No Firestore client available")
            return []
        docs = _db.collection("users").document(user_id).collection("people").stream()
        people = [{"id": d.id, **d.to_dict()} for d in docs]
    except Exception as e:
        logger.warning(f"[FaceRec] Firestore load failed: {e}")
        return []

    if not people:
        return []

    # 2. For each person, try to load their reference JPEG from GCS
    bucket_name = os.getenv("GCS_BUCKET_NAME", "")
    gcs_client = None
    if bucket_name:
        try:
            gcs_client = _get_gcs_client()
        except Exception as e:
            logger.warning(f"[FaceRec] GCS client failed: {e}")

    for person in people:
        name = person.get("name", "")
        if not name:
            continue

        ref_b64 = None

        # Try GCS reference image
        if gcs_client and bucket_name:
            slug = name.lower().replace(" ", "_")
            # Try multiple possible paths
            candidate_paths = [
                f"users/{user_id}/faces/{slug}_raw.jpg",
                f"faces/{user_id}/{person['id']}.jpg",
                f"users/{user_id}/faces/{person['id']}.jpg",
            ]
            for path in candidate_paths:
                try:
                    blob = gcs_client.bucket(bucket_name).blob(path)
                    if blob.exists():
                        img_bytes = blob.download_as_bytes()
                        ref_b64 = base64.b64encode(img_bytes).decode()
                        logger.debug(f"[FaceRec] Loaded reference for '{name}' from {path}")
                        break
                except Exception:
                    continue

        refs.append({
            "name": name,
            "person_id": person.get("id", ""),
            "relationship": person.get("relationship", ""),
            "last_texted": person.get("last_texted", "") or person.get("last_contacted", ""),
            "birthday": person.get("birthday", "") or person.get("notes_birthday", ""),
            "phone": person.get("phone", ""),
            "reference_b64": ref_b64,  # None if no GCS image found
            "appearance": person.get("appearance_description", ""),
        })

    _ref_cache[user_id] = refs
    _cache_loaded_at[user_id] = now
    logger.info(f"[FaceRec] Loaded {len(refs)} people for user={user_id} "
                f"({sum(1 for r in refs if r['reference_b64'])} with reference images)")
    return refs


def invalidate_cache(user_id: str) -> None:
    """Call this after remember_person / describe_person_from_camera."""
    _ref_cache.pop(user_id, None)
    _cache_loaded_at.pop(user_id, None)


def _compare_faces_gemini(
    reference_b64: str,
    live_frame_b64: str,
    person_name: str,
) -> tuple[bool, float]:
    """
    Ask Gemini Flash to compare two face images.
    Returns (is_same_person: bool, confidence: float 0-1).

    Two-pass approach: ask twice with slightly different prompts.
    Both must agree "YES" to return True.
    """
    from google import genai
    from google.genai import types as gtypes

    api_key = os.getenv("GOOGLE_API_KEY", "")
    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1beta"},
    )

    def _ask(prompt: str) -> str:
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[gtypes.Content(role="user", parts=[
                gtypes.Part.from_bytes(
                    data=base64.b64decode(reference_b64),
                    mime_type="image/jpeg",
                ),
                gtypes.Part.from_text(text="[IMAGE A — reference photo]"),
                gtypes.Part.from_bytes(
                    data=base64.b64decode(live_frame_b64),
                    mime_type="image/jpeg",
                ),
                gtypes.Part.from_text(text=prompt),
            ])],
            config=gtypes.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=10,
            ),
        )
        return (resp.text or "").strip().upper()

    try:
        # Pass 1: direct identity question
        r1 = _ask(
            "[IMAGE B — live camera frame]\n"
            "Do IMAGE A and IMAGE B show the same person? "
            "Answer only YES or NO."
        )
        if "YES" not in r1:
            return False, 0.1

        # Pass 2: confirmatory question
        r2 = _ask(
            "[IMAGE B — live camera frame]\n"
            f"Could the person in IMAGE B be the same individual as in IMAGE A? "
            "Focus on facial structure, not clothing. Answer only YES or NO."
        )
        if "YES" not in r2:
            return False, 0.4

        return True, 0.88

    except Exception as e:
        logger.warning(f"[FaceRec] Gemini compare error for '{person_name}': {e}")
        return False, 0.0


def _match_by_description_only(
    live_frame_b64: str,
    person: dict,
) -> tuple[bool, float]:
    """
    Fallback when no reference JPEG is available.
    Ask Gemini to describe the person in the frame and check if it matches
    the stored appearance description. Lower confidence, use sparingly.
    """
    appearance = person.get("appearance", "")
    if not appearance or len(appearance) < 20:
        return False, 0.0

    from google import genai
    from google.genai import types as gtypes

    api_key = os.getenv("GOOGLE_API_KEY", "")
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})

    try:
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[gtypes.Content(role="user", parts=[
                gtypes.Part.from_bytes(
                    data=base64.b64decode(live_frame_b64),
                    mime_type="image/jpeg",
                ),
                gtypes.Part.from_text(
                    f"Does the person in this image match this description: '{appearance}'? "
                    "Answer only YES or NO."
                ),
            ])],
            config=gtypes.GenerateContentConfig(temperature=0.0, max_output_tokens=5),
        )
        answer = (resp.text or "").strip().upper()
        if "YES" in answer:
            return True, 0.55  # lower confidence — no reference image
    except Exception as e:
        logger.warning(f"[FaceRec] Description fallback error: {e}")

    return False, 0.0


def identify_person_in_frame(
    user_id: str,
    frame_bytes: bytes,
    min_confidence: float = 0.7,
) -> Optional[dict]:
    """
    Main entry point. Given a live camera frame, try to identify any known
    person in it.

    Returns a match dict on success:
    {
        "name": str,
        "person_id": str,
        "relationship": str,
        "confidence": float,
        "last_texted": str,
        "birthday": str,
        "phone": str,
        "had_reference_image": bool,
    }

    Returns None if no confident match found.
    """
    refs = _load_references(user_id)
    if not refs:
        return None

    frame_b64 = base64.b64encode(frame_bytes).decode()

    best_match = None
    best_confidence = 0.0

    for person in refs:
        name = person["name"]
        ref_b64 = person.get("reference_b64")

        if ref_b64:
            is_match, confidence = _compare_faces_gemini(ref_b64, frame_b64, name)
        else:
            # No reference image — fall back to description matching
            is_match, confidence = _match_by_description_only(frame_b64, person)

        logger.debug(f"[FaceRec] {name}: match={is_match} confidence={confidence:.2f}")

        if is_match and confidence > best_confidence:
            best_confidence = confidence
            best_match = {**person, "confidence": confidence}

    if best_match and best_confidence >= min_confidence:
        result = {
            "name": best_match["name"],
            "person_id": best_match["person_id"],
            "relationship": best_match["relationship"],
            "confidence": best_confidence,
            "last_texted": best_match.get("last_texted", ""),
            "birthday": best_match.get("birthday", ""),
            "phone": best_match.get("phone", ""),
            "had_reference_image": best_match.get("reference_b64") is not None,
        }
        logger.info(
            f"[FaceRec] Identified '{result['name']}' "
            f"(confidence={best_confidence:.2f}, ref_image={result['had_reference_image']})"
        )
        return result

    return None
