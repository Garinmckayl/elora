"""
Elora Backend -- FastAPI server with text chat + Live API bidi-streaming
Connects Expo mobile app to Gemini via Google ADK (text) and direct Live API (audio)
"""

import os
import json
import base64
import asyncio
import logging
import struct

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("elora")

# ---------------------------------------------------------------------------
# Firebase Auth -- verify ID tokens from the mobile client
# ---------------------------------------------------------------------------

_firebase_initialized = False

def _init_firebase():
    global _firebase_initialized
    if _firebase_initialized:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials
        # Prefer explicit service account file; fall back to ADC (works on Cloud Run automatically)
        sa_path = os.getenv("FIREBASE_SERVICE_ACCOUNT", "")
        if sa_path and os.path.exists(sa_path):
            cred = credentials.Certificate(sa_path)
        else:
            cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        logger.info("[Auth] Firebase Admin initialized")
    except Exception as e:
        logger.warning(f"[Auth] Firebase Admin init failed (auth disabled): {e}")


def verify_firebase_token(token: str) -> str | None:
    """
    Verify a Firebase ID token and return the uid, or None if invalid.
    Returns None (not raises) so callers can decide whether to reject or
    fall back to anonymous mode.
    """
    if not token:
        return None
    _init_firebase()
    try:
        from firebase_admin import auth as fb_auth
        decoded = fb_auth.verify_id_token(token)
        return decoded["uid"]
    except Exception as e:
        logger.warning(f"[Auth] Token verification failed: {e}")
        return None

app = FastAPI(title="Elora API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def strip_wav_header(data: bytes) -> bytes:
    """
    If *data* starts with a RIFF/WAVE header, return only the PCM payload
    (the contents of the 'data' sub-chunk). Otherwise return *data* unchanged.
    This is needed because the mobile client records WAV files (header + PCM)
    but Gemini Live expects raw PCM bytes.
    """
    if len(data) < 44:
        return data
    # Quick check: starts with "RIFF" … "WAVE"?
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return data
    # Walk the sub-chunks to find "data"
    pos = 12  # right after "WAVE"
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        chunk_size = struct.unpack_from("<I", data, pos + 4)[0]
        if chunk_id == b"data":
            start = pos + 8
            end = start + chunk_size
            return data[start:end]
        pos += 8 + chunk_size
    # Fallback: standard 44-byte header
    return data[44:]


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "elora-backend",
        "version": "0.4.0",
    }


# ---------------------------------------------------------------------------
# LiveKit Token Endpoint -- issues room tokens for the mobile app
# ---------------------------------------------------------------------------

LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")


@app.post("/livekit/token")
async def livekit_token(
    user_id: str = Query(default="anonymous"),
    token: str = Query(default=""),
):
    """Issue a LiveKit room token so the mobile app can join a voice session."""
    if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        return JSONResponse({"error": "LiveKit not configured"}, status_code=500)

    # Optionally verify Firebase token
    resolved_user_id = user_id
    if token:
        uid = verify_firebase_token(token)
        if uid:
            resolved_user_id = uid

    try:
        from livekit.api import AccessToken, VideoGrants, RoomConfiguration
        from livekit.protocol.agent_dispatch import RoomAgentDispatch
        room_name = f"elora-{resolved_user_id}"

        # Build participant token with agent dispatch request
        dispatch = RoomAgentDispatch(agent_name="elora")
        room_config = RoomConfiguration(agents=[dispatch])

        at = (
            AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(resolved_user_id)
            .with_name(resolved_user_id)
            .with_metadata(json.dumps({"user_id": resolved_user_id}))
            .with_grants(VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            ))
            .with_room_config(room_config)
        )

        return {
            "token": at.to_jwt(),
            "url": LIVEKIT_URL,
            "room": room_name,
        }
    except ImportError as ie:
        logger.error(f"[LiveKit] Import error: {ie}")
        return JSONResponse({"error": "livekit-api not installed"}, status_code=500)
    except Exception as e:
        logger.error(f"[LiveKit] Token error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# OAuth2 Flow for Gmail + Calendar
# ---------------------------------------------------------------------------

OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")
OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


@app.get("/auth/login/{user_id}")
async def auth_login(user_id: str):
    """Start OAuth2 flow -- redirect user to Google consent screen."""
    if not OAUTH_CLIENT_ID:
        return {"error": "OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID env var."}

    import urllib.parse
    params = {
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI or f"https://elora-backend-453139277365.us-central1.run.app/auth/callback",
        "response_type": "code",
        "scope": " ".join(OAUTH_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": user_id,  # Pass user_id through state param
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return {"auth_url": url}


@app.get("/auth/callback")
async def auth_callback(code: str = "", state: str = "", error: str = ""):
    """OAuth2 callback -- exchange code for tokens, then redirect back to Elora app."""
    if error:
        deep_link = f"elora://auth/error?message={error}"
        return HTMLResponse(_oauth_result_page(
            success=False,
            message=f"Authorization failed: {error}",
            deep_link=deep_link,
        ))

    user_id = state or "anonymous"

    try:
        import httpx
        token_resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": OAUTH_CLIENT_ID,
                "client_secret": OAUTH_CLIENT_SECRET,
                "redirect_uri": OAUTH_REDIRECT_URI or f"https://elora-backend-453139277365.us-central1.run.app/auth/callback",
                "grant_type": "authorization_code",
            },
        )
        token_data = token_resp.json()

        if "access_token" in token_data:
            from tools.gmail import set_user_token
            set_user_token(user_id, token_data)
            logger.info(f"OAuth tokens stored for user={user_id}")
            deep_link = f"elora://auth/success?user_id={user_id}"
            return HTMLResponse(_oauth_result_page(
                success=True,
                message="Connected! Elora can now send emails and manage your calendar.",
                deep_link=deep_link,
            ))
        else:
            msg = token_data.get("error_description", "Token exchange failed")
            deep_link = f"elora://auth/error?message={msg}"
            return HTMLResponse(_oauth_result_page(
                success=False,
                message=f"Connection failed: {msg}",
                deep_link=deep_link,
            ))

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        deep_link = f"elora://auth/error?message={str(e)}"
        return HTMLResponse(_oauth_result_page(
            success=False,
            message=f"An error occurred: {str(e)}",
            deep_link=deep_link,
        ))


def _oauth_result_page(success: bool, message: str, deep_link: str) -> str:
    """Return an HTML page that auto-redirects to the Elora app deep link."""
    icon = "✅" if success else "❌"
    color = "#48BB78" if success else "#E53E3E"
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Elora — {("Connected" if success else "Error")}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0A0E1A; color: #E8EAF0; display: flex; align-items: center;
           justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }}
    .card {{ background: #141929; border: 1px solid #2A3050; border-radius: 16px;
             padding: 40px 32px; max-width: 400px; width: 100%; text-align: center; }}
    .icon {{ font-size: 48px; margin-bottom: 16px; }}
    h2 {{ color: {color}; margin: 0 0 12px; font-size: 22px; }}
    p {{ color: #9BA3B8; margin: 0 0 24px; line-height: 1.5; }}
    .btn {{ display: inline-block; background: {color}; color: #fff; padding: 12px 28px;
            border-radius: 999px; text-decoration: none; font-weight: 600; font-size: 15px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h2>{"Success" if success else "Error"}</h2>
    <p>{message}</p>
    <a class="btn" href="{deep_link}">Return to Elora</a>
  </div>
  <script>
    // Auto-open the app after a short delay
    setTimeout(function() {{
      window.location.href = "{deep_link}";
    }}, 1200);
  </script>
</body>
</html>"""


@app.get("/auth/status/{user_id}")
async def auth_status(user_id: str):
    """Check if a user has connected their Google account."""
    from tools.gmail import get_user_token
    token = get_user_token(user_id)
    if token:
        return {"connected": True, "user_id": user_id}
    return {"connected": False, "user_id": user_id}


# ---------------------------------------------------------------------------
# ADK Agent Runner (text mode only)
# ---------------------------------------------------------------------------

from google import genai
from google.adk.runners import InMemoryRunner
from google.genai import types

from elora_agent.agent import (
    text_agent, current_user_id, current_browser_callback,
    send_email, read_emails,
    manage_email, batch_manage_emails,
    create_calendar_event, list_calendar_events,
    search_calendar_events, update_calendar_event, delete_calendar_event,
    web_search, fetch_webpage, browse_web,
    save_file, read_file, list_files, delete_file,
    remember, recall, get_current_time,
    schedule_reminder, list_reminders, cancel_reminder,
    create_presentation, create_document,
    set_morning_briefing, disable_morning_briefing,
    run_code,
    remember_person, recall_person, list_people, update_person_appearance,
    describe_person_from_camera, request_photo_search,
    send_sms, lookup_phone_for_person,
    generate_image, generate_music,
    SYSTEM_INSTRUCTION,
)

text_runner = InMemoryRunner(agent=text_agent, app_name="elora-text")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
LIVE_MODEL = os.getenv("ELORA_LIVE_MODEL", os.getenv("ELORA_MODEL", "gemini-2.0-flash-live-001"))
WAKE_MODEL = os.getenv("ELORA_WAKE_MODEL", "gemini-2.0-flash-live-001")

live_client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={"api_version": "v1beta"},
)

# Map tool names -> callable functions
TOOL_FUNCTIONS = {
    "send_email": send_email,
    "read_emails": read_emails,
    "manage_email": manage_email,
    "batch_manage_emails": batch_manage_emails,
    "create_calendar_event": create_calendar_event,
    "list_calendar_events": list_calendar_events,
    "search_calendar_events": search_calendar_events,
    "update_calendar_event": update_calendar_event,
    "delete_calendar_event": delete_calendar_event,
    "web_search": web_search,
    "fetch_webpage": fetch_webpage,
    "browse_web": browse_web,
    "save_file": save_file,
    "read_file": read_file,
    "list_files": list_files,
    "delete_file": delete_file,
    "remember": remember,
    "recall": recall,
    "get_current_time": get_current_time,
    "schedule_reminder": schedule_reminder,
    "list_reminders": list_reminders,
    "cancel_reminder": cancel_reminder,
    "create_presentation": create_presentation,
    "create_document": create_document,
    "set_morning_briefing": set_morning_briefing,
    "disable_morning_briefing": disable_morning_briefing,
    "run_code": run_code,
    "remember_person": remember_person,
    "recall_person": recall_person,
    "list_people": list_people,
    "update_person_appearance": update_person_appearance,
    "describe_person_from_camera": describe_person_from_camera,
    "request_photo_search": request_photo_search,
    "send_sms": send_sms,
    "lookup_phone_for_person": lookup_phone_for_person,
    "generate_image": generate_image,
    "generate_music": generate_music,
}

# Function declarations for the Live API (schema derived from docstrings)
LIVE_TOOL_DECLARATIONS = [
    {
        "name": "send_email",
        "description": "Sends an email on behalf of the user via Gmail.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Email address of the recipient."},
                "subject": {"type": "string", "description": "Subject line of the email."},
                "body": {"type": "string", "description": "Body text of the email."},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "read_emails",
        "description": "Reads recent emails from the user's inbox.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail search query (e.g., 'is:unread')."},
                "max_results": {"type": "integer", "description": "Maximum number of emails to return."},
            },
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Creates a calendar event for the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Name of the event."},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format."},
                "time": {"type": "string", "description": "Start time in HH:MM format (24-hour)."},
                "duration_minutes": {"type": "integer", "description": "Duration in minutes."},
                "timezone": {"type": "string", "description": "IANA timezone (e.g. 'America/New_York', 'Africa/Addis_Ababa'). Defaults to UTC."},
            },
            "required": ["title", "date", "time"],
        },
    },
    {
        "name": "list_calendar_events",
        "description": "Lists calendar events for a given date.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date: 'today', 'tomorrow', or YYYY-MM-DD."},
            },
        },
    },
    {
        "name": "web_search",
        "description": "Searches the web for current information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "save_file",
        "description": "Saves a file to the user's cloud workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Name of the file."},
                "content": {"type": "string", "description": "Text content to write."},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Reads a file from the user's cloud workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Name of the file."},
            },
            "required": ["filename"],
        },
    },
    {
        "name": "remember",
        "description": "Saves a fact or preference to the user's long-term memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "The fact or preference to remember."},
            },
            "required": ["fact"],
        },
    },
    {
        "name": "recall",
        "description": "Retrieves relevant facts from the user's long-term memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for in memory."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_current_time",
        "description": "Returns the current time, optionally in a specific city's timezone.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name or timezone (default: UTC)."},
            },
        },
    },
    {
        "name": "fetch_webpage",
        "description": "Fetches a webpage and returns its readable text content. Use for reading articles, checking prices, or summarising pages (no clicking needed).",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to fetch (must start with http:// or https://)."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "browse_web",
        "description": "Opens a real browser and autonomously completes a web task. Use for interactive tasks: booking flights, filling forms, logging into websites, clicking buttons.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Natural-language description of what to do (e.g. 'find round-trip flights from Addis Ababa to Dubai under $500')."},
                "start_url": {"type": "string", "description": "Optional starting URL. Defaults to Google."},
            },
            "required": ["task"],
        },
    },
    {
        "name": "schedule_reminder",
        "description": "Schedules a reminder that sends a push notification to the user's phone at the specified time.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "What to remind the user about."},
                "when": {"type": "string", "description": "When to fire: ISO datetime, or offset like '+2h', '+30m', '+1d', or 'tomorrow 9am'."},
                "repeat": {"type": "string", "description": "Optional repeat: 'daily', 'weekly', or omit for one-shot."},
            },
            "required": ["message", "when"],
        },
    },
    {
        "name": "list_reminders",
        "description": "Lists all pending reminders for the user.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_reminder",
        "description": "Cancels a scheduled reminder by its job ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The reminder job ID to cancel."},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "create_presentation",
        "description": "Creates a Google Slides presentation and returns a shareable link.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title of the presentation."},
                "slides": {
                    "type": "array",
                    "description": "List of slides, each with 'heading' (str) and 'body' (str).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "body": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["title", "slides"],
        },
    },
    {
        "name": "create_document",
        "description": "Creates a Google Doc with the given content and returns a shareable link.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title."},
                "content": {"type": "string", "description": "Full text content of the document."},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "set_morning_briefing",
        "description": "Sets up a daily proactive morning briefing. Elora will push a summary of your day every morning: calendar events, unread emails, and pending reminders.",
        "parameters": {
            "type": "object",
            "properties": {
                "time": {"type": "string", "description": "Time in HH:MM 24h format, e.g. '08:00'."},
                "timezone": {"type": "string", "description": "IANA timezone, e.g. 'America/New_York', 'Africa/Addis_Ababa'."},
            },
            "required": ["time"],
        },
    },
    {
        "name": "disable_morning_briefing",
        "description": "Disables the daily morning briefing.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "manage_email",
        "description": "Takes an action on a specific email: archive, trash, mark_read, mark_unread, label, or unlabel.",
        "parameters": {
            "type": "object",
            "properties": {
                "email_id": {"type": "string", "description": "The email ID from read_emails results."},
                "action": {"type": "string", "description": "One of: archive, trash, mark_read, mark_unread, label, unlabel."},
                "label": {"type": "string", "description": "Label name (required for label/unlabel actions)."},
            },
            "required": ["email_id", "action"],
        },
    },
    {
        "name": "batch_manage_emails",
        "description": "Applies an action to ALL emails matching a Gmail query. Confirm with user first.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail search query, e.g. 'from:newsletter@example.com'."},
                "action": {"type": "string", "description": "One of: archive, trash, mark_read, mark_unread, label, unlabel."},
                "label": {"type": "string", "description": "Label name (required for label/unlabel)."},
            },
            "required": ["query", "action"],
        },
    },
    {
        "name": "search_calendar_events",
        "description": "Searches calendar events by keyword across next 30 days. Returns event IDs needed for update/delete.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to search, e.g. 'dentist', 'standup'."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "update_calendar_event",
        "description": "Updates an existing calendar event. Use search_calendar_events first to get the event_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID from search_calendar_events."},
                "title": {"type": "string", "description": "New title (optional)."},
                "date": {"type": "string", "description": "New date in YYYY-MM-DD (optional)."},
                "time": {"type": "string", "description": "New start time in HH:MM (optional)."},
                "duration_minutes": {"type": "integer", "description": "New duration in minutes (optional)."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "delete_calendar_event",
        "description": "Permanently deletes a calendar event. Confirm with user first.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID to delete."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "list_files",
        "description": "Lists all files saved in the user's cloud workspace.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "delete_file",
        "description": "Permanently deletes a file from the user's workspace. Confirm first.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Name of the file to delete."},
            },
            "required": ["filename"],
        },
    },
    {
        "name": "run_code",
        "description": (
            "Executes Python or JavaScript code in a secure cloud sandbox and returns the output. "
            "Use for: calculations, data processing, scripts, algorithms, generating text/data programmatically."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "language": {"type": "string", "description": "Programming language: 'python' or 'javascript'."},
                "code": {"type": "string", "description": "The full source code to execute."},
                "timeout": {"type": "integer", "description": "Max execution time in seconds (5-120). Default 30."},
            },
            "required": ["language", "code"],
        },
    },
    {
        "name": "remember_person",
        "description": "Store or update a person who matters to the user — their name, relationship, appearance, contact info, and notes.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "relationship": {"type": "string", "description": "e.g. girlfriend, mom, colleague, friend"},
                "appearance_description": {"type": "string"},
                "contact_email": {"type": "string"},
                "contact_phone": {"type": "string"},
                "notes": {"type": "string"},
                "aliases": {"type": "string", "description": "Comma-separated nicknames"},
            },
            "required": ["name", "relationship"],
        },
    },
    {
        "name": "recall_person",
        "description": "Look up what Elora knows about a person by name or relationship. Use before messaging them.",
        "parameters": {
            "type": "object",
            "properties": {
                "name_or_relationship": {"type": "string"},
            },
            "required": ["name_or_relationship"],
        },
    },
    {
        "name": "list_people",
        "description": "Return everyone Elora knows about for this user.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "update_person_appearance",
        "description": "Update visual appearance description for a known person after seeing their photo.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "appearance_description": {"type": "string"},
            },
            "required": ["name", "appearance_description"],
        },
    },
    {
        "name": "send_sms",
        "description": "Send a text message (SMS) to a phone number. Always confirm with user first.",
        "parameters": {
            "type": "object",
            "properties": {
                "to_phone": {"type": "string", "description": "E.164 phone number e.g. +14155552671"},
                "message": {"type": "string"},
            },
            "required": ["to_phone", "message"],
        },
    },
    {
        "name": "request_photo_search",
        "description": (
            "Ask the user's phone to search their camera roll for photos containing a specific person. "
            "Uses on-device face detection (ML Kit) + Gemini Vision for matching. "
            "Results come back as a follow-up message. "
            "Use when user asks 'find photos with Maya', 'show me pictures of mom', etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "person_name": {
                    "type": "string",
                    "description": "Name of the person to find photos of. e.g. 'Maya', 'mom', 'me'",
                },
            },
            "required": ["person_name"],
        },
    },
    {
        "name": "describe_person_from_camera",
        "description": (
            "Use the live camera to see and describe the person in front of it, "
            "then remember what they look like. "
            "Call this when the user says 'this is [name]', 'remember what she looks like', "
            "or 'this is me' while the camera is active."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The person's name. Use 'me' if the user is showing themselves.",
                },
                "relationship": {
                    "type": "string",
                    "description": "Their relationship to the user, e.g. 'girlfriend', 'mom', 'colleague'. Optional if already stored.",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "lookup_phone_for_person",
        "description": "Looks up the phone number for a remembered person.",
        "parameters": {
            "type": "object",
            "properties": {
                "name_or_relationship": {"type": "string"},
            },
            "required": ["name_or_relationship"],
        },
    },
    {
        "name": "generate_image",
        "description": "Generates an image from a text description. Use for art, logos, illustrations, photos, or any visual content the user asks for.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description of the image to create.",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "Aspect ratio like '1:1', '16:9', '9:16', '3:2'. Defaults to '1:1'.",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "generate_music",
        "description": "Generates original music from a text description of mood, genre, and style using Google Lyria 3. Use when the user asks for a song, jingle, background music, or any audio track.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of the music (mood, genre, instruments, tempo, energy).",
                },
                "duration_seconds": {
                    "type": "integer",
                    "description": "How long the track should be in seconds (5-30). Defaults to 15.",
                },
            },
            "required": ["prompt"],
        },
    },
]

# ---------------------------------------------------------------------------
# Live API config -- voice + tool declarations
# ---------------------------------------------------------------------------

LIVE_CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name="Aoede",   # warm, natural female voice
            )
        )
    ),
    system_instruction=types.Content(
        parts=[types.Part.from_text(text=SYSTEM_INSTRUCTION)]
    ),
    tools=[{"function_declarations": LIVE_TOOL_DECLARATIONS}],
)


def execute_tool(
    name: str,
    args: dict,
    user_id: str,
    browser_cb=None,
) -> dict:
    """
    Dispatch a tool call by name, running it in the correct user context.
    Called from the Live API tool_call handler (sync, inside asyncio.to_thread).
    """
    from elora_agent.agent import current_user_id, current_browser_callback

    # Set per-request context vars for this thread
    uid_token = current_user_id.set(user_id)
    cb_token = current_browser_callback.set(browser_cb) if browser_cb is not None else None

    try:
        fn = TOOL_FUNCTIONS.get(name)
        if fn is None:
            logger.warning(f"[execute_tool] Unknown tool: {name}")
            return {"status": "error", "report": f"Unknown tool: {name}"}
        result = fn(**args) if args else fn()
        logger.info(f"[execute_tool] {name} -> {str(result)[:120]}")

        # Trim large tool results so they don't bloat the Gemini context window
        # (inspired by OpenClaw's compaction strategy)
        if isinstance(result, dict):
            for key in ("report", "content", "text", "output", "html", "body"):
                if key in result and isinstance(result[key], str) and len(result[key]) > 2000:
                    original_len = len(result[key])
                    s = result[key]
                    result[key] = s[:900] + f"\n...[{original_len - 1800} chars trimmed]...\n" + s[-900:]

        # Invalidate face recognition cache after describe_person_from_camera
        # (a new face reference was just stored in GCS)
        if name == "describe_person_from_camera":
            try:
                from tools.face_recognition_engine import invalidate_cache
                invalidate_cache(user_id)
            except Exception:
                pass

        return result if isinstance(result, dict) else {"status": "success", "report": str(result)}
    except Exception as e:
        logger.error(f"[execute_tool] {name} error: {e}", exc_info=True)
        return {"status": "error", "report": str(e)}
    finally:
        current_user_id.reset(uid_token)
        if cb_token is not None:
            current_browser_callback.reset(cb_token)


# ---------------------------------------------------------------------------
# Text chat -- streaming tool events + final response
# ---------------------------------------------------------------------------

async def run_text_agent(
    user_id: str,
    session_id: str,
    message: str,
    websocket: WebSocket | None = None,
):
    """
    Run Elora in text mode.

    If *websocket* is provided:
      - intermediate tool_call/tool_result events are streamed in real time
      - browser screenshots and step narration are forwarded as
        browser_screenshot / browser_step messages (same format as live mode)
    """
    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=message)],
    )

    # Wire up browser screenshot streaming for text mode
    loop = asyncio.get_event_loop()

    if websocket is not None:
        async def _send_browser_event(event_type: str, png: bytes | None, text_content: str | None):
            try:
                if event_type == "screenshot" and png is not None:
                    b64 = base64.b64encode(png).decode()
                    await websocket.send_text(json.dumps({
                        "type": "browser_screenshot",
                        "content": b64,
                    }))
                elif event_type == "step" and text_content:
                    await websocket.send_text(json.dumps({
                        "type": "browser_step",
                        "content": text_content,
                    }))
            except Exception as e:
                logger.warning(f"[Text WS] browser event send failed: {e}")

        def _thread_safe_browser_cb(event_type: str, png: bytes | None, text_content: str | None):
            fut = asyncio.run_coroutine_threadsafe(
                _send_browser_event(event_type, png, text_content), loop
            )
            try:
                fut.result(timeout=10)
            except Exception as e:
                logger.warning(f"[Text WS] browser cb timeout: {e}")

        async def _async_browser_cb(event_type: str, png: bytes | None, text_content: str | None):
            _thread_safe_browser_cb(event_type, png, text_content)

        browser_cb_token = current_browser_callback.set(_async_browser_cb)

        # Tell the client a browser task is starting so it opens the modal
        # Only sent when browse_web is actually invoked (checked in tool_call handler below)
        # We store a reference to the websocket for the tool_call handler to use
    else:
        browser_cb_token = None

    user_token = current_user_id.set(user_id)

    response_text = ""
    try:
        async for event in text_runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            # Stream tool-call/result events so the frontend shows tool cards
            if websocket is not None:
                try:
                    if hasattr(event, "get_function_calls"):
                        for fc in (event.get_function_calls() or []):
                            # Send browser_starting before browse_web so the modal opens immediately
                            if fc.name == "browse_web":
                                await websocket.send_text(json.dumps({
                                    "type": "status",
                                    "content": "browser_starting",
                                }))
                            await websocket.send_text(json.dumps({
                                "type": "tool_call",
                                "name": fc.name,
                                "args": dict(fc.args) if fc.args else {},
                            }))
                    if hasattr(event, "get_function_responses"):
                        for fr in (event.get_function_responses() or []):
                            result = fr.response if isinstance(fr.response, dict) else {"value": str(fr.response)}

                            # For music/image generation, send the large binary payload
                            # as a separate message so we don't blow up the WebSocket frame
                            if isinstance(result, dict) and result.get("audio_base64"):
                                # Send a dedicated audio message first
                                await websocket.send_text(json.dumps({
                                    "type": "audio_result",
                                    "name": fr.name,
                                    "audio_base64": result["audio_base64"],
                                    "mime_type": result.get("mime_type", "audio/wav"),
                                    "duration_seconds": result.get("duration_seconds"),
                                    "report": result.get("report", ""),
                                }))
                                # Then send a slim tool_result without the huge base64
                                slim = {k: v for k, v in result.items() if k != "audio_base64"}
                                await websocket.send_text(json.dumps({
                                    "type": "tool_result",
                                    "name": fr.name,
                                    "result": slim,
                                }))
                            elif isinstance(result, dict) and result.get("image_base64"):
                                # Same for images
                                await websocket.send_text(json.dumps({
                                    "type": "image_result",
                                    "name": fr.name,
                                    "image_base64": result["image_base64"],
                                    "mime_type": result.get("mime_type", "image/png"),
                                    "report": result.get("report", ""),
                                }))
                                slim = {k: v for k, v in result.items() if k != "image_base64"}
                                await websocket.send_text(json.dumps({
                                    "type": "tool_result",
                                    "name": fr.name,
                                    "result": slim,
                                }))
                            else:
                                await websocket.send_text(json.dumps({
                                    "type": "tool_result",
                                    "name": fr.name,
                                    "result": result,
                                }))
                except Exception as e:
                    logger.warning(f"[Text WS] Failed to stream tool event: {e}")

            if event.is_final_response():
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text
    finally:
        current_user_id.reset(user_token)
        if browser_cb_token is not None:
            current_browser_callback.reset(browser_cb_token)

    return response_text


# ---------------------------------------------------------------------------
# WebSocket -- text mode
# ---------------------------------------------------------------------------

@app.websocket("/ws/{user_id}")
async def websocket_text(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(default=""),
):
    """WebSocket endpoint for text chat with Elora."""
    await websocket.accept()

    # Resolve real uid from Firebase token if provided; fall back to path param
    verified_uid = verify_firebase_token(token)
    resolved_user_id = verified_uid if verified_uid else user_id
    if verified_uid:
        logger.info(f"[Text WS] Authenticated: uid={resolved_user_id}")
    else:
        logger.info(f"[Text WS] Unauthenticated (demo mode): user={resolved_user_id}")

    # Set user context so all tool calls are scoped to this user
    token_ctx = current_user_id.set(resolved_user_id)

    # Track user activity for the proactive engine
    from tools.proactive import update_last_active
    update_last_active(resolved_user_id)

    session = await text_runner.session_service.create_session(
        app_name="elora-text",
        user_id=resolved_user_id,
    )

    # Inject long-term memory context into the text session
    # (The text agent has static system instruction, so we send context as a hidden first turn)
    _memory_header = ""
    try:
        from tools.session_memory import build_memory_context
        _sm = build_memory_context(resolved_user_id)
        if _sm:
            _memory_header += _sm + "\n\n"
    except Exception:
        pass
    try:
        from tools.memory_compaction import build_profile_context
        _pc = build_profile_context(resolved_user_id)
        if _pc:
            _memory_header += _pc + "\n\n"
    except Exception:
        pass
    if _memory_header:
        # Send a context injection message so the agent is aware of the user's history
        try:
            name = _get_user_name(resolved_user_id)
            name_line = f"The user's name is {name}. Address them as {name.split()[0]}.\n\n" if name else ""
            context_msg = f"[SYSTEM CONTEXT — do not repeat this to the user, just use it to inform your responses]\n\n{name_line}{_memory_header}"
            await run_text_agent(resolved_user_id, session.id, context_msg)
        except Exception as e:
            logger.debug(f"[Text WS] Memory context injection failed: {e}")

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type", "text")
            content = message.get("content", "")

            # Track every interaction for proactive engine
            update_last_active(resolved_user_id)

            if msg_type == "text":
                try:
                    response = await run_text_agent(
                        resolved_user_id, session.id, content, websocket=websocket
                    )
                    await websocket.send_text(json.dumps({
                        "type": "text",
                        "content": response,
                    }))
                    # Fire-and-forget: extract and store any personal facts from this turn
                    asyncio.create_task(asyncio.to_thread(
                        __import__("tools.memory", fromlist=["auto_memorise"]).auto_memorise,
                        resolved_user_id,
                        f"User: {content}\nElora: {response}",
                    ))
                except Exception as e:
                    logger.error(f"[Text WS] run_text_agent error: {type(e).__name__}: {e}")
                    try:
                        await websocket.send_text(json.dumps({
                            "type": "text",
                            "content": f"Sorry, I hit an error processing that: {type(e).__name__}. Please try again.",
                        }))
                    except Exception:
                        pass
            elif msg_type == "image":
                # Pass image to Gemini multimodal via text runner
                image_content = types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(
                            data=base64.b64decode(content),
                            mime_type="image/jpeg",
                        ),
                        types.Part.from_text(
                            text=message.get("prompt", "What do you see in this image?")
                        ),
                    ],
                )
                response_text = ""
                async for event in text_runner.run_async(
                    user_id=resolved_user_id,
                    session_id=session.id,
                    new_message=image_content,
                ):
                    try:
                        if hasattr(event, "get_function_calls"):
                            for fc in (event.get_function_calls() or []):
                                await websocket.send_text(json.dumps({
                                    "type": "tool_call",
                                    "name": fc.name,
                                    "args": dict(fc.args) if fc.args else {},
                                }))
                        if hasattr(event, "get_function_responses"):
                            for fr in (event.get_function_responses() or []):
                                await websocket.send_text(json.dumps({
                                    "type": "tool_result",
                                    "name": fr.name,
                                    "result": fr.response if isinstance(fr.response, dict) else {"value": str(fr.response)},
                                }))
                    except Exception as e:
                        logger.warning(f"[Text WS] Failed to stream image tool event: {e}")
                    if event.is_final_response() and event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                response_text += part.text

                await websocket.send_text(json.dumps({
                    "type": "text",
                    "content": response_text,
                }))

    except WebSocketDisconnect:
        logger.info(f"[Text WS] Disconnected: user={resolved_user_id}")
    except Exception as e:
        logger.error(f"[Text WS] Error: {e}")
        await websocket.close()
    finally:
        current_user_id.reset(token_ctx)


# ---------------------------------------------------------------------------
# Per-user Live config -- includes user's name in system instruction
# ---------------------------------------------------------------------------

def _get_user_name(user_id: str) -> str:
    """Fetch the user's saved name from Firestore (fast, best-effort)."""
    try:
        from google.cloud import firestore as fs
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
        if not project:
            return ""
        db = fs.Client(project=project)
        doc = db.collection("user_profiles").document(user_id).get()
        if doc.exists:
            return doc.to_dict().get("name", "")
    except Exception:
        pass
    return ""


def _make_live_config(user_id: str) -> types.LiveConnectConfig:
    """Build a personalised LiveConnectConfig for this user."""
    name = _get_user_name(user_id)
    instruction = SYSTEM_INSTRUCTION

    # Inject recent session summaries for long-term memory continuity
    try:
        from tools.session_memory import build_memory_context
        memory_context = build_memory_context(user_id)
    except Exception:
        memory_context = ""

    # Inject compacted user profile from long-term memory
    try:
        from tools.memory_compaction import build_profile_context
        profile_context = build_profile_context(user_id)
    except Exception:
        profile_context = ""

    header = ""
    if name:
        header += f"The user's name is {name}. Address them as {name.split()[0]}.\n\n"
    if profile_context:
        header += profile_context + "\n\n"
    if memory_context:
        header += memory_context + "\n\n"

    if header:
        instruction = header + SYSTEM_INSTRUCTION

    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Aoede",
                )
            )
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=instruction)]
        ),
        tools=[{"function_declarations": LIVE_TOOL_DECLARATIONS}],
    )


# ---------------------------------------------------------------------------
# WebSocket -- live audio mode (Gemini Live API direct bidi-streaming)
# ---------------------------------------------------------------------------

@app.websocket("/ws/live/{user_id}")
async def websocket_live(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(default=""),
):
    """
    WebSocket endpoint for live audio with Elora.

    Supports two modes:
    1. Single-shot: send audio, get voice response (per-interaction Gemini session)
    2. Call mode: persistent Gemini session for continuous conversation

    Protocol (client -> server):
      - {"type": "audio", "content": "<base64>", "mime_type": "..."}
      - {"type": "text", "content": "..."}
      - {"type": "call_start"}  -- open persistent session
      - {"type": "call_end"}    -- close persistent session

    Protocol (server -> client):
      - Binary frames: raw PCM audio (24kHz 16-bit mono)
      - {"type": "text", "content": "..."}
      - {"type": "transcript", "content": "..."}
      - {"type": "tool_call", "name": "...", "args": {...}}
      - {"type": "status", "content": "processing|done|error:..."}
    """
    await websocket.accept()

    # Resolve real uid from Firebase token if provided; fall back to path param
    verified_uid = verify_firebase_token(token)
    resolved_user_id = verified_uid if verified_uid else user_id
    if verified_uid:
        logger.info(f"[Live WS] Authenticated: uid={resolved_user_id}")
    else:
        logger.info(f"[Live WS] Unauthenticated (demo mode): user={resolved_user_id}")

    # Set user context for this connection
    ctx_token = current_user_id.set(resolved_user_id)

    # Track user activity for the proactive engine
    from tools.proactive import update_last_active
    update_last_active(resolved_user_id)

    # Persistent Gemini session for call mode
    call_session = None
    call_ctx = None  # async context manager

    # Lock to prevent concurrent reads from the Gemini session
    # (proactive vision loop and main handler both call session.receive())
    _session_lock = asyncio.Lock()

    # ---------------------------------------------------------------------------
    # Session transcript accumulator — for post-call memory summarisation
    # ---------------------------------------------------------------------------
    _session_transcript: list[dict] = []   # {"role": "user"|"elora", "text": str}

    def _add_to_transcript(role: str, text: str):
        """Append a turn to the in-memory transcript. Caps at 200 turns."""
        if text and len(text.strip()) > 2:
            _session_transcript.append({"role": role, "text": text.strip()})
            if len(_session_transcript) > 200:
                _session_transcript.pop(0)

    # ---------------------------------------------------------------------------
    # Proactive vision state -- Elora speaks up when she notices something
    # ---------------------------------------------------------------------------
    import time as _time

    _vision_state = {
        "camera_active": False,
        "last_user_activity": _time.monotonic(),   # updated on every user message / frame
        "last_proactive_at": 0.0,                   # last time we injected a vision prompt
        "last_scene_desc": "",                      # avoid repeating the same observation
        "proactive_task": None,                     # asyncio.Task handle
    }

    PROACTIVE_SILENCE_THRESHOLD = 8.0    # seconds of silence before Elora looks around
    PROACTIVE_COOLDOWN = 25.0            # minimum seconds between proactive observations
    PROACTIVE_CHECK_INTERVAL = 3.0       # how often the background loop polls

    async def _proactive_vision_loop():
        """
        Background task: every PROACTIVE_CHECK_INTERVAL seconds, check whether:
          1. Camera is active
          2. User has been quiet for PROACTIVE_SILENCE_THRESHOLD seconds
          3. It's been at least PROACTIVE_COOLDOWN since the last proactive comment
        If all three → grab the latest frame → inject a hidden [VISION CHECK] turn
        into the live Gemini session so Elora can decide whether to say something.
        """
        while True:
            await asyncio.sleep(PROACTIVE_CHECK_INTERVAL)
            try:
                if not call_session:
                    continue
                if not _vision_state["camera_active"]:
                    continue

                now = _time.monotonic()
                silence = now - _vision_state["last_user_activity"]
                since_last = now - _vision_state["last_proactive_at"]

                if silence < PROACTIVE_SILENCE_THRESHOLD:
                    continue
                if since_last < PROACTIVE_COOLDOWN:
                    continue

                from tools.camera_memory import get_last_frame
                frame_bytes = get_last_frame(resolved_user_id)
                if not frame_bytes:
                    continue

                # ── Step 1: dedicated face recognition (deterministic, ~85% accuracy) ──
                # Run in a thread so we don't block the event loop during Gemini REST calls
                face_match = None
                try:
                    from tools.face_recognition_engine import identify_person_in_frame
                    face_match = await asyncio.to_thread(
                        identify_person_in_frame, resolved_user_id, frame_bytes
                    )
                except Exception as e:
                    logger.warning(f"[ProactiveVision] Face recognition error: {e}")

                # ── Step 2: build the Gemini prompt ──
                # If we identified someone, tell Elora exactly who it is.
                # Elora's job is purely to decide what to say — not to do recognition.
                if face_match:
                    name = face_match["name"]
                    relationship = face_match.get("relationship", "")
                    last_texted = face_match.get("last_texted", "")
                    birthday = face_match.get("birthday", "")
                    confidence = face_match.get("confidence", 0)

                    # Build natural context for last-contact timing
                    last_contact_str = ""
                    if last_texted:
                        try:
                            import datetime
                            lt = datetime.datetime.fromisoformat(last_texted)
                            days = (datetime.datetime.utcnow() - lt).days
                            if days == 0:
                                last_contact_str = "you were in touch today"
                            elif days == 1:
                                last_contact_str = "you last texted yesterday"
                            elif days < 7:
                                last_contact_str = f"you last texted {days} days ago"
                            elif days < 30:
                                weeks = days // 7
                                last_contact_str = f"you haven't texted in {weeks} week{'s' if weeks>1 else ''}"
                            else:
                                last_contact_str = f"you haven't been in touch for over a month"
                        except Exception:
                            pass

                    birthday_str = ""
                    if birthday:
                        try:
                            import datetime
                            bday = datetime.datetime.strptime(birthday, "%Y-%m-%d")
                            today = datetime.datetime.utcnow()
                            next_bday = bday.replace(year=today.year)
                            if next_bday < today:
                                next_bday = next_bday.replace(year=today.year + 1)
                            days_to_bday = (next_bday - today).days
                            if days_to_bday <= 14:
                                birthday_str = f" Their birthday is in {days_to_bday} days."
                        except Exception:
                            pass

                    vision_prompt = (
                        f"[VISION CHECK — FACE IDENTIFIED]\n"
                        f"The face recognition system has identified the person in the camera "
                        f"as {name} ({relationship}) with {int(confidence*100)}% confidence.\n"
                        f"{f'Context: {last_contact_str}.' if last_contact_str else ''}"
                        f"{birthday_str}\n\n"
                        f"React naturally as Elora — mention {name.split()[0]} warmly in 1-2 sentences. "
                        f"You might note that you haven't seen them talk in a while, or wish them well, "
                        f"or offer to send a message. Keep it warm and personal, not robotic."
                    )
                    logger.info(
                        f"[ProactiveVision] Face match: {name} "
                        f"(confidence={confidence:.2f}) — injecting identity-aware prompt"
                    )
                else:
                    # No face identified — general scene observation
                    # Build people list for context (Elora may recognise from voice/context)
                    people_context = ""
                    try:
                        from tools.people import list_people as _list_people
                        ppl = _list_people(user_id=resolved_user_id)
                        people_list = ppl.get("people", [])
                        if people_list:
                            names = ", ".join(
                                f"{p.get('name','?')} ({p.get('relationship','?')})"
                                for p in people_list[:6]
                            )
                            people_context = f"\nFor context, people you know: {names}."
                    except Exception:
                        pass

                    vision_prompt = (
                        "[VISION CHECK] The camera is active. Look at this frame and decide "
                        "whether there is anything worth mentioning to the user — something interesting, "
                        "useful, or worth a gentle observation. "
                        "If there is nothing notable, respond with exactly: <silent>"
                        f"{people_context}"
                        "\nDo NOT describe the image as a caption. React like a caring friend "
                        "who glances over and notices something. 1-2 sentences max."
                    )
                    logger.info(f"[ProactiveVision] No face match — general vision check")

                await call_session.send_client_content(
                    turns=[
                        {"role": "user", "parts": [
                            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(frame_bytes).decode()}},
                            {"text": vision_prompt},
                        ]},
                    ],
                    turn_complete=True,
                )

                _vision_state["last_proactive_at"] = now

                # The background _receive_loop handles streaming the response
                # so we don't need to read here.
                logger.info("[ProactiveVision] Vision prompt sent — receive loop will handle response")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[ProactiveVision] Error: {e}")

    async def transcribe_audio(audio_bytes: bytes, mime: str) -> str:
        """Transcribe audio using Gemini generate_content (async)."""
        try:
            resp = await live_client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=[types.Content(role="user", parts=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime),
                    types.Part.from_text(text="Transcribe this audio exactly. Return only the transcription, nothing else."),
                ])],
            )
            return (resp.text or "").strip()
        except Exception as e:
            logger.error(f"[Transcribe] Failed with {type(e).__name__}: {e}")
            raise

    async def stream_gemini_response(gemini_session, websocket):
        """Read one full turn of response from Gemini and stream to client.
        Used for single-shot mode only (non-call mode).
        """
        audio_chunk_count = 0
        loop = asyncio.get_event_loop()
        # Browser callback: called from a worker thread, posts messages back to the
        # main event loop so screenshots arrive over the WebSocket in real time.
        def _make_browser_callback(ws):
            async def _send_browser_event(event_type: str, png: bytes | None, text: str | None):
                if event_type == "screenshot" and png is not None:
                    b64 = base64.b64encode(png).decode()
                    await ws.send_text(json.dumps({
                        "type": "browser_screenshot",
                        "content": b64,
                    }))
                elif event_type == "step" and text:
                    await ws.send_text(json.dumps({
                        "type": "browser_step",
                        "content": text,
                    }))

            # Wrap in a thread-safe version that can be called from asyncio.run() in a thread
            def thread_safe_callback(event_type: str, png: bytes | None, text: str | None):
                fut = asyncio.run_coroutine_threadsafe(_send_browser_event(event_type, png, text), loop)
                try:
                    fut.result(timeout=10)
                except Exception as e:
                    logger.warning(f"[Browser CB] Failed to send event: {e}")

            # Return an async wrapper that agent.py's browse_web() can await
            async def async_callback(event_type: str, png: bytes | None, text: str | None):
                thread_safe_callback(event_type, png, text)

            return async_callback

        browser_cb = _make_browser_callback(websocket)

        async with _session_lock:
            turn = gemini_session.receive()
            async for response in turn:
                if pcm_data := response.data:
                    await websocket.send_bytes(pcm_data)
                    audio_chunk_count += 1
                if text := response.text:
                    await websocket.send_text(json.dumps({"type": "text", "content": text}))
                    _add_to_transcript("elora", text)
                if tool_call := response.tool_call:
                    function_responses = []
                    for fc in tool_call.function_calls:
                        logger.info(f"[Live WS] Tool: {fc.name}({fc.args})")
                        await websocket.send_text(json.dumps({
                            "type": "tool_call", "name": fc.name, "args": fc.args or {},
                        }))
                        result = await asyncio.to_thread(
                            execute_tool, fc.name, fc.args or {}, resolved_user_id,
                            browser_cb if fc.name == "browse_web" else None,
                        )
                        function_responses.append(types.FunctionResponse(
                            id=fc.id, name=fc.name, response=result,
                        ))
                    await gemini_session.send_tool_response(function_responses=function_responses)
        logger.info(f"[Live WS] Turn done: {audio_chunk_count} audio chunks")
        return audio_chunk_count

    # ------------------------------------------------------------------
    # Background receive loop — continuously reads from call_session and
    # forwards audio/text/tool_call/transcript to the client.
    # ------------------------------------------------------------------
    _receive_task = None   # asyncio.Task handle

    async def _receive_loop():
        """Continuously read from call_session.receive() and forward to client."""
        nonlocal call_session, call_ctx
        loop = asyncio.get_event_loop()

        def _make_browser_callback_for_loop(ws):
            async def _send_browser_event(event_type: str, png: bytes | None, text: str | None):
                if event_type == "screenshot" and png is not None:
                    b64 = base64.b64encode(png).decode()
                    await ws.send_text(json.dumps({
                        "type": "browser_screenshot",
                        "content": b64,
                    }))
                elif event_type == "step" and text:
                    await ws.send_text(json.dumps({
                        "type": "browser_step",
                        "content": text,
                    }))
            def thread_safe_callback(event_type: str, png: bytes | None, text: str | None):
                fut = asyncio.run_coroutine_threadsafe(_send_browser_event(event_type, png, text), loop)
                try:
                    fut.result(timeout=10)
                except Exception as e:
                    logger.warning(f"[Browser CB] Failed to send event: {e}")
            async def async_callback(event_type: str, png: bytes | None, text: str | None):
                thread_safe_callback(event_type, png, text)
            return async_callback

        browser_cb = _make_browser_callback_for_loop(websocket)

        try:
            while call_session:
                try:
                    turn = call_session.receive()
                    async for response in turn:
                        # Input audio transcription (what the user said)
                        # This can arrive independently of model_turn
                        if response.server_content:
                            sc = response.server_content
                            if sc.input_transcription and sc.input_transcription.text:
                                transcript_text = sc.input_transcription.text.strip()
                                if transcript_text:
                                    logger.info(f"[ReceiveLoop] User transcript: {transcript_text[:80]}")
                                    _add_to_transcript("user", transcript_text)
                                    try:
                                        await websocket.send_text(json.dumps({
                                            "type": "transcript",
                                            "content": transcript_text,
                                        }))
                                    except Exception:
                                        return

                            # Barge-in: model was interrupted by user speech
                            if sc.interrupted:
                                logger.info("[ReceiveLoop] Model interrupted (barge-in)")
                                try:
                                    await websocket.send_text(json.dumps({
                                        "type": "status", "content": "interrupted",
                                    }))
                                except Exception:
                                    return

                        # Binary PCM audio from Gemini
                        if pcm_data := response.data:
                            try:
                                await websocket.send_bytes(pcm_data)
                            except Exception:
                                return

                        # Text response (live captions / answers)
                        if text := response.text:
                            if "<silent>" in text.lower():
                                logger.debug("[ReceiveLoop] Elora chose silence")
                                continue
                            _add_to_transcript("elora", text)
                            try:
                                await websocket.send_text(json.dumps({"type": "text", "content": text}))
                            except Exception:
                                return

                        # Tool calls
                        if tool_call := response.tool_call:
                            function_responses = []
                            for fc in tool_call.function_calls:
                                logger.info(f"[ReceiveLoop] Tool: {fc.name}({fc.args})")
                                try:
                                    await websocket.send_text(json.dumps({
                                        "type": "tool_call", "name": fc.name, "args": fc.args or {},
                                    }))
                                except Exception:
                                    return
                                result = await asyncio.to_thread(
                                    execute_tool, fc.name, fc.args or {}, resolved_user_id,
                                    browser_cb if fc.name == "browse_web" else None,
                                )
                                function_responses.append(types.FunctionResponse(
                                    id=fc.id, name=fc.name, response=result,
                                ))
                            if call_session:
                                await call_session.send_tool_response(function_responses=function_responses)

                    logger.debug("[ReceiveLoop] Turn complete")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(f"[ReceiveLoop] Turn error: {e}")
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.info("[ReceiveLoop] Cancelled")
        except Exception as e:
            logger.error(f"[ReceiveLoop] Fatal: {e}")

    try:
        while True:
            data = await websocket.receive()

            # ==== BINARY FRAME: raw PCM audio chunk (streaming mode) ====
            if "bytes" in data and data["bytes"]:
                raw_pcm = data["bytes"]
                _vision_state["last_user_activity"] = _time.monotonic()
                if call_session:
                    try:
                        await call_session.send_realtime_input(
                            media=types.Blob(data=raw_pcm, mime_type="audio/pcm;rate=16000")
                        )
                    except Exception as e:
                        logger.warning(f"[Live WS] Binary audio forward error: {e}")
                continue

            if "text" not in data:
                continue

            msg = json.loads(data["text"])
            msg_type = msg.get("type", "text")

            # ==== CALL MODE: start persistent session ====
            if msg_type == "call_start":
                if call_session:
                    logger.info("[Live WS] Call already active, ignoring")
                    continue
                try:
                    call_ctx = live_client.aio.live.connect(model=LIVE_MODEL, config=_make_live_config(resolved_user_id))
                    call_session = await call_ctx.__aenter__()
                    logger.info(f"[Live WS] Call started for user={resolved_user_id}")
                    # Start proactive vision background task
                    _vision_state["last_user_activity"] = _time.monotonic()
                    _vision_state["last_proactive_at"] = 0.0
                    task = asyncio.create_task(_proactive_vision_loop())
                    _vision_state["proactive_task"] = task
                    # Start background receive loop
                    _receive_task = asyncio.create_task(_receive_loop())
                    await websocket.send_text(json.dumps({"type": "status", "content": "call_started"}))
                except Exception as e:
                    logger.error(f"[Live WS] Call start error: {e}")
                    await websocket.send_text(json.dumps({"type": "status", "content": f"error: {e}"}))
                    call_session = None
                    call_ctx = None
                continue

            # ==== CALL MODE: end persistent session ====
            if msg_type == "call_end":
                # Cancel receive loop
                if _receive_task:
                    _receive_task.cancel()
                    _receive_task = None
                # Cancel proactive vision task
                if _vision_state["proactive_task"]:
                    _vision_state["proactive_task"].cancel()
                    _vision_state["proactive_task"] = None
                _vision_state["camera_active"] = False
                if call_ctx:
                    try:
                        await call_ctx.__aexit__(None, None, None)
                    except Exception:
                        pass
                call_session = None
                call_ctx = None
                logger.info(f"[Live WS] Call ended for user={resolved_user_id}")
                await websocket.send_text(json.dumps({"type": "status", "content": "call_ended"}))

                # Post-call memory summarisation — fire-and-forget in background
                if len(_session_transcript) >= 2:
                    transcript_snapshot = list(_session_transcript)
                    turn_count = len(transcript_snapshot)
                    _session_transcript.clear()

                    async def _summarise_and_store():
                        try:
                            from tools.session_memory import summarise_call, store_summary
                            summary = await asyncio.to_thread(
                                summarise_call, resolved_user_id, transcript_snapshot
                            )
                            if summary:
                                await asyncio.to_thread(
                                    store_summary, resolved_user_id, summary, turn_count
                                )
                                logger.info(
                                    f"[SessionMemory] Post-call summary stored "
                                    f"({turn_count} turns) for user={resolved_user_id}"
                                )
                            # Trigger memory compaction if threshold met (low threshold on first run)
                            try:
                                from tools.memory_compaction import should_compact, compact_memories
                                if should_compact(resolved_user_id):
                                    await asyncio.to_thread(compact_memories, resolved_user_id)
                                    logger.info(f"[MemoryCompaction] Post-call compaction for user={resolved_user_id}")
                            except Exception as e:
                                logger.debug(f"[MemoryCompaction] Post-call compaction skipped: {e}")
                        except Exception as e:
                            logger.warning(f"[SessionMemory] Post-call summarisation failed: {e}")

                    asyncio.create_task(_summarise_and_store())

                continue

            # ==== AUDIO MESSAGE ====
            if msg_type == "audio":
                _vision_state["last_user_activity"] = _time.monotonic()
                audio_b64 = msg.get("content", "")
                mime = msg.get("mime_type", "audio/mp4")
                audio_bytes = base64.b64decode(audio_b64)
                logger.info(f"[Live WS] Got audio: {len(audio_bytes)} bytes, mime={mime}")

                # ---- Call mode: stream raw audio to Gemini via realtime_input ----
                if call_session:
                    try:
                        await call_session.send_realtime_input(
                            media=types.Blob(data=audio_bytes, mime_type=mime)
                        )
                        # Receive loop handles the response — no need to read here
                    except Exception as e:
                        logger.error(f"[Live WS] Call audio stream error: {e}")
                    continue

                # ---- Single-shot mode: transcribe then respond ----
                await websocket.send_text(json.dumps({"type": "status", "content": "processing"}))

                # Transcribe
                try:
                    transcript = await transcribe_audio(audio_bytes, mime)
                    logger.info(f"[Live WS] Transcribed: {transcript}")
                    if not transcript:
                        await websocket.send_text(json.dumps({"type": "status", "content": "error: empty transcript"}))
                        continue
                    await websocket.send_text(json.dumps({"type": "transcript", "content": transcript}))
                    _add_to_transcript("user", transcript)
                except Exception as e:
                    logger.error(f"[Live WS] Transcription error: {type(e).__name__}: {e}")
                    await websocket.send_text(json.dumps({"type": "status", "content": f"error: transcription failed - {type(e).__name__}: {e}"}))
                    continue

                try:
                    async with live_client.aio.live.connect(model=LIVE_MODEL, config=_make_live_config(resolved_user_id)) as gs:
                        await gs.send_client_content(
                            turns={"role": "user", "parts": [{"text": transcript}]},
                            turn_complete=True,
                        )
                        await stream_gemini_response(gs, websocket)
                    await websocket.send_text(json.dumps({"type": "status", "content": "done"}))
                except Exception as e:
                    logger.error(f"[Live WS] Single-shot error: {e}")
                    await websocket.send_text(json.dumps({"type": "status", "content": f"error: {e}"}))

            # ==== AUDIO CHUNK (streaming PCM via JSON) ====
            elif msg_type == "audio_chunk":
                _vision_state["last_user_activity"] = _time.monotonic()
                audio_b64 = msg.get("content", "")
                if audio_b64 and call_session:
                    try:
                        audio_bytes = base64.b64decode(audio_b64)
                        # Client sends WAV files (header + PCM) -- strip the
                        # header so Gemini receives clean raw PCM samples.
                        pcm_bytes = strip_wav_header(audio_bytes)
                        logger.info(f"[Live WS] Audio chunk: {len(audio_bytes)}B raw -> {len(pcm_bytes)}B PCM (stripped {len(audio_bytes)-len(pcm_bytes)}B header)")
                        await call_session.send_realtime_input(
                            media=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
                        )
                    except Exception as e:
                        logger.warning(f"[Live WS] Audio chunk forward error: {e}")
                elif audio_b64 and not call_session:
                    logger.warning("[Live WS] Audio chunk received but no call_session active")

            # ==== TEXT MESSAGE ====
            elif msg_type == "text":
                _vision_state["last_user_activity"] = _time.monotonic()
                content = msg.get("content", "")
                logger.info(f"[Live WS] Got text: {content[:80]}")

                if call_session:
                    # In call mode, send as client content — receive loop handles the response
                    try:
                        await call_session.send_client_content(
                            turns={"role": "user", "parts": [{"text": content}]},
                            turn_complete=True,
                        )
                        _add_to_transcript("user", content)
                    except Exception as e:
                        logger.error(f"[Live WS] Call text error: {e}")
                        try:
                            await call_ctx.__aexit__(None, None, None)
                        except Exception:
                            pass
                        call_session = None
                        call_ctx = None
                else:
                    try:
                        async with live_client.aio.live.connect(model=LIVE_MODEL, config=_make_live_config(resolved_user_id)) as gs:
                            await gs.send_client_content(
                                turns={"role": "user", "parts": [{"text": content}]},
                                turn_complete=True,
                            )
                            await stream_gemini_response(gs, websocket)
                        await websocket.send_text(json.dumps({"type": "status", "content": "done"}))
                    except Exception as e:
                        logger.error(f"[Live WS] Text error: {e}")

            # ==== VIDEO FRAME (camera → Gemini Live) ====
            elif msg_type == "video_frame":
                # Client sends base64-encoded JPEG frames from the phone camera.
                # We forward them into the active Gemini Live session as realtime input
                # so Elora can "see" what the user is looking at in real time.
                # Frames are fire-and-forget (no turn_complete) — Gemini processes them
                # as ambient context while the conversation continues.
                frame_b64 = msg.get("content", "")
                mime = msg.get("mime_type", "image/jpeg")
                if frame_b64:
                    try:
                        frame_bytes = base64.b64decode(frame_b64)
                        # Always store the latest frame so describe_person_from_camera can use it
                        from tools.camera_memory import store_frame
                        store_frame(resolved_user_id, frame_bytes)
                        # Forward to Gemini Live session if active
                        if call_session:
                            await call_session.send_realtime_input(
                                media=types.Blob(data=frame_bytes, mime_type=mime)
                            )
                            logger.debug(f"[Live WS] Video frame sent: {len(frame_bytes)} bytes")
                    except Exception as e:
                        logger.warning(f"[Live WS] Video frame error: {e}")

            # ==== CAMERA STATE (frontend tells us camera is on/off) ====
            elif msg_type == "camera_active":
                active = msg.get("active", False)
                _vision_state["camera_active"] = active
                logger.info(f"[Live WS] Camera {'activated' if active else 'deactivated'} for user={resolved_user_id}")

    except WebSocketDisconnect:
        logger.info(f"[Live WS] Disconnected: user={resolved_user_id}")
    except Exception as e:
        logger.error(f"[Live WS] Error: {e}")
    finally:
        # Cancel receive loop
        if _receive_task:
            _receive_task.cancel()
        # Cancel proactive vision task
        if _vision_state.get("proactive_task"):
            _vision_state["proactive_task"].cancel()
        # Clean up call session
        if call_ctx:
            try:
                await call_ctx.__aexit__(None, None, None)
            except Exception:
                pass
        current_user_id.reset(ctx_token)
        logger.info(f"[Live WS] Session ended: user={resolved_user_id}")


# ---------------------------------------------------------------------------
# REST endpoint -- simple text chat fallback
# ---------------------------------------------------------------------------

@app.post("/chat")
async def chat(request: dict):
    user_id = request.get("user_id", "anonymous")
    message = request.get("message", "")

    session = await text_runner.session_service.create_session(
        app_name="elora-text",
        user_id=user_id,
    )

    response = await run_text_agent(user_id, session.id, message)
    return {"response": response}


# ---------------------------------------------------------------------------
# Voice endpoint -- accepts audio, transcribes with Gemini, responds
# ---------------------------------------------------------------------------

@app.post("/voice")
async def voice_chat(request: dict):
    """Accept base64 audio, transcribe with Gemini, then run agent on transcript."""
    user_id = request.get("user_id", "anonymous")
    audio_base64 = request.get("audio", "")
    mime_type = request.get("mime_type", "audio/wav")

    if not audio_base64:
        return {"error": "No audio provided"}

    try:
        import base64 as b64

        # First, use Gemini to transcribe the audio
        from google.genai import Client
        client = Client()

        audio_bytes = b64.b64decode(audio_base64)
        transcribe_response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                        types.Part.from_text(text="Transcribe this audio exactly. Return only the transcription, nothing else."),
                    ],
                )
            ],
        )

        transcript = transcribe_response.text.strip()
        logger.info(f"[Voice] Transcribed: {transcript}")

        if not transcript:
            return {"transcript": "", "response": "I couldn't hear anything. Could you try again?"}

        # Now run the agent with the transcribed text
        session = await text_runner.session_service.create_session(
            app_name="elora-text",
            user_id=user_id,
        )

        response = await run_text_agent(user_id, session.id, transcript)
        return {"transcript": transcript, "response": response}

    except Exception as e:
        logger.error(f"[Voice] Error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# WebSocket -- wake word detector ("Hey Elora")
#
# The phone streams raw PCM audio continuously (even in background).
# We feed it into a persistent Gemini Live session configured to ONLY
# respond when it hears "Hey Elora".  When triggered it sends back:
#   {"type": "wake"}
# The app then activates the mic for a full conversation turn.
# ---------------------------------------------------------------------------

WAKE_CONFIG = types.LiveConnectConfig(
    response_modalities=["TEXT"],   # text only — faster, no audio to play
    system_instruction=types.Content(parts=[types.Part.from_text(text=
        "You are a wake-word detector. Your ONLY job is to detect when someone says "
        "'Hey Elora' or 'Elora' in the audio stream. "
        "When you hear it, respond with exactly the word: WAKE "
        "Do not respond to anything else. Do not greet. Do not converse. "
        "If you do not hear the wake word, respond with exactly: SLEEP"
    )]),
)

@app.websocket("/ws/wake/{user_id}")
async def websocket_wake(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(default=""),
):
    """
    Always-on wake-word detector.
    Client streams PCM chunks; server replies {"type":"wake"} when triggered.
    """
    await websocket.accept()
    verified_uid = verify_firebase_token(token)
    resolved_user_id = verified_uid if verified_uid else user_id
    logger.info(f"[Wake] Connected: user={resolved_user_id}")

    try:
        async with live_client.aio.live.connect(
            model=WAKE_MODEL, config=WAKE_CONFIG
        ) as session:
            async def _listen():
                """Read responses from Gemini and emit wake events."""
                async for msg in session.receive():
                    if msg.text and "WAKE" in msg.text.upper():
                        logger.info(f"[Wake] Triggered for user={resolved_user_id}")
                        try:
                            await websocket.send_text(json.dumps({"type": "wake"}))
                        except Exception:
                            return

            listen_task = asyncio.create_task(_listen())

            try:
                while True:
                    data = await websocket.receive()
                    if "bytes" in data:
                        # Raw PCM chunk from phone mic (binary frame)
                        pcm = data["bytes"]
                        await session.send_realtime_input(
                            media=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000")
                        )
                    elif "text" in data:
                        msg = json.loads(data["text"])
                        if msg.get("type") == "ping":
                            await websocket.send_text(json.dumps({"type": "pong"}))
                        elif msg.get("type") == "audio_chunk":
                            # Base64-encoded audio from React Native (can't send binary easily)
                            chunk_b64 = msg.get("content", "")
                            mime = msg.get("mime_type", "audio/wav")
                            if chunk_b64:
                                try:
                                    audio_bytes = base64.b64decode(chunk_b64)
                                    await session.send_realtime_input(
                                        media=types.Blob(data=audio_bytes, mime_type=mime)
                                    )
                                except Exception as e:
                                    logger.warning(f"[Wake] audio_chunk decode error: {e}")
            finally:
                listen_task.cancel()

    except WebSocketDisconnect:
        logger.info(f"[Wake] Disconnected: user={resolved_user_id}")
    except Exception as e:
        logger.error(f"[Wake] Error: {e}")


# ---------------------------------------------------------------------------
# User profile -- name capture + personalisation
# ---------------------------------------------------------------------------

@app.post("/user/profile")
async def save_user_profile(request: dict):
    """
    Save the user's name and basic profile so Elora can use it in conversation.

    Body: {"user_id": "...", "name": "Alex", "token": "firebase_id_token"}
    """
    firebase_token = request.get("token", "")
    user_id = request.get("user_id", "anonymous")
    name = request.get("name", "").strip()

    verified_uid = verify_firebase_token(firebase_token)
    resolved_user_id = verified_uid if verified_uid else user_id

    if not name:
        return {"status": "error", "error": "name is required"}

    try:
        from google.cloud import firestore as fs
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
        if project:
            db = fs.Client(project=project)
            db.collection("user_profiles").document(resolved_user_id).set({
                "name": name,
                "updated_at": __import__("datetime").datetime.utcnow().isoformat(),
            }, merge=True)

            # Also store as a memory so Elora surfaces it naturally
            from tools.memory import remember as _remember
            from elora_agent.agent import current_user_id as _cuid
            token = _cuid.set(resolved_user_id)
            try:
                _remember(f"The user's name is {name}.")
            finally:
                _cuid.reset(token)

        logger.info(f"[Profile] Saved name='{name}' for user={resolved_user_id}")
        return {"status": "ok", "name": name}
    except Exception as e:
        logger.error(f"[Profile] Error saving: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/user/profile")
async def get_user_profile(user_id: str, token: str = ""):
    """Get the user's saved profile."""
    verified_uid = verify_firebase_token(token)
    resolved_user_id = verified_uid if verified_uid else user_id

    try:
        from google.cloud import firestore as fs
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
        if project:
            db = fs.Client(project=project)
            doc = db.collection("user_profiles").document(resolved_user_id).get()
            if doc.exists:
                return {"status": "ok", "profile": doc.to_dict()}
        return {"status": "ok", "profile": {}}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Face reference -- store + retrieve + compare face crops for photo search
# ---------------------------------------------------------------------------

@app.post("/face/reference")
async def store_face_reference(request: dict):
    """
    Store a cropped face JPEG as the reference for a person.
    Called by the app when the user says 'this is Maya' and a face is detected.

    Body: {
        user_id: str,
        person_name: str,
        face_image_base64: str,   # 256x256 JPEG
        token: str,               # Firebase ID token (optional)
    }
    """
    firebase_token = request.get("token", "")
    user_id = request.get("user_id", "anonymous")
    person_name = request.get("person_name", "").strip()
    face_b64 = request.get("face_image_base64", "")

    verified_uid = verify_firebase_token(firebase_token)
    resolved_user_id = verified_uid if verified_uid else user_id

    if not person_name or not face_b64:
        return {"status": "error", "error": "person_name and face_image_base64 are required"}

    try:
        import base64 as _b64
        face_bytes = _b64.b64decode(face_b64)

        # Store in GCS: users/{uid}/faces/{person_name_slug}.jpg
        bucket_name = os.getenv("GCS_BUCKET_NAME", "")
        if bucket_name:
            from google.cloud import storage as gcs
            client = gcs.Client()
            bucket = client.bucket(bucket_name)
            slug = person_name.lower().replace(" ", "_")
            blob_path = f"users/{resolved_user_id}/faces/{slug}.jpg"
            blob = bucket.blob(blob_path)
            blob.upload_from_string(face_bytes, content_type="image/jpeg")
            reference_url = f"gs://{bucket_name}/{blob_path}"
        else:
            reference_url = ""

        # Also store the person_id link in Firestore people record
        from tools.people import _find_by_name
        existing = _find_by_name(resolved_user_id, person_name)
        person_id = existing.get("id", "") if existing else ""

        logger.info(f"[Face] Stored reference for '{person_name}' (user={resolved_user_id})")
        return {
            "status": "ok",
            "person_name": person_name,
            "person_id": person_id,
            "reference_url": reference_url,
        }
    except Exception as e:
        logger.error(f"[Face] store_face_reference error: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/face/reference")
async def get_face_reference(
    user_id: str,
    person_name: str,
    token: str = "",
):
    """
    Retrieve the stored face reference crop for a person.
    Returns {"face_image_base64": str} or {"face_image_base64": null} if not found.
    """
    verified_uid = verify_firebase_token(token)
    resolved_user_id = verified_uid if verified_uid else user_id

    try:
        import base64 as _b64
        bucket_name = os.getenv("GCS_BUCKET_NAME", "")
        if not bucket_name:
            return {"face_image_base64": None}

        from google.cloud import storage as gcs
        client = gcs.Client()
        bucket = client.bucket(bucket_name)
        slug = person_name.lower().replace(" ", "_")
        blob_path = f"users/{resolved_user_id}/faces/{slug}.jpg"
        blob = bucket.blob(blob_path)

        if not blob.exists():
            return {"face_image_base64": None}

        face_bytes = blob.download_as_bytes()
        return {"face_image_base64": _b64.b64encode(face_bytes).decode()}
    except Exception as e:
        logger.error(f"[Face] get_face_reference error: {e}")
        return {"face_image_base64": None}


@app.post("/face/compare")
async def compare_face(request: dict):
    """
    Compare a face crop against the stored reference for a person using Gemini Vision.
    Returns {"match": bool, "confidence": "high"|"medium"|"low"}.

    Body: {
        user_id: str,
        person_name: str,
        face_image_base64: str,    # the candidate face crop to compare
        reference_base64: str,     # optional, if client already has it
        token: str,
    }
    """
    firebase_token = request.get("token", "")
    user_id = request.get("user_id", "anonymous")
    person_name = request.get("person_name", "").strip()
    candidate_b64 = request.get("face_image_base64", "")
    reference_b64 = request.get("reference_base64", "") or ""

    verified_uid = verify_firebase_token(firebase_token)
    resolved_user_id = verified_uid if verified_uid else user_id

    if not candidate_b64:
        return {"match": False, "confidence": "low", "error": "No face image provided"}

    try:
        import base64 as _b64

        # Fetch reference from GCS if not provided
        if not reference_b64:
            bucket_name = os.getenv("GCS_BUCKET_NAME", "")
            if bucket_name:
                from google.cloud import storage as gcs
                client = gcs.Client()
                slug = person_name.lower().replace(" ", "_")
                blob = client.bucket(bucket_name).blob(
                    f"users/{resolved_user_id}/faces/{slug}.jpg"
                )
                if blob.exists():
                    reference_b64 = _b64.b64encode(blob.download_as_bytes()).decode()

        if not reference_b64:
            # No reference stored — fall back to Gemini description comparison
            # Get person's appearance description from people memory
            from tools.people import recall_person
            person = recall_person(person_name, user_id=resolved_user_id)
            appearance = person.get("person", {}).get("appearance", "") if person.get("status") == "found" else ""

            if not appearance:
                return {"match": False, "confidence": "low",
                        "note": "No face reference or appearance description stored for this person."}

            # Use Gemini Vision to compare candidate face against text description
            candidate_bytes = _b64.b64decode(candidate_b64)
            result = await _compare_face_to_description(candidate_bytes, person_name, appearance)
            return result

        # Compare two face images with Gemini Vision
        candidate_bytes = _b64.b64decode(candidate_b64)
        reference_bytes = _b64.b64decode(reference_b64)
        result = await _compare_two_faces(candidate_bytes, reference_bytes, person_name)
        return result

    except Exception as e:
        logger.error(f"[Face] compare_face error: {e}")
        return {"match": False, "confidence": "low", "error": str(e)}


async def _compare_two_faces(candidate: bytes, reference: bytes, person_name: str) -> dict:
    """Use Gemini Vision to compare two face crops."""
    try:
        prompt = (
            f"You are comparing two face images to determine if they show the same person.\n"
            f"Image 1 is a reference photo of {person_name}.\n"
            f"Image 2 is a candidate photo.\n\n"
            f"Answer ONLY with one of:\n"
            f"SAME_HIGH - definitely the same person\n"
            f"SAME_MEDIUM - probably the same person\n"
            f"DIFFERENT - different people or unclear\n\n"
            f"Consider: facial structure, eyes, nose shape, chin. Ignore lighting, angle, expression."
        )
        response = await asyncio.to_thread(
            _gemini_compare_faces, candidate, reference, prompt
        )
        text = (response or "").strip().upper()
        if "SAME_HIGH" in text:
            return {"match": True, "confidence": "high"}
        elif "SAME_MEDIUM" in text:
            return {"match": True, "confidence": "medium"}
        else:
            return {"match": False, "confidence": "low"}
    except Exception as e:
        return {"match": False, "confidence": "low", "error": str(e)}


async def _compare_face_to_description(candidate: bytes, person_name: str, appearance: str) -> dict:
    """Compare a face image against a text appearance description."""
    try:
        prompt = (
            f"You are checking if the person in this photo matches this description of {person_name}:\n"
            f'"{appearance}"\n\n'
            f"Answer ONLY with one of:\n"
            f"MATCH_HIGH - the person clearly matches the description\n"
            f"MATCH_MEDIUM - the person probably matches\n"
            f"NO_MATCH - does not match or unclear\n\n"
            f"Focus on physical characteristics, not clothing."
        )
        response = await asyncio.to_thread(
            _gemini_compare_face_description, candidate, prompt
        )
        text = (response or "").strip().upper()
        if "MATCH_HIGH" in text:
            return {"match": True, "confidence": "high"}
        elif "MATCH_MEDIUM" in text:
            return {"match": True, "confidence": "medium"}
        else:
            return {"match": False, "confidence": "low"}
    except Exception as e:
        return {"match": False, "confidence": "low", "error": str(e)}


def _gemini_compare_faces(candidate: bytes, reference: bytes, prompt: str) -> str:
    """Sync Gemini Vision call comparing two face images."""
    from google import genai as _genai
    from google.genai import types as _types
    client = _genai.Client(
        api_key=GOOGLE_API_KEY,
        http_options={"api_version": "v1beta"},
    )
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[_types.Content(role="user", parts=[
            _types.Part.from_bytes(data=reference, mime_type="image/jpeg"),
            _types.Part.from_bytes(data=candidate, mime_type="image/jpeg"),
            _types.Part.from_text(text=prompt),
        ])],
    )
    return resp.text or ""


def _gemini_compare_face_description(candidate: bytes, prompt: str) -> str:
    """Sync Gemini Vision call comparing face image to text description."""
    from google import genai as _genai
    from google.genai import types as _types
    client = _genai.Client(
        api_key=GOOGLE_API_KEY,
        http_options={"api_version": "v1beta"},
    )
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[_types.Content(role="user", parts=[
            _types.Part.from_bytes(data=candidate, mime_type="image/jpeg"),
            _types.Part.from_text(text=prompt),
        ])],
    )
    return resp.text or ""


# ---------------------------------------------------------------------------
# Push notification -- device token registration
# ---------------------------------------------------------------------------

@app.post("/push/register")
async def push_register(request: dict):
    """
    Register an Expo push token for a user.
    Called by the app on startup so Elora can send proactive notifications.

    Body: {"user_id": "...", "expo_token": "ExponentPushToken[...]", "token": "firebase_id_token"}
    """
    firebase_token = request.get("token", "")
    user_id = request.get("user_id", "anonymous")
    expo_token = request.get("expo_token", "")

    # Verify Firebase token if provided
    verified_uid = verify_firebase_token(firebase_token)
    resolved_user_id = verified_uid if verified_uid else user_id

    if not expo_token:
        return {"status": "error", "report": "Missing expo_token"}

    from tools.push import store_push_token
    store_push_token(resolved_user_id, expo_token)
    logger.info(f"[Push] Registered token for user={resolved_user_id}")
    return {"status": "ok", "user_id": resolved_user_id}


# ---------------------------------------------------------------------------
# Gmail Pub/Sub webhook -- proactive email triage
#
# Setup (one-time):
#   1. Create a Pub/Sub topic: gcloud pubsub topics create elora-gmail
#   2. Create a push subscription pointing to: POST /gmail/webhook
#   3. Grant gmail-api-push@system.gserviceaccount.com publish access to the topic
#   4. For each user: call gmail.users().watch(userId='me', body={
#        'labelIds': ['INBOX'], 'topicName': 'projects/elor-487806/topics/elora-gmail'
#      }).execute()
#
# When a new email arrives, Gmail pushes a Pub/Sub message here.
# We notify Elora to triage it and push a summary to the user's phone.
# ---------------------------------------------------------------------------

@app.post("/gmail/webhook")
async def gmail_webhook(request: dict):
    """
    Receive Gmail Pub/Sub push notifications.
    Payload: {"message": {"data": "<base64>", "messageId": "..."}, "subscription": "..."}
    """
    import base64 as b64
    try:
        msg_data = request.get("message", {}).get("data", "")
        if not msg_data:
            return {"status": "ok"}  # ack empty messages

        decoded = b64.b64decode(msg_data).decode("utf-8")
        import json as _json
        payload = _json.loads(decoded)
        email_address = payload.get("emailAddress", "")
        history_id = payload.get("historyId", "")

        logger.info(f"[Gmail Webhook] New mail for {email_address}, historyId={history_id}")

        # Find user by email address (stored in Firestore oauth_tokens)
        user_id = await _find_user_by_email(email_address)
        if not user_id:
            logger.warning(f"[Gmail Webhook] No user found for {email_address}")
            return {"status": "ok"}

        # Fire background task: read newest email and push summary to phone
        asyncio.create_task(_triage_new_email(user_id, email_address))
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"[Gmail Webhook] Error: {e}")
        return {"status": "ok"}  # always ack to prevent retry loops


async def _find_user_by_email(email: str) -> str | None:
    """Look up user_id by their Gmail address in Firestore oauth_tokens."""
    try:
        from google.cloud import firestore as fs
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
        if not project:
            return None
        db = fs.Client(project=project)
        # Check all oauth_token docs for a matching email
        docs = db.collection("oauth_tokens").stream()
        for doc in docs:
            data = doc.to_dict() or {}
            # The email is stored after first triage or we can decode the id_token
            if data.get("email") == email:
                return doc.id
        return None
    except Exception as e:
        logger.error(f"[Gmail Webhook] _find_user_by_email error: {e}")
        return None


async def _triage_new_email(user_id: str, email_address: str):
    """Read the newest unread email and send a push notification summary."""
    try:
        from tools.gmail import read_emails_sync
        from tools.push import send_push_notification, get_push_token

        # Check if user has a push token
        if not get_push_token(user_id):
            return

        result = read_emails_sync(user_id, query="is:unread", max_results=1)
        emails = result.get("emails", [])
        if not emails:
            return

        email = emails[0]
        sender = email.get("from", "Someone")
        subject = email.get("subject", "No subject")
        snippet = email.get("snippet", "")[:80]

        # Truncate sender to just name if possible
        if "<" in sender:
            sender = sender.split("<")[0].strip().strip('"')

        message = f"New email from {sender}: {subject}"
        if snippet:
            message += f" — {snippet}"

        await send_push_notification(
            user_id=user_id,
            title="New Email",
            message=message,
            data={"type": "new_email", "email_id": email.get("id", "")},
        )
        logger.info(f"[Gmail Webhook] Pushed email summary to user={user_id}")
    except Exception as e:
        logger.error(f"[Gmail Webhook] Triage error: {e}")


# ---------------------------------------------------------------------------
# App startup -- launch background tasks
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Start background tasks when the server starts."""
    from tools.push import send_push_notification
    from tools.reminders import reminder_poller
    from tools.briefing import briefing_poller
    from tools.proactive import proactive_engine_poller
    from tools.memory_compaction import compaction_poller

    async def _push_sender(user_id: str, message: str = "", title: str = "Elora", data: dict | None = None) -> bool:
        return await send_push_notification(
            user_id=user_id,
            title=title,
            message=message,
            data=data or {},
        )

    async def _reminder_push(user_id: str, message: str):
        await _push_sender(user_id=user_id, message=message, title="Elora Reminder", data={"type": "reminder"})

    asyncio.create_task(reminder_poller(_reminder_push))
    asyncio.create_task(briefing_poller(_push_sender))
    asyncio.create_task(proactive_engine_poller(_push_sender))
    asyncio.create_task(compaction_poller())
    logger.info("[Startup] Reminder poller + briefing poller + proactive engine + compaction poller started")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

