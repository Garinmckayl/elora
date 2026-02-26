"""
Push notification service for Elora.

Uses Expo's push notification service to send notifications to the user's device.
Device push tokens are stored in Firestore at:
  users/{user_id}/device/push_token

The app registers its Expo push token on startup (see useExpoPush hook).
The backend stores it here and uses it when reminders fire or Elora
wants to proactively reach the user.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("elora.push")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# ── Firestore ────────────────────────────────────────────────────────────────
_db = None
_project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")

try:
    if _project:
        from google.cloud import firestore
        _db = firestore.Client(project=_project)
except Exception as e:
    logger.warning(f"[Push] Firestore unavailable: {e}")

# In-memory fallback
_mem_tokens: dict[str, str] = {}


# ── Token management ─────────────────────────────────────────────────────────

def store_push_token(user_id: str, expo_token: str) -> None:
    """Store the user's Expo push token (called by the app on startup)."""
    _mem_tokens[user_id] = expo_token
    if _db:
        try:
            _db.collection("users").document(user_id).collection("device").document("push_token").set({
                "expo_token": expo_token,
                "updated_at": __import__("datetime").datetime.utcnow().isoformat(),
            })
            logger.info(f"[Push] Token stored for user={user_id}")
        except Exception as e:
            logger.error(f"[Push] Firestore store error: {e}")


def get_push_token(user_id: str) -> Optional[str]:
    """Get the stored Expo push token for a user."""
    if user_id in _mem_tokens:
        return _mem_tokens[user_id]
    if _db:
        try:
            doc = _db.collection("users").document(user_id).collection("device").document("push_token").get()
            if doc.exists:
                token = doc.to_dict().get("expo_token")
                if token:
                    _mem_tokens[user_id] = token
                    return token
        except Exception as e:
            logger.error(f"[Push] Firestore get error: {e}")
    return None


# ── Send notification ────────────────────────────────────────────────────────

async def send_push_notification(
    user_id: str,
    message: str,
    title: str = "Elora",
    data: Optional[dict] = None,
) -> bool:
    """
    Send a push notification to the user's device via Expo.

    Returns True if sent successfully, False otherwise.
    """
    token = get_push_token(user_id)
    if not token:
        logger.warning(f"[Push] No push token for user={user_id}, cannot send notification")
        return False

    payload = {
        "to": token,
        "title": title,
        "body": message,
        "sound": "default",
        "priority": "high",
    }
    if data:
        payload["data"] = data

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                EXPO_PUSH_URL,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            result = resp.json()
            if result.get("data", {}).get("status") == "ok":
                logger.info(f"[Push] Sent to user={user_id}: '{message[:50]}'")
                return True
            else:
                logger.warning(f"[Push] Expo error for user={user_id}: {result}")
                return False
    except Exception as e:
        logger.error(f"[Push] Send error for user={user_id}: {e}")
        return False
