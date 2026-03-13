# Elora - Your Personal AI Computer, In Your Pocket

<p align="center">
  <strong>Not a chatbot. A secure, Gemini-powered personal AI that learns skills, runs code in your private sandbox, and acts on the real world.</strong>
</p>

<p align="center">
  Built for the <a href="https://geminiliveagentchallenge.devpost.com/">Gemini Live Agent Challenge</a> &nbsp;|&nbsp; Category: Live Agents
</p>

---

## The Problem

300K+ people starred OpenClaw in 6 weeks because they want a personal AI that actually *does things* -- sends emails, manages files, browses the web, runs code, learns new skills.

But every solution requires a Mac Mini, Docker, terminal commands, API keys, SSH tunnels, or a cloud bill.

**8 billion people want a personal AI computer. 99% of them will never run a Docker container.**

## The Solution

Elora is not a chatbot. She is a **personal AI computer that lives on your phone** -- with her own sandbox, her own skill system, and a trust protocol that protects everything she does.

- **Voice-first, barge-in native** -- "Hey Elora" wakes from any screen. Gemini Live API powers full duplex audio. Interrupt her mid-sentence, she interrupts you back.
- **Vision** -- Point your camera at anything. She sees it, recognizes faces, and responds in real time. During calls, she watches your camera every 3 seconds and speaks up when she notices something.
- **40+ real tools** -- Sends emails, texts friends, books calendar events, browses the web, executes code, creates Google Docs and Slides, manages files, pushes code to GitHub.
- **Self-extending skill system** -- Elora can search for, install, create, and execute skills on the fly. Tell her what you need -- she'll find it, build it, or learn it. Skills persist in your library forever.
- **Per-user sandbox** -- Each user gets their own isolated cloud VM (via [E2B](https://e2b.dev)). Install packages. Run code. Create files. Everything persists across sessions.
- **Security built in** -- Every interaction is protected by [Agntor](https://github.com/agntor/agntor): prompt injection guard, PII redaction, tool guardrails, SSRF protection.
- **People memory** -- Knows the people in your life. Remembers faces, birthdays, relationships, contact info.
- **3-layer persistent memory** -- Raw facts via vector search, compacted user profile, session summaries. She remembers what you told her three weeks ago.
- **Truly proactive** -- Background engine reaches out via push notifications when meetings approach, birthdays are near, or you haven't talked to someone close in a while.
- **Fully managed** -- No servers. No API keys. No Docker. Download and talk.

---

## Architecture

> **Visual diagram:** See [`docs/architecture-diagram.svg`](docs/architecture-diagram.svg) for the full system architecture diagram.

```
+---------------------------------------------------------+
|                   MOBILE APP (Expo / React Native)       |
|                                                          |
|  +--------------+  +----------+  +--------+  +-------+  |
|  |  Wake Word   |  |  Voice   |  | Vision |  |  Chat |  |
|  |  (always-on  |  |  (Live   |  |(Camera)|  | (Text)|  |
|  |   mic ws)    |  |   API)   |  |        |  |       |  |
|  +------+-------+  +----+-----+  +---+----+  +---+---+  |
|         +---------------+-----------+------------+       |
|                          |  WebSocket                    |
+--------------------------+------------------------------+
                           |
                           v
+----------------------------------------------------------+
|                  ELORA CLOUD  (Google Cloud Run)          |
|                                                          |
|  +----------------------------------------------------+  |
|  |          FastAPI  +  Google ADK  +  Gemini Live     |  |
|  |                                                     |  |
|  |  +--------------------------------------------+    |  |
|  |  |              AGENT HIERARCHY                |    |  |
|  |  |                                             |    |  |
|  |  |  elora_root (orchestrator)                  |    |  |
|  |  |  +-- web_researcher  (search + fetch)       |    |  |
|  |  |  +-- browser_worker  (Playwright + CU)      |    |  |
|  |  |  +-- email_calendar  (Gmail + GCal)         |    |  |
|  |  |  +-- file_memory     (GCS + Firestore)      |    |  |
|  |  |  +-- research_loop   (iterative verify)     |    |  |
|  |  +--------------------------------------------+    |  |
|  |                                                     |  |
|  |  +----------------------------------------------+  |  |
|  |  |                  TOOLS (40+)                  |  |  |
|  |  |  Gmail - Calendar - Browser - Memory          |  |  |
|  |  |  People - SMS - Face Recognition - Camera     |  |  |
|  |  |  Files - Reminders - Workspace - Push         |  |  |
|  |  |  Briefing - Proactive Engine - GitHub Push    |  |  |
|  |  |  -------------------------------------------- |  |  |
|  |  |  Skill System: search, install, create,       |  |  |
|  |  |    execute, publish (community registry)      |  |  |
|  |  +----------------------------------------------+  |  |
|  |                                                     |  |
|  |  +----------------------------------------------+  |  |
|  |  |         SECURITY (Agntor Protocol)            |  |  |
|  |  |  Prompt Guard - PII Redact - Tool Guard       |  |  |
|  |  |  SSRF Protection - Agent Identity             |  |  |
|  |  +----------------------------------------------+  |  |
|  +----------------------------------------------------+  |
|                                                          |
|  +--------------+  +---------------+  +--------------+   |
|  |  Firestore   |  |Cloud Storage  |  |  Firebase    |   |
|  |  (memory,    |  |(per-user      |  |  Auth        |   |
|  |   reminders, |  | files, faces) |  |  (anon UID)  |   |
|  |   people,    |  |               |  |              |   |
|  |   tokens)    |  |               |  |              |   |
|  +--------------+  +---------------+  +--------------+   |
+----------------------------------------------------------+
                           |
               +-----------+-----------+
               |    External Services  |
               |  E2B (Per-User Sandbox) |
               |  Agntor (Trust Protocol)|
               |  Twilio (SMS)           |
               |  Expo Push              |
               +-----------+-----------+
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|------------|-----|
| **Mobile** | Expo / React Native (TypeScript) | Cross-platform, fast iteration |
| **Voice** | Gemini Live API (`gemini-2.5-flash-native-audio`) | Real-time bidi audio + vision stream |
| **Wake Word** | Gemini Live API (same model, VAD mode) | Always-on, model-level VAD + intent detection |
| **Agent** | Google ADK | Multi-agent orchestration, tool calling, session state |
| **LLM** | Gemini 2.0 Flash / 2.5 Flash | Fast, multimodal, native tool use |
| **Browser** | Gemini 2.5 Flash + Playwright | Autonomous browser with live screenshot stream |
| **Face Recognition** | Gemini Vision (two-pass comparison) | Identify known people from camera |
| **Code** | E2B Code Interpreter | Per-user persistent sandbox, auto-pause/resume |
| **Skills** | Custom skill system | Search, install, create, execute skills; community registry |
| **Security** | [Agntor](https://github.com/agntor/agntor) trust protocol | Prompt injection guard, PII redaction, tool guardrails, SSRF |
| **Backend** | FastAPI + Python 3.11 on Cloud Run | ADK-native, auto-scaling, 0-to-N |
| **Memory** | Firestore + `text-embedding-004` + [MemU](https://github.com/NevaMind-AI/memU) | 3-layer memory: vector search, compacted profile, session summaries |
| **SMS** | Twilio (primary) / deep-link fallback | Text messaging with last-contacted tracking |
| **Files** | Cloud Storage | Per-user isolated workspace + face reference images |
| **Auth** | Firebase Anonymous Auth | Zero friction -- no login screen, real UID |
| **Push** | Expo Push Notifications | Proactive alerts, reminders, email triage, meeting nudges |
| **Deploy** | Cloud Run + GitHub Actions CI/CD | Auto-deploy on push, Terraform IaC |

---

## Quick Start

### Prerequisites

- **Node.js** >= 18 and **npm** >= 9
- **Python** 3.11+
- **Expo Go** app on your phone ([iOS](https://apps.apple.com/app/expo-go/id982107779) / [Android](https://play.google.com/store/apps/details?id=host.exp.exponent))
- (Optional for local backend) A Google Cloud project with Firestore in Native mode

### Option A: Try the live deployment (fastest)

The backend is **already deployed** on Cloud Run. Just run the mobile app:

```bash
git clone https://github.com/Garinmckayl/elora.git
cd elora/app
npm install
npx expo start --tunnel
```

Scan the QR code with Expo Go. The app connects to the live backend at:
```
https://elora-backend-qf7tbdhnnq-uc.a.run.app
```

#### Verify the backend is live (zero dependencies)

```bash
chmod +x verify.sh && ./verify.sh
```

Runs 20 checks against the live backend using only `curl` -- no Python, no API keys, no Docker. Verifies health, security capabilities (Agntor trust protocol), all bundled skills, REST endpoints, WebSocket, and Cloud Run deployment.

### Option B: Run the backend locally

```bash
git clone https://github.com/Garinmckayl/elora.git
cd elora

# 1. Backend
cd core
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Install Playwright browser (needed for browser_worker agent)
playwright install chromium

# 2. Configure environment
cp .env.example .env
# Edit .env and fill in:
#   GOOGLE_API_KEY          -- Gemini API key (required)
#   GOOGLE_CLOUD_PROJECT    -- Your GCP project ID (required for Firestore/GCS)
#   FIRESTORE_PROJECT_ID    -- Same as GOOGLE_CLOUD_PROJECT
#   GCS_BUCKET_NAME         -- GCS bucket for file storage
#   GOOGLE_OAUTH_CLIENT_ID  -- For Gmail/Calendar (optional, graceful fallback)
#   GOOGLE_OAUTH_CLIENT_SECRET
#   GOOGLE_OAUTH_REDIRECT_URI -- http://localhost:8080/auth/callback for local
#   E2B_API_KEY             -- For code execution (optional)
#   TWILIO_ACCOUNT_SID      -- For SMS (optional, deep-link fallback)

# 3. Start the server
uvicorn main:app --host 0.0.0.0 --port 8080

# 4. In another terminal, start the mobile app
cd ../app
npm install
# Update src/config.ts to point BACKEND_URL to http://<your-ip>:8080
npx expo start --tunnel
```

### Option C: Deploy your own with Terraform

```bash
cd elora/infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your GCP project ID, API keys, etc.

terraform init
terraform plan
terraform apply
```

This provisions: Cloud Run service, Artifact Registry, GCS bucket, Firestore API, IAM roles.

### Option D: Deploy via Docker

```bash
cd elora/core
docker build -t elora-backend .
docker run -p 8080:8080 --env-file .env elora-backend
```

---

## Google Cloud Services Used

| Service | Purpose |
|---------|---------|
| **Cloud Run** | Backend hosting (auto-scaling, stateless, HTTPS) |
| **Firestore** | Per-user memory, people profiles, reminders, OAuth tokens, session summaries, notification history, push tokens |
| **Cloud Storage (GCS)** | Per-user file workspace, face reference images |
| **Firebase Auth** | Anonymous authentication (zero-friction identity) |
| **Gemini Live API** | Real-time bidirectional audio + vision streaming |
| **Gemini 2.0 Flash** | Text agent, sub-agents, auto-memorize, proactive evaluator, face recognition |
| **Gemini 2.5 Flash** | Browser worker agent (Playwright + screenshot reasoning) |
| **text-embedding-004** | 768-dim vector embeddings for semantic memory search |
| **Google Search** | Grounded web search via GoogleSearch tool |
| **Gmail API** | Send, read, archive, trash, label, bulk-manage emails |
| **Google Calendar API** | Create, update, delete, list, search events |
| **Google Slides API** | Programmatic presentation creation with shareable links |
| **Google Docs API** | Programmatic document creation with shareable links |
| **Google Drive API** | File sharing permissions |
| **Artifact Registry** | Docker image storage for CI/CD |

**Proof of Google Cloud deployment:** [YouTube - Cloud Run, Firestore, Cloud Storage](https://youtu.be/W9jnF3Cvj6E)

---

## Live Backend

```
https://elora-backend-qf7tbdhnnq-uc.a.run.app
```

| Endpoint | What |
|----------|------|
| `GET /health` | Health check |
| `GET /agent/identity` | Agntor agent identity + security capabilities |
| `GET /agent/skills` | List bundled skills |
| `WS /ws/{user_id}` | Text agent (ADK) |
| `WS /ws/live/{user_id}` | Live audio (Gemini Live API) |
| `WS /ws/wake/{user_id}` | Always-on wake word detector |
| `GET /auth/login/{user_id}` | Start Google OAuth |
| `GET /auth/callback` | OAuth callback |
| `GET /auth/status/{user_id}` | Check OAuth connection status |
| `POST /push/register` | Register Expo push token |
| `POST /gmail/webhook` | Gmail Pub/Sub push receiver |
| `POST /user/profile` | Store user name/preferences |
| `GET /user/profile/{user_id}` | Get user profile |
| `POST /face/reference` | Upload face reference image |
| `POST /face/compare` | Compare face against references |

---

## Full Feature Set

### Voice & Presence
- **Always-on wake word** - "Hey Elora" wakes from any screen; 800ms WAV clips streamed to Gemini
- **Live call mode** - Continuous bidi audio; natural interruptions in both directions (barge-in)
- **Immersive call UI** - Full-screen camera feed, floating controls, live captions, audio waveform
- **Hold-to-talk** - Single utterance mode
- **Voice activity detection** - Model-level, no silence padding

### Vision & Face Recognition
- **Camera capture** - Point and ask; single-shot JPEG to Gemini multimodal
- **Live camera feed** - Share camera stream during a call (frame every 2s)
- **Proactive vision** - During calls, Elora observes the camera every 3s and speaks up when she sees something relevant
- **Face recognition** - Two-pass Gemini Vision comparison against stored reference images in GCS
- **Face memory** - "This is Maya" -> Gemini describes their appearance, stores it, uploads face crop for future recognition
- **Photo search** - "Find photos with Maya" -> on-device ML Kit face detection + Gemini Vision matching

### People & Relationships
- **People memory** - Rich profiles: name, relationship, aliases, appearance, contact info, birthday, notes
- **Contact lookup** - "Text my girlfriend" -> recalls person -> finds phone -> sends SMS
- **Last-contacted tracking** - Every SMS or email updates the person's `last_contacted` timestamp
- **Birthday awareness** - Proactive engine checks upcoming birthdays and notifies

### Communication
- **Gmail** - Read, send, archive, trash, label, bulk-manage by query string
- **Google Calendar** - Create, update, delete, list, search events
- **SMS** - Twilio primary, deep-link fallback; "Text Maya I'll be late"
- **Smart triage** - Gmail Pub/Sub webhook; new emails -> instant push notification + summary

### Intelligence & Memory
- **3-layer memory** - Raw facts (vector search) -> compacted profile (structured) -> session summaries
- **Auto-memorize** - Background task extracts and stores key facts after every exchange
- **Memory compaction** - Gemini Flash merges/deduplicates raw facts into a categorized user profile
- **Session memory** - Post-call summarization; last 3 summaries injected into next session
- **Research loop** - LoopAgent with self-verification: searches, evaluates quality, retries up to 3 times

### Action
- **Browser** - Playwright per-user `BrowserContext` + Gemini; live screenshot stream
- **Code execution** - E2B sandbox; runs Python or JavaScript; returns stdout + cell outputs
- **GitHub push** - Clone repos, edit files, commit, and push -- all by voice from the phone
- **Google Workspace** - Creates Google Slides and Google Docs; returns shareable link
- **File manager** - Upload, read, list, delete files in per-user GCS workspace

### Proactive
- **Background proactive engine** - Observer -> Evaluator -> Dispatcher running every 5 minutes
  - **Meeting alerts** - Push notification 15 min before calendar events
  - **Birthday nudges** - "Maya's birthday is in 2 days -- want me to send something?"
  - **Stale contact check-ins** - "You haven't texted Maya in 3 weeks -- want me to say hi?"
  - **Inactivity check-ins** - Caring nudge if user hasn't opened app in 24h+
  - **Quality gate** - Gemini Flash evaluator decides if each notification is worth sending
  - **Rate limiting** - Max 3/day, 60-min cooldown, 24h dedup per entity
- **Reminders** - Natural language time parsing; repeating support; push notification delivery
- **Morning briefing** - Configurable time; digest of email, calendar, reminders
- **Gmail webhook** - Instant push alert on new email with AI-generated subject summary

---

## Why Elora Wins

| What Others Build | What Elora Does |
|---|---|
| Fixed set of tools | **Self-extending skill system** -- learns new skills on the fly, creates them from scratch |
| Shared compute, no isolation | **Per-user sandbox** -- each user gets their own isolated cloud VM that persists |
| No security model | **Agntor trust protocol** -- prompt guard, PII redaction, tool guardrails, SSRF protection |
| Text chatbot with voice bolted on | **Voice-first** -- wake word, barge-in, live camera during calls |
| Web-only demo | **Mobile app** you hold in your hand |
| Single-turn Q&A | **Multi-step autonomous workflows** |
| No real actions | Sends actual emails, texts actual people, pushes code to GitHub |
| No memory | **3-layer memory** -- remembers your name, your people, your preferences across sessions |
| Doesn't know your people | Remembers faces, birthdays, relationships; recognizes your girlfriend on camera |
| Requires setup | Download -> talk. Zero setup. |

---

## Project Structure

```
elora/
+-- app/                          # Expo / React Native mobile app
|   +-- App.tsx                   # Root: routing, main screen, immersive call UI
|   +-- src/
|   |   +-- components/
|   |   |   +-- LiveCallScreen.tsx   # Full-screen immersive call experience
|   |   |   +-- ChatBubble.tsx       # Rich message rendering (markdown, tool cards)
|   |   |   +-- VoiceButton.tsx      # Animated push-to-talk
|   |   |   +-- VisionCapture.tsx    # Camera capture modal
|   |   |   +-- BrowserModal.tsx     # Live browser screenshot viewer
|   |   |   +-- PhotoGrid.tsx        # Photo grid with lightbox
|   |   +-- hooks/                   # 10 custom hooks (auth, voice, live, wake, push, etc.)
|   |   +-- screens/                 # Onboarding, Settings, Skills, Journey
|   |   +-- services/                # WebSocket service
|   |   +-- config.ts                # Backend URLs
|   |   +-- theme.ts                 # Design system
|   +-- package.json
+-- core/                         # Python backend
|   +-- main.py                   # FastAPI server, all endpoints, Live API orchestration
|   +-- elora_agent/
|   |   +-- agent.py              # Multi-agent hierarchy, system prompt, 40+ tool defs
|   +-- tools/                    # 18 tool modules
|   |   +-- gmail.py              # Gmail API (send, read, manage, batch)
|   |   +-- calendar.py           # Google Calendar API
|   |   +-- browser.py            # Playwright + Gemini computer-use
|   |   +-- memory.py             # Vector search memory (text-embedding-004)
|   |   +-- memory_compaction.py  # Profile compaction engine
|   |   +-- session_memory.py     # Post-call summarization
|   |   +-- people.py             # People profiles & relationships
|   |   +-- face_recognition_engine.py  # Two-pass Gemini Vision face comparison
|   |   +-- camera_memory.py      # Camera frame storage & description
|   |   +-- reminders.py          # Natural language reminders + poller
|   |   +-- briefing.py           # Morning briefing engine
|   |   +-- proactive.py          # Observer/Evaluator/Dispatcher engine
|   |   +-- push.py               # Expo push notifications
|   |   +-- notification_history.py  # Rate limiting & dedup
|   |   +-- sms.py                # Twilio SMS + fallback
|   |   +-- e2b_sandbox.py        # Per-user persistent sandbox (E2B auto-pause)
|   |   +-- mcp_skills.py         # Skill system: search, install, create, execute
|   |   +-- agntor_security.py    # Agntor trust protocol: guard, redact, SSRF
|   |   +-- workspace.py          # Google Slides & Docs creation
|   |   +-- files.py              # GCS per-user file storage
|   +-- requirements.txt
|   +-- Dockerfile
+-- infra/                        # Terraform IaC
|   +-- main.tf                   # Cloud Run, GCS, Artifact Registry, IAM
|   +-- terraform.tfvars.example
+-- .github/workflows/
|   +-- deploy.yml                # CI/CD: build, push, deploy to Cloud Run
+-- docs/
|   +-- architecture-diagram.svg  # System architecture diagram
|   +-- architecture.md           # Detailed system design
|   +-- changelog.md              # Version changelog
+-- verify.sh                     # 20-test backend smoke test
+-- README.md
```

---

## Infrastructure as Code

The `infra/` directory contains Terraform configuration that provisions the complete Google Cloud infrastructure:

- **Cloud Run** service (2 CPU, 2Gi memory, auto-scaling 0-10, 3600s timeout)
- **Artifact Registry** Docker repository
- **GCS bucket** for per-user file storage
- **Service Account** with Firestore and GCS IAM roles
- **API enablement** for Cloud Run, Artifact Registry, and Firestore
- All environment variables configured via Terraform variables (secrets marked sensitive)

CI/CD via GitHub Actions: every push to `main` triggers Docker build, push, and Cloud Run deployment with Firestore index creation.

---

## Hackathon

Built for the [Gemini Live Agent Challenge](https://geminiliveagentchallenge.devpost.com/) on Devpost.

**Deadline**: March 16, 2026 | **Prize pool**: $80,000 | **Grand prize**: $25K + Google Cloud Next demo slot

### Proof of Google Cloud Deployment

[YouTube - Cloud Run console, Firestore, Cloud Storage walkthrough](https://youtu.be/W9jnF3Cvj6E)

### Bonus Contributions

- **Blog Post:** [I Built a Personal AI Computer With Gemini -- Here's How](https://dev.to/zeshama/i-built-a-personal-ai-computer-with-gemini-heres-how-934) (dev.to)
- **Infrastructure as Code:** [`infra/main.tf`](infra/main.tf) (Terraform) + [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) (CI/CD)
- **GDG Membership:** [Profile](https://gdg.community.dev/u/m4z26f/#/about)

`#GeminiLiveAgentChallenge`
