terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Cloud Run region"
  type        = string
  default     = "us-central1"
}

variable "image" {
  description = "Container image (e.g. gcr.io/PROJECT/elora-backend:latest)"
  type        = string
  default     = ""
}

variable "google_api_key" {
  description = "Gemini API key (GOOGLE_API_KEY)"
  type        = string
  sensitive   = true
}

variable "oauth_client_id" {
  description = "Google OAuth2 client ID"
  type        = string
}

variable "oauth_client_secret" {
  description = "Google OAuth2 client secret"
  type        = string
  sensitive   = true
}

variable "gcs_bucket" {
  description = "GCS bucket name for per-user file storage (GCS_BUCKET_NAME)"
  type        = string
  default     = ""
}

variable "e2b_api_key" {
  description = "E2B Code Interpreter API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "twilio_account_sid" {
  description = "Twilio account SID for SMS"
  type        = string
  default     = ""
}

variable "twilio_auth_token" {
  description = "Twilio auth token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "twilio_phone_number" {
  description = "Twilio sender phone number"
  type        = string
  default     = ""
}

variable "github_pat" {
  description = "GitHub Personal Access Token for push_to_github tool"
  type        = string
  sensitive   = true
  default     = ""
}

# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------------
# Enable required APIs
# ---------------------------------------------------------------------------

resource "google_project_service" "run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifact_registry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "firestore" {
  service            = "firestore.googleapis.com"
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------
# Artifact Registry (Docker repo)
# ---------------------------------------------------------------------------

resource "google_artifact_registry_repository" "elora" {
  location      = var.region
  repository_id = "elora"
  format        = "DOCKER"
  description   = "Elora backend container images"

  depends_on = [google_project_service.artifact_registry]
}

# ---------------------------------------------------------------------------
# GCS bucket for user file storage
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "elora_files" {
  count    = var.gcs_bucket != "" ? 0 : 1
  name     = "${var.project_id}-elora-files"
  location = var.region

  uniform_bucket_level_access = true

  lifecycle_rule {
    action { type = "Delete" }
    condition { age = 365 }
  }
}

locals {
  gcs_bucket_name = var.gcs_bucket != "" ? var.gcs_bucket : (
    length(google_storage_bucket.elora_files) > 0
    ? google_storage_bucket.elora_files[0].name
    : ""
  )

  # Build the image URI from Artifact Registry if no custom image provided
  image_uri = var.image != "" ? var.image : (
    "${var.region}-docker.pkg.dev/${var.project_id}/elora/elora-backend:latest"
  )

  # Redirect URI points at this Cloud Run service
  oauth_redirect_uri = "https://elora-backend-${var.project_id}.${var.region}.run.app/auth/callback"
}

# ---------------------------------------------------------------------------
# Service account for Cloud Run
# ---------------------------------------------------------------------------

resource "google_service_account" "elora_run" {
  account_id   = "elora-cloud-run"
  display_name = "Elora Cloud Run Service Account"
}

resource "google_project_iam_member" "elora_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.elora_run.email}"
}

resource "google_storage_bucket_iam_member" "elora_files_rw" {
  count  = local.gcs_bucket_name != "" ? 1 : 0
  bucket = local.gcs_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.elora_run.email}"
}

# ---------------------------------------------------------------------------
# Cloud Run service
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "elora_backend" {
  name     = "elora-backend"
  location = var.region

  depends_on = [google_project_service.run]

  template {
    service_account = google_service_account.elora_run.email

    timeout = "3600s"

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    containers {
      image = local.image_uri

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        startup_cpu_boost = true
      }

      env {
        name  = "GOOGLE_API_KEY"
        value = var.google_api_key
      }
      env {
        name  = "GOOGLE_OAUTH_CLIENT_ID"
        value = var.oauth_client_id
      }
      env {
        name  = "GOOGLE_OAUTH_CLIENT_SECRET"
        value = var.oauth_client_secret
      }
      env {
        name  = "GOOGLE_OAUTH_REDIRECT_URI"
        value = local.oauth_redirect_uri
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "FIRESTORE_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCS_BUCKET_NAME"
        value = local.gcs_bucket_name
      }
      env {
        name  = "E2B_API_KEY"
        value = var.e2b_api_key
      }
      env {
        name  = "TWILIO_ACCOUNT_SID"
        value = var.twilio_account_sid
      }
      env {
        name  = "TWILIO_AUTH_TOKEN"
        value = var.twilio_auth_token
      }
      env {
        name  = "TWILIO_PHONE_NUMBER"
        value = var.twilio_phone_number
      }
      env {
        name  = "GITHUB_PAT"
        value = var.github_pat
      }
    }

    max_instance_request_concurrency = 10
  }
}

# Allow unauthenticated access (public API)
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.elora_backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "service_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.elora_backend.uri
}

output "image_repo" {
  description = "Artifact Registry repo for pushing images"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/elora"
}

output "gcs_bucket" {
  description = "GCS bucket name for user file storage"
  value       = local.gcs_bucket_name
}
