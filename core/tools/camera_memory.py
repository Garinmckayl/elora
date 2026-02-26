"""
Camera Memory -- Gemini Vision integration for face/people memory.

Stores the most recently received camera frame per user (in memory on the server).
When the user says "this is Maya" while the live camera is active, the agent calls
describe_and_remember_person() which:
  1. Grabs the last frame stored for this user
  2. Runs Gemini Vision to generate a detailed appearance description
  3. Stores the description in the people collection via tools.people

Frame storage:
  _last_frames: dict[user_id, bytes]  -- raw JPEG bytes, max 1 per user at a time
  Updated by main.py whenever a video_frame message arrives.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger("elora.camera_memory")

# In-memory store: user_id -> JPEG bytes of the most recent camera frame
_last_frames: dict[str, bytes] = {}


def store_frame(user_id: str, jpeg_bytes: bytes) -> None:
    """Called by the WebSocket handler every time a video_frame arrives."""
    _last_frames[user_id] = jpeg_bytes


def get_last_frame(user_id: str) -> Optional[bytes]:
    """Return the most recent camera frame for this user, or None."""
    return _last_frames.get(user_id)


def describe_and_remember_person(
    user_id: str,
    name: str,
    relationship: str = "",
) -> dict:
    """
    Use Gemini Vision to describe the person in the most recent camera frame,
    then store the description in people memory.

    Called by the describe_person_from_camera agent tool.

    Args:
        user_id:      The user's uid (injected by agent wrapper).
        name:         Name of the person visible in the camera.
                      Pass "me" if the user is showing themselves.
        relationship: Their relationship to the user (optional if already stored).

    Returns:
        dict: {
            "status": "ok",
            "description": str,   # appearance description
            "person_id": str,
        }
        or {"status": "no_frame", "note": "..."}
        or {"status": "error",    "error": str}
    """
    frame_bytes = get_last_frame(user_id)
    if not frame_bytes:
        return {
            "status": "no_frame",
            "note": (
                "I don't have a camera frame yet. "
                "Make sure the camera is active (tap the CAM button during a call) "
                "and try again."
            ),
        }

    # --- Gemini Vision: describe the person ---
    try:
        from google import genai
        from google.genai import types

        api_key = os.getenv("GOOGLE_API_KEY", "")
        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"},
        )

        prompt = (
            f"Describe the person in this image in detail for a personal AI that wants to "
            f"remember what they look like. Focus on:\n"
            f"- Hair colour and style\n"
            f"- Eye colour if visible\n"
            f"- Approximate age range\n"
            f"- Skin tone\n"
            f"- Height/build impression if visible\n"
            f"- Distinctive features (glasses, beard, freckles, tattoos, etc.)\n"
            f"- What they are wearing in this photo\n\n"
            f"Be specific and concise. If no person is clearly visible, say so.\n"
            f"Do NOT include their name — only physical description."
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=frame_bytes, mime_type="image/jpeg"),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ],
        )
        description = (response.text or "").strip()

        if not description or "no person" in description.lower():
            return {
                "status": "no_person",
                "note": "I couldn't see a person clearly in the camera frame. Try pointing the camera directly at them.",
            }

        logger.info(f"[CameraMemory] Vision description for '{name}': {description[:80]}...")

        # Store a face reference crop for photo search (best-effort, non-blocking)
        _store_face_crop_background(frame_bytes, user_id, name)

    except Exception as e:
        logger.error(f"[CameraMemory] Gemini Vision error: {e}")
        return {"status": "error", "error": f"Vision analysis failed: {str(e)}"}

    # --- Store in people memory ---
    try:
        from tools.people import remember_person, update_person_appearance, _find_by_name

        # Handle "me" / self-portrait case
        actual_name = name
        actual_relationship = relationship or "self"

        if name.lower() in ("me", "myself", "i"):
            # Store as the user themselves
            # Try to get user's real name from profile
            actual_name = _get_user_real_name(user_id) or "User"
            actual_relationship = "self"

        # Check if person already exists — update appearance only, or create new
        existing = _find_by_name(user_id, actual_name)
        if existing:
            result = update_person_appearance(
                name=actual_name,
                appearance_description=description,
                user_id=user_id,
            )
            person_id = existing.get("id", "")
            action = "updated"
        else:
            result = remember_person(
                name=actual_name,
                relationship=actual_relationship,
                appearance_description=description,
                user_id=user_id,
            )
            person_id = result.get("person_id", "")
            action = "remembered"

        logger.info(f"[CameraMemory] {action.capitalize()} appearance for '{actual_name}' (user={user_id})")

        # Invalidate face recognition cache so the new/updated person is picked up immediately
        try:
            from tools.face_recognition_engine import invalidate_cache
            invalidate_cache(user_id)
        except Exception:
            pass

        return {
            "status": "ok",
            "name": actual_name,
            "description": description,
            "person_id": person_id,
            "action": action,
        }

    except Exception as e:
        logger.error(f"[CameraMemory] People store error: {e}")
        # Return description even if storing failed
        return {
            "status": "partial",
            "description": description,
            "error": f"Could describe but failed to store: {str(e)}",
        }


def _get_user_real_name(user_id: str) -> str | None:
    """Attempt to retrieve the user's real name from Firestore profile."""
    try:
        from google.cloud import firestore as fs
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
        if not project:
            return None
        db = fs.Client(project=project)
        doc = db.collection("user_profiles").document(user_id).get()
        if doc.exists:
            return doc.to_dict().get("name")
    except Exception:
        pass
    return None


def _store_face_crop_background(frame_bytes: bytes, user_id: str, person_name: str) -> None:
    """
    Fire-and-forget: upload the full frame as a face reference to GCS.
    The frame is the whole camera image — the /face/reference endpoint (called by the
    frontend useFaceMemory hook) handles the proper ML Kit crop.
    Here we do a best-effort direct GCS store of the raw frame so the backend
    compare endpoint can also work without client-side cropping.
    """
    import threading

    def _upload():
        try:
            bucket_name = os.getenv("GCS_BUCKET_NAME", "")
            if not bucket_name:
                return
            from google.cloud import storage as gcs
            client = gcs.Client()
            slug = person_name.lower().replace(" ", "_")
            blob_path = f"users/{user_id}/faces/{slug}_raw.jpg"
            blob = client.bucket(bucket_name).blob(blob_path)
            blob.upload_from_string(frame_bytes, content_type="image/jpeg")
            logger.info(f"[CameraMemory] Raw face frame stored: {blob_path}")
        except Exception as e:
            logger.warning(f"[CameraMemory] Face crop upload failed (non-fatal): {e}")

    threading.Thread(target=_upload, daemon=True).start()

