# GCP Deployment Proof

## Overview

Elora's backend runs on **Google Cloud Run** in the `elor-487806` GCP project, region `us-central1`.

**Live endpoint:** `https://elora-backend-453139277365.us-central1.run.app`

---

## Proof 1: Infrastructure as Code (Terraform)

**File:** [`infra/main.tf`](../infra/main.tf)

Provisions:
- Cloud Run service (2 CPU, 2Gi RAM, auto-scaling 0-10 instances)
- Artifact Registry Docker repository
- GCS bucket for per-user file storage (365-day lifecycle)
- Service account with Firestore + GCS IAM roles
- API enablement (Cloud Run, Artifact Registry, Firestore)

## Proof 2: CI/CD Pipeline (GitHub Actions)

**File:** [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)

On every push to `main`:
1. Authenticates to GCP via service account
2. Builds Docker image (`core/Dockerfile`)
3. Pushes to `gcr.io/elor-487806/elora-backend`
4. Deploys to Cloud Run (`gcloud run deploy`)
5. Creates Firestore vector indexes

## Proof 3: Google Cloud Services Used

| Service | Usage | Evidence |
|---------|-------|----------|
| **Cloud Run** | Backend hosting | `deploy.yml:42`, `infra/main.tf:90` |
| **Firestore** | Memory, people, reminders, sessions, tokens | `core/tools/memory.py`, `core/tools/people.py`, `core/tools/reminders.py` |
| **Cloud Storage (GCS)** | Per-user file workspace, face reference images | `core/tools/files.py`, `core/tools/face_recognition_engine.py` |
| **Firebase Auth** | Anonymous authentication | `core/main.py` (Firebase Admin SDK) |
| **Gemini API** | Text agent, Live API, vision, embeddings | `core/elora_agent/agent.py`, `core/main.py` |
| **Vertex AI** | Imagen 3 image generation, Lyria 3 music | `core/tools/imagen_images.py`, `core/tools/lyria_music.py` |
| **Gmail API** | Send, read, manage emails | `core/tools/gmail.py` |
| **Calendar API** | Create, list, search, update events | `core/tools/calendar.py` |
| **Slides API** | Create presentations | `core/tools/workspace.py` |
| **Docs API** | Create documents | `core/tools/workspace.py` |
| **Artifact Registry** | Docker image storage | `deploy.yml:36` |

## Proof 4: Screen Recording Instructions

To record a quick GCP console proof for submission:

1. Open https://console.cloud.google.com/run?project=elor-487806
2. Show the `elora-backend` service running
3. Click into it -- show the URL, region, and recent revisions
4. Open the **Logs** tab -- show recent request logs
5. Open **Firestore** (https://console.cloud.google.com/firestore?project=elor-487806) -- show user data collections
6. Open **Cloud Storage** -- show the elora bucket with user files

Record this as a 30-60 second screencast.

## Backend Health Check

```bash
curl https://elora-backend-453139277365.us-central1.run.app/health
# Expected: {"status": "ok", "version": "..."}
```

**Note:** Cloud Run scales to zero when idle. First request after cold start may take 10-30 seconds.
