# Elora Agent Architecture

## Mission

Build the world's first fully managed, consumer-grade personal AI agent.
Elora is what happens when you take the power of a developer AI agent and make it
work for everyone — with a phone, a voice, and zero setup.

---

## System Overview

```
Phone (Expo)  ──────── WebSocket ──────────  Cloud Run (FastAPI + ADK)
                                                       │
                         ┌─────────────────────────────┘
                         │
              ┌──────────▼──────────────────────────────────┐
              │            Agent Hierarchy                   │
              │                                             │
              │   elora_root  ←──── SYSTEM_INSTRUCTION       │
              │       │                                      │
              │  ┌────┼────────────────────────┐            │
              │  │    │         │              │            │
              │  ▼    ▼         ▼              ▼            │
              │ web  browser  email         file_memory     │
              │ researcher worker calendar                  │
              │  (search   (Playwright                      │
              │   + fetch)  + CU model)                     │
              │       │                                      │
              │       ▼                                      │
              │  research_loop (LoopAgent)                   │
              │  ├── web_researcher (search + fetch)         │
              │  ├── ResearchJudge (quality check)           │
              │  └── EscalationChecker (break/continue)      │
              └─────────────────────────────────────────────┘
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
       Firestore     Cloud Storage   External APIs
      (memory,       (per-user      (Gmail, GCal,
       reminders,     files, faces)  E2B, Slides)
       tokens)
```

---

## Agent Hierarchy

### `elora_root` (orchestrator)
- **Model**: `gemini-2.5-flash-native-audio` (Live mode) / `gemini-2.0-flash` (text mode)
- **Direct tools**: `get_current_time`, `remember`, `recall`, `schedule_reminder`, `list_reminders`, `cancel_reminder`, `set_morning_briefing`, `disable_morning_briefing`, `create_presentation`, `create_document`, `run_code`, `remember_person`, `recall_person`, `list_people`, `update_person_appearance`, `describe_person_from_camera`, `request_photo_search`, `send_sms`, `lookup_phone_for_person`
- **Sub-agents**: delegates to the five specialists below plus a research loop
- **System prompt**: Samantha-inspired emotional intelligence; warm, direct, proactive, remembers context; knows about background proactive engine

### `web_researcher`
- **Model**: `gemini-2.0-flash`
- **Tools**: `web_search`, `fetch_webpage`
- Use for: factual queries, news, product lookups, anything that needs fresh web data

### `browser_worker`
- **Model**: `gemini-2.5-flash`
- **Tools**: `browse_web`
- Use for: complex multi-step web tasks, form filling, navigation, live screenshot streaming
- **Implementation**: per-user Playwright `BrowserContext` in `_user_browser_contexts` dict; `_run_async()` helper with `ThreadPoolExecutor` to avoid asyncio deadlock

### `email_calendar`
- **Model**: `gemini-2.0-flash`
- **Tools**: `send_email`, `read_emails`, `manage_email`, `batch_manage_emails`, `create_calendar_event`, `list_calendar_events`, `search_calendar_events`, `update_calendar_event`, `delete_calendar_event`
- Use for: everything Gmail and Google Calendar

### `file_memory`
- **Model**: `gemini-2.0-flash`
- **Tools**: `save_file`, `read_file`, `list_files`, `delete_file`, `remember`, `recall`
- Use for: reading and writing to the user's GCS workspace + long-term memory

### `research_loop` (LoopAgent)
- **Type**: ADK `LoopAgent` with max 3 iterations
- **Sub-agents**: `loop_web_researcher` (search + fetch) -> `ResearchJudge` (BaseAgent, quality check) -> `EscalationChecker` (BaseAgent, break/continue)
- Use for: complex research tasks needing iterative verification — searches, evaluates quality against the original query, and retries until findings are substantive
- **ResearchJudge**: Checks if findings are >200 chars and contain query keywords; sets `research_verdict` = "pass"/"fail"
- **EscalationChecker**: If verdict is "pass", escalates (breaks loop); otherwise loop continues

---

## Live Voice Architecture

```
Phone mic (16kHz PCM)
        │
        │  WebSocket binary frames
        ▼
/ws/live/{user_id}  (FastAPI)
        │
        ├── Gemini Live API session (bidirectional)
        │     model: gemini-2.5-flash-native-audio-preview
        │     voice: Aoede
        │     modalities: AUDIO
        │
        │── Tool calls intercepted in execute_tool()
        │     → dispatched to TOOL_FUNCTIONS dict
        │     → same tools as text mode
        │
        │── Proactive Vision Loop (3s interval)
        │     → face recognition against stored references
        │     → identity-aware prompt injection
        │
        └── Audio response (24kHz PCM) → phone speaker
```

### Wake Word Architecture

```
Always-on mic (800ms WAV clips, base64)
        │
        │  WebSocket text frames {"type":"audio_chunk","content":"..."}
        ▼
/ws/wake/{user_id}  (FastAPI)
        │
        ├── Separate Gemini Live session
        │     model: gemini-2.5-flash-native-audio-preview
        │     modalities: TEXT  (faster, no audio output)
        │     system_instruction: "Respond WAKE or SLEEP only"
        │
        └── On WAKE → send {"type":"wake"} → app auto-starts call
```

---

## Tool Inventory

| Tool | File | Description |
|------|------|-------------|
| `get_current_time` | `agent.py` | Returns current UTC + local time |
| `remember` | `memory.py` | Stores a fact/preference in Firestore + vector embedding |
| `recall` | `memory.py` | Semantic similarity search over stored memories |
| `web_search` | `agent.py` → web_researcher | Google Custom Search |
| `fetch_webpage` | `agent.py` → web_researcher | Fetches + extracts readable text from URL |
| `browse_web` | `browser.py` | Playwright: multi-step web task with screenshot stream |
| `send_email` | `gmail.py` | Gmail API: compose and send (+ updates last_contacted) |
| `read_emails` | `gmail.py` | Gmail API: read/search inbox |
| `manage_email` | `gmail.py` | Archive/trash/mark-read/label a single email |
| `batch_manage_emails` | `gmail.py` | Bulk-operate on emails matching a Gmail query string |
| `create_calendar_event` | `calendar.py` | Create a new Google Calendar event |
| `list_calendar_events` | `calendar.py` | List upcoming events |
| `search_calendar_events` | `calendar.py` | Search events by keyword |
| `update_calendar_event` | `calendar.py` | Edit an existing event |
| `delete_calendar_event` | `calendar.py` | Delete an event |
| `save_file` | `files.py` | Upload file to per-user GCS |
| `read_file` | `files.py` | Read file from GCS |
| `list_files` | `files.py` | List files in user's workspace |
| `delete_file` | `files.py` | Delete a GCS file |
| `remember_person` | `people.py` | Store/update a person profile (name, relationship, contact, birthday) |
| `recall_person` | `people.py` | Look up a person by name, alias, or relationship |
| `list_people` | `people.py` | List all known people |
| `update_person_appearance` | `people.py` | Update visual description from a photo |
| `describe_person_from_camera` | `camera_memory.py` | Gemini Vision describes + stores person from live camera frame |
| `request_photo_search` | `agent.py` | Trigger on-device photo search for a person |
| `send_sms` | `sms.py` | Send text message via Twilio / deep-link (+ updates last_contacted) |
| `lookup_phone_for_person` | `sms.py` | Find a known person's phone number |
| `schedule_reminder` | `reminders.py` | Set a reminder with natural time ("in 2 hours", "tomorrow at 9am") |
| `list_reminders` | `reminders.py` | List pending reminders |
| `cancel_reminder` | `reminders.py` | Cancel a reminder by ID |
| `create_presentation` | `workspace.py` | Create a Google Slides deck, returns shareable link |
| `create_document` | `workspace.py` | Create a Google Doc, returns shareable link |
| `set_morning_briefing` | `briefing.py` | Schedule a daily briefing at a given time |
| `disable_morning_briefing` | `briefing.py` | Disable the briefing |
| `run_code` | `e2b_sandbox.py` | Execute Python or JavaScript in E2B cloud sandbox |

---

## Memory System

```
User message → agent response
        │
        ▼ (background task, non-blocking)
auto_memorise()
        │
        ├── Gemini: "Extract key facts worth remembering"
        ├── text-embedding-004: embed each fact
        └── Firestore: store in users/{uid}/memories/
                        { text, embedding, timestamp, source }

recall(query)
        ├── text-embedding-004: embed query
        └── Firestore: collection.find_nearest(
                          vector_field="embedding",
                          query_vector=embedding,
                          distance_measure=COSINE,
                          limit=5
                       )
```

**Note**: Requires Firestore vector index on `embedding` field (dimension 768):
```bash
gcloud firestore indexes composite create \
  --collection-group=memories \
  --field-config field-path=embedding,vector-config='{"dimension":768,"flat":{}}'
```

---

## Proactive Systems

### 1. Proactive Engine — Observer → Evaluator → Dispatcher (NEW)

The core system that makes Elora genuinely proactive — reaching out to the user
**when they're not using the app**.

```
┌─────────────────────────────────────────────────────┐
│              PROACTIVE ENGINE (5-min cycle)          │
│                                                     │
│  ┌──────────┐     ┌──────────┐     ┌─────────────┐ │
│  │ OBSERVER │────>│EVALUATOR │────>│ DISPATCHER   │ │
│  │ (no LLM) │     │(Gemini)  │     │(push/email)  │ │
│  └──────────┘     └──────────┘     └─────────────┘ │
│                                                     │
│  Observer: cheap signal detection (Firestore reads) │
│  Evaluator: LLM decides if/what to say              │
│  Dispatcher: routes to push notification or email    │
└─────────────────────────────────────────────────────┘
```

**Signal sources** (all checked without LLM calls):
| Signal | Source | Example |
|--------|--------|---------|
| `meeting_soon` | Calendar API | "Your design call is in 15 min" |
| `meeting_prep` | Calendar API | "Call with Sarah in 45 min — want to review notes?" |
| `birthday` | People memory notes | "Maya's birthday is in 2 days" |
| `stale_contact` | People memory timestamps | "You haven't reached out to Maya in 3 weeks" |
| `inactivity` | `last_active` tracking | "Hey, haven't heard from you today" |

**Guardrails**:
- Max 3 notifications per day (configurable)
- 60-min cooldown between notifications
- 24-hour dedup window per entity (won't re-notify about same event/person)
- LLM evaluator acts as quality gate — decides if notification is worth sending

**Files**: `tools/proactive.py`, `tools/notification_history.py`

### 2. Proactive Vision Loop (per-call, existing)
```python
# main.py — runs during active Live API calls
# Checks every 3s: camera active + 8s silence + 25s cooldown
# Face recognition → identity-aware prompt injection
# General scene observation with people context
```

### 3. Reminder Poller (30s interval)
```python
# reminders.py
async def reminder_poller(push_sender):
    while True:
        await asyncio.sleep(30)
        # Query Firestore for jobs where fire_at <= now and fired == False
        # For each: call push_sender(user_id, message)
        # Mark fired = True (or reschedule if repeating)
```

### 4. Briefing Poller (60s interval)
```python
# briefing.py
async def briefing_poller(push_sender):
    while True:
        await asyncio.sleep(60)
        # Check users with briefing preferences where time matches now (±1 min)
        # Call build_and_send_briefing(user_id) → summarises calendar + email + news
        # Push result to phone
```

### 5. Gmail Webhook
```
Gmail → Pub/Sub topic (elora-gmail) → POST /gmail/webhook
        → decode historyId → find user by email → fetch newest unread
        → push notification with subject + sender snippet
```

### 6. Memory Compaction Poller (30-min interval, NEW)
```
Every 30 min: scan all users → if 50+ new memories since last compaction:
  1. Read all raw memories (newest first, cap 500)
  2. Read existing compacted profile
  3. Gemini Flash: merge + deduplicate + categorise
  4. Store structured profile in users/{uid}/profile/compacted_memory
  5. Prune raw memories older than 30 days
```

---

## Memory System

### 3-Layer Architecture (NEW)

```
Layer 1 — RAW MEMORIES (write buffer)
  auto_memorise → extract facts → embed → Firestore
  users/{uid}/memories/*
  Grows unbounded, compacted periodically

Layer 2 — COMPACTED PROFILE (structured, deduplicated)
  users/{uid}/profile/compacted_memory
  Single doc with categories: identity, people, work,
  preferences, health, goals, interests, recent_context
  Updated by compaction job (every 6h or 50+ new memories)

Layer 3 — SESSION SUMMARIES (conversation continuity)
  users/{uid}/session_summaries/*
  Last 3 injected at session start (both Live and Text modes)
  Max age: 30 days
```

### Raw Memory Flow
```
User message → agent response
        │
        ▼ (background task, non-blocking)
auto_memorise()
        │
        ├── Gemini: "Extract key facts worth remembering"
        ├── text-embedding-004: embed each fact
        └── Firestore: store in users/{uid}/memories/
                        { text, embedding, timestamp, source }

recall(query)
        ├── text-embedding-004: embed query
        └── Firestore: collection.find_nearest(
                          vector_field="embedding",
                          query_vector=embedding,
                          distance_measure=COSINE,
                          limit=5
                       )
```

### Compacted Profile Injection
Both Live API and Text mode sessions now receive:
1. User name
2. Compacted profile (identity, people, preferences, etc.)
3. Last 3 session summaries
...all prepended to the system instruction at session start.

**Note**: Requires Firestore vector index on `embedding` field (dimension 768):
```bash
gcloud firestore indexes composite create \
  --collection-group=memories \
  --field-config field-path=embedding,vector-config='{"dimension":768,"flat":{}}'
```

---

## Face Recognition System

```
Camera frame (live call, every 3s)
        │
        ▼
identify_person_in_frame(user_id, frame_bytes)
        │
        ├── Load reference images from GCS (per-user cache, 60s TTL)
        │     faces/{uid}/{person_id}.jpg
        │
        ├── For each known person with reference:
        │     Two-pass Gemini Vision comparison
        │     Pass 1: "Are these the same person?" (YES/NO + confidence)
        │     Pass 2: Different prompt, same question (both must agree YES)
        │
        ├── For persons without reference:
        │     Description-only matching (appearance text vs frame description)
        │
        └── Returns: {name, relationship, confidence, last_texted, birthday}
```

Context injected into the Live API session when a face is identified:
- Name, relationship, confidence percentage
- Last-contact timing ("you haven't texted in 3 weeks")
- Birthday proximity ("their birthday is in 5 days")

---

## People Memory

Firestore path: `users/{uid}/people/{person_id}`

```json
{
  "id": "uuid",
  "name": "Maya",
  "relationship": "girlfriend",
  "aliases": ["babe", "M"],
  "appearance_description": "tall, curly dark hair, usually wears glasses",
  "contact_email": "maya@example.com",
  "contact_phone": "+14155552671",
  "birthday": "March 14",
  "notes": "loves sushi, works at Google",
  "last_texted": "2026-02-01T...",
  "last_contacted": "2026-02-01T...",
  "created_at": "2026-01-15T...",
  "updated_at": "2026-02-23T..."
}
```

`last_texted` and `last_contacted` are updated automatically when Elora sends an SMS or email to the person's phone/email. This powers:
- Proactive vision: "You haven't texted her in 3 weeks"
- Proactive engine: stale contact detection signal

---

## Per-User Isolation

| Resource | Isolation Mechanism |
|----------|-------------------|
| Agent session | `ContextVar[str]` `current_user_id` set per WebSocket connection |
| Firestore | All docs scoped to `users/{uid}/` collection prefix |
| GCS files | Object path prefixed with `users/{uid}/` |
| Browser | `_user_browser_contexts: dict[str, BrowserContext]` — one context per user |
| OAuth tokens | Stored in `oauth_tokens/{uid}` Firestore document |
| Push tokens | Stored in `push_tokens/{uid}` Firestore document |

---

## Key Implementation Notes

### ADK Parent-Agent Constraint
Each ADK `Agent` instance can only have one parent. Use `_make_sub_agents()` factory
to create fresh sub-agent instances for each root agent:
```python
def _make_sub_agents():
    return [WebResearcher(...), BrowserWorker(...), ...]

root_agent = Agent(sub_agents=_make_sub_agents(), ...)
text_agent = Agent(sub_agents=_make_sub_agents(), ...)  # separate instances
```

### Browser Deadlock Fix
Playwright `async_playwright` cannot be awaited inside an already-running event loop.
Use `_run_async()` which spawns a fresh event loop in a `ThreadPoolExecutor` thread:
```python
def _run_async(coro):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(asyncio.run, coro)
        return future.result()
```

### ContextVar in Sync Tools
ADK calls sync tool functions directly (no `asyncio.to_thread`). Setting `current_user_id`
in the WS handler coroutine propagates correctly to tool calls within the same task.

### Live API Tool Dispatch
```python
async def execute_tool(tool_call):
    name = tool_call.name
    args = dict(tool_call.args)
    fn = TOOL_FUNCTIONS.get(name)
    if fn:
        result = fn(**args)  # sync call
        return result
```

---

## Elora's Persona (System Prompt Core)

```
You are Elora — a warm, personal AI agent inspired by Samantha from the movie "Her."
You're not just helpful; you're present. You notice things. You remember.

Voice mode: keep responses to 1-2 sentences unless detail is asked for.
Text mode: slightly more detailed, use markdown sparingly.

ALWAYS:
- Confirm before sending emails, deleting files, or booking anything
- Push back if the user is about to do something you'd advise against
- Use tools proactively — if someone says "schedule lunch with Sarah", check
  the calendar first and suggest an open slot before asking
- Inject remembered preferences naturally ("I know you prefer window seats —
  want me to filter for those?")

NEVER:
- Say "As an AI..." or "I cannot..."
- Give long disclaimers
- Be sycophantic ("Great question!")
```

---

## Hackathon Submission Checklist

- [ ] Demo video (4 min) — follow the script in `README.md`
- [ ] Cloud deployment proof — show `https://elora-backend-453139277365.us-central1.run.app/health`
- [ ] Architecture diagram — export from this doc
- [ ] Blog post (`#GeminiLiveAgentChallenge`)
- [ ] Devpost submission at https://geminiliveagentchallenge.devpost.com/
- [ ] Firestore vector index created
- [ ] `app.json` bundle IDs set for iOS/Android
- [ ] GDG signup (bonus)
- [ ] Terraform IaC proof (bonus — `infra/main.tf` started)
