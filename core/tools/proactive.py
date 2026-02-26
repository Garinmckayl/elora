"""
Proactive Engine — Elora's autonomous outreach system.

Architecture: Observer → Evaluator → Dispatcher

OBSERVER (cheap, no LLM):
  Runs every 5 minutes per active user. Checks lightweight signals:
  - Calendar events approaching
  - People birthdays within 3 days
  - Stale contacts (not contacted in 14+ days)
  - New unread emails
  - Time-of-day patterns (end of workday)
  - User inactivity (hasn't opened app in 24h+)

  Each check returns a Signal dataclass. If no signals → do nothing (zero cost).

EVALUATOR (smart, only when signals exist):
  Takes signals + user profile + notification history → Gemini Flash decides:
  - Should Elora reach out? (yes/no)
  - What should she say?
  - Which channel? (push/email)
  - Urgency level

DISPATCHER:
  Routes the evaluator's decision to push notification or email.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("elora.proactive")

# ── Firestore ────────────────────────────────────────────────────────────────
_db = None
_project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")

try:
    if _project:
        from google.cloud import firestore
        _db = firestore.Client(project=_project)
except Exception as e:
    logger.warning(f"[Proactive] Firestore unavailable: {e}")

# ── Gemini client ────────────────────────────────────────────────────────────
_genai_client = None
try:
    from google import genai as _genai
    _genai_client = _genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))
except Exception as e:
    logger.warning(f"[Proactive] Gemini client unavailable: {e}")


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class Signal:
    """A proactive signal detected by the observer."""
    signal_type: str          # "meeting_soon", "birthday", "stale_contact", etc.
    urgency: str              # "low", "medium", "high"
    entity_ref: str           # unique ID for dedup (event_id, person_name, etc.)
    summary: str              # human-readable description for the evaluator
    raw_data: dict = field(default_factory=dict)  # optional structured data


@dataclass
class ProactiveDecision:
    """The evaluator's output."""
    should_notify: bool
    message: str = ""
    channel: str = "push"     # "push" or "email"
    urgency: str = "low"
    signal_type: str = ""
    entity_ref: str = ""


# ── Constants ────────────────────────────────────────────────────────────────
PROACTIVE_CHECK_INTERVAL = 5 * 60    # 5 minutes
MEETING_SOON_MINUTES = 15            # notify N min before meetings
MEETING_PREP_MINUTES = 60            # prepare/context check N min before
BIRTHDAY_WINDOW_DAYS = 3             # notify about birthdays within N days
STALE_CONTACT_DAYS = 14              # notify about contacts not reached in N days
INACTIVITY_HOURS = 24                # notify after N hours of no app usage
END_OF_DAY_HOUR = 18                 # 6pm local time


# ── Last active tracking ─────────────────────────────────────────────────────
_last_active: dict[str, datetime] = {}  # uid -> last interaction time


def update_last_active(user_id: str) -> None:
    """Called whenever the user interacts with Elora (WS message, API call, etc.)."""
    _last_active[user_id] = datetime.now(timezone.utc)
    # Also persist to Firestore (fire-and-forget)
    if _db:
        try:
            _db.collection("users").document(user_id).set(
                {"last_active": datetime.now(timezone.utc)},
                merge=True,
            )
        except Exception:
            pass


def get_last_active(user_id: str) -> Optional[datetime]:
    """Get the user's last activity time."""
    if user_id in _last_active:
        return _last_active[user_id]
    if _db:
        try:
            doc = _db.collection("users").document(user_id).get()
            if doc.exists:
                data = doc.to_dict() or {}
                la = data.get("last_active")
                if la:
                    if isinstance(la, datetime):
                        _last_active[user_id] = la
                        return la
        except Exception:
            pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# OBSERVER — cheap signal detection (no LLM calls)
# ══════════════════════════════════════════════════════════════════════════════

async def observe_signals(user_id: str) -> list[Signal]:
    """
    Run all signal detectors for a user. Returns a list of detected signals.
    Each detector is cheap (Firestore reads + simple logic, no LLM).
    """
    signals = []

    # Run all detectors concurrently
    detectors = [
        _check_calendar_proximity(user_id),
        _check_birthdays(user_id),
        _check_stale_contacts(user_id),
        _check_inactivity(user_id),
    ]

    results = await asyncio.gather(*detectors, return_exceptions=True)
    for result in results:
        if isinstance(result, list):
            signals.extend(result)
        elif isinstance(result, Exception):
            logger.debug(f"[Proactive] Detector error: {result}")

    return signals


async def _check_calendar_proximity(user_id: str) -> list[Signal]:
    """Check if any calendar events are approaching."""
    signals = []
    try:
        from tools.gmail import get_user_token
        token = get_user_token(user_id)
        if not token:
            return []

        from tools.calendar import list_events_sync
        result = await asyncio.to_thread(
            list_events_sync, user_id, date="today"
        )
        events = result.get("events", [])
        now = datetime.now(timezone.utc)

        for event in events:
            start_str = event.get("start", "")
            title = event.get("title", "No title")

            try:
                # Parse event start time
                if "T" in str(start_str):
                    # Strip timezone suffix for parsing, assume UTC if no offset
                    clean = str(start_str).replace("Z", "+00:00")
                    event_time = datetime.fromisoformat(clean)
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=timezone.utc)
                else:
                    continue  # all-day event, skip

                minutes_until = (event_time - now).total_seconds() / 60

                if 0 < minutes_until <= MEETING_SOON_MINUTES:
                    signals.append(Signal(
                        signal_type="meeting_soon",
                        urgency="high",
                        entity_ref=f"cal_{title}_{start_str}",
                        summary=f"'{title}' starts in {int(minutes_until)} minutes",
                        raw_data={"title": title, "start": start_str, "minutes_until": int(minutes_until)},
                    ))
                elif MEETING_SOON_MINUTES < minutes_until <= MEETING_PREP_MINUTES:
                    signals.append(Signal(
                        signal_type="meeting_prep",
                        urgency="medium",
                        entity_ref=f"prep_{title}_{start_str}",
                        summary=f"'{title}' is in {int(minutes_until)} minutes — good time to prepare",
                        raw_data={"title": title, "start": start_str, "minutes_until": int(minutes_until)},
                    ))
            except (ValueError, TypeError):
                continue

    except Exception as e:
        logger.debug(f"[Proactive] Calendar check error: {e}")
    return signals


async def _check_birthdays(user_id: str) -> list[Signal]:
    """Check if any known person has a birthday within BIRTHDAY_WINDOW_DAYS."""
    signals = []
    try:
        from tools.people import _get_all_people
        people = await asyncio.to_thread(_get_all_people, user_id)
        now = datetime.now(timezone.utc)

        for person in people:
            name = person.get("name", "Unknown")

            # Try structured birthday field first (e.g. "2000-03-14", "March 14")
            birthday = None
            raw_birthday = person.get("birthday", "") or ""
            if raw_birthday:
                birthday = _parse_birthday_field(raw_birthday)

            # Fall back to extracting from freeform notes
            if not birthday:
                notes = (person.get("notes", "") or "").lower()
                if notes:
                    birthday = _extract_birthday(notes)

            if not birthday:
                continue

            # Calculate days until birthday this year
            this_year_bday = birthday.replace(year=now.year)
            if this_year_bday < now.replace(hour=0, minute=0, second=0, microsecond=0):
                this_year_bday = this_year_bday.replace(year=now.year + 1)

            days_until = (this_year_bday - now).days

            if 0 <= days_until <= BIRTHDAY_WINDOW_DAYS:
                day_str = "today" if days_until == 0 else (
                    "tomorrow" if days_until == 1 else f"in {days_until} days"
                )
                signals.append(Signal(
                    signal_type="birthday",
                    urgency="medium" if days_until <= 1 else "low",
                    entity_ref=f"bday_{name}_{this_year_bday.strftime('%m%d')}",
                    summary=f"{name}'s birthday is {day_str} ({this_year_bday.strftime('%B %d')})",
                    raw_data={"name": name, "days_until": days_until,
                              "date": this_year_bday.strftime("%B %d")},
                ))

    except Exception as e:
        logger.debug(f"[Proactive] Birthday check error: {e}")
    return signals


def _parse_birthday_field(value: str) -> Optional[datetime]:
    """Parse a structured birthday field value. Handles multiple formats."""
    value = value.strip()
    if not value:
        return None

    # Try ISO format: "2000-03-14", "1995-12-25"
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d", "%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(year=2000, tzinfo=timezone.utc)
        except ValueError:
            continue

    # Try natural: "March 14", "Mar 3", "March 14th"
    import re
    month_names = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
        "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    m = re.match(r"(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?", value, re.IGNORECASE)
    if m:
        month_str = m.group(1).lower()
        if month_str in month_names:
            try:
                return datetime(2000, month_names[month_str], int(m.group(2)), tzinfo=timezone.utc)
            except ValueError:
                pass

    return None


def _extract_birthday(notes: str) -> Optional[datetime]:
    """Extract a birthday date from freeform notes text."""
    import re
    # Patterns: "birthday march 14", "birthday: Mar 3rd", "bday 03/14", "born July 5"
    patterns = [
        r"(?:birthday|bday|born)[:\s]+(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?",
        r"(?:birthday|bday)[:\s]+(\d{1,2})[/\-](\d{1,2})",
    ]

    month_names = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
        "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    for pattern in patterns:
        m = re.search(pattern, notes, re.IGNORECASE)
        if m:
            groups = m.groups()
            if len(groups) == 2:
                try:
                    # Try month name + day
                    month_str = groups[0].lower()
                    if month_str in month_names:
                        month = month_names[month_str]
                        day = int(groups[1])
                        return datetime(2000, month, day, tzinfo=timezone.utc)
                    # Try MM/DD format
                    month = int(groups[0])
                    day = int(groups[1])
                    if 1 <= month <= 12 and 1 <= day <= 31:
                        return datetime(2000, month, day, tzinfo=timezone.utc)
                except (ValueError, KeyError):
                    continue
    return None


async def _check_stale_contacts(user_id: str) -> list[Signal]:
    """Check if any important contacts haven't been reached in a while."""
    signals = []
    try:
        from tools.people import _get_all_people
        people = await asyncio.to_thread(_get_all_people, user_id)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=STALE_CONTACT_DAYS)

        # Only flag people with close relationships
        close_relationships = {
            "girlfriend", "boyfriend", "wife", "husband", "partner",
            "mom", "mother", "dad", "father", "sister", "brother",
            "best friend", "close friend",
        }

        for person in people:
            name = person.get("name", "Unknown")
            relationship = (person.get("relationship", "") or "").lower()

            # Only flag close relationships
            if relationship not in close_relationships:
                continue

            # Check last_contacted timestamp
            last_contacted = person.get("last_contacted")
            updated_at_str = person.get("updated_at", "")

            # Use updated_at as proxy for last contact if last_contacted doesn't exist
            ref_time = None
            if last_contacted:
                if isinstance(last_contacted, datetime):
                    ref_time = last_contacted
            elif updated_at_str:
                try:
                    ref_time = datetime.fromisoformat(str(updated_at_str))
                    if ref_time.tzinfo is None:
                        ref_time = ref_time.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

            if ref_time and ref_time < cutoff:
                days_since = (now - ref_time).days
                signals.append(Signal(
                    signal_type="stale_contact",
                    urgency="low",
                    entity_ref=f"stale_{name}",
                    summary=f"You haven't reached out to {name} ({relationship}) in {days_since} days",
                    raw_data={"name": name, "relationship": relationship,
                              "days_since": days_since,
                              "phone": person.get("contact_phone", ""),
                              "email": person.get("contact_email", "")},
                ))

    except Exception as e:
        logger.debug(f"[Proactive] Stale contact check error: {e}")
    return signals


async def _check_inactivity(user_id: str) -> list[Signal]:
    """Check if the user hasn't interacted with Elora in a while."""
    signals = []
    try:
        last = get_last_active(user_id)
        if not last:
            return []

        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)

        hours_since = (datetime.now(timezone.utc) - last).total_seconds() / 3600

        if hours_since >= INACTIVITY_HOURS:
            signals.append(Signal(
                signal_type="inactivity",
                urgency="low",
                entity_ref=f"inactive_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                summary=f"User hasn't interacted with Elora in {int(hours_since)} hours",
                raw_data={"hours_since": int(hours_since)},
            ))
    except Exception as e:
        logger.debug(f"[Proactive] Inactivity check error: {e}")
    return signals


# ══════════════════════════════════════════════════════════════════════════════
# EVALUATOR — LLM decides whether to reach out
# ══════════════════════════════════════════════════════════════════════════════

EVALUATOR_PROMPT = """You are the proactive decision engine for Elora, a deeply personal AI companion.
Elora is warm, thoughtful, and genuinely cares about the user. She speaks like someone who knows them well.

CURRENT SIGNALS detected:
{signals}

USER PROFILE:
{profile}

RECENT NOTIFICATIONS ALREADY SENT (last 24h):
{recent_notifications}

CURRENT TIME: {current_time}

DECISION RULES:
- Only reach out if this is genuinely worth the user's attention
- NEVER be annoying. If in doubt, stay silent.
- Be warm and personal, not robotic. Write like a close friend texting.
- Reference specific people, events, and context from the user's life
- If a signal duplicates a recent notification, skip it
- Meeting reminders are almost always worth sending (if not already notified)
- Birthday reminders are worth sending once
- Stale contact nudges should be gentle and infrequent
- Inactivity check-ins should be caring, not guilt-tripping (max 1 per day)

OUTPUT FORMAT — Return EXACTLY this JSON (no markdown fences):
{{
  "should_notify": true/false,
  "message": "The notification text (1-2 warm, personal sentences)",
  "channel": "push",
  "urgency": "low/medium/high",
  "signal_type": "the primary signal_type being addressed",
  "entity_ref": "the entity_ref for dedup tracking"
}}

If should_notify is false, still return the JSON with empty message and the reason in entity_ref.
"""


async def evaluate_signals(
    user_id: str,
    signals: list[Signal],
) -> Optional[ProactiveDecision]:
    """
    Send signals to Gemini Flash for evaluation.
    Returns a ProactiveDecision or None if evaluation fails.
    """
    if not signals or not _genai_client:
        return None

    try:
        from tools.notification_history import (
            get_recent_notifications,
            can_send_notification,
            was_recently_notified_about,
        )
        from tools.memory_compaction import build_profile_context

        # Pre-check: can we even send?
        allowed, reason = can_send_notification(user_id)
        if not allowed:
            logger.info(f"[Proactive] Skipping evaluation for user={user_id}: {reason}")
            return None

        # Filter out signals we already notified about
        fresh_signals = [
            s for s in signals
            if not was_recently_notified_about(user_id, s.entity_ref)
        ]
        if not fresh_signals:
            logger.info(f"[Proactive] All signals already notified for user={user_id}")
            return None

        # Build context
        profile = build_profile_context(user_id)
        recent_notifs = get_recent_notifications(user_id, hours=24)
        recent_strs = [
            f"[{n.get('signal_type', '?')}] {n.get('message', '')}"
            for n in recent_notifs
        ] or ["(none)"]

        signals_str = "\n".join(
            f"- [{s.signal_type}] (urgency: {s.urgency}) {s.summary}"
            for s in fresh_signals
        )

        prompt = EVALUATOR_PROMPT.format(
            signals=signals_str,
            profile=profile or "(no profile yet — this is a new user)",
            recent_notifications="\n".join(recent_strs),
            current_time=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )

        resp = await asyncio.to_thread(
            _genai_client.models.generate_content,
            model="gemini-2.0-flash",
            contents=prompt,
        )
        result_text = (resp.text or "").strip()

        # Parse JSON
        import json
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(
                lines[1:-1] if lines[-1].startswith("```") else lines[1:]
            )

        data = json.loads(result_text)

        decision = ProactiveDecision(
            should_notify=data.get("should_notify", False),
            message=data.get("message", ""),
            channel=data.get("channel", "push"),
            urgency=data.get("urgency", "low"),
            signal_type=data.get("signal_type", fresh_signals[0].signal_type),
            entity_ref=data.get("entity_ref", fresh_signals[0].entity_ref),
        )

        logger.info(
            f"[Proactive] Evaluation for user={user_id}: "
            f"notify={decision.should_notify}, type={decision.signal_type}"
        )
        return decision

    except Exception as e:
        logger.error(f"[Proactive] Evaluation error for user={user_id}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# DISPATCHER — sends the notification via the right channel
# ══════════════════════════════════════════════════════════════════════════════

async def dispatch_notification(
    user_id: str,
    decision: ProactiveDecision,
    push_sender,
) -> bool:
    """
    Send the proactive notification through the chosen channel.
    Records it in notification history. Returns True on success.
    """
    if not decision.should_notify or not decision.message:
        return False

    from tools.notification_history import record_notification

    success = False

    if decision.channel == "push":
        success = await push_sender(
            user_id=user_id,
            title="Elora",
            message=decision.message,
            data={
                "type": "proactive",
                "signal_type": decision.signal_type,
                "urgency": decision.urgency,
                "message": decision.message,
            },
        )

    elif decision.channel == "email":
        try:
            from tools.gmail import send_email_sync
            # Get user's own email to send to self (or stored preferred email)
            result = await asyncio.to_thread(
                send_email_sync,
                user_id,
                "me",  # send to self as a note
                f"Elora: {decision.signal_type.replace('_', ' ').title()}",
                decision.message,
            )
            success = result.get("status") == "success"
        except Exception as e:
            logger.error(f"[Proactive] Email dispatch error: {e}")
            # Fall back to push
            success = await push_sender(
                user_id=user_id,
                title="Elora",
                message=decision.message,
                data={"type": "proactive", "signal_type": decision.signal_type},
            )

    if success:
        record_notification(
            user_id=user_id,
            signal_type=decision.signal_type,
            message=decision.message,
            channel=decision.channel,
            entity_ref=decision.entity_ref,
        )
        logger.info(
            f"[Proactive] Dispatched {decision.channel} to user={user_id}: "
            f"'{decision.message[:60]}'"
        )

    return success


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP — the background poller
# ══════════════════════════════════════════════════════════════════════════════

async def proactive_engine_poller(push_sender) -> None:
    """
    Main proactive engine loop. Runs forever as a background asyncio task.

    Every PROACTIVE_CHECK_INTERVAL seconds:
    1. Get all active user IDs
    2. For each user: observe → evaluate → dispatch
    """
    logger.info("[Proactive] Engine started")

    # Wait 2 minutes after startup before first check (let things settle)
    await asyncio.sleep(120)

    while True:
        try:
            await _run_proactive_cycle(push_sender)
        except Exception as e:
            logger.error(f"[Proactive] Engine cycle error: {e}")
        await asyncio.sleep(PROACTIVE_CHECK_INTERVAL)


async def _run_proactive_cycle(push_sender) -> None:
    """Run one cycle of the proactive engine across all users."""
    user_ids = _get_active_user_ids()
    if not user_ids:
        return

    for uid in user_ids:
        try:
            # OBSERVE — cheap signal detection
            signals = await observe_signals(uid)
            if not signals:
                continue

            logger.info(
                f"[Proactive] Found {len(signals)} signal(s) for user={uid}: "
                f"{[s.signal_type for s in signals]}"
            )

            # EVALUATE — LLM decides
            decision = await evaluate_signals(uid, signals)
            if not decision or not decision.should_notify:
                continue

            # DISPATCH — send it
            await dispatch_notification(uid, decision, push_sender)

        except Exception as e:
            logger.error(f"[Proactive] Error for user={uid}: {e}")


def _get_active_user_ids() -> list[str]:
    """
    Get user IDs that should be checked by the proactive engine.
    Returns users who have a push token registered (meaning they use the app).
    """
    if not _db:
        return list(_last_active.keys())

    try:
        # Get users with push tokens (they're actively using the app)
        users_ref = _db.collection("users").stream()
        user_ids = []
        for doc in users_ref:
            uid = doc.id
            # Check if user has a push token
            try:
                token_doc = (
                    _db.collection("users").document(uid)
                    .collection("device").document("push_token")
                    .get()
                )
                if token_doc.exists:
                    user_ids.append(uid)
            except Exception:
                continue

        return user_ids

    except Exception as e:
        logger.error(f"[Proactive] Get active users error: {e}")
        return list(_last_active.keys())
