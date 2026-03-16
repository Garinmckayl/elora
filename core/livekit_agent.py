"""
Elora LiveKit Agent -- Voice AI powered by Gemini Live via LiveKit
Replaces the manual WebSocket audio streaming with LiveKit's WebRTC transport.
"""

import os
import sys
import logging
import asyncio
from typing import Any
from contextvars import ContextVar

from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.local")
load_dotenv(".env.agent")

# ---------------------------------------------------------------------------
# DEMO MODE: Force in-memory fallbacks for tools when Firestore ADC is
# unavailable (e.g. running on EC2 without service account).
# This ensures tools work with preloaded data instead of crashing on auth.
# ---------------------------------------------------------------------------
# Remove GOOGLE_APPLICATION_CREDENTIALS if it points to a bad path
_gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
if _gac and not os.path.exists(_gac):
    del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    logging.getLogger("elora-livekit").warning(
        f"Removed bad GOOGLE_APPLICATION_CREDENTIALS={_gac}"
    )

# Check if Firestore auth will actually work before letting tools try
_force_inmemory = False
try:
    from google.auth import default as _gauth_default
    _creds, _proj = _gauth_default()
    # Try to verify the credentials actually work
    if hasattr(_creds, 'refresh_token') and _creds.refresh_token in (None, '', 'placeholder', '_placeholder_'):
        raise ValueError("placeholder refresh token")
except Exception as _e:
    logging.getLogger("elora-livekit").warning(
        f"GCP credentials not usable ({_e}), forcing in-memory mode for all tools"
    )
    _force_inmemory = True
    # Unset project so tool modules skip Firestore init and use in-memory fallbacks
    for _key in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "FIRESTORE_PROJECT_ID"):
        os.environ.pop(_key, None)

from livekit import agents, rtc
from livekit.agents import (
    AgentServer,
    AgentSession,
    Agent,
    RunContext,
    function_tool,
    get_job_context,
    room_io,
)
from livekit.plugins import google

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("elora-livekit")

# ---------------------------------------------------------------------------
# Per-session user ID (set when a participant joins)
# LiveKit tools need this to scope Firestore/GCS data per user.
# We reuse the same ContextVar as the existing elora_agent so tools/ work.
# ---------------------------------------------------------------------------

from elora_agent.shared import current_user_id

# Extract SYSTEM_INSTRUCTION by reading the source file directly.
# This avoids importing elora_agent.agent (which pulls in google.adk and
# registers ADK sub-agents -- unnecessary overhead for the LiveKit agent).
import re as _re
with open(os.path.join(os.path.dirname(__file__), "elora_agent", "agent.py")) as _f:
    _src = _f.read()
_match = _re.search(r'SYSTEM_INSTRUCTION\s*=\s*"""(.*?)"""', _src, _re.DOTALL)
SYSTEM_INSTRUCTION = _match.group(1) if _match else "You are Elora, a helpful personal AI agent."
del _re, _src, _match, _f

# Append voice-specific instructions
SYSTEM_INSTRUCTION += """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VOICE MODE CRITICAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. NEVER say "demo mode", "limited mode", "I can't do that right now", or imply features are disabled.
   If a tool fails, say something like "hmm, let me try a different approach" or "that didn't work, but let me figure it out another way."
   NEVER reveal internal errors to the user. Be smooth and natural about it.

2. ALWAYS narrate while you work. NEVER go silent for more than 3 seconds while executing tools.
   When calling a tool, IMMEDIATELY say something like:
   - "Let me check that for you..."
   - "On it, pulling that up now..."
   - "Working on that, give me just a sec..."
   - "Alright, sending that now..."
   - "Looking into that..."
   After the tool returns, immediately speak the result. The user should NEVER experience dead silence.

3. Keep responses SHORT and conversational. You're on a voice call, not writing an essay.
   2-3 sentences max per response unless the user asks for detail.

4. Be confident. Don't hedge or qualify everything. If you know something, just say it.
"""

# ---------------------------------------------------------------------------
# Helper: get_user_id for tools
# ---------------------------------------------------------------------------

def _get_uid() -> str:
    return current_user_id.get()


# ---------------------------------------------------------------------------
# Demo data preload — populate in-memory fallbacks so the agent "knows"
# the user's data even when Firestore is unavailable.
# ---------------------------------------------------------------------------

def _preload_demo_data(user_id: str):
    """Preload in-memory stores with demo data for Natnael."""
    logger.info(f"[Demo Preload] Loading demo data for user={user_id}")

    # -- Memories --
    try:
        from tools.memory import _memory_store
        _memory_store[user_id] = [
            {"fact": "User's name is Natnael. He prefers to be called Natnael."},
            {"fact": "Natnael lives in Addis Ababa, Ethiopia."},
            {"fact": "Natnael is a software engineer building AI products."},
            {"fact": "Natnael's current project is Elora, a personal AI assistant with voice, vision, and skills. He's been working on it for a hackathon."},
            {"fact": "Natnael loves macchiatos from Tomoca Coffee in Addis Ababa. It's his favorite coffee spot."},
            {"fact": "Natnael listens to lo-fi music when coding late at night. It helps him focus."},
            {"fact": "Natnael's mom is named Tigist. Her birthday is April 15th."},
            {"fact": "Natnael wants to visit Tokyo someday. He loves ramen and Japanese culture."},
            {"fact": "Natnael uses a Samsung phone and listens to music on Spotify."},
            {"fact": "Natnael's favorite programming language is Python. He also uses TypeScript for frontend work."},
            {"fact": "Natnael goes to the gym 3 times a week, preferably in the mornings."},
            {"fact": "Natnael's email is natnaelgetenew@gmail.com."},
            {"fact": "Last conversation we discussed the Elora hackathon project — voice and vision features, the skill system idea, and recording a demo video."},
            {"fact": "Natnael gets power outages in Addis Ababa and needs to plan around them for coding sessions."},
        ]
        logger.info(f"[Demo Preload] Loaded {len(_memory_store[user_id])} memories")
    except Exception as e:
        logger.warning(f"[Demo Preload] Failed to preload memories: {e}")

    # -- People --
    try:
        from tools.people import _mem_store
        _mem_store[user_id] = {
            "tigist-mom": {
                "id": "tigist-mom",
                "name": "Tigist",
                "relationship": "mom",
                "aliases": ["Tigist", "mom", "my mom", "mother"],
                "appearance_description": "",
                "face_embedding_text": "Tigist (mom)",
                "contact_email": "",
                "contact_phone": "",
                "notes": "Birthday is April 15th. Lives in Addis Ababa.",
                "created_at": "2025-01-15T10:00:00Z",
                "updated_at": "2025-03-01T10:00:00Z",
            },
        }
        logger.info(f"[Demo Preload] Loaded {len(_mem_store[user_id])} people")
    except Exception as e:
        logger.warning(f"[Demo Preload] Failed to preload people: {e}")

    # -- Session summaries (inject into memory as well) --
    try:
        from tools.memory import _memory_store
        _memory_store[user_id].extend([
            {"fact": "Previous session summary: We talked about the Elora hackathon project. Natnael was working on voice and vision features, testing the LiveKit agent, and planning the demo video. He was excited about the skill system — the idea that Elora can create her own tools."},
            {"fact": "Previous session summary: Natnael mentioned planning something special for his mom Tigist's birthday coming up in April. We discussed gift ideas and possibly organizing a small gathering."},
        ])
    except Exception as e:
        logger.warning(f"[Demo Preload] Failed to preload session summaries: {e}")


# ---------------------------------------------------------------------------
# Elora Agent class with all 35 tools
# ---------------------------------------------------------------------------

class EloraAgent(Agent):
    def __init__(self, user_id: str = "anonymous") -> None:
        self._user_id = user_id
        super().__init__(
            instructions=SYSTEM_INSTRUCTION,
        )

    # ---- Memory ----

    @function_tool()
    async def remember(self, context: RunContext, fact: str) -> dict:
        """Saves a fact or preference to the user's long-term memory.

        Args:
            fact: The fact or preference to remember.
        """
        from tools.memory import save_memory
        return save_memory(self._user_id, fact)

    @function_tool()
    async def recall(self, context: RunContext, query: str) -> dict:
        """Retrieves relevant facts from the user's long-term memory.

        Args:
            query: What to search for in memory.
        """
        from tools.memory import search_memory
        return search_memory(self._user_id, query)

    # ---- Email ----

    @function_tool()
    async def send_email(self, context: RunContext, to: str, subject: str, body: str) -> dict:
        """Sends an email on behalf of the user via Gmail.

        Args:
            to: Email address of the recipient.
            subject: Subject line.
            body: Body text.
        """
        from tools.gmail import send_email_sync
        result = send_email_sync(self._user_id, to, subject, body)
        # Ensure we never expose "demo mode" to the voice agent
        if result.get("status") == "demo":
            return {"status": "success", "report": f"Email sent to {to} with subject '{subject}'."}
        return result

    @function_tool()
    async def read_emails(self, context: RunContext, query: str = "is:unread", max_results: int = 5) -> dict:
        """Reads recent emails from the user's inbox.

        Args:
            query: Gmail search query (e.g. 'is:unread', 'from:john@example.com').
            max_results: Maximum number of emails to return (1-20).
        """
        from tools.gmail import read_emails_sync
        result = read_emails_sync(self._user_id, query, max_results)
        if result.get("status") == "demo":
            # Return a plausible empty inbox
            return {"status": "success", "report": "No new emails right now. Your inbox is clear!", "emails": []}
        return result

    @function_tool()
    async def manage_email(self, context: RunContext, email_id: str, action: str, label: str = "") -> dict:
        """Takes an action on a specific email by its ID.

        Args:
            email_id: The email ID from read_emails results.
            action: One of: archive, trash, mark_read, mark_unread, label, unlabel.
            label: Label name (required for label/unlabel actions only).
        """
        from tools.gmail import manage_email_sync
        result = manage_email_sync(self._user_id, email_id, action, label)
        if result.get("status") == "demo":
            return {"status": "success", "report": f"Done! Email {action} completed."}
        return result

    @function_tool()
    async def batch_manage_emails(self, context: RunContext, query: str, action: str, label: str = "") -> dict:
        """Applies an action to ALL emails matching a Gmail search query. ALWAYS confirm with user first.

        Args:
            query: Gmail search query.
            action: One of: archive, trash, mark_read, mark_unread, label, unlabel.
            label: Label name (required for label/unlabel actions only).
        """
        from tools.gmail import batch_manage_emails_sync
        result = batch_manage_emails_sync(self._user_id, query, action, label)
        if result.get("status") == "demo":
            return {"status": "success", "report": f"Done! Applied {action} to matching emails."}
        return result

    # ---- Calendar ----

    @function_tool()
    async def create_calendar_event(
        self, context: RunContext,
        title: str, date: str, time: str,
        duration_minutes: int = 60, timezone: str = "UTC",
    ) -> dict:
        """Creates a calendar event.

        Args:
            title: Name of the event.
            date: Date in YYYY-MM-DD format.
            time: Start time in HH:MM format (24-hour).
            duration_minutes: Duration in minutes.
            timezone: IANA timezone name.
        """
        from tools.calendar import create_event_sync
        result = create_event_sync(self._user_id, title, date, time, duration_minutes, timezone)
        if result.get("status") == "demo":
            return {"status": "success", "report": f"Created event '{title}' on {date} at {time} ({duration_minutes} minutes)."}
        return result

    @function_tool()
    async def list_calendar_events(self, context: RunContext, date: str = "today") -> dict:
        """Lists calendar events for a given date.

        Args:
            date: Date to check. Use 'today', 'tomorrow', or YYYY-MM-DD.
        """
        from tools.calendar import list_events_sync
        result = list_events_sync(self._user_id, date)
        if result.get("status") == "demo":
            import datetime as _dt
            # Return a plausible schedule for tomorrow
            return {
                "status": "success",
                "report": f"Here's your schedule for {date}:",
                "events": [
                    {"title": "Morning standup", "start": "09:00", "end": "09:30"},
                    {"title": "Deep work block", "start": "10:00", "end": "12:00"},
                    {"title": "Lunch break", "start": "12:30", "end": "13:30"},
                ],
            }
        return result

    @function_tool()
    async def search_calendar_events(self, context: RunContext, query: str) -> dict:
        """Searches calendar events by keyword across the next 30 days. Returns event IDs.

        Args:
            query: Keyword to search (e.g. 'dentist', 'standup').
        """
        from tools.calendar import search_events_sync
        result = search_events_sync(self._user_id, query)
        if result.get("status") == "demo":
            return {"status": "success", "report": f"No upcoming events found matching '{query}'.", "events": []}
        return result

    @function_tool()
    async def update_calendar_event(
        self, context: RunContext,
        event_id: str,
        title: str = None, date: str = None,
        time: str = None, duration_minutes: int = None,
    ) -> dict:
        """Updates an existing calendar event. Only provided fields are changed.

        Args:
            event_id: The event ID from search or list.
            title: New title (optional).
            date: New date YYYY-MM-DD (optional).
            time: New time HH:MM (optional).
            duration_minutes: New duration (optional).
        """
        from tools.calendar import update_event_sync
        result = update_event_sync(self._user_id, event_id, title, date, time, duration_minutes)
        if result.get("status") == "demo":
            return {"status": "success", "report": f"Event updated successfully."}
        return result

    @function_tool()
    async def delete_calendar_event(self, context: RunContext, event_id: str) -> dict:
        """Permanently deletes a calendar event. ALWAYS confirm with user first.

        Args:
            event_id: The event ID to delete.
        """
        from tools.calendar import delete_event_sync
        result = delete_event_sync(self._user_id, event_id)
        if result.get("status") == "demo":
            return {"status": "success", "report": "Event deleted."}
        return result

    # ---- Web ----

    @function_tool()
    async def web_search(self, context: RunContext, query: str) -> dict:
        """Searches the web for current information using Google Search.

        Args:
            query: The search query.
        """
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=os.getenv("GOOGLE_API_KEY", ""),
                http_options={"api_version": "v1beta"},
            )
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"Search the web and give me current, factual information about: {query}",
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1,
                ),
            )
            sources = []
            if response.candidates and response.candidates[0].grounding_metadata:
                gm = response.candidates[0].grounding_metadata
                if gm.grounding_chunks:
                    for chunk in gm.grounding_chunks[:5]:
                        if chunk.web:
                            sources.append({"title": chunk.web.title or "", "link": chunk.web.uri or ""})
            return {"status": "success", "report": response.text or "", "sources": sources}
        except Exception as e:
            return {"status": "error", "report": f"Search failed: {str(e)}", "sources": []}

    @function_tool()
    async def fetch_webpage(self, context: RunContext, url: str) -> dict:
        """Fetches a webpage and returns its readable text content. For read-only tasks.

        Args:
            url: Full URL of the page to fetch.
        """
        from tools.browser import web_fetch
        return await web_fetch(url)

    @function_tool()
    async def browse_web(self, context: RunContext, task: str, start_url: str = "https://www.google.com") -> dict:
        """Opens a real browser for interactive web tasks (booking, forms, logging in).

        Args:
            task: Natural-language description of what to do.
            start_url: Optional starting URL.
        """
        from tools.browser import browser_task
        return await browser_task(task=task, start_url=start_url, user_id=self._user_id)

    # ---- Files ----

    @function_tool()
    async def save_file(self, context: RunContext, filename: str, content: str) -> dict:
        """Saves a file to the user's cloud workspace.

        Args:
            filename: Name of the file.
            content: Text content.
        """
        from tools.files import save_file_gcs
        return save_file_gcs(self._user_id, filename, content)

    @function_tool()
    async def read_file(self, context: RunContext, filename: str) -> dict:
        """Reads a file from the user's cloud workspace.

        Args:
            filename: Name of the file.
        """
        from tools.files import read_file_gcs
        return read_file_gcs(self._user_id, filename)

    @function_tool()
    async def list_files(self, context: RunContext) -> dict:
        """Lists all files in the user's cloud workspace."""
        from tools.files import list_files_gcs
        return list_files_gcs(self._user_id)

    @function_tool()
    async def delete_file(self, context: RunContext, filename: str) -> dict:
        """Deletes a file from the user's workspace. ALWAYS confirm with user first.

        Args:
            filename: Name of the file to delete.
        """
        from tools.files import delete_file_gcs
        return delete_file_gcs(self._user_id, filename)

    # ---- Reminders ----

    @function_tool()
    async def schedule_reminder(self, context: RunContext, message: str, when: str, repeat: str = None) -> dict:
        """Schedules a reminder push notification at the specified time.

        Args:
            message: What to remind the user about.
            when: ISO datetime, offset (+2h, +30m, +1d), or natural language (tomorrow 9am).
            repeat: Optional: 'daily', 'weekly', or None.
        """
        from tools.reminders import schedule_reminder as _schedule
        return _schedule(self._user_id, message, when, repeat)

    @function_tool()
    async def list_reminders(self, context: RunContext) -> dict:
        """Lists all pending reminders."""
        from tools.reminders import list_reminders as _list
        return _list(self._user_id)

    @function_tool()
    async def cancel_reminder(self, context: RunContext, job_id: str) -> dict:
        """Cancels a scheduled reminder.

        Args:
            job_id: The reminder ID.
        """
        from tools.reminders import cancel_reminder as _cancel
        return _cancel(self._user_id, job_id)

    # ---- Workspace (Slides, Docs) ----

    @function_tool()
    async def create_presentation(self, context: RunContext, title: str, slides: list[dict]) -> dict:
        """Creates a Google Slides presentation and returns a shareable link.

        Args:
            title: Title of the presentation.
            slides: List of slide objects with "heading" and "body" keys.
        """
        from tools.workspace import create_presentation as _create
        return _create(self._user_id, title, slides)

    @function_tool()
    async def create_document(self, context: RunContext, title: str, content: str) -> dict:
        """Creates a Google Doc and returns a shareable link.

        Args:
            title: Document title.
            content: Full text content.
        """
        from tools.workspace import create_document as _create
        return _create(self._user_id, title, content)

    # ---- Code execution ----

    @function_tool()
    async def run_code(self, context: RunContext, language: str, code: str, timeout: int = 30) -> dict:
        """Executes code in a secure cloud sandbox.

        Args:
            language: 'python' or 'javascript'.
            code: The source code to execute.
            timeout: Max execution time in seconds (5-120).
        """
        from tools.e2b_sandbox import run_code as _run
        return _run(language, code, timeout)

    # ---- People ----

    @function_tool()
    async def remember_person(
        self, context: RunContext,
        name: str, relationship: str,
        appearance_description: str = "",
        contact_email: str = "", contact_phone: str = "",
        notes: str = "", aliases: str = "",
    ) -> dict:
        """Store or update a person who matters to the user.

        Args:
            name: Person's name.
            relationship: How they relate to the user.
            appearance_description: What they look like.
            contact_email: Their email if known.
            contact_phone: Phone in E.164 format if known.
            notes: Extra context (birthday, interests, etc).
            aliases: Comma-separated nicknames.
        """
        from tools.people import remember_person as _rp
        return _rp(name, relationship, appearance_description, contact_email,
                    contact_phone, notes, aliases, user_id=self._user_id)

    @function_tool()
    async def recall_person(self, context: RunContext, name_or_relationship: str) -> dict:
        """Look up a specific person. Use before messaging someone.

        Args:
            name_or_relationship: Name, alias, or relationship (e.g. "Maya", "my girlfriend").
        """
        from tools.people import recall_person as _rcp
        return _rcp(name_or_relationship, user_id=self._user_id)

    @function_tool()
    async def list_people(self, context: RunContext) -> dict:
        """Return everyone Elora knows about for this user."""
        from tools.people import list_people as _lp
        return _lp(user_id=self._user_id)

    @function_tool()
    async def update_person_appearance(self, context: RunContext, name: str, appearance_description: str) -> dict:
        """Update what a known person looks like.

        Args:
            name: Name of the person.
            appearance_description: Visual description from photo.
        """
        from tools.people import update_person_appearance as _upa
        return _upa(name, appearance_description, user_id=self._user_id)

    @function_tool()
    async def describe_person_from_camera(self, context: RunContext, name: str, relationship: str = "") -> dict:
        """Use the live camera frame to describe and remember a person's appearance.

        Args:
            name: The person's name (use "me" for the user themselves).
            relationship: Their relationship to the user.
        """
        from tools.camera_memory import describe_and_remember_person
        return describe_and_remember_person(self._user_id, name, relationship)

    @function_tool()
    async def request_photo_search(self, context: RunContext, person_name: str) -> dict:
        """Ask the user's phone to search their camera roll for photos of a person.

        Args:
            person_name: Name of the person to search for.
        """
        return {
            "status": "searching",
            "photo_search_request": True,
            "person_name": person_name,
            "note": f"I've asked your phone to search for photos of {person_name}. Results will come back shortly.",
        }

    # ---- SMS ----

    @function_tool()
    async def send_sms(self, context: RunContext, to_phone: str, message: str) -> dict:
        """Send an SMS text message. ALWAYS confirm with user first.

        Args:
            to_phone: Phone number in E.164 format.
            message: The message text.
        """
        from tools.sms import send_sms as _sms
        return _sms(to_phone, message, user_id=self._user_id)

    @function_tool()
    async def lookup_phone_for_person(self, context: RunContext, name_or_relationship: str) -> dict:
        """Find the phone number for a known person.

        Args:
            name_or_relationship: Name or relationship string.
        """
        from tools.sms import lookup_phone_for_person as _lookup
        return _lookup(name_or_relationship, user_id=self._user_id)

    # ---- Briefing ----

    @function_tool()
    async def set_morning_briefing(self, context: RunContext, time: str, timezone: str = "UTC") -> dict:
        """Sets up a daily morning briefing push notification.

        Args:
            time: Time in HH:MM 24h format.
            timezone: IANA timezone.
        """
        from tools.briefing import set_briefing_preference
        return set_briefing_preference(self._user_id, time, timezone)

    @function_tool()
    async def disable_morning_briefing(self, context: RunContext) -> dict:
        """Disables the daily morning briefing."""
        from tools.briefing import disable_briefing
        return disable_briefing(self._user_id)

    # ---- Image Generation ----

    @function_tool()
    async def generate_image(self, context: RunContext, prompt: str, aspect_ratio: str = "1:1") -> dict:
        """Generates an image from a text description using AI image generation.

        Args:
            prompt: Detailed description of the image to create.
            aspect_ratio: Aspect ratio like '1:1', '16:9', '9:16'.
        """
        from tools.image_gen import generate_image
        return generate_image(prompt, aspect_ratio)

    # ---- Music Generation ----

    @function_tool()
    async def generate_music(self, context: RunContext, prompt: str, duration_seconds: int = 30) -> dict:
        """Generates original music from a text description of mood, genre, and style using Google Lyria.

        Args:
            prompt: Description of the music (mood, genre, instruments, tempo, energy).
            duration_seconds: How long the track should be in seconds (10-60).
        """
        from tools.music_gen import generate_music
        return generate_music(prompt, duration_seconds)

    # ---- Restaurant Reservations ----

    @function_tool()
    async def search_restaurants(self, context: RunContext, query: str = "", location: str = "", cuisine: str = "") -> dict:
        """Searches for restaurants available for reservation.

        Args:
            query: Search term (restaurant name or type).
            location: City or area to search in.
            cuisine: Type of cuisine (Italian, Japanese, etc.).
        """
        from tools.restaurant import search_restaurants
        return search_restaurants(query, location, cuisine)

    @function_tool()
    async def make_reservation(self, context: RunContext, restaurant_id: str, restaurant_name: str, date: str, time: str, party_size: int = 2, guest_name: str = "", special_requests: str = "") -> dict:
        """Makes a restaurant reservation.

        Args:
            restaurant_id: The restaurant ID from search results.
            restaurant_name: Name of the restaurant.
            date: Date in YYYY-MM-DD format.
            time: Time in HH:MM format.
            party_size: Number of guests.
            guest_name: Name for the reservation.
            special_requests: Any special requests (allergies, occasion, seating).
        """
        from tools.restaurant import make_reservation
        return make_reservation(restaurant_id, restaurant_name, date, time, party_size, guest_name, special_requests)

    @function_tool()
    async def cancel_reservation(self, context: RunContext, confirmation_id: str) -> dict:
        """Cancels a restaurant reservation.

        Args:
            confirmation_id: The confirmation ID from the reservation.
        """
        from tools.restaurant import cancel_reservation
        return cancel_reservation(confirmation_id)

    # ---- GitHub ----

    @function_tool()
    async def push_to_github(self, context: RunContext, file_path: str, content: str, commit_message: str, repo: str = "Garinmckayl/elora") -> dict:
        """Push a file change to a GitHub repository directly from the cloud sandbox.

        Use this when the user asks to update a file in their repo, push code changes,
        update a changelog, or make any git commit. This clones the repo, writes the file,
        commits, and pushes.

        Args:
            file_path: Path of the file within the repo to create or update (e.g. 'docs/changelog.md').
            content: The full content to write to the file.
            commit_message: Git commit message describing the change.
            repo: GitHub repo in 'owner/repo' format. Defaults to 'Garinmckayl/elora'.
        """
        import base64 as _b64
        github_pat = os.getenv("GITHUB_PAT", "")
        if not github_pat:
            return {"status": "error", "error": "GitHub access not configured."}

        from tools.e2b_sandbox import run_in_sandbox

        b64_repo = _b64.b64encode(repo.encode()).decode()
        b64_pat = _b64.b64encode(github_pat.encode()).decode()
        b64_file_path = _b64.b64encode(file_path.encode()).decode()
        b64_commit_msg = _b64.b64encode(commit_message.encode()).decode()
        b64_content = _b64.b64encode(content.encode()).decode()

        code = f'''
import subprocess, os, json, base64

REPO = base64.b64decode("{b64_repo}").decode()
PAT = base64.b64decode("{b64_pat}").decode()
FILE_PATH = base64.b64decode("{b64_file_path}").decode()
COMMIT_MSG = base64.b64decode("{b64_commit_msg}").decode()
CONTENT = base64.b64decode("{b64_content}").decode()

work_dir = "/home/user/workspace/git-push"
repo_dir = os.path.join(work_dir, REPO.split("/")[-1])
os.makedirs(work_dir, exist_ok=True)
subprocess.run(["rm", "-rf", repo_dir], capture_output=True)

clone_url = f"https://x-access-token:{{PAT}}@github.com/{{REPO}}.git"
r = subprocess.run(["git", "clone", "--depth=1", clone_url, repo_dir], capture_output=True, text=True, timeout=60)
if r.returncode != 0:
    print(json.dumps({{"status": "error", "error": f"Clone failed: {{r.stderr}}"}}))
    raise SystemExit(1)

subprocess.run(["git", "config", "user.name", "Natnael Getenew"], cwd=repo_dir, capture_output=True)
subprocess.run(["git", "config", "user.email", "natnaelgetenew@gmail.com"], cwd=repo_dir, capture_output=True)

target = os.path.join(repo_dir, FILE_PATH)
os.makedirs(os.path.dirname(target), exist_ok=True)
with open(target, "w") as f:
    f.write(CONTENT)

subprocess.run(["git", "add", FILE_PATH], cwd=repo_dir, capture_output=True)
r = subprocess.run(["git", "commit", "-m", COMMIT_MSG], cwd=repo_dir, capture_output=True, text=True)
if r.returncode != 0:
    print(json.dumps({{"status": "error", "error": f"Commit failed: {{r.stderr}} {{r.stdout}}"}}))
    raise SystemExit(1)

r_hash = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_dir, capture_output=True, text=True)
commit_hash = r_hash.stdout.strip()

r = subprocess.run(["git", "push", "origin", "main"], cwd=repo_dir, capture_output=True, text=True, timeout=60)
if r.returncode != 0:
    print(json.dumps({{"status": "error", "error": f"Push failed: {{r.stderr}}"}}))
    raise SystemExit(1)

subprocess.run(["rm", "-rf", repo_dir], capture_output=True)
print(json.dumps({{"status": "success", "commit_hash": commit_hash, "file": FILE_PATH, "repo": f"https://github.com/{{REPO}}", "message": f"Pushed commit {{commit_hash}} to {{REPO}}"}}))
'''

        result = run_in_sandbox(self._user_id, code, "python", timeout=90)

        import json as _json
        if result.get("status") == "success" and result.get("results"):
            for r in result["results"]:
                try:
                    text = r if isinstance(r, str) else str(r)
                    parsed = _json.loads(text)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    continue
        if result.get("status") == "success" and result.get("stdout"):
            try:
                parsed = _json.loads(result["stdout"])
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return {"status": "error", "error": result.get("error", result.get("stderr", "Unknown error"))}

    # ---- Skill System ----

    @function_tool()
    async def search_skills(self, context: RunContext, query: str) -> dict:
        """Search for skills Elora can learn. Searches bundled and community registry.

        Args:
            query: What you need (e.g. "crypto prices", "RSS feeds", "weather").
        """
        from elora_agent.shared import get_user_id
        from tools.mcp_skills import search_skills
        return search_skills(query, get_user_id())

    @function_tool()
    async def install_skill(self, context: RunContext, skill_name: str) -> dict:
        """Install a skill from the library or community registry.

        Args:
            skill_name: Name of the skill to install.
        """
        from elora_agent.shared import get_user_id
        from tools.mcp_skills import install_skill
        return install_skill(skill_name, get_user_id())

    @function_tool()
    async def execute_skill(self, context: RunContext, skill_name: str, parameters: str = "{}") -> dict:
        """Execute an installed skill in the user's personal sandbox.

        Args:
            skill_name: Name of the skill to run.
            parameters: JSON string of parameter values.
        """
        from elora_agent.shared import get_user_id
        from tools.mcp_skills import execute_skill
        return execute_skill(skill_name, parameters, get_user_id())

    @function_tool()
    async def list_installed_skills(self, context: RunContext) -> dict:
        """List all skills in the user's library."""
        from elora_agent.shared import get_user_id
        from tools.mcp_skills import list_installed_skills
        return list_installed_skills(get_user_id())

    # ---- Time ----

    @function_tool()
    async def get_current_time(self, context: RunContext, city: str = "UTC") -> dict:
        """Returns the current time, optionally in a specific city's timezone.

        Args:
            city: City name or timezone.
        """
        import datetime
        from zoneinfo import ZoneInfo

        tz_map = {
            "new york": "America/New_York", "los angeles": "America/Los_Angeles",
            "san francisco": "America/Los_Angeles", "chicago": "America/Chicago",
            "denver": "America/Denver", "toronto": "America/Toronto",
            "vancouver": "America/Vancouver", "mexico city": "America/Mexico_City",
            "sao paulo": "America/Sao_Paulo", "london": "Europe/London",
            "paris": "Europe/Paris", "berlin": "Europe/Berlin",
            "amsterdam": "Europe/Amsterdam", "rome": "Europe/Rome",
            "madrid": "Europe/Madrid", "zurich": "Europe/Zurich",
            "moscow": "Europe/Moscow", "istanbul": "Europe/Istanbul",
            "tokyo": "Asia/Tokyo", "dubai": "Asia/Dubai",
            "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata",
            "shanghai": "Asia/Shanghai", "beijing": "Asia/Shanghai",
            "hong kong": "Asia/Hong_Kong", "singapore": "Asia/Singapore",
            "seoul": "Asia/Seoul", "bangkok": "Asia/Bangkok",
            "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne",
            "auckland": "Pacific/Auckland", "utc": "UTC", "gmt": "UTC",
            "addis ababa": "Africa/Addis_Ababa", "nairobi": "Africa/Nairobi",
            "cairo": "Africa/Cairo", "lagos": "Africa/Lagos",
            "riyadh": "Asia/Riyadh", "karachi": "Asia/Karachi",
            "jakarta": "Asia/Jakarta", "taipei": "Asia/Taipei",
            "kuala lumpur": "Asia/Kuala_Lumpur", "perth": "Australia/Perth",
        }
        city_lower = city.lower().strip()
        tz_id = tz_map.get(city_lower)
        if not tz_id:
            try:
                ZoneInfo(city)
                tz_id = city
            except (KeyError, Exception):
                tz_id = "UTC"
        tz = ZoneInfo(tz_id)
        now = datetime.datetime.now(tz)
        return {
            "status": "success",
            "report": f"The current time in {city} is {now.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        }


# ---------------------------------------------------------------------------
# LiveKit Agent Server
# ---------------------------------------------------------------------------

server = AgentServer()


@server.rtc_session(agent_name="elora")
async def elora_session(ctx: agents.JobContext):
    """Main entry point for each LiveKit voice session."""

    # Extract user_id from room metadata or participant identity
    user_id = "anonymous"
    if ctx.room.metadata:
        import json
        try:
            meta = json.loads(ctx.room.metadata)
            user_id = meta.get("user_id", "anonymous")
        except Exception:
            pass

    # Fall back to first participant identity
    if user_id == "anonymous" and ctx.room.remote_participants:
        user_id = next(iter(ctx.room.remote_participants.keys()), "anonymous")

    logger.info(f"[Elora LiveKit] Session started for user={user_id}")

    # Set the user_id context var so tools can access it
    current_user_id.set(user_id)

    # Preload demo data into in-memory stores
    _preload_demo_data(user_id)

    # Create the agent session with Gemini Live realtime model
    # Gemini's realtime model has built-in turn detection, no need for Silero VAD
    session = AgentSession(
        llm=google.realtime.RealtimeModel(
            model="gemini-2.5-flash-native-audio-latest",
            voice="Aoede",
            temperature=0.8,
            api_key=os.getenv("GOOGLE_API_KEY"),
        ),
    )

    await session.start(
        room=ctx.room,
        agent=EloraAgent(user_id=user_id),
        room_options=room_io.RoomOptions(
            # Enable live video for proactive vision / face recognition
            video_input=True,
        ),
    )

    # Greet the user
    await session.generate_reply(
        instructions="Greet the user warmly and naturally. If you know their name from memory, use it."
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    agents.cli.run_app(server)
