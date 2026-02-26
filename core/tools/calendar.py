"""
Google Calendar integration for Elora.
Uses Google Calendar API with OAuth2 for creating and listing events.
Falls back to demo responses if credentials are not available.
"""

import os
import logging
from datetime import datetime, timedelta, timezone as dt_timezone

logger = logging.getLogger("elora.calendar")

# Default timezone used when the user doesn't specify one
DEFAULT_TZ = os.getenv("ELORA_DEFAULT_TZ", "UTC")


def _get_calendar_service(user_id: str):
    """Get an authenticated Calendar service for a user."""
    from tools.gmail import get_user_token, set_user_token

    token_info = get_user_token(user_id)
    if not token_info:
        logger.info(f"[Calendar] No token for user={user_id}")
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
            token_info["access_token"] = creds.token
            token_info["expiry"] = creds.expiry.isoformat() if creds.expiry else None
            set_user_token(user_id, token_info)
            logger.info(f"[Calendar] Token refreshed for user={user_id}")

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return service
    except Exception as e:
        logger.error(f"[Calendar] Service error for user={user_id}: {e}")
        return None


def create_event_sync(
    user_id: str, title: str, date: str, time: str,
    duration_minutes: int = 60, timezone: str = DEFAULT_TZ
) -> dict:
    """Create a calendar event via Google Calendar API (synchronous)."""
    service = _get_calendar_service(user_id)

    if not service:
        return {
            "status": "demo",
            "report": f"[Demo mode] Event '{title}' on {date} at {time} ({duration_minutes}min, {timezone}) would be created. Visit /auth/login/{user_id} to connect Google Calendar.",
        }

    try:
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        event = {
            "summary": title,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone},
        }

        result = service.events().insert(calendarId="primary", body=event).execute()
        logger.info(f"[Calendar] Created event '{title}', id={result.get('id')}")

        return {
            "status": "success",
            "report": f"Created event '{title}' on {date} at {time} ({duration_minutes}min, {timezone}). Link: {result.get('htmlLink', 'N/A')}",
        }
    except Exception as e:
        logger.error(f"[Calendar] Create error: {e}")
        return {"status": "error", "report": f"Failed to create event: {str(e)}"}


def update_event_sync(
    user_id: str,
    event_id: str,
    title: str = None,
    date: str = None,
    time: str = None,
    duration_minutes: int = None,
    timezone: str = DEFAULT_TZ,
) -> dict:
    """Update an existing calendar event. Only provided fields are changed."""
    service = _get_calendar_service(user_id)
    if not service:
        return {"status": "demo", "report": f"[Demo mode] Would update event {event_id}. Connect Google Calendar first."}

    try:
        # Fetch the existing event
        event = service.events().get(calendarId="primary", eventId=event_id).execute()

        if title:
            event["summary"] = title

        if date or time:
            # Rebuild start/end datetimes
            existing_start = event["start"].get("dateTime", "")
            if existing_start:
                from datetime import datetime as dt
                existing_dt = dt.fromisoformat(existing_start.replace("Z", "+00:00"))
            else:
                from datetime import datetime as dt
                existing_dt = dt.now()

            new_date = date or existing_dt.strftime("%Y-%m-%d")
            new_time = time or existing_dt.strftime("%H:%M")
            new_tz = event["start"].get("timeZone", timezone)

            start_dt = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")

            if duration_minutes is None:
                # Preserve existing duration
                existing_end = event["end"].get("dateTime", "")
                if existing_end and existing_start:
                    from datetime import datetime as dt
                    s = dt.fromisoformat(existing_start.replace("Z", "+00:00"))
                    e = dt.fromisoformat(existing_end.replace("Z", "+00:00"))
                    duration_minutes = int((e - s).total_seconds() / 60)
                else:
                    duration_minutes = 60

            end_dt = start_dt + timedelta(minutes=duration_minutes)
            event["start"] = {"dateTime": start_dt.isoformat(), "timeZone": new_tz}
            event["end"] = {"dateTime": end_dt.isoformat(), "timeZone": new_tz}

        elif duration_minutes is not None:
            existing_start = event["start"].get("dateTime", "")
            if existing_start:
                from datetime import datetime as dt
                start_dt = dt.fromisoformat(existing_start.replace("Z", "+00:00"))
                end_dt = start_dt + timedelta(minutes=duration_minutes)
                event["end"] = {"dateTime": end_dt.isoformat(), "timeZone": event["start"].get("timeZone", timezone)}

        result = service.events().update(
            calendarId="primary", eventId=event_id, body=event
        ).execute()

        logger.info(f"[Calendar] Updated event id={event_id}")
        return {
            "status": "success",
            "report": f"Event updated. Link: {result.get('htmlLink', 'N/A')}",
        }
    except Exception as e:
        logger.error(f"[Calendar] Update error: {e}")
        return {"status": "error", "report": f"Failed to update event: {str(e)}"}


def delete_event_sync(user_id: str, event_id: str) -> dict:
    """Delete a calendar event permanently."""
    service = _get_calendar_service(user_id)
    if not service:
        return {"status": "demo", "report": f"[Demo mode] Would delete event {event_id}. Connect Google Calendar first."}

    try:
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        logger.info(f"[Calendar] Deleted event id={event_id}")
        return {"status": "success", "report": "Event deleted."}
    except Exception as e:
        logger.error(f"[Calendar] Delete error: {e}")
        return {"status": "error", "report": f"Failed to delete event: {str(e)}"}


def search_events_sync(user_id: str, query: str, timezone: str = DEFAULT_TZ) -> dict:
    """
    Search calendar events by title keyword across the next 30 days.
    Returns events with their IDs so they can be updated or deleted.
    """
    service = _get_calendar_service(user_id)
    if not service:
        return {"status": "demo", "report": "[Demo mode] Connect Google Calendar first.", "events": []}

    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        future = now + timedelta(days=30)

        results = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=future.isoformat(),
            q=query,
            maxResults=10,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = []
        for event in results.get("items", []):
            start = event["start"].get("dateTime", event["start"].get("date"))
            events.append({
                "id": event["id"],
                "title": event.get("summary", "No title"),
                "start": start,
                "link": event.get("htmlLink", ""),
            })

        logger.info(f"[Calendar] Search '{query}' found {len(events)} events")
        return {
            "status": "success",
            "report": f"Found {len(events)} event(s) matching '{query}'",
            "events": events,
        }
    except Exception as e:
        logger.error(f"[Calendar] Search error: {e}")
        return {"status": "error", "report": str(e), "events": []}


def list_events_sync(user_id: str, date: str = "today", timezone: str = DEFAULT_TZ) -> dict:
    """List calendar events for a given date (synchronous)."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(timezone)
    except Exception:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("UTC")

    now_local = datetime.now(tz)

    if date == "today":
        target = now_local
    elif date == "tomorrow":
        target = now_local + timedelta(days=1)
    else:
        try:
            target = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=tz)
        except ValueError:
            target = now_local

    service = _get_calendar_service(user_id)

    if not service:
        return {
            "status": "demo",
            "report": f"[Demo mode] Would list events for {target.strftime('%Y-%m-%d')} ({timezone}). Visit /auth/login/{user_id} to connect Google Calendar.",
            "events": [],
        }

    try:
        day_start = target.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = target.replace(hour=23, minute=59, second=59, microsecond=0)

        results = service.events().list(
            calendarId="primary",
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
            maxResults=10,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = []
        for event in results.get("items", []):
            start = event["start"].get("dateTime", event["start"].get("date"))
            events.append({
                "title": event.get("summary", "No title"),
                "start": start,
                "link": event.get("htmlLink", ""),
            })

        logger.info(f"[Calendar] Found {len(events)} events for {target.strftime('%Y-%m-%d')}")
        return {
            "status": "success",
            "report": f"Found {len(events)} events for {target.strftime('%Y-%m-%d')} ({timezone})",
            "events": events,
        }
    except Exception as e:
        logger.error(f"[Calendar] List error: {e}")
        return {"status": "error", "report": f"Failed to list events: {str(e)}", "events": []}
