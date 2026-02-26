"""
Memory Compaction Engine for Elora.

Solves the unbounded memory growth problem by periodically compacting
raw memories into a structured, deduplicated user profile.

Architecture:
  Layer 1 — RAW MEMORIES  (existing: users/{uid}/memories/*)
    Written by auto_memorise after every conversation turn.
    Grows unbounded, contains duplicates.

  Layer 2 — COMPACTED PROFILE  (new: users/{uid}/profile/compacted_memory)
    A single document with categorised, deduplicated facts.
    Updated by the compaction job every 6 hours or after 50+ new memories.

  Layer 3 — SESSION SUMMARIES  (existing: users/{uid}/session_summaries/*)
    Last 3 injected at session start (unchanged).

The compaction job:
  1. Reads ALL raw memories for a user
  2. Reads the existing compacted profile (if any)
  3. Sends both to Gemini Flash to merge + deduplicate + categorise
  4. Writes the new compacted profile
  5. Prunes raw memories older than 30 days that have been compacted
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("elora.memory_compaction")

# ── Firestore ────────────────────────────────────────────────────────────────
_db = None
_project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")

try:
    if _project:
        from google.cloud import firestore
        _db = firestore.Client(project=_project)
        logger.info(f"[MemoryCompaction] Firestore ready (project={_project})")
except Exception as e:
    logger.warning(f"[MemoryCompaction] Firestore unavailable: {e}")

# ── Gemini client ────────────────────────────────────────────────────────────
_genai_client = None
try:
    from google import genai as _genai
    _genai_client = _genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))
except Exception as e:
    logger.warning(f"[MemoryCompaction] Gemini client unavailable: {e}")

# ── Constants ────────────────────────────────────────────────────────────────
COMPACTION_THRESHOLD = 50       # compact after this many new memories since last compaction
FIRST_COMPACTION_THRESHOLD = 5  # for first-ever compaction, use a much lower threshold (demo-friendly)
PRUNE_AGE_DAYS = 30             # prune raw memories older than this after compaction
COMPACTION_INTERVAL_HOURS = 6   # minimum hours between automatic compactions

PROFILE_CATEGORIES = [
    "identity",       # name, age, location, occupation
    "people",         # relationships, names, birthdays, contact info
    "work",           # job, projects, colleagues, stress points
    "preferences",    # likes, dislikes, habits, routines
    "health",         # sleep, exercise, medical, mood patterns
    "goals",          # aspirations, plans, savings targets
    "interests",      # hobbies, travel plans, media preferences
    "recent_context", # recent events, ongoing situations, emotional state
]

COMPACTION_PROMPT = """You are a memory compaction engine for a personal AI assistant named Elora.

TASK: Merge and deduplicate the following raw memory fragments into a clean, structured user profile.

EXISTING PROFILE (may be empty if this is the first compaction):
{existing_profile}

RAW MEMORIES TO INTEGRATE (newest first):
{raw_memories}

RULES:
1. Deduplicate aggressively — if the same fact appears 10 times, include it ONCE.
2. When facts contradict, keep the MOST RECENT version (memories are ordered newest-first).
3. Be concise but preserve ALL unique, meaningful information.
4. Merge related facts into coherent sentences.
5. Drop trivial or meaningless fragments.
6. Preserve exact names, dates, numbers, and contact info verbatim.

OUTPUT FORMAT — Return EXACTLY this JSON structure (no markdown fences, just raw JSON):
{{
  "identity": "...",
  "people": "...",
  "work": "...",
  "preferences": "...",
  "health": "...",
  "goals": "...",
  "interests": "...",
  "recent_context": "..."
}}

Each field should be a paragraph of concise, natural-language facts. Use empty string "" if no info exists for that category.
"""


# ── Public API ───────────────────────────────────────────────────────────────

def get_compacted_profile(user_id: str) -> dict:
    """
    Retrieve the compacted memory profile for a user.
    Returns a dict with category keys, or empty dict if none exists.
    """
    if not _db:
        return {}
    try:
        doc = (
            _db.collection("users").document(user_id)
            .collection("profile").document("compacted_memory")
            .get()
        )
        if doc.exists:
            data = doc.to_dict() or {}
            # Return only the profile categories
            return {k: data.get(k, "") for k in PROFILE_CATEGORIES if data.get(k)}
        return {}
    except Exception as e:
        logger.error(f"[MemoryCompaction] Get profile error: {e}")
        return {}


def build_profile_context(user_id: str) -> str:
    """
    Build a context string from the compacted profile for injection
    into the system prompt. Returns empty string if no profile exists.
    """
    profile = get_compacted_profile(user_id)
    if not profile:
        return ""

    lines = ["━━━ USER PROFILE (from long-term memory) ━━━"]
    category_labels = {
        "identity": "Who they are",
        "people": "People in their life",
        "work": "Work & career",
        "preferences": "Preferences & habits",
        "health": "Health & wellbeing",
        "goals": "Goals & plans",
        "interests": "Interests",
        "recent_context": "Recent context",
    }
    for cat in PROFILE_CATEGORIES:
        val = profile.get(cat, "")
        if val:
            label = category_labels.get(cat, cat.title())
            lines.append(f"[{label}]: {val}")
    lines.append("━━━ END PROFILE ━━━")
    return "\n".join(lines)


def get_memory_count_since_compaction(user_id: str) -> int:
    """Count raw memories created since the last compaction."""
    if not _db:
        return 0
    try:
        # Get last compaction timestamp
        profile_doc = (
            _db.collection("users").document(user_id)
            .collection("profile").document("compacted_memory")
            .get()
        )
        last_compacted = None
        if profile_doc.exists:
            data = profile_doc.to_dict() or {}
            last_compacted = data.get("last_compacted_at")

        # Count memories since then
        q = (
            _db.collection("users").document(user_id)
            .collection("memories")
            .order_by("created_at")
        )
        if last_compacted:
            q = q.where("created_at", ">", last_compacted)

        count = 0
        for _ in q.stream():
            count += 1
        return count
    except Exception as e:
        logger.debug(f"[MemoryCompaction] Count error: {e}")
        return 0


def should_compact(user_id: str) -> bool:
    """Check if this user needs a memory compaction run."""
    if not _db:
        return False
    try:
        profile_doc = (
            _db.collection("users").document(user_id)
            .collection("profile").document("compacted_memory")
            .get()
        )
        is_first_compaction = True
        if profile_doc.exists:
            is_first_compaction = False
            data = profile_doc.to_dict() or {}
            last_compacted = data.get("last_compacted_at")
            source_count = data.get("source_count", 0)

            if last_compacted:
                # Check time since last compaction
                if isinstance(last_compacted, datetime):
                    age = datetime.now(timezone.utc) - last_compacted.replace(tzinfo=timezone.utc)
                else:
                    age = timedelta(hours=COMPACTION_INTERVAL_HOURS + 1)

                if age < timedelta(hours=COMPACTION_INTERVAL_HOURS):
                    return False  # too soon

        # Check if enough new memories exist
        # Use a much lower threshold for the first-ever compaction (demo-friendly)
        new_count = get_memory_count_since_compaction(user_id)
        threshold = FIRST_COMPACTION_THRESHOLD if is_first_compaction else COMPACTION_THRESHOLD
        return new_count >= threshold
    except Exception as e:
        logger.debug(f"[MemoryCompaction] should_compact error: {e}")
        return False


def compact_memories(user_id: str) -> bool:
    """
    Run memory compaction for a user.

    1. Read all raw memories
    2. Read existing compacted profile
    3. Send to Gemini Flash for merge + dedup
    4. Store the new compacted profile
    5. Prune old raw memories

    Returns True on success.
    """
    if not _db or not _genai_client:
        logger.warning("[MemoryCompaction] Cannot compact — missing Firestore or Gemini client")
        return False

    try:
        # 1. Read all raw memories (newest first)
        docs = (
            _db.collection("users").document(user_id)
            .collection("memories")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(500)  # cap to prevent token overflow
            .stream()
        )
        raw_entries = []
        oldest_included = None
        for doc in docs:
            data = doc.to_dict() or {}
            fact = data.get("fact", "")
            ts = data.get("timestamp", "")
            if fact:
                raw_entries.append(f"[{ts}] {fact}")
                created = data.get("created_at")
                if created:
                    oldest_included = created

        if not raw_entries:
            logger.info(f"[MemoryCompaction] No raw memories for user={user_id}")
            return True

        # 2. Read existing profile
        existing_profile = get_compacted_profile(user_id)
        existing_str = ""
        if existing_profile:
            parts = []
            for k, v in existing_profile.items():
                if v:
                    parts.append(f"  {k}: {v}")
            existing_str = "\n".join(parts) if parts else "(empty — first compaction)"
        else:
            existing_str = "(empty — first compaction)"

        # 3. Send to Gemini Flash
        raw_text = "\n".join(raw_entries[:300])  # further cap for prompt length
        prompt = COMPACTION_PROMPT.format(
            existing_profile=existing_str,
            raw_memories=raw_text,
        )

        resp = _genai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        result_text = (resp.text or "").strip()

        # Parse JSON response
        import json
        # Strip markdown code fences if present
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        profile_data = json.loads(result_text)

        # 4. Store the compacted profile
        now = datetime.now(timezone.utc)
        profile_doc = {
            **{k: profile_data.get(k, "") for k in PROFILE_CATEGORIES},
            "last_compacted_at": now,
            "source_count": len(raw_entries),
            "updated_at": now.isoformat(),
        }
        (
            _db.collection("users").document(user_id)
            .collection("profile").document("compacted_memory")
            .set(profile_doc)
        )
        logger.info(
            f"[MemoryCompaction] Compacted {len(raw_entries)} memories "
            f"for user={user_id}"
        )

        # 5. Prune old raw memories (older than PRUNE_AGE_DAYS)
        _prune_old_memories(user_id)

        return True

    except json.JSONDecodeError as e:
        logger.error(f"[MemoryCompaction] JSON parse error: {e}\nRaw: {result_text[:500]}")
        return False
    except Exception as e:
        logger.error(f"[MemoryCompaction] Compaction error for user={user_id}: {e}")
        return False


def _prune_old_memories(user_id: str) -> int:
    """
    Delete raw memories older than PRUNE_AGE_DAYS that have been compacted.
    Returns the number of deleted documents.
    """
    if not _db:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=PRUNE_AGE_DAYS)
    pruned = 0

    try:
        docs = (
            _db.collection("users").document(user_id)
            .collection("memories")
            .where("created_at", "<", cutoff)
            .stream()
        )
        batch = _db.batch()
        batch_count = 0

        for doc in docs:
            batch.delete(doc.reference)
            batch_count += 1
            pruned += 1

            # Firestore batches max 500 writes
            if batch_count >= 450:
                batch.commit()
                batch = _db.batch()
                batch_count = 0

        if batch_count > 0:
            batch.commit()

        if pruned > 0:
            logger.info(f"[MemoryCompaction] Pruned {pruned} old memories for user={user_id}")
        return pruned

    except Exception as e:
        logger.error(f"[MemoryCompaction] Prune error: {e}")
        return 0


# ── Background compaction poller ─────────────────────────────────────────────

async def compaction_poller() -> None:
    """
    Background task that checks all users and compacts memories when needed.
    Runs every 30 minutes. Actual compaction only triggers if threshold met.
    """
    import asyncio
    logger.info("[MemoryCompaction] Poller started")

    while True:
        try:
            await _run_compaction_check()
        except Exception as e:
            logger.error(f"[MemoryCompaction] Poller error: {e}")
        await asyncio.sleep(30 * 60)  # check every 30 minutes


async def _run_compaction_check() -> None:
    """Check all users and compact if needed."""
    if not _db:
        return

    try:
        # Get all user IDs that have memories
        users_ref = _db.collection("users").stream()
        user_ids = [doc.id for doc in users_ref]

        for uid in user_ids:
            try:
                if should_compact(uid):
                    logger.info(f"[MemoryCompaction] Starting compaction for user={uid}")
                    # Run in thread to avoid blocking the event loop
                    import asyncio
                    await asyncio.to_thread(compact_memories, uid)
            except Exception as e:
                logger.error(f"[MemoryCompaction] Error for user={uid}: {e}")
    except Exception as e:
        logger.error(f"[MemoryCompaction] User scan error: {e}")
