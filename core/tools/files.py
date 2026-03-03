"""
Google Cloud Storage file tools for Elora.
Stores per-user files in a GCS bucket under users/{user_id}/{filename}.

Falls back to an in-memory dict if GCS is not configured
(GCS_BUCKET_NAME env var not set), so local dev works without credentials.
"""

import os
import logging

logger = logging.getLogger("elora.files")

# In-memory fallback store: {user_id: {filename: content}}
_memory_store: dict[str, dict[str, str]] = {}

GCS_BUCKET = os.getenv("GCS_BUCKET_NAME", "") or os.getenv("ELORA_GCS_BUCKET", "")


def _get_storage_client():
    """Return a GCS client, or None if GCS is not available."""
    if not GCS_BUCKET:
        return None, None
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        return client, bucket
    except Exception as e:
        logger.warning(f"[Files] GCS not available: {e}")
        return None, None


def _blob_path(user_id: str, filename: str) -> str:
    """Build the GCS object path for a user's file."""
    # Sanitise filename to prevent path traversal
    safe_name = os.path.basename(filename)
    return f"users/{user_id}/{safe_name}"


def save_file_gcs(user_id: str, filename: str, content: str) -> dict:
    """Save a text file to GCS (or in-memory fallback)."""
    _, bucket = _get_storage_client()

    if bucket:
        try:
            blob = bucket.blob(_blob_path(user_id, filename))
            blob.upload_from_string(content, content_type="text/plain; charset=utf-8")
            logger.info(f"[Files] Saved gs://{GCS_BUCKET}/{_blob_path(user_id, filename)}")
            return {
                "status": "success",
                "report": f"File '{filename}' saved to your workspace.",
            }
        except Exception as e:
            logger.error(f"[Files] GCS save error: {e}")
            return {"status": "error", "report": f"Failed to save file: {str(e)}"}

    # In-memory fallback
    if user_id not in _memory_store:
        _memory_store[user_id] = {}
    _memory_store[user_id][filename] = content
    logger.info(f"[Files] Saved in-memory for user={user_id}: {filename}")
    return {
        "status": "success",
        "report": f"File '{filename}' saved to your workspace (local session only — set GCS_BUCKET_NAME for persistence).",
    }


def read_file_gcs(user_id: str, filename: str) -> dict:
    """Read a text file from GCS (or in-memory fallback)."""
    _, bucket = _get_storage_client()

    if bucket:
        try:
            blob = bucket.blob(_blob_path(user_id, filename))
            if not blob.exists():
                return {
                    "status": "not_found",
                    "report": f"File '{filename}' not found in your workspace.",
                    "content": "",
                }
            content = blob.download_as_text(encoding="utf-8")
            logger.info(f"[Files] Read gs://{GCS_BUCKET}/{_blob_path(user_id, filename)}")
            return {
                "status": "success",
                "report": f"Contents of '{filename}':",
                "content": content,
            }
        except Exception as e:
            logger.error(f"[Files] GCS read error: {e}")
            return {"status": "error", "report": f"Failed to read file: {str(e)}", "content": ""}

    # In-memory fallback
    user_files = _memory_store.get(user_id, {})
    if filename not in user_files:
        return {
            "status": "not_found",
            "report": f"File '{filename}' not found in your workspace.",
            "content": "",
        }
    content = user_files[filename]
    logger.info(f"[Files] Read in-memory for user={user_id}: {filename}")
    return {
        "status": "success",
        "report": f"Contents of '{filename}':",
        "content": content,
    }


def list_files_gcs(user_id: str) -> dict:
    """List all files in the user's workspace. Returns a dict with status and filenames."""
    _, bucket = _get_storage_client()
    prefix = f"users/{user_id}/"

    if bucket:
        try:
            blobs = bucket.list_blobs(prefix=prefix)
            filenames = [b.name[len(prefix):] for b in blobs]
            return {
                "status": "success",
                "report": f"You have {len(filenames)} file(s) in your workspace.",
                "files": filenames,
            }
        except Exception as e:
            logger.error(f"[Files] GCS list error: {e}")
            return {"status": "error", "report": str(e), "files": []}

    filenames = list(_memory_store.get(user_id, {}).keys())
    return {
        "status": "success",
        "report": f"You have {len(filenames)} file(s) in your workspace (local session).",
        "files": filenames,
    }


def delete_file_gcs(user_id: str, filename: str) -> dict:
    """Delete a file from the user's workspace."""
    _, bucket = _get_storage_client()

    if bucket:
        try:
            blob = bucket.blob(_blob_path(user_id, filename))
            if not blob.exists():
                return {"status": "not_found", "report": f"File '{filename}' not found."}
            blob.delete()
            logger.info(f"[Files] Deleted gs://{GCS_BUCKET}/{_blob_path(user_id, filename)}")
            return {"status": "success", "report": f"File '{filename}' deleted."}
        except Exception as e:
            logger.error(f"[Files] GCS delete error: {e}")
            return {"status": "error", "report": f"Failed to delete: {str(e)}"}

    user_files = _memory_store.get(user_id, {})
    if filename not in user_files:
        return {"status": "not_found", "report": f"File '{filename}' not found."}
    del user_files[filename]
    return {"status": "success", "report": f"File '{filename}' deleted."}
