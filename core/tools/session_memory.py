"""
Session Memory — Post-call summarisation and cross-session memory injection.

Inspired by OpenClaw's compaction approach: after each call ends, summarise
the conversation and persist it to Firestore. On the next session, inject
the most recent summary at the top of the system instruction so Elora
always has continuity across calls.

Storage layout in Firestore:
  users/{user_id}/session_summaries/{timestamp}
    - summary: str          (3-5 sentence narrative)
    - timestamp: datetime
    - turn_count: int
    - topics: list[str]     (extracted topic tags)

The most recent N summaries are injected into _make_live_config() and the
ADK text agent system prompt, giving Elora genuine long-term memory without
carrying raw transcripts.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("elora.session_memory")

MAX_SUMMARIES_TO_INJECT = 3    # how many recent summaries to show Elora at session start
MAX_SUMMARY_AGE_DAYS = 30      # don't inject summaries older than this

# ── Shared Firestore client (reused across calls) ────────────────────────────
_db = None
_project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")

try:
    if _project:
        from google.cloud import firestore as _fs
        _db = _fs.Client(project=_project)
        logger.info(f"[SessionMemory] Firestore ready (project={_project})")
except Exception as e:
    logger.warning(f"[SessionMemory] Firestore unavailable: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Summarise a completed call transcript
# ─────────────────────────────────────────────────────────────────────────────

def summarise_call(
    user_id: str,
    transcript: list[dict],   # list of {"role": "user"|"elora", "text": str}
) -> Optional[str]:
    """
    Use Gemini Flash to summarise a completed call into 3-5 sentences.
    Focuses on: what was discussed, what was done, what matters for next time.
    Returns the summary string, or None on failure.
    """
    if not transcript:
        return None

    # Build a compact transcript string (cap at ~6000 chars to keep prompt lean)
    lines = []
    for turn in transcript:
        role = turn.get("role", "?")
        text = turn.get("text", "").strip()
        if text:
            prefix = "User" if role == "user" else "Elora"
            lines.append(f"{prefix}: {text}")

    raw = "\n".join(lines)
    if len(raw) > 6000:
        # Keep beginning and end — the most contextually important parts
        raw = raw[:2500] + "\n...[middle trimmed]...\n" + raw[-2500:]

    if len(raw) < 50:
        return None  # too short to summarise

    try:
        from google import genai
        from google.genai import types

        api_key = os.getenv("GOOGLE_API_KEY", "")
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})

        prompt = (
            "You are summarising a conversation between a user and their personal AI assistant Elora.\n\n"
            "CONVERSATION:\n"
            f"{raw}\n\n"
            "Write a 3-5 sentence summary in the FIRST PERSON from Elora's perspective "
            "(i.e. 'We talked about...', 'I helped with...', 'The user mentioned...'). "
            "Focus on:\n"
            "- Key topics discussed\n"
            "- Actions taken (emails sent, bookings made, reminders set, people introduced)\n"
            "- Anything the user mentioned about their life, feelings, or plans\n"
            "- Anything Elora should remember for next time\n\n"
            "Be concise and personal. Write as if you're leaving yourself a note before the next conversation."
        )

        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
        )
        summary = (resp.text or "").strip()
        logger.info(f"[SessionMemory] Summary generated ({len(summary)} chars) for user={user_id}")
        return summary if len(summary) > 20 else None

    except Exception as e:
        logger.error(f"[SessionMemory] Summarisation failed: {e}")
        return None


def store_summary(user_id: str, summary: str, turn_count: int) -> bool:
    """Store a session summary to Firestore."""
    if not _db:
        logger.warning("[SessionMemory] No Firestore client — cannot store summary")
        return False
    try:
        now = datetime.now(timezone.utc)
        doc_ref = (
            _db.collection("users")
            .document(user_id)
            .collection("session_summaries")
            .document(now.strftime("%Y%m%d_%H%M%S"))
        )
        doc_ref.set({
            "summary": summary,
            "timestamp": now,
            "turn_count": turn_count,
            "created_at": now.isoformat(),
        })
        logger.info(f"[SessionMemory] Stored summary for user={user_id}")
        return True
    except Exception as e:
        logger.error(f"[SessionMemory] Store failed: {e}")
        return False


def get_recent_summaries(user_id: str, limit: int = MAX_SUMMARIES_TO_INJECT) -> list[str]:
    """
    Retrieve the most recent session summaries for this user.
    Returns a list of summary strings, most recent first.
    """
    if not _db:
        return []
    try:
        from datetime import timedelta
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=MAX_SUMMARY_AGE_DAYS)
            if MAX_SUMMARY_AGE_DAYS else None
        )

        q = (
            _db.collection("users")
            .document(user_id)
            .collection("session_summaries")
            .order_by("timestamp", direction=_fs.Query.DESCENDING)
            .limit(limit)
        )
        if cutoff:
            q = q.where("timestamp", ">=", cutoff)
        query = q

        docs = query.stream()
        summaries = []
        for doc in docs:
            data = doc.to_dict()
            if data:
                summaries.append(data.get("summary", ""))

        return [s for s in summaries if s]

    except Exception as e:
        logger.warning(f"[SessionMemory] Load summaries failed: {e}")
        return []


def build_memory_context(user_id: str) -> str:
    """
    Build a memory context string to inject at the top of the system instruction.
    Returns empty string if no summaries exist.
    """
    summaries = get_recent_summaries(user_id)
    if not summaries:
        return ""

    lines = ["━━━ MEMORY FROM PREVIOUS CONVERSATIONS ━━━"]
    for i, summary in enumerate(summaries):
        label = "Last conversation" if i == 0 else f"{i+1} conversations ago"
        lines.append(f"[{label}]: {summary}")
    lines.append("━━━ END OF MEMORY ━━━")

    return "\n".join(lines)
