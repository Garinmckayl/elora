"""
Morning briefing service for Elora.

Every morning at a user-configured time, Elora proactively pushes a
personalized briefing to the user's phone:
  - Good morning greeting
  - Today's calendar events
  - Unread email count + top sender
  - Any pending reminders due today
  - Optional: weather (if user location is stored in memory)

Users can set their briefing time by saying:
  "Hey Elora, give me a morning briefing every day at 8am"

Elora calls schedule_briefing(time="08:00") which persists the preference
in Firestore and the daily poller fires it automatically.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("elora.briefing")

_project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
_db = None

try:
    if _project:
        from google.cloud import firestore
        _db = firestore.Client(project=_project)
except Exception as e:
    logger.warning(f"[Briefing] Firestore unavailable: {e}")

# In-memory fallback: {user_id: {"time": "08:00", "timezone": "UTC"}}
_mem_prefs: dict[str, dict] = {}


# ── Preference management ─────────────────────────────────────────────────────

def set_briefing_preference(user_id: str, time: str, timezone_name: str = "UTC") -> dict:
    """
    Set the user's daily briefing time.

    Args:
        user_id:       The user's ID.
        time:          Time string in HH:MM 24h format (e.g. '08:00', '07:30').
        timezone_name: IANA timezone (e.g. 'America/New_York', 'Africa/Addis_Ababa').

    Returns:
        dict with status and confirmation.
    """
    pref = {
        "time": time,
        "timezone": timezone_name,
        "enabled": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _mem_prefs[user_id] = pref

    if _db:
        try:
            _db.collection("briefing_prefs").document(user_id).set(pref)
            logger.info(f"[Briefing] Set briefing for user={user_id} at {time} {timezone_name}")
        except Exception as e:
            logger.error(f"[Briefing] Firestore set error: {e}")

    return {
        "status": "success",
        "report": f"Morning briefing set for {time} {timezone_name} every day. I'll send you a summary of your day each morning.",
    }


def disable_briefing(user_id: str) -> dict:
    """Disable the daily morning briefing for a user."""
    if user_id in _mem_prefs:
        _mem_prefs[user_id]["enabled"] = False
    if _db:
        try:
            _db.collection("briefing_prefs").document(user_id).update({"enabled": False})
        except Exception as e:
            logger.error(f"[Briefing] Disable error: {e}")
    return {"status": "success", "report": "Morning briefing disabled."}


def get_briefing_preference(user_id: str) -> Optional[dict]:
    """Get briefing preference for a user."""
    if user_id in _mem_prefs:
        return _mem_prefs[user_id]
    if _db:
        try:
            doc = _db.collection("briefing_prefs").document(user_id).get()
            if doc.exists:
                pref = doc.to_dict()
                _mem_prefs[user_id] = pref
                return pref
        except Exception as e:
            logger.error(f"[Briefing] Get pref error: {e}")
    return None


# ── Briefing content builder ──────────────────────────────────────────────────

async def build_and_send_briefing(user_id: str, push_sender) -> None:
    """
    Compile and send the morning briefing for a user.
    Called by the daily briefing poller.
    """
    try:
        from tools.gmail import read_emails_sync
        from tools.calendar import list_events_sync
        from tools.reminders import list_reminders
        from tools.memory import search_memory

        pref = get_briefing_preference(user_id) or {}
        tz_name = pref.get("timezone", "UTC")

        # 1. Calendar events today
        cal = list_events_sync(user_id, date="today", timezone=tz_name)
        events = cal.get("events", [])

        # 2. Unread emails
        email_result = read_emails_sync(user_id, query="is:unread", max_results=5)
        emails = email_result.get("emails", [])
        unread_count = len(emails)
        top_sender = emails[0].get("from", "").split("<")[0].strip().strip('"') if emails else None

        # 3. Reminders due today
        reminders_result = list_reminders(user_id)
        reminders = reminders_result.get("reminders", [])
        today_str = datetime.now(timezone.utc).strftime("%b %d")
        due_today = [r for r in reminders if today_str in r.get("fire_at", "")]

        # 4. Build message
        now_utc = datetime.now(timezone.utc)
        # Use user's local timezone for greeting, not UTC
        try:
            from zoneinfo import ZoneInfo
            local_tz = ZoneInfo(tz_name)
            local_now = datetime.now(local_tz)
            hour = local_now.hour
        except Exception:
            hour = now_utc.hour
        greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"

        parts = [f"{greeting}! Here's your day:"]

        if events:
            event_strs = [f"{e['title']} at {e['start'].split('T')[1][:5] if 'T' in str(e['start']) else e['start']}" for e in events[:3]]
            parts.append(f"📅 {', '.join(event_strs)}")
        else:
            parts.append("📅 Nothing on your calendar today.")

        if unread_count > 0:
            if top_sender:
                parts.append(f"📧 {unread_count} unread email{'s' if unread_count > 1 else ''}, latest from {top_sender}.")
            else:
                parts.append(f"📧 {unread_count} unread email{'s' if unread_count > 1 else ''}.")

        if due_today:
            reminder_strs = [r["message"] for r in due_today[:2]]
            parts.append(f"⏰ Reminders today: {', '.join(reminder_strs)}")

        message = " ".join(parts)

        await push_sender(
            user_id=user_id,
            title="Elora — Good Morning",
            message=message,
            data={"type": "morning_briefing"},
        )
        logger.info(f"[Briefing] Sent to user={user_id}: {message[:80]}")

    except Exception as e:
        logger.error(f"[Briefing] Build error for user={user_id}: {e}")


# ── Daily poller ──────────────────────────────────────────────────────────────

async def briefing_poller(push_sender) -> None:
    """
    Checks every minute if any user's briefing time has arrived and fires it.
    Runs forever as an asyncio background task alongside the reminder poller.
    """
    # Track which users have already received a briefing today (reset at midnight)
    fired_today: dict[str, str] = {}  # {user_id: date_str}

    logger.info("[Briefing] Poller started")
    while True:
        try:
            await _check_and_brief(push_sender, fired_today)
        except Exception as e:
            logger.error(f"[Briefing] Poller error: {e}")
        await asyncio.sleep(60)  # check every minute


async def _check_and_brief(push_sender, fired_today: dict) -> None:
    now_utc = datetime.now(timezone.utc)
    today_date = now_utc.strftime("%Y-%m-%d")

    # Load all briefing prefs
    prefs = dict(_mem_prefs)  # local copy

    if _db:
        try:
            docs = _db.collection("briefing_prefs").where("enabled", "==", True).stream()
            for doc in docs:
                data = doc.to_dict() or {}
                if data.get("enabled"):
                    prefs[doc.id] = data
        except Exception as e:
            logger.error(f"[Briefing] Load prefs error: {e}")

    for user_id, pref in prefs.items():
        if not pref.get("enabled"):
            continue

        # Already fired today?
        if fired_today.get(user_id) == today_date:
            continue

        tz_name = pref.get("timezone", "UTC")
        brief_time = pref.get("time", "08:00")

        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tz_name)
            now_local = datetime.now(tz)
            local_hhmm = now_local.strftime("%H:%M")

            # Fire within the target minute
            if local_hhmm == brief_time:
                fired_today[user_id] = today_date
                asyncio.create_task(build_and_send_briefing(user_id, push_sender))
                logger.info(f"[Briefing] Fired for user={user_id} at {brief_time} {tz_name}")

        except Exception as e:
            logger.warning(f"[Briefing] Time check error for user={user_id}: {e}")
