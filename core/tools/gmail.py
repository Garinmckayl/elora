"""
Gmail integration for Elora.
Uses Google Gmail API with OAuth2 for sending and reading emails.
Falls back to demo responses if credentials are not available.

Tokens are persisted to Firestore so they survive Cloud Run restarts.
"""

import os
import base64
import logging
from email.mime.text import MIMEText

logger = logging.getLogger("elora.gmail")

# In-memory token cache (backed by Firestore)
_user_tokens: dict[str, dict] = {}

# Firestore client for token persistence
_db = None
try:
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    if project:
        from google.cloud import firestore
        _db = firestore.Client(project=project)
        logger.info(f"[Gmail] Firestore token store initialized (project={project})")
except Exception as e:
    logger.warning(f"[Gmail] Firestore not available for tokens: {e}")


def set_user_token(user_id: str, token_info: dict):
    """Store OAuth tokens for a user (in-memory + Firestore)."""
    _user_tokens[user_id] = token_info
    logger.info(f"[Gmail] Token cached for user={user_id}, keys={list(token_info.keys())}")

    # Persist to Firestore
    if _db:
        try:
            _db.collection("oauth_tokens").document(user_id).set(token_info)
            logger.info(f"[Gmail] Token persisted to Firestore for user={user_id}")
        except Exception as e:
            logger.error(f"[Gmail] Firestore token save error: {e}")


def get_user_token(user_id: str) -> dict | None:
    """Get stored OAuth tokens for a user (checks cache, then Firestore)."""
    # Check in-memory cache first
    if user_id in _user_tokens:
        return _user_tokens[user_id]

    # Try Firestore
    if _db:
        try:
            doc = _db.collection("oauth_tokens").document(user_id).get()
            if doc.exists:
                token_info = doc.to_dict()
                _user_tokens[user_id] = token_info  # Cache it
                logger.info(f"[Gmail] Token loaded from Firestore for user={user_id}")
                return token_info
        except Exception as e:
            logger.error(f"[Gmail] Firestore token load error: {e}")

    return None


def _get_gmail_service(user_id: str):
    """Get an authenticated Gmail service for a user."""
    token_info = get_user_token(user_id)
    if not token_info:
        logger.info(f"[Gmail] No token for user={user_id}")
        return None

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=token_info.get("access_token"),
            refresh_token=token_info.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        )

        # Auto-refresh if expired
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            # Update stored token (cache + Firestore) including new expiry
            token_info["access_token"] = creds.token
            if creds.expiry:
                token_info["expiry"] = creds.expiry.isoformat()
            set_user_token(user_id, token_info)
            logger.info(f"[Gmail] Token refreshed for user={user_id}")

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return service
    except Exception as e:
        logger.error(f"[Gmail] Service error for user={user_id}: {e}")
        return None


def send_email_sync(user_id: str, to: str, subject: str, body: str) -> dict:
    """Send an email via Gmail API (synchronous)."""
    service = _get_gmail_service(user_id)

    if not service:
        return {
            "status": "demo",
            "report": f"[Demo mode] Email to {to} with subject '{subject}' would be sent. Visit /auth/login/{user_id} to connect your Gmail.",
        }

    try:
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        logger.info(f"[Gmail] Sent email to {to}, id={result.get('id')}")

        # Update last_contacted for the person associated with this email
        _update_last_contacted_by_email(user_id, to)

        return {
            "status": "success",
            "report": f"Email sent to {to} with subject '{subject}'.",
        }
    except Exception as e:
        logger.error(f"[Gmail] Send error: {e}")
        return {"status": "error", "report": f"Failed to send email: {str(e)}"}


def manage_email_sync(user_id: str, email_id: str, action: str, label: str = "") -> dict:
    """
    Take an action on a specific email.

    Actions:
      archive    -- remove from inbox (remove INBOX label)
      trash      -- move to trash
      mark_read  -- mark as read (remove UNREAD label)
      mark_unread -- mark as unread (add UNREAD label)
      label      -- apply a label (creates it if it doesn't exist)
      unlabel    -- remove a label by name
    """
    service = _get_gmail_service(user_id)
    if not service:
        return {
            "status": "demo",
            "report": f"[Demo mode] Would {action} email {email_id}. Connect your Gmail first.",
        }

    try:
        if action == "archive":
            service.users().messages().modify(
                userId="me", id=email_id,
                body={"removeLabelIds": ["INBOX"]}
            ).execute()
            return {"status": "success", "report": f"Email archived."}

        elif action == "trash":
            service.users().messages().trash(userId="me", id=email_id).execute()
            return {"status": "success", "report": f"Email moved to trash."}

        elif action == "mark_read":
            service.users().messages().modify(
                userId="me", id=email_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            return {"status": "success", "report": f"Email marked as read."}

        elif action == "mark_unread":
            service.users().messages().modify(
                userId="me", id=email_id,
                body={"addLabelIds": ["UNREAD"]}
            ).execute()
            return {"status": "success", "report": f"Email marked as unread."}

        elif action == "label":
            if not label:
                return {"status": "error", "report": "Provide a label name."}
            label_id = _get_or_create_label(service, label)
            service.users().messages().modify(
                userId="me", id=email_id,
                body={"addLabelIds": [label_id]}
            ).execute()
            return {"status": "success", "report": f"Label '{label}' applied."}

        elif action == "unlabel":
            if not label:
                return {"status": "error", "report": "Provide a label name to remove."}
            label_id = _get_label_id(service, label)
            if not label_id:
                return {"status": "error", "report": f"Label '{label}' not found."}
            service.users().messages().modify(
                userId="me", id=email_id,
                body={"removeLabelIds": [label_id]}
            ).execute()
            return {"status": "success", "report": f"Label '{label}' removed."}

        else:
            return {"status": "error", "report": f"Unknown action '{action}'. Use: archive, trash, mark_read, mark_unread, label, unlabel."}

    except Exception as e:
        logger.error(f"[Gmail] manage_email error (action={action}): {e}")
        return {"status": "error", "report": f"Failed to {action} email: {str(e)}"}


def batch_manage_emails_sync(user_id: str, query: str, action: str, label: str = "") -> dict:
    """
    Apply an action to all emails matching a Gmail query.
    e.g. archive all emails from newsletters, trash all from a sender, etc.

    Args:
        query:  Gmail search query (e.g. 'from:newsletter@example.com', 'older_than:1y label:promotions')
        action: Same actions as manage_email (archive, trash, mark_read, label, unlabel)
        label:  Label name (only required for label/unlabel actions)
    """
    service = _get_gmail_service(user_id)
    if not service:
        return {
            "status": "demo",
            "report": f"[Demo mode] Would {action} all emails matching '{query}'. Connect Gmail first.",
        }

    try:
        results = service.users().messages().list(
            userId="me", q=query, maxResults=50
        ).execute()
        messages = results.get("messages", [])
        if not messages:
            return {"status": "success", "report": f"No emails found matching '{query}'."}

        success_count = 0
        for msg in messages:
            result = manage_email_sync(user_id, msg["id"], action, label)
            if result.get("status") == "success":
                success_count += 1

        return {
            "status": "success",
            "report": f"{action.replace('_', ' ').title()}d {success_count} of {len(messages)} emails matching '{query}'.",
        }
    except Exception as e:
        logger.error(f"[Gmail] batch_manage error: {e}")
        return {"status": "error", "report": f"Failed batch operation: {str(e)}"}


def _get_or_create_label(service, name: str) -> str:
    """Get a Gmail label ID by name, creating it if it doesn't exist."""
    existing = _get_label_id(service, name)
    if existing:
        return existing
    result = service.users().labels().create(
        userId="me",
        body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    ).execute()
    return result["id"]


def _get_label_id(service, name: str) -> str | None:
    """Return label ID for a given name, or None if not found."""
    try:
        labels = service.users().labels().list(userId="me").execute()
        for lbl in labels.get("labels", []):
            if lbl["name"].lower() == name.lower():
                return lbl["id"]
    except Exception:
        pass
    return None


def read_emails_sync(user_id: str, query: str = "is:unread", max_results: int = 5) -> dict:
    """Read emails from Gmail inbox (synchronous)."""
    service = _get_gmail_service(user_id)

    if not service:
        return {
            "status": "demo",
            "report": f"[Demo mode] Would search inbox for '{query}'. Visit /auth/login/{user_id} to connect your Gmail.",
            "emails": [],
        }

    try:
        results = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()

        messages = results.get("messages", [])
        emails = []

        for msg in messages[:max_results]:
            msg_data = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"]
            ).execute()

            headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
            emails.append({
                "id": msg["id"],
                "from": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "No subject"),
                "date": headers.get("Date", "Unknown"),
                "snippet": msg_data.get("snippet", ""),
            })

        logger.info(f"[Gmail] Read {len(emails)} emails for query='{query}'")
        return {
            "status": "success",
            "report": f"Found {len(emails)} emails matching '{query}'",
            "emails": emails,
        }
    except Exception as e:
        logger.error(f"[Gmail] Read error: {e}")
        return {"status": "error", "report": f"Failed to read emails: {str(e)}", "emails": []}


# ── Last-contacted tracking ──────────────────────────────────────────────────

def _update_last_contacted_by_email(user_id: str, email_address: str) -> None:
    """After sending an email, update the person's last_contacted timestamp."""
    try:
        from tools.people import _get_all_people, _people_col
        from datetime import datetime, timezone

        people = _get_all_people(user_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        email_lower = email_address.lower().strip()

        for person in people:
            p_email = (person.get("contact_email", "") or "").lower().strip()
            if p_email and p_email == email_lower:
                col = _people_col(user_id)
                if col:
                    col.document(person["id"]).update({
                        "last_contacted": now_iso,
                        "updated_at": now_iso,
                    })
                    logger.info(f"[Gmail] Updated last_contacted for '{person.get('name')}' user={user_id}")
                break
    except Exception as e:
        logger.debug(f"[Gmail] last_contacted update error: {e}")
