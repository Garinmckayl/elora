"""
Notification History — tracks all proactive notifications Elora sends.

Used by the proactive engine to:
  1. Avoid repeating the same notification
  2. Enforce daily frequency limits
  3. Track which notifications were opened (future: feedback loop)

Firestore path: users/{uid}/notifications/{auto_id}
  {
    signal_type: str,        # "meeting_soon", "birthday", "stale_contact", etc.
    message: str,            # what was sent
    channel: str,            # "push", "email", "in_app"
    sent_at: datetime,
    entity_ref: str,         # reference to what triggered it (event ID, person name, etc.)
    opened: bool,            # whether user tapped the notification
  }
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("elora.notification_history")

_db = None
_project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")

try:
    if _project:
        from google.cloud import firestore
        _db = firestore.Client(project=_project)
except Exception as e:
    logger.warning(f"[NotifHistory] Firestore unavailable: {e}")

# In-memory fallback
_mem_history: dict[str, list[dict]] = {}  # uid -> [notification dicts]

# ── Constants ────────────────────────────────────────────────────────────────
MAX_DAILY_NOTIFICATIONS = 3     # conservative: max proactive notifications per day
COOLDOWN_MINUTES = 60           # minimum minutes between any two proactive notifications
DEDUP_HOURS = 24                # don't re-notify about the same entity within this window


# ── Public API ───────────────────────────────────────────────────────────────

def record_notification(
    user_id: str,
    signal_type: str,
    message: str,
    channel: str = "push",
    entity_ref: str = "",
) -> str:
    """
    Record a sent notification. Returns the notification ID.
    """
    now = datetime.now(timezone.utc)
    entry = {
        "signal_type": signal_type,
        "message": message,
        "channel": channel,
        "entity_ref": entity_ref,
        "sent_at": now,
        "sent_at_iso": now.isoformat(),
        "opened": False,
    }

    if _db:
        try:
            doc_ref = (
                _db.collection("users").document(user_id)
                .collection("notifications").document()
            )
            doc_ref.set(entry)
            logger.info(f"[NotifHistory] Recorded: {signal_type} for user={user_id}")
            return doc_ref.id
        except Exception as e:
            logger.error(f"[NotifHistory] Record error: {e}")

    # In-memory fallback
    _mem_history.setdefault(user_id, []).append(entry)
    return f"mem_{len(_mem_history[user_id])}"


def get_recent_notifications(
    user_id: str,
    hours: int = 24,
    limit: int = 10,
) -> list[dict]:
    """Get recent notifications for a user within the last N hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    if _db:
        try:
            docs = (
                _db.collection("users").document(user_id)
                .collection("notifications")
                .where("sent_at", ">=", cutoff)
                .order_by("sent_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            return [doc.to_dict() for doc in docs if doc.to_dict()]
        except Exception as e:
            logger.error(f"[NotifHistory] Get recent error: {e}")

    # In-memory fallback
    entries = _mem_history.get(user_id, [])
    recent = [e for e in entries if e.get("sent_at", cutoff) >= cutoff]
    return sorted(recent, key=lambda x: x.get("sent_at", cutoff), reverse=True)[:limit]


def count_today_notifications(user_id: str) -> int:
    """Count how many proactive notifications were sent today."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if _db:
        try:
            docs = (
                _db.collection("users").document(user_id)
                .collection("notifications")
                .where("sent_at", ">=", start_of_day)
                .stream()
            )
            return sum(1 for _ in docs)
        except Exception as e:
            logger.error(f"[NotifHistory] Count error: {e}")
            return 0

    entries = _mem_history.get(user_id, [])
    return sum(1 for e in entries if e.get("sent_at", start_of_day) >= start_of_day)


def time_since_last_notification(user_id: str) -> Optional[timedelta]:
    """Return the time since the last proactive notification, or None if never."""
    recent = get_recent_notifications(user_id, hours=48, limit=1)
    if not recent:
        return None
    last_sent = recent[0].get("sent_at")
    if not last_sent:
        return None
    if isinstance(last_sent, datetime):
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last_sent
    return None


def was_recently_notified_about(user_id: str, entity_ref: str) -> bool:
    """
    Check if we already notified about this entity (person, event, etc.)
    within the dedup window.
    """
    if not entity_ref:
        return False

    recent = get_recent_notifications(user_id, hours=DEDUP_HOURS, limit=50)
    for notif in recent:
        if notif.get("entity_ref", "") == entity_ref:
            return True
    return False


def can_send_notification(user_id: str) -> tuple[bool, str]:
    """
    Check if we're allowed to send another proactive notification.
    Returns (allowed: bool, reason: str).
    """
    # Check daily limit
    today_count = count_today_notifications(user_id)
    if today_count >= MAX_DAILY_NOTIFICATIONS:
        return False, f"Daily limit reached ({today_count}/{MAX_DAILY_NOTIFICATIONS})"

    # Check cooldown
    since_last = time_since_last_notification(user_id)
    if since_last is not None and since_last < timedelta(minutes=COOLDOWN_MINUTES):
        remaining = COOLDOWN_MINUTES - int(since_last.total_seconds() / 60)
        return False, f"Cooldown active ({remaining} min remaining)"

    return True, "ok"


def mark_opened(user_id: str, notification_id: str) -> bool:
    """Mark a notification as opened/tapped by the user."""
    if _db:
        try:
            (
                _db.collection("users").document(user_id)
                .collection("notifications").document(notification_id)
                .update({"opened": True})
            )
            return True
        except Exception as e:
            logger.error(f"[NotifHistory] Mark opened error: {e}")
    return False
