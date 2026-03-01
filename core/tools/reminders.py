"""
Reminder / scheduler tool for Elora.

Reminders are stored in Firestore at:
  reminders/{user_id}/jobs/{job_id}

A background asyncio task polls every 30 seconds and fires any due reminders
by pushing an Expo push notification to the user's device token.

Tools exposed to the agent:
  schedule_reminder(message, when, repeat?)  → stores job
  list_reminders()                           → shows pending jobs
  cancel_reminder(job_id)                    → removes job
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("elora.reminders")

# ── Firestore ────────────────────────────────────────────────────────────────
_db = None
_project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")

try:
    if _project:
        from google.cloud import firestore
        _db = firestore.Client(project=_project)
        logger.info(f"[Reminders] Firestore ready (project={_project})")
    else:
        logger.warning("[Reminders] No GCP project — in-memory fallback")
except Exception as e:
    logger.warning(f"[Reminders] Firestore unavailable: {e}")

# In-memory fallback
_mem_reminders: dict[str, list[dict]] = {}


def _reminders_col(user_id: str):
    return _db.collection("reminders").document(user_id).collection("jobs")


# ── Public tool functions ────────────────────────────────────────────────────

def schedule_reminder(
    user_id: str,
    message: str,
    when: str,
    repeat: Optional[str] = None,
) -> dict:
    """
    Schedule a reminder for the user.

    Args:
        user_id: The user's ID.
        message: What Elora should say / send as notification.
        when:    ISO-8601 datetime string (e.g. '2026-03-15T09:00:00') or a
                 natural-language offset like '+2h', '+30m', '+1d'.
        repeat:  Optional repeat cadence: 'daily', 'weekly', or None.

    Returns:
        dict with status and job_id.
    """
    # Parse `when`
    fire_at = _parse_when(when)
    if fire_at is None:
        return {"status": "error", "report": f"Could not parse time: '{when}'. Use ISO format or '+2h', '+30m', '+1d'."}

    job_id = str(uuid.uuid4())[:8]
    job: dict = {
        "job_id": job_id,
        "user_id": user_id,
        "message": message,
        "fire_at": fire_at.isoformat(),
        "repeat": repeat,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fired": False,
    }

    if _db:
        try:
            _reminders_col(user_id).document(job_id).set(job)
            logger.info(f"[Reminders] Scheduled job={job_id} for {fire_at.isoformat()} user={user_id}")
        except Exception as e:
            logger.error(f"[Reminders] Firestore save error: {e}")
    else:
        _mem_reminders.setdefault(user_id, []).append(job)

    fire_str = fire_at.strftime("%b %d at %I:%M %p UTC")
    return {
        "status": "success",
        "report": f"Reminder set for {fire_str}: \"{message}\"",
        "job_id": job_id,
        "fire_at": fire_at.isoformat(),
    }


def list_reminders(user_id: str) -> dict:
    """List pending (not yet fired) reminders for the user."""
    jobs = []

    if _db:
        try:
            docs = (
                _reminders_col(user_id)
                .where("fired", "==", False)
                .order_by("fire_at")
                .stream()
            )
            jobs = [d.to_dict() for d in docs]
        except Exception as e:
            logger.error(f"[Reminders] List error: {e}")
    else:
        jobs = [j for j in _mem_reminders.get(user_id, []) if not j.get("fired")]

    if not jobs:
        return {"status": "success", "report": "No pending reminders.", "reminders": []}

    summary = []
    for j in jobs:
        try:
            dt = datetime.fromisoformat(j["fire_at"])
            summary.append({
                "job_id": j["job_id"],
                "message": j["message"],
                "fire_at": dt.strftime("%b %d at %I:%M %p UTC"),
                "repeat": j.get("repeat"),
            })
        except Exception:
            pass

    return {
        "status": "success",
        "report": f"You have {len(summary)} pending reminder(s).",
        "reminders": summary,
    }


def cancel_reminder(user_id: str, job_id: str) -> dict:
    """Cancel a scheduled reminder by job_id."""
    if _db:
        try:
            _reminders_col(user_id).document(job_id).delete()
            return {"status": "success", "report": f"Reminder {job_id} cancelled."}
        except Exception as e:
            return {"status": "error", "report": str(e)}
    else:
        jobs = _mem_reminders.get(user_id, [])
        before = len(jobs)
        _mem_reminders[user_id] = [j for j in jobs if j["job_id"] != job_id]
        if len(_mem_reminders[user_id]) < before:
            return {"status": "success", "report": f"Reminder {job_id} cancelled."}
        return {"status": "error", "report": f"Reminder {job_id} not found."}


# ── Time parser ──────────────────────────────────────────────────────────────

def _parse_when(when: str) -> Optional[datetime]:
    """
    Parse a time string into a UTC datetime.
    Supports:
      - ISO-8601:      '2026-03-15T09:00:00'
      - Offset:        '+2h', '+30m', '+1d', '+1w'
      - Natural:       'tomorrow 9am', 'in 2 hours'
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    w = when.strip().lower()

    # Offset shorthand: +Nh / +Nm / +Nd / +Nw
    import re
    m = re.match(r"^\+?(\d+)(h|m|d|w)$", w)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"h": timedelta(hours=n), "m": timedelta(minutes=n),
                 "d": timedelta(days=n), "w": timedelta(weeks=n)}[unit]
        return now + delta

    # ISO-8601
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(when.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    # Natural language basics
    if "tomorrow" in w:
        base = now + timedelta(days=1)
        hour = _extract_hour(w) or 9
        return base.replace(hour=hour, minute=0, second=0, microsecond=0)

    if "in " in w:
        m2 = re.search(r"in\s+(\d+)\s*(hour|minute|day|week)", w)
        if m2:
            n2, unit2 = int(m2.group(1)), m2.group(2)
            unit_map = {"hour": timedelta(hours=n2), "minute": timedelta(minutes=n2),
                        "day": timedelta(days=n2), "week": timedelta(weeks=n2)}
            return now + unit_map.get(unit2, timedelta(hours=n2))

    return None


def _extract_hour(text: str) -> Optional[int]:
    import re
    m = re.search(r"(\d{1,2})\s*(am|pm)?", text)
    if not m:
        return None
    h = int(m.group(1))
    if m.group(2) == "pm" and h < 12:
        h += 12
    elif m.group(2) == "am" and h == 12:
        h = 0
    return h


# ── Background poller ────────────────────────────────────────────────────────

async def reminder_poller(push_sender):
    """
    Polls Firestore every 30 seconds for due reminders.
    Calls push_sender(user_id, message) for each fired job.
    Runs forever as an asyncio background task.
    """
    logger.info("[Reminders] Poller started")
    while True:
        try:
            await _check_and_fire(push_sender)
        except Exception as e:
            logger.error(f"[Reminders] Poller error: {e}")
        await asyncio.sleep(30)


async def _check_and_fire(push_sender):
    """Check Firestore for due reminders and fire them."""
    now_iso = datetime.now(timezone.utc).isoformat()

    if not _db:
        # In-memory path
        for user_id, jobs in list(_mem_reminders.items()):
            for job in jobs:
                if not job.get("fired") and job["fire_at"] <= now_iso:
                    job["fired"] = True
                    logger.info(f"[Reminders] Firing (mem) job={job['job_id']} user={user_id}")
                    await push_sender(user_id, job["message"])
                    _handle_repeat(job, user_id)
        return

    try:
        # Query all users' reminders collections that are due
        # Firestore collection group query across all users
        from google.cloud import firestore as fs
        jobs_ref = _db.collection_group("jobs")
        due_docs = (
            jobs_ref
            .where("fired", "==", False)
            .where("fire_at", "<=", now_iso)
            .stream()
        )
        for doc in due_docs:
            job = doc.to_dict()
            job_id = job.get("job_id", doc.id)
            user_id = job.get("user_id", "")
            if not user_id:
                continue
            logger.info(f"[Reminders] Firing job={job_id} user={user_id}")
            # Mark fired
            doc.reference.update({"fired": True})
            await push_sender(user_id, job["message"])
            # Handle repeat
            repeat = job.get("repeat")
            if repeat:
                _schedule_next(user_id, job, repeat)
    except Exception as e:
        logger.error(f"[Reminders] Check error: {e}")


def _handle_repeat(job: dict, user_id: str):
    """Re-schedule a repeating reminder (in-memory path)."""
    from datetime import timedelta
    repeat = job.get("repeat")
    if not repeat:
        return
    delta_map = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1)}
    delta = delta_map.get(repeat)
    if not delta:
        return
    try:
        old_fire = datetime.fromisoformat(job["fire_at"])
        new_fire = old_fire + delta
        new_job = {**job, "job_id": str(uuid.uuid4())[:8], "fire_at": new_fire.isoformat(), "fired": False}
        _mem_reminders.setdefault(user_id, []).append(new_job)
    except Exception as e:
        logger.warning(f"[Reminders] Repeat schedule error: {e}")


def _schedule_next(user_id: str, job: dict, repeat: str):
    """Re-schedule a repeating reminder (Firestore path)."""
    from datetime import timedelta
    delta_map = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1)}
    delta = delta_map.get(repeat)
    if not delta:
        return
    try:
        old_fire = datetime.fromisoformat(job["fire_at"])
        new_fire = old_fire + delta
        new_job_id = str(uuid.uuid4())[:8]
        new_job = {**job, "job_id": new_job_id, "fire_at": new_fire.isoformat(), "fired": False,
                   "created_at": datetime.now(timezone.utc).isoformat()}
        _reminders_col(user_id).document(new_job_id).set(new_job)
        logger.info(f"[Reminders] Rescheduled repeat job={new_job_id} for {new_fire.isoformat()}")
    except Exception as e:
        logger.warning(f"[Reminders] Reschedule error: {e}")
