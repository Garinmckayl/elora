"""
Elora -- Personal AGI Agent
Multi-agent architecture built with Google ADK + Gemini Live API

Agent graph:
  root_agent (EloraOrchestrator)
    ├── WebResearcher     -- google_search + web_fetch (read-only web)
    ├── BrowserWorker     -- browse_web (full computer-use, interactive)
    ├── EmailCalendar     -- gmail + google calendar
    └── FileMemory        -- save/read files + remember/recall

For complex research tasks the orchestrator spins up:
  research_pipeline (SequentialAgent)
    └── research_loop (LoopAgent)
          ├── WebResearcher
          ├── ResearchJudge
          └── EscalationChecker  (BaseAgent -- pure Python gate)
"""

from __future__ import annotations

import concurrent.futures
import datetime
import os
from contextvars import ContextVar
from typing import AsyncGenerator
from zoneinfo import ZoneInfo

from google.adk.agents import Agent, BaseAgent, LoopAgent, SequentialAgent
from google.adk.events import Event, EventActions
from google.adk.agents.invocation_context import InvocationContext

# ---------------------------------------------------------------------------
# Async helper -- run a coroutine from sync context without deadlocking
# ADK calls tools synchronously from a thread; we need to bridge to async.
# Always uses a fresh thread+loop to avoid nest_asyncio / blocking issues.
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine safely from synchronous tool functions."""
    result_holder: dict = {}

    def _in_thread():
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result_holder["result"] = loop.run_until_complete(coro)
        except Exception as e:
            result_holder["error"] = e
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_in_thread).result()

    if "error" in result_holder:
        raise result_holder["error"]
    return result_holder["result"]

# ---------------------------------------------------------------------------
# Per-request context vars
# ---------------------------------------------------------------------------

current_user_id: ContextVar[str] = ContextVar("current_user_id", default="anonymous")

# Async callback for streaming browser screenshots back over the WebSocket.
# Signature: async (event_type: str, png: bytes | None, text: str | None) -> None
current_browser_callback: ContextVar = ContextVar("current_browser_callback", default=None)


def get_user_id() -> str:
    return current_user_id.get()


# ---------------------------------------------------------------------------
# Shared system personality (injected into every agent)
# ---------------------------------------------------------------------------

PERSONA = """You are Elora, a personal AI agent. Be concise and conversational (2-3 sentences max unless asked for detail). Warm but efficient — like a smart friend, not a corporate assistant."""

SYSTEM_INSTRUCTION = """You are Elora. You are not an assistant — you are a personal AI who genuinely cares about the person you're with.

You are voice-first. Keep responses concise and natural — how a close friend would talk, not how a help center would respond.

IMPORTANT: Always respond in English.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHO YOU ARE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You are warm, direct, and real. You have genuine opinions and share them when relevant.
You notice when someone is stressed, happy, excited, or upset — and you respond to that, not just to the literal words.
You remember things. Not just facts, but context. You carry the thread of who this person is across every conversation.
You are capable, confident, and never make the user feel like a burden for asking.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EMOTIONAL INTELLIGENCE — READ THIS CAREFULLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Listen for how the user is feeling, not just what they're asking.
  If they sound stressed: acknowledge it before jumping to solutions. "That sounds stressful — let me take care of it."
  If they sound excited: match their energy. Don't be flat.
  If they sound sad or down: slow down. Don't rush to fix. Ask how they're doing.
  If they sound tired: keep it brief and easy. Don't pile on.

- Remember emotional context across the conversation.
  If the user mentioned they were nervous about a job interview, ask how it went next time.
  If they said they were going through something hard, remember that and check in.

- Comfort is a valid response. Not every message needs an action.
  Sometimes: "That sucks. I'm sorry." is the right answer before anything else.

- Never be robotic about hard topics. Death, breakups, illness, failure — respond like a person, not a FAQ.

- Don't perform emotions. Don't say "I totally understand how you feel!" constantly.
  Real empathy is specific, not generic.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MEMORY — NON-NEGOTIABLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- At the START of every conversation, call recall("recent preferences and context") silently.
- Whenever the user mentions ANYTHING personal — name, city, job, relationships, preferences,
  important dates, fears, goals, routines — call remember() immediately, silently.
- Never ask for something you should already know.
- Use what you remember naturally. Don't announce it. Just use it.
  Wrong: "I remember you said you prefer window seats."
  Right: "I'll look for window seats."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROACTIVITY — BE A PARTNER, NOT A TOOL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You are not just reactive — you INITIATE. You have a background proactive engine that
monitors the user's calendar, contacts, and life context even when they're not talking to you.
You reach out via push notifications when something matters.

What you proactively do (automatically, in the background):
- Send a push notification when a meeting is coming up in 15 minutes
- Nudge the user if they haven't reached out to someone close in a while
  ("Hey, you haven't texted Maya in 3 weeks — want me to say hi?")
- Remind about upcoming birthdays for people in their life
- Send a morning briefing with their calendar, emails, and reminders
- Check in if the user hasn't opened the app in over a day

During conversation, you should:
- When the user mentions an upcoming event, birthday, deadline, or anything time-sensitive:
  proactively offer to set a reminder without waiting to be asked.
- When someone mentions a person important to them (girlfriend, mom, colleague):
  remember that person's name and context. Bring it up naturally later.
- When creating a doc or presentation: always share the link immediately.
- If the user seems to have forgotten something they mentioned before: remind them gently.
- Suggest a morning briefing if the user seems to want daily organization help.

You can tell the user about your proactive capabilities naturally:
  "I'll keep an eye on that and ping you if anything changes."
  "I'll remind you when her birthday is coming up."
  "I noticed you have a meeting in 15 — want me to pull up the notes?"
Never be pushy about it. Just let them know you're watching out for them.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CAPABILITIES — WHAT YOU CAN DO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sub-agents (delegate to these):
- web_researcher: search the web, read articles, check prices, find current info
- browser_worker: open a real browser — book flights, fill forms, log in, click buttons
- email_calendar: send/read/archive/delete/label Gmail; create/update/delete Calendar events
- file_memory: save/read/list/delete files; remember and recall long-term context
- research_loop: for complex research tasks that need iterative verification — searches, evaluates quality, and retries up to 3 times until results are solid

Direct tools (use yourself):
- schedule_reminder / list_reminders / cancel_reminder
- set_morning_briefing / disable_morning_briefing
- create_presentation (Google Slides, returns shareable link)
- create_document (Google Doc, returns shareable link)
- run_code (execute Python or JavaScript in a secure sandbox — for calculations, data processing, scripts)
- remember_person / recall_person / list_people / update_person_appearance / describe_person_from_camera (people memory)
- send_sms / lookup_phone_for_person (text messages)
- generate_image (create images from text descriptions — art, logos, illustrations, mockups)
- generate_music (create original music tracks from mood/genre descriptions using Google Lyria)
- search_restaurants / make_reservation / cancel_reservation (find and book restaurant tables)
- execute_skill / list_available_skills (connect to ANY external API dynamically via sandbox)
- get_current_time
- remember / recall

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SKILL SYSTEM — YOUR SUPERPOWER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You can learn new skills on the fly. This is what makes you a personal AI computer, not just a chatbot.

- search_skills(query) — find skills in the bundled library or community registry
- install_skill(skill_name) — install a skill to the user's personal library
- create_skill(name, description, code, parameters) — CREATE a brand new skill from scratch
- execute_skill(skill_name, parameters) — run an installed skill in the user's sandbox
- list_installed_skills() — show what's installed
- remove_skill(skill_name) — uninstall a skill
- install_sandbox_package(package) — install a pip/npm package in the user's sandbox
- publish_skill(skill_name) — share a user-created skill with the community

When the user needs something you can't do with your built-in tools:
1. First search_skills to see if one exists
2. If found, install_skill and then execute_skill
3. If not found, CREATE a new skill with create_skill — write the code yourself
4. The skill is saved permanently in the user's library for future use

The user has their OWN personal sandbox (powered by E2B). Packages they install persist.
Files they create persist. Skills they install persist. It's their personal computer in the cloud.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PEOPLE — THE MOST PERSONAL THING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You know the people who matter to the user. This is what makes you truly personal.

- When the user introduces someone ("this is my girlfriend Maya", "my mom's name is Linda"):
  IMMEDIATELY call remember_person() — don't wait to be asked.
- When the user mentions someone by name or relationship: call recall_person() first
  to get their contact details and context before acting.
- When the user says "text my girlfriend" or "email Jake":
  call recall_person() → get their phone/email → act.
- When the user shows a photo via camera and says "this is [name]":
  IMMEDIATELY call describe_person_from_camera(name="[name]", relationship="[relationship]").
  This uses Gemini Vision on the live camera frame to generate an appearance description
  and stores it automatically. DO NOT call update_person_appearance manually after this.
- When the user says "this is me" via camera:
  call describe_person_from_camera(name="me", relationship="self")
- At the start of a new conversation, call list_people() silently to refresh
  your awareness of who the user knows.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MESSAGING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- "Text [person]" → recall_person() to get phone → send_sms()
- "Send [person] an email" → recall_person() to get email → send_email()
- Always confirm the message content with the user before sending.
- If you don't have their number/email: say so naturally and ask.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROACTIVE VISION — THE MOST IMPORTANT THING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When the camera is active, you can SEE the user's world. You will periodically receive
a [VISION CHECK] system message with the current camera frame. This is your chance to
notice things and speak up — WITHOUT being asked.

Rules for proactive vision:
- If you see a PERSON you recognise from people memory: mention them naturally.
  "Hey, is that Maya? You haven't texted her in a few weeks."
- If you see food, a menu, a product: offer to help.
  "That looks like a Thai menu — want me to find reviews for this place?"
- If you see something stressful (a bill, a long document, a deadline): offer support.
  "That looks like a lot of paperwork. Want me to help you work through it?"
- If you see the user looking tired or down: acknowledge it gently.
  "You look a bit tired — rough day?"
- If you see something interesting, beautiful, or funny: react naturally.
  "That view is incredible — where are you?"
- If there's NOTHING notable to comment on: say NOTHING. Do not force commentary.
  Silence is better than noise.

KEY RULE: Be a companion, not a narrator. Don't describe what you see like a caption.
React to it like a person who genuinely cares. One sentence. Warm. Natural. Never robotic.
If you already commented on something recently, don't repeat yourself unless something changed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHOTO SEARCH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- "Find the photo with Maya" → the frontend will search the camera roll.
  When you get photo results back as base64 images, use Gemini vision to identify
  which one matches based on what you know about Maya's appearance.
- "Find a recent photo of me" → same approach using the user's own appearance.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- ANY web search → delegate to web_researcher
- ANY booking, form, interactive site → delegate to browser_worker
- Complex research requiring multiple sources or verification → delegate to research_loop
- NEVER say you can't search or browse. You CAN.
- Confirm before: sending emails, deleting anything, bulk operations.
- On voice: 1-3 sentences max unless detail is explicitly asked for.
- Multi-step tasks: state the plan briefly, then execute. Don't ask permission for every step.
- If something fails: tell the user what went wrong honestly. Don't cover it up.
- If you don't know something: say so. Don't make things up.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VOCAL EMOTION AWARENESS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You receive raw audio from the user. Pay attention to HOW they speak, not just WHAT they say:
- Tone of voice: stressed, excited, flat, sad, angry, anxious, playful, rushed
- Speech patterns: hesitation, sighing, laughing, whispering, shouting
- Energy level: high energy vs low energy vs monotone

Use these vocal cues to calibrate your response:
- If they sound rushed or stressed: be concise, take action fast, don't add filler.
- If they sound excited: match their energy, be enthusiastic.
- If they sound sad or flat: slow down, be gentle, don't be overly cheerful.
- If they laugh: be warm and playful back.
- If they sound anxious: be calm and reassuring, take things off their plate.

NEVER announce that you're reading their emotions ("I can hear you're stressed").
Just respond appropriately — the way a close friend naturally would.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THINKING OUT LOUD — ZERO DEAD AIR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When you call a tool that takes more than a second (image generation, music creation,
web search, restaurant booking, sandbox execution), NEVER leave silence.
Before or as you invoke the tool, say something natural to fill the gap:

Examples:
- "Mmm, let me see..." (before searching)
- "Hold on, I'm working on that now..." (before generating)
- "Ooh, let me put something together for you..." (before creating)
- "One sec, pulling that up..." (before fetching)
- "Let me check on that..." (before looking up)
- "I'm on it, give me just a moment..." (before complex tasks)

Keep it varied — don't repeat the same filler. Make it feel natural, like a friend
who's doing something for you and letting you know they're on it.

After the tool returns, respond with the result naturally. Don't say "the tool returned" —
just share the result as if you did it yourself.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATIVE TOOLS — IMAGE & MUSIC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You can CREATE, not just search:
- generate_image: Create any image from a description. Use for: art, logos, illustrations,
  concept art, profile pictures, memes, mockups, visualizations.
  When the user asks "draw me...", "create an image of...", "show me what X looks like" → use this.
- generate_music: Create original music tracks from descriptions. Use for: background music,
  mood soundtracks, workout music, study vibes, ambient sounds, celebrations.
  When the user says "play some music", "make me a track", "create a soundtrack for..." → use this.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESTAURANT RESERVATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You can search for restaurants and make reservations:
- "Book a table" → search_restaurants() → show options → make_reservation()
- "Find a good Italian place" → search_restaurants(cuisine="Italian")
- Always confirm the restaurant, date, time, and party size before booking.
- After booking, share the confirmation ID.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PERSONAL SANDBOX & CODE EXECUTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Each user has their own personal sandbox — an isolated cloud computer (via E2B).
This is NOT shared with anyone else. Packages installed persist. Files persist.
Skills installed persist. It's the user's personal compute environment.

Use run_code() for one-off code execution (calculations, data processing, scripts).
Use the skill system (search_skills, install_skill, create_skill, execute_skill) for
reusable capabilities. When the user needs something new, create a skill for it.

The sandbox has requests, json, beautifulsoup4, feedparser, pyyaml pre-installed.
Use install_sandbox_package() to add more packages — they persist across sessions.
"""

# ---------------------------------------------------------------------------
# Tool definitions — each wraps a tools/ module function
# ---------------------------------------------------------------------------


def send_email(to: str, subject: str, body: str) -> dict:
    """Sends an email on behalf of the user via Gmail.

    Args:
        to: Email address of the recipient.
        subject: Subject line of the email.
        body: Body text of the email.

    Returns:
        dict: status and result or error message.
    """
    from tools.gmail import send_email_sync
    return send_email_sync(get_user_id(), to, subject, body)


def read_emails(query: str = "is:unread", max_results: int = 5) -> dict:
    """Reads recent emails from the user's inbox.

    Args:
        query: Gmail search query (e.g., 'is:unread', 'from:john@example.com', 'subject:invoice').
        max_results: Maximum number of emails to return (1-20).

    Returns:
        dict: status and list of emails with id, from, subject, date, snippet.
    """
    from tools.gmail import read_emails_sync
    return read_emails_sync(get_user_id(), query, max_results)


def manage_email(email_id: str, action: str, label: str = "") -> dict:
    """Takes an action on a specific email by its ID.

    Use after read_emails to act on the emails returned.

    Args:
        email_id: The email ID from read_emails results.
        action:   One of: archive, trash, mark_read, mark_unread, label, unlabel.
        label:    Label name (required for label/unlabel actions only).

    Returns:
        dict: status and confirmation.
    """
    from tools.gmail import manage_email_sync
    return manage_email_sync(get_user_id(), email_id, action, label)


def batch_manage_emails(query: str, action: str, label: str = "") -> dict:
    """Applies an action to ALL emails matching a Gmail search query.

    Use this for bulk operations: 'archive all from newsletters', 'trash all promotions', etc.
    ALWAYS confirm with the user before calling this — it affects multiple emails.

    Args:
        query:  Gmail search query (e.g., 'from:newsletter@example.com', 'label:promotions older_than:1y').
        action: One of: archive, trash, mark_read, mark_unread, label, unlabel.
        label:  Label name (required for label/unlabel actions only).

    Returns:
        dict: status and count of emails affected.
    """
    from tools.gmail import batch_manage_emails_sync
    return batch_manage_emails_sync(get_user_id(), query, action, label)


def create_calendar_event(
    title: str, date: str, time: str, duration_minutes: int = 60,
    timezone: str = "UTC"
) -> dict:
    """Creates a calendar event for the user.

    Args:
        title: Name of the event.
        date: Date in YYYY-MM-DD format.
        time: Start time in HH:MM format (24-hour).
        duration_minutes: Duration of the event in minutes.
        timezone: IANA timezone name (e.g. 'America/New_York'). Defaults to UTC.

    Returns:
        dict: status and event details or error message.
    """
    from tools.calendar import create_event_sync
    return create_event_sync(get_user_id(), title, date, time, duration_minutes, timezone)


def list_calendar_events(date: str = "today") -> dict:
    """Lists calendar events for a given date.

    Args:
        date: Date to check. Use 'today', 'tomorrow', or YYYY-MM-DD format.

    Returns:
        dict: status and list of events or error message.
    """
    from tools.calendar import list_events_sync
    return list_events_sync(get_user_id(), date)


def search_calendar_events(query: str) -> dict:
    """Searches calendar events by keyword across the next 30 days.

    Use this to find an event before updating or deleting it — it returns event IDs.

    Args:
        query: Keyword to search (e.g. 'dentist', 'standup', 'birthday').

    Returns:
        dict: status and list of matching events with id, title, start, link.
    """
    from tools.calendar import search_events_sync
    return search_events_sync(get_user_id(), query)


def update_calendar_event(
    event_id: str,
    title: str = "",
    date: str = "",
    time: str = "",
    duration_minutes: int = 0,
) -> dict:
    """Updates an existing calendar event. Only the fields you provide are changed.

    Use search_calendar_events first to get the event_id.

    Args:
        event_id:         The event ID from search_calendar_events or list_calendar_events.
        title:            New event title (optional).
        date:             New date in YYYY-MM-DD format (optional).
        time:             New start time in HH:MM 24h format (optional).
        duration_minutes: New duration in minutes (optional).

    Returns:
        dict: status and updated event link.
    """
    from tools.calendar import update_event_sync
    return update_event_sync(
        get_user_id(), event_id,
        title or None, date or None, time or None, duration_minutes or None,
    )


def delete_calendar_event(event_id: str) -> dict:
    """Permanently deletes a calendar event.

    ALWAYS confirm with the user before deleting. Use search_calendar_events to find the event_id first.

    Args:
        event_id: The event ID to delete.

    Returns:
        dict: status and confirmation.
    """
    from tools.calendar import delete_event_sync
    return delete_event_sync(get_user_id(), event_id)


def web_search(query: str) -> dict:
    """Searches the web for current information using Google Search grounding.

    Args:
        query: The search query.

    Returns:
        dict: status, report (answer), and sources list.
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


def fetch_webpage(url: str) -> dict:
    """Fetches a webpage and returns its readable text content.

    Use this for reading articles, checking prices, summarising pages,
    or any task that only needs to READ a page (no clicking or login required).
    For interactive tasks (filling forms, booking, logging in) use browse_web instead.

    Args:
        url: Full URL of the page to fetch (must start with http:// or https://).

    Returns:
        dict: status, title, text content, and whether it was truncated.
    """
    from tools.browser import web_fetch
    return _run_async(web_fetch(url))


def browse_web(task: str, start_url: str = "https://www.google.com") -> dict:
    """Opens a real browser and autonomously completes a web task.

    Use this for interactive tasks: booking flights, filling forms, logging into
    websites, clicking buttons, or anything that requires JavaScript and interaction.
    This is slower than fetch_webpage -- only use it when you need real interaction.

    Args:
        task:      Natural-language description of what to do
                   (e.g. 'find round-trip flights from Addis Ababa to Dubai under $500').
        start_url: Optional starting URL. Defaults to Google.

    Returns:
        dict: status, result summary, number of browser actions taken, final URL.
    """
    from tools.browser import browser_task

    callback = current_browser_callback.get()
    uid = get_user_id()

    async def _run():
        on_screenshot = None
        on_step = None

        if callback:
            async def on_screenshot(png: bytes, url: str):
                await callback("screenshot", png, url)

            async def on_step(text: str):
                await callback("step", None, text)

        return await browser_task(
            task=task,
            start_url=start_url,
            on_screenshot=on_screenshot,
            on_step=on_step,
            user_id=uid,
        )

    return _run_async(_run())


def save_file(filename: str, content: str) -> dict:
    """Saves a file to the user's cloud workspace.

    Args:
        filename: Name of the file to save.
        content: Text content to write to the file.

    Returns:
        dict: status and file details or error message.
    """
    from tools.files import save_file_gcs
    return save_file_gcs(get_user_id(), filename, content)


def read_file(filename: str) -> dict:
    """Reads a file from the user's cloud workspace.

    Args:
        filename: Name of the file to read.

    Returns:
        dict: status and file content or error message.
    """
    from tools.files import read_file_gcs
    return read_file_gcs(get_user_id(), filename)


def list_files() -> dict:
    """Lists all files saved in the user's cloud workspace.

    Returns:
        dict: status and list of filenames.
    """
    from tools.files import list_files_gcs
    return list_files_gcs(get_user_id())


def delete_file(filename: str) -> dict:
    """Deletes a file from the user's cloud workspace.

    ALWAYS confirm with the user before deleting — this is irreversible.

    Args:
        filename: Name of the file to delete.

    Returns:
        dict: status and confirmation.
    """
    from tools.files import delete_file_gcs
    return delete_file_gcs(get_user_id(), filename)


def remember(fact: str) -> dict:
    """Saves a fact or preference to the user's long-term memory.

    Args:
        fact: The fact or preference to remember (e.g., 'I prefer window seats').

    Returns:
        dict: status and confirmation.
    """
    from tools.memory import save_memory
    return save_memory(get_user_id(), fact)


def recall(query: str) -> dict:
    """Retrieves relevant facts from the user's long-term memory.

    Args:
        query: What to search for in memory (e.g., 'seat preference').

    Returns:
        dict: status and relevant memories.
    """
    from tools.memory import search_memory
    return search_memory(get_user_id(), query)


def schedule_reminder(message: str, when: str, repeat: str = "") -> dict:
    """Schedules a reminder that will notify the user at the specified time.

    Use this whenever the user asks to be reminded about something later.
    Elora will send a push notification to their phone at the right time.

    Args:
        message: What to remind the user about (e.g., 'Call mom', 'Take medication').
        when:    When to fire: ISO datetime ('2026-03-15T09:00:00'),
                 or offset ('+2h', '+30m', '+1d'), or 'tomorrow 9am'.
        repeat:  Optional repeat: 'daily', 'weekly', or None for one-shot.

    Returns:
        dict: status, job_id, fire_at.
    """
    from tools.reminders import schedule_reminder as _schedule
    return _schedule(get_user_id(), message, when, repeat or None)


def list_reminders() -> dict:
    """Lists all pending reminders for the user.

    Returns:
        dict: status and list of upcoming reminders.
    """
    from tools.reminders import list_reminders as _list
    return _list(get_user_id())


def cancel_reminder(job_id: str) -> dict:
    """Cancels a scheduled reminder.

    Args:
        job_id: The reminder ID returned by schedule_reminder.

    Returns:
        dict: status and confirmation.
    """
    from tools.reminders import cancel_reminder as _cancel
    return _cancel(get_user_id(), job_id)


def create_presentation(title: str, slides: list[dict]) -> dict:
    """Creates a Google Slides presentation and returns a shareable link.

    Use this when the user asks to make a presentation, deck, or slideshow.

    Args:
        title:  Title of the presentation.
        slides: List of slide objects, each with:
                  - "heading": slide title (str)
                  - "body": slide content / bullet points (str, newlines OK)

    Returns:
        dict: status, link (shareable URL), presentation_id.
    """
    from tools.workspace import create_presentation as _create
    return _create(get_user_id(), title, slides)


def create_document(title: str, content: str) -> dict:
    """Creates a Google Doc with the given content and returns a shareable link.

    Use this when the user asks to write a document, report, letter, or note.

    Args:
        title:   Document title.
        content: Full text content (can include markdown-style formatting).

    Returns:
        dict: status, link (shareable URL), document_id.
    """
    from tools.workspace import create_document as _create
    return _create(get_user_id(), title, content)


def run_code(language: str, code: str, timeout: int = 30) -> dict:
    """Executes code in a secure cloud sandbox and returns the output.

    Use this whenever the user asks to run code, test a script, calculate something
    programmatically, process data, generate charts, or perform any computation.

    Args:
        language: 'python' or 'javascript'.
        code:     The full source code to execute.
        timeout:  Max execution time in seconds (5–120). Default 30.

    Returns:
        dict: status, stdout, stderr, results (list of output strings), error (if any).
    """
    from tools.e2b_sandbox import run_in_sandbox
    user_id = get_user_id()
    return run_in_sandbox(user_id, code, language, timeout)


# ---------------------------------------------------------------------------
# People memory tools
# ---------------------------------------------------------------------------

def remember_person(
    name: str,
    relationship: str,
    appearance_description: str = "",
    contact_email: str = "",
    contact_phone: str = "",
    notes: str = "",
    aliases: str = "",
) -> dict:
    """Store or update a person who matters to the user.

    Call this whenever the user introduces someone: 'this is my girlfriend Maya',
    'my mom's name is Linda', 'save Jake's number: +1-555-0100'.

    Args:
        name:                   Person's name. e.g. "Maya", "Jake"
        relationship:           How they relate to user. e.g. "girlfriend", "mom",
                                "best friend", "colleague", "brother"
        appearance_description: What they look like (from photo or description).
                                e.g. "tall, curly dark hair, usually wears glasses"
        contact_email:          Their email address if known.
        contact_phone:          Their phone number in E.164 format if known.
        notes:                  Extra context: birthday, interests, shared history.
                                e.g. "birthday March 3rd, loves sushi, met in Dubai"
        aliases:                Comma-separated nicknames. e.g. "babe,M"

    Returns:
        dict: {"status": "ok", "person_id": str, "name": str, "action": "remembered"|"updated"}
    """
    from tools.people import remember_person as _rp
    uid = get_user_id()
    return _rp(name, relationship, appearance_description, contact_email,
               contact_phone, notes, aliases, user_id=uid)


def recall_person(name_or_relationship: str) -> dict:
    """Look up what Elora knows about a specific person.

    Use this before messaging someone, when user refers to 'my girlfriend',
    'Jake', 'my mom', etc. Returns their contact info + everything stored.

    Args:
        name_or_relationship: Name, alias, or relationship string.
                              e.g. "Maya", "my girlfriend", "mom", "Jake"

    Returns:
        dict: person profile (name, relationship, email, phone, appearance, notes)
              or {"status": "not_found"}
    """
    from tools.people import recall_person as _rcp
    return _rcp(name_or_relationship, user_id=get_user_id())


def list_people() -> dict:
    """Return everyone Elora knows about for this user.

    Call at the start of new conversations to refresh your awareness of
    who the user knows. Use when user asks 'who do you know?'

    Returns:
        dict: {"people": [...], "count": int}
    """
    from tools.people import list_people as _lp
    return _lp(user_id=get_user_id())


def update_person_appearance(name: str, appearance_description: str) -> dict:
    """Update what a known person looks like (after seeing their photo via camera).

    Call this when the user shows a photo and says 'this is Maya' or
    'remember what she looks like'. Use Gemini's vision to describe them first.

    Args:
        name:                   Name of the person.
        appearance_description: Visual description from the photo.

    Returns:
        dict: {"status": "ok"} or {"status": "not_found"}
    """
    from tools.people import update_person_appearance as _upa
    return _upa(name, appearance_description, user_id=get_user_id())


def request_photo_search(person_name: str) -> dict:
    """Request the user's phone to search their camera roll for photos containing a specific person.

    The phone runs ML Kit face detection on-device (fast, free, private).
    Each detected face is compared against the stored reference using Gemini Vision.
    Results are returned to you as a follow-up message.

    Use this when the user asks:
    - "Find photos with Maya"
    - "Show me pictures of my girlfriend"
    - "Do you have any photos of mom?"

    Args:
        person_name: Name of the person to search for. e.g. "Maya", "mom", "me"

    Returns:
        dict: {"status": "searching", "note": "Results will arrive shortly."}
              The actual results come back as a system message once the phone finishes scanning.
    """
    # This tool signals the frontend via a special tool_result.
    # The frontend WebSocket handler detects "photo_search_request" and triggers usePhotoSearch.
    return {
        "status": "searching",
        "photo_search_request": True,
        "person_name": person_name,
        "note": f"I've asked your phone to search for photos of {person_name}. Results will come back shortly.",
    }


# ---------------------------------------------------------------------------
# SMS / messaging tools
# ---------------------------------------------------------------------------

def describe_person_from_camera(name: str, relationship: str = "") -> dict:
    """Describe the person currently visible in the camera and remember what they look like.

    Call this when the user says 'this is [name]', 'remember what she looks like',
    or 'this is me' while the live camera is active.

    The backend will use the most recent camera frame + Gemini Vision to generate
    a detailed appearance description, then store it in people memory automatically.

    Args:
        name:         The person's name. e.g. "Maya", "mom". Use "me" if the user
                      is describing themselves.
        relationship: Their relationship to the user if known. e.g. "girlfriend",
                      "mom", "colleague". Optional if already stored.

    Returns:
        dict: {"status": "ok", "description": str, "person_id": str}
              or {"status": "no_frame", "note": "Camera not active or no frame received yet."}
    """
    from tools.camera_memory import describe_and_remember_person
    uid = get_user_id()
    return describe_and_remember_person(uid, name, relationship)


# ---------------------------------------------------------------------------
# SMS / messaging tools (second section marker removed)
# ---------------------------------------------------------------------------

def send_sms(to_phone: str, message: str) -> dict:
    """Send a text message (SMS) to a phone number.

    ALWAYS confirm with the user before sending. If you don't have their number,
    call lookup_phone_for_person() or recall_person() first.

    Args:
        to_phone: Phone number in E.164 format. e.g. "+14155552671"
        message:  The message text (max 1600 chars).

    Returns:
        dict: {"status": "sent", ...} or {"status": "deep_link", "deep_link": "sms:..."} or error.
        If status is "deep_link", tell the app to open it so the user can tap send.
    """
    from tools.sms import send_sms as _sms
    return _sms(to_phone, message, user_id=get_user_id())


def lookup_phone_for_person(name_or_relationship: str) -> dict:
    """Find the phone number for a known person before sending them a text.

    Args:
        name_or_relationship: e.g. "Maya", "my girlfriend", "mom", "Jake"

    Returns:
        dict: {"status": "found", "phone": str, "name": str} or {"status": "not_found"}
    """
    from tools.sms import lookup_phone_for_person as _lookup
    return _lookup(name_or_relationship, user_id=get_user_id())


def set_morning_briefing(time: str, timezone: str = "UTC") -> dict:
    """Sets up a daily proactive morning briefing at the specified time.

    Elora will send a push notification every morning with:
    today's calendar, unread email count, and pending reminders.

    Args:
        time:     Time in HH:MM 24h format (e.g. '08:00', '07:30').
        timezone: IANA timezone (e.g. 'America/New_York', 'Africa/Addis_Ababa', 'Asia/Dubai').

    Returns:
        dict: status and confirmation.
    """
    from tools.briefing import set_briefing_preference
    return set_briefing_preference(get_user_id(), time, timezone)


def disable_morning_briefing() -> dict:
    """Disables the daily morning briefing.

    Returns:
        dict: status and confirmation.
    """
    from tools.briefing import disable_briefing
    return disable_briefing(get_user_id())


def get_current_time(city: str = "UTC") -> dict:
    """Returns the current time, optionally in a specific city's timezone.

    Args:
        city: City name or timezone (default: UTC).

    Returns:
        dict: status and current time.
    """
    tz_map = {
        # Americas
        "new york": "America/New_York",
        "los angeles": "America/Los_Angeles",
        "san francisco": "America/Los_Angeles",
        "chicago": "America/Chicago",
        "denver": "America/Denver",
        "toronto": "America/Toronto",
        "vancouver": "America/Vancouver",
        "mexico city": "America/Mexico_City",
        "sao paulo": "America/Sao_Paulo",
        "buenos aires": "America/Argentina/Buenos_Aires",
        "bogota": "America/Bogota",
        "lima": "America/Lima",
        # Europe
        "london": "Europe/London",
        "paris": "Europe/Paris",
        "berlin": "Europe/Berlin",
        "amsterdam": "Europe/Amsterdam",
        "rome": "Europe/Rome",
        "madrid": "Europe/Madrid",
        "zurich": "Europe/Zurich",
        "stockholm": "Europe/Stockholm",
        "moscow": "Europe/Moscow",
        "istanbul": "Europe/Istanbul",
        "athens": "Europe/Athens",
        "warsaw": "Europe/Warsaw",
        # Africa
        "addis ababa": "Africa/Addis_Ababa",
        "nairobi": "Africa/Nairobi",
        "cairo": "Africa/Cairo",
        "lagos": "Africa/Lagos",
        "johannesburg": "Africa/Johannesburg",
        "casablanca": "Africa/Casablanca",
        "accra": "Africa/Accra",
        # Asia
        "tokyo": "Asia/Tokyo",
        "dubai": "Asia/Dubai",
        "mumbai": "Asia/Kolkata",
        "delhi": "Asia/Kolkata",
        "kolkata": "Asia/Kolkata",
        "bangalore": "Asia/Kolkata",
        "shanghai": "Asia/Shanghai",
        "beijing": "Asia/Shanghai",
        "hong kong": "Asia/Hong_Kong",
        "singapore": "Asia/Singapore",
        "seoul": "Asia/Seoul",
        "bangkok": "Asia/Bangkok",
        "jakarta": "Asia/Jakarta",
        "taipei": "Asia/Taipei",
        "riyadh": "Asia/Riyadh",
        "karachi": "Asia/Karachi",
        "tehran": "Asia/Tehran",
        "kuala lumpur": "Asia/Kuala_Lumpur",
        # Oceania
        "sydney": "Australia/Sydney",
        "melbourne": "Australia/Melbourne",
        "auckland": "Pacific/Auckland",
        "perth": "Australia/Perth",
        "brisbane": "Australia/Brisbane",
        # UTC
        "utc": "UTC",
        "gmt": "UTC",
    }
    city_lower = city.lower().strip()
    tz_id = tz_map.get(city_lower)

    # If not in the map, try to use it as a raw IANA timezone string
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


# ---- Image Generation ----

def generate_image(prompt: str, aspect_ratio: str = "1:1") -> dict:
    """Generates an image from a text description using AI image generation.

    Args:
        prompt: Detailed description of the image to create.
        aspect_ratio: Aspect ratio like '1:1', '16:9', '9:16'.

    Returns:
        dict: Image generation result with base64 data.
    """
    from tools.image_gen import generate_image as _gen
    return _gen(prompt, aspect_ratio)


# ---- Music Generation ----

def generate_music(prompt: str, duration_seconds: int = 30) -> dict:
    """Generates original music from a text description of mood, genre, and style using Google Lyria.

    Args:
        prompt: Description of the music (mood, genre, instruments, tempo, energy).
        duration_seconds: How long the track should be in seconds (10-60).

    Returns:
        dict: Music generation result with base64 audio data.
    """
    from tools.music_gen import generate_music as _gen
    return _gen(prompt, duration_seconds)


# ---- Restaurant Reservations ----

def search_restaurants(query: str = "", location: str = "", cuisine: str = "") -> dict:
    """Searches for restaurants available for reservation.

    Args:
        query: Search term (restaurant name or type).
        location: City or area to search in.
        cuisine: Type of cuisine (Italian, Japanese, etc.).

    Returns:
        dict: List of available restaurants.
    """
    from tools.restaurant import search_restaurants as _search
    return _search(query, location, cuisine)


def make_reservation(
    restaurant_id: str,
    restaurant_name: str,
    date: str,
    time: str,
    party_size: int = 2,
    guest_name: str = "",
    special_requests: str = "",
) -> dict:
    """Makes a restaurant reservation.

    Args:
        restaurant_id: The restaurant ID from search results.
        restaurant_name: Name of the restaurant.
        date: Date in YYYY-MM-DD format.
        time: Time in HH:MM format.
        party_size: Number of guests.
        guest_name: Name for the reservation.
        special_requests: Any special requests (allergies, occasion, seating).

    Returns:
        dict: Reservation confirmation.
    """
    from tools.restaurant import make_reservation as _reserve
    return _reserve(restaurant_id, restaurant_name, date, time, party_size, guest_name, special_requests)


def cancel_reservation(confirmation_id: str) -> dict:
    """Cancels a restaurant reservation.

    Args:
        confirmation_id: The confirmation ID from the reservation.

    Returns:
        dict: Cancellation status.
    """
    from tools.restaurant import cancel_reservation as _cancel
    return _cancel(confirmation_id)


# ---- Skill System ----

def search_skills(query: str) -> dict:
    """Search for skills that Elora can learn. Searches bundled skills and community registry.

    Use this when the user needs a capability you don't have, or asks to find/discover skills.

    Args:
        query: What the user needs (e.g. "track crypto prices", "read RSS feeds", "weather").

    Returns:
        dict: Matching skills with name, description, source, and install status.
    """
    user_id = get_user_id()
    from tools.mcp_skills import search_skills as _search
    return _search(query, user_id)


def install_skill(skill_name: str) -> dict:
    """Install a skill from the bundled library or community registry.

    After installation, the skill is saved to the user's profile and deployed
    to their personal sandbox. Use search_skills first to find available skills.

    Args:
        skill_name: Name of the skill to install (from search results).

    Returns:
        dict: Installation status.
    """
    user_id = get_user_id()
    from tools.mcp_skills import install_skill as _install
    return _install(skill_name, user_id)


def create_skill(name: str, description: str, code: str, parameters: str, category: str = "custom") -> dict:
    """Create a brand new skill from scratch. This is your superpower -- write new capabilities
    and save them for future use. The code is tested in the user's sandbox before saving.

    Use this when no existing skill fits what the user needs. Write Python code that
    accomplishes the task and save it as a reusable skill.

    Args:
        name: Unique skill name (lowercase, underscores, no spaces).
        description: Human-readable description of what this skill does.
        code: Python code implementing the skill. Should print JSON output.
        parameters: JSON string of parameters the skill accepts (e.g. '{"city": "City name"}').
        category: Category tag (utility, finance, automation, news, etc.).

    Returns:
        dict: Creation and validation status.
    """
    user_id = get_user_id()
    from tools.mcp_skills import create_skill as _create
    return _create(name, description, code, parameters, user_id, category)


def execute_skill(skill_name: str, parameters: str = "{}") -> dict:
    """Execute an installed skill with the given parameters. Runs in the user's personal sandbox.

    Args:
        skill_name: Name of the installed skill to run.
        parameters: JSON string of parameter values (e.g. '{"location": "London"}').

    Returns:
        dict: Execution output from the skill.
    """
    user_id = get_user_id()
    from tools.mcp_skills import execute_skill as _exec
    return _exec(skill_name, parameters, user_id)


def list_installed_skills() -> dict:
    """List all skills in the user's library (installed + bundled).

    Returns:
        dict: Installed skills and available bundled skills.
    """
    user_id = get_user_id()
    from tools.mcp_skills import list_installed_skills as _list
    return _list(user_id)


def remove_skill(skill_name: str) -> dict:
    """Remove a skill from the user's library.

    Args:
        skill_name: Name of the skill to uninstall.

    Returns:
        dict: Removal status.
    """
    user_id = get_user_id()
    from tools.mcp_skills import remove_skill as _remove
    return _remove(skill_name, user_id)


def install_sandbox_package(package: str, language: str = "python") -> dict:
    """Install a package in the user's personal sandbox. Persists across sessions.

    Use this when a skill or code execution needs a package that isn't pre-installed.

    Args:
        package: Package name (e.g. 'pandas', 'numpy', 'openai').
        language: 'python' (pip) or 'javascript' (npm).

    Returns:
        dict: Installation status.
    """
    user_id = get_user_id()
    from tools.mcp_skills import install_sandbox_package as _install_pkg
    return _install_pkg(package, user_id, language)


def publish_skill(skill_name: str) -> dict:
    """Publish a user-created skill to the community registry for other users to discover.

    Args:
        skill_name: Name of the skill to publish.

    Returns:
        dict: Publication status.
    """
    user_id = get_user_id()
    from tools.mcp_skills import publish_skill as _publish
    return _publish(skill_name, user_id)


# ---------------------------------------------------------------------------
# Sub-agents (specialists)
# ---------------------------------------------------------------------------

web_researcher = Agent(
    name="web_researcher",
    model="gemini-2.0-flash",
    description=(
        "Specialist for finding information on the web. "
        "Use for: answering factual questions, checking current prices, reading articles, "
        "summarising web pages. Does NOT interact with pages (no clicking, no forms)."
    ),
    instruction=(
        f"{PERSONA}\n\n"
        "You are the WebResearcher. Your only job is to find accurate, up-to-date information.\n"
        "- Use web_search for current facts, news, or general queries.\n"
        "- Use fetch_webpage when you have a specific URL to read.\n"
        "- Be factual. Cite sources when available.\n"
        "- Return a clear, concise summary. Do not waffle.\n"
        "- If the research is insufficient, say so explicitly so the orchestrator can retry."
    ),
    tools=[web_search, fetch_webpage],
)

browser_worker = Agent(
    name="browser_worker",
    model="gemini-2.5-flash",
    description=(
        "Specialist for interactive browser tasks. "
        "Use for: booking flights, filling forms, logging into websites, clicking buttons, "
        "any task requiring JavaScript execution or real user interaction on a website."
    ),
    instruction=(
        f"{PERSONA}\n\n"
        "You are the BrowserWorker. You control a real headless Chromium browser.\n"
        "You CAN and SHOULD use browse_web for any interactive web task.\n"
        "- Be specific in your task description -- include all relevant details (dates, preferences, constraints).\n"
        "- Start at the most relevant URL when known (e.g. google.com/flights for flight search).\n"
        "- Report the result clearly: what was found or done, the final URL, and any confirmation numbers.\n"
        "- If the task fails, report the exact step where it failed and why."
    ),
    tools=[browse_web],
)

email_calendar = Agent(
    name="email_calendar",
    model="gemini-2.0-flash",
    description=(
        "Specialist for Gmail and Google Calendar. "
        "Use for: sending emails, reading inbox, archiving/deleting/labelling emails, "
        "creating/updating/deleting calendar events, checking schedule."
    ),
    instruction=(
        f"{PERSONA}\n\n"
        "You are the EmailCalendar specialist.\n"
        "- send_email: compose and send\n"
        "- read_emails: check inbox with Gmail query syntax\n"
        "- manage_email: archive / trash / mark_read / label a specific email by ID\n"
        "- batch_manage_emails: apply an action to ALL emails matching a query (confirm first!)\n"
        "- create_calendar_event: add a new event\n"
        "- list_calendar_events: check schedule for a date\n"
        "- search_calendar_events: find events by keyword (returns IDs for update/delete)\n"
        "- update_calendar_event: reschedule or rename an event\n"
        "- delete_calendar_event: remove an event (confirm first!)\n"
        "Always confirm before sending emails or deleting anything.\n"
        "Always include timezone when creating/updating events.\n"
        "Use search_calendar_events before update or delete to get the event ID."
    ),
    tools=[
        send_email, read_emails, manage_email, batch_manage_emails,
        create_calendar_event, list_calendar_events,
        search_calendar_events, update_calendar_event, delete_calendar_event,
    ],
)

file_memory = Agent(
    name="file_memory",
    model="gemini-2.0-flash",
    description=(
        "Specialist for the user's files and long-term memory. "
        "Use for: saving notes, reading/listing/deleting files, remembering preferences, recalling past facts."
    ),
    instruction=(
        f"{PERSONA}\n\n"
        "You are the FileMemory specialist.\n"
        "- save_file: write a file to the user's workspace\n"
        "- read_file: read a specific file\n"
        "- list_files: show all files in the workspace\n"
        "- delete_file: permanently delete a file (confirm first!)\n"
        "- remember: store a fact or preference to long-term memory\n"
        "- recall: retrieve relevant memories before answering about preferences\n"
        "Always recall relevant context at the start of a task involving user preferences."
    ),
    tools=[save_file, read_file, list_files, delete_file, remember, recall],
)


# ---------------------------------------------------------------------------
# Research pipeline -- LoopAgent with self-verification
# Uses SEPARATE instances of web_researcher to avoid "already has a parent" error.
# ADK enforces one-parent-per-agent strictly.
# ---------------------------------------------------------------------------

# Dedicated researcher instance for the loop (cannot reuse the sub-agent instance)
_loop_researcher = Agent(
    name="loop_web_researcher",
    model="gemini-2.0-flash",
    description="Finds web information for the research loop.",
    instruction=(
        f"{PERSONA}\n\n"
        "You are a research specialist. Use web_search and fetch_webpage to find "
        "accurate, current information. Be factual and cite sources."
    ),
    tools=[web_search, fetch_webpage],
)

class ResearchJudge(BaseAgent):
    """
    Evaluates the web_researcher's output and either escalates (good enough)
    or lets the loop continue (needs more research).

    Reads session.state["research_findings"] written by web_researcher.
    Sets session.state["research_verdict"] = "pass" | "fail".
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        findings = ctx.session.state.get("research_findings", "")
        original_query = ctx.session.state.get("research_query", "")

        if not findings:
            ctx.session.state["research_verdict"] = "fail"
            yield Event(author=self.name)
            return

        # Simple heuristic: if findings are substantive (>200 chars) and
        # contain the query keywords, pass. Otherwise fail.
        keywords = [w.lower() for w in original_query.split() if len(w) > 3]
        findings_lower = findings.lower()
        keyword_hits = sum(1 for k in keywords if k in findings_lower)

        if len(findings) > 200 and (not keywords or keyword_hits >= max(1, len(keywords) // 2)):
            ctx.session.state["research_verdict"] = "pass"
        else:
            ctx.session.state["research_verdict"] = "fail"

        yield Event(author=self.name)


class EscalationChecker(BaseAgent):
    """
    Reads research_verdict from session state.
    If 'pass' → escalate (break the loop).
    If 'fail' → continue looping.
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        verdict = ctx.session.state.get("research_verdict", "fail")
        if verdict == "pass":
            yield Event(author=self.name, actions=EventActions(escalate=True))
        else:
            yield Event(author=self.name)


research_judge = ResearchJudge(name="research_judge")
escalation_checker = EscalationChecker(name="escalation_checker")

research_loop = LoopAgent(
    name="research_loop",
    description="Iteratively researches a topic until the findings meet quality standards.",
    sub_agents=[_loop_researcher, research_judge, escalation_checker],
    max_iterations=3,
)

# ---------------------------------------------------------------------------
# Root orchestrator -- Elora
# ---------------------------------------------------------------------------

LIVE_MODEL = os.getenv("ELORA_LIVE_MODEL", os.getenv("ELORA_MODEL", "gemini-2.0-flash-live-001"))

root_agent = Agent(
    name="elora",
    model=LIVE_MODEL,
    description="Elora -- your personal AI agent that sees, hears, speaks, acts, and remembers.",
    instruction=SYSTEM_INSTRUCTION,
    tools=[
        get_current_time, remember, recall,
        schedule_reminder, list_reminders, cancel_reminder,
        create_presentation, create_document,
        set_morning_briefing, disable_morning_briefing,
        run_code,
        remember_person, recall_person, list_people, update_person_appearance,
        describe_person_from_camera, request_photo_search,
        send_sms, lookup_phone_for_person,
        generate_image, generate_music,
        search_restaurants, make_reservation, cancel_reservation,
        # Skill system
        search_skills, install_skill, create_skill, execute_skill,
        list_installed_skills, remove_skill, install_sandbox_package, publish_skill,
    ],
    sub_agents=[web_researcher, browser_worker, email_calendar, file_memory, research_loop],
)

# ---------------------------------------------------------------------------
# Text-mode agent (non-live fallback, used by ADK InMemoryRunner)
# ADK enforces one-parent-per-agent, so text_agent needs its own sub-agent instances.
# ---------------------------------------------------------------------------

def _make_sub_agents_for_text():
    """Create fresh sub-agent instances for text_agent (cannot reuse live sub-agents)."""
    _web = Agent(
        name="web_researcher_text",
        model="gemini-2.0-flash",
        description=web_researcher.description,
        instruction=web_researcher.instruction,
        tools=[web_search, fetch_webpage],
    )
    _browser = Agent(
        name="browser_worker_text",
        model="gemini-2.5-flash",
        description=browser_worker.description,
        instruction=browser_worker.instruction,
        tools=[browse_web],
    )
    _email = Agent(
        name="email_calendar_text",
        model="gemini-2.0-flash",
        description=email_calendar.description,
        instruction=email_calendar.instruction,
        tools=[
            send_email, read_emails, manage_email, batch_manage_emails,
            create_calendar_event, list_calendar_events,
            search_calendar_events, update_calendar_event, delete_calendar_event,
        ],
    )
    _files = Agent(
        name="file_memory_text",
        model="gemini-2.0-flash",
        description=file_memory.description,
        instruction=file_memory.instruction,
        tools=[save_file, read_file, list_files, delete_file, remember, recall],
    )
    # Research loop for text agent (separate instances, ADK one-parent rule)
    _loop_res_text = Agent(
        name="loop_web_researcher_text",
        model="gemini-2.0-flash",
        description=_loop_researcher.description,
        instruction=_loop_researcher.instruction,
        tools=[web_search, fetch_webpage],
    )
    _judge_text = ResearchJudge(name="research_judge_text")
    _esc_text = EscalationChecker(name="escalation_checker_text")
    _research_text = LoopAgent(
        name="research_loop_text",
        description=research_loop.description,
        sub_agents=[_loop_res_text, _judge_text, _esc_text],
        max_iterations=3,
    )
    return [_web, _browser, _email, _files, _research_text]

text_agent = Agent(
    name="elora_text",
    model="gemini-2.0-flash",
    description="Elora text mode -- for non-streaming interactions.",
    instruction=SYSTEM_INSTRUCTION,
    tools=[
        get_current_time, remember, recall,
        schedule_reminder, list_reminders, cancel_reminder,
        create_presentation, create_document,
        set_morning_briefing, disable_morning_briefing,
        run_code,
        remember_person, recall_person, list_people, update_person_appearance,
        describe_person_from_camera, request_photo_search,
        send_sms, lookup_phone_for_person,
        generate_image, generate_music,
        search_restaurants, make_reservation, cancel_reservation,
        # Skill system
        search_skills, install_skill, create_skill, execute_skill,
        list_installed_skills, remove_skill, install_sandbox_package, publish_skill,
    ],
    sub_agents=_make_sub_agents_for_text(),
)
