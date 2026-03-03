"""
Google Slides and Docs creation tools for Elora.

Lets Elora create presentations and documents on the user's behalf,
returning a shareable link the user can open or send to others.

Requires the same OAuth token as Gmail/Calendar (already stored).
Additional scopes needed:
  https://www.googleapis.com/auth/presentations
  https://www.googleapis.com/auth/documents
  https://www.googleapis.com/auth/drive

Add these to OAUTH_SCOPES in main.py so they're requested on next re-auth.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("elora.workspace")


def _get_credentials(user_id: str):
    """Get refreshed Google OAuth credentials for the user."""
    from tools.gmail import get_user_token, set_user_token
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    token_info = get_user_token(user_id)
    if not token_info:
        return None

    creds = Credentials(
        token=token_info.get("access_token"),
        refresh_token=token_info.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
        client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_info["access_token"] = creds.token
        set_user_token(user_id, token_info)
    return creds


# ── Google Slides ─────────────────────────────────────────────────────────────

def create_presentation(
    user_id: str,
    title: str,
    slides: list[dict],
) -> dict:
    """
    Create a Google Slides presentation.

    Args:
        user_id: The user's ID.
        title:   Presentation title.
        slides:  List of slide dicts, each with:
                   - "heading": str  (slide title)
                   - "body": str     (bullet points or paragraph, newlines OK)

    Returns:
        dict with status, link, presentation_id.
    """
    creds = _get_credentials(user_id)
    if not creds:
        return {
            "status": "demo",
            "report": f"[Demo] Would create presentation '{title}' with {len(slides)} slides. Connect Google account first.",
            "link": "",
        }

    try:
        from googleapiclient.discovery import build

        slides_service = build("slides", "v1", credentials=creds, cache_discovery=False)
        drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)

        # Create blank presentation
        pres = slides_service.presentations().create(
            body={"title": title}
        ).execute()
        pres_id = pres["presentationId"]

        # Remove the default blank slide so we start fresh
        default_slide_id = pres["slides"][0]["objectId"] if pres.get("slides") else None

        requests = []

        # Add slides
        slide_ids = []
        for i, slide in enumerate(slides):
            sid = f"slide_{i}"
            slide_ids.append(sid)
            heading_id = f"heading_{i}"
            body_id = f"body_{i}"

            requests.append({
                "createSlide": {
                    "objectId": sid,
                    "insertionIndex": i,
                    "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"},
                    "placeholderIdMappings": [
                        {"layoutPlaceholder": {"type": "TITLE", "index": 0}, "objectId": heading_id},
                        {"layoutPlaceholder": {"type": "BODY", "index": 0}, "objectId": body_id},
                    ],
                }
            })

        # Delete default blank slide after our slides are added
        if default_slide_id:
            requests.append({"deleteObject": {"objectId": default_slide_id}})

        if requests:
            slides_service.presentations().batchUpdate(
                presentationId=pres_id,
                body={"requests": requests},
            ).execute()

        # Populate text content
        text_requests = []
        for i, slide in enumerate(slides):
            heading_id = f"heading_{i}"
            body_id = f"body_{i}"
            heading_text = slide.get("heading", f"Slide {i + 1}")
            body_text = slide.get("body", "")

            text_requests.append({
                "insertText": {
                    "objectId": heading_id,
                    "text": heading_text,
                    "insertionIndex": 0,
                }
            })
            if body_text:
                text_requests.append({
                    "insertText": {
                        "objectId": body_id,
                        "text": body_text,
                        "insertionIndex": 0,
                    }
                })

        if text_requests:
            slides_service.presentations().batchUpdate(
                presentationId=pres_id,
                body={"requests": text_requests},
            ).execute()

        # Make it readable by anyone with link
        drive_service.permissions().create(
            fileId=pres_id,
            body={"role": "reader", "type": "anyone"},
        ).execute()

        link = f"https://docs.google.com/presentation/d/{pres_id}/edit"
        logger.info(f"[Workspace] Created presentation '{title}' id={pres_id} user={user_id}")
        return {
            "status": "success",
            "report": f"Presentation '{title}' created with {len(slides)} slides.",
            "link": link,
            "presentation_id": pres_id,
        }

    except Exception as e:
        logger.error(f"[Workspace] Slides create error: {e}")
        return {"status": "error", "report": f"Failed to create presentation: {str(e)}", "link": ""}


# ── Google Docs ───────────────────────────────────────────────────────────────

def create_document(
    user_id: str,
    title: str,
    content: str,
) -> dict:
    """
    Create a Google Doc with the given content.

    Args:
        user_id: The user's ID.
        title:   Document title.
        content: Full text content of the document (markdown-ish is fine).

    Returns:
        dict with status, link, document_id.
    """
    creds = _get_credentials(user_id)
    if not creds:
        return {
            "status": "demo",
            "report": f"[Demo] Would create document '{title}'. Connect Google account first.",
            "link": "",
        }

    try:
        from googleapiclient.discovery import build

        docs_service = build("docs", "v1", credentials=creds, cache_discovery=False)
        drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)

        # Create blank doc
        doc = docs_service.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]

        # Insert content
        if content.strip():
            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={
                    "requests": [{
                        "insertText": {
                            "location": {"index": 1},
                            "text": content,
                        }
                    }]
                },
            ).execute()

        # Make readable by anyone with link
        drive_service.permissions().create(
            fileId=doc_id,
            body={"role": "reader", "type": "anyone"},
        ).execute()

        link = f"https://docs.google.com/document/d/{doc_id}/edit"
        logger.info(f"[Workspace] Created doc '{title}' id={doc_id} user={user_id}")
        return {
            "status": "success",
            "report": f"Document '{title}' created.",
            "link": link,
            "document_id": doc_id,
        }

    except Exception as e:
        logger.error(f"[Workspace] Docs create error: {e}")
        return {"status": "error", "report": f"Failed to create document: {str(e)}", "link": ""}
