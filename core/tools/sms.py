"""
SMS / Messaging tool for Elora.

Primary: Twilio SMS API (if TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN + TWILIO_FROM_NUMBER set)
Fallback: Returns a deep link the frontend can open (sms: URI scheme) — the user taps send.

This lets Elora say: "I've drafted a message to Maya — tap to send" even without Twilio.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("elora.sms")

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_FROM_NUMBER", "")  # e.g. "+12025551234"


def send_sms(to_phone: str, message: str, user_id: str = "") -> dict:
    """Send a text message (SMS) to a phone number.

    Tries Twilio first. Falls back to a deep link the app can open if Twilio
    is not configured.

    IMPORTANT: Always confirm with the user before sending a message.

    Args:
        to_phone: Recipient phone number in E.164 format. e.g. "+14155552671"
                  If the user gives a local number, try to infer country code
                  from context or ask.
        message:  The message text to send (max 1600 characters).
        user_id:  Injected automatically.

    Returns:
        dict with status, message_sid (if Twilio), or deep_link (if fallback).
    """
    if not to_phone or not message:
        return {"status": "error", "error": "Missing to_phone or message"}

    # Normalise phone — strip spaces/dashes
    phone = to_phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    # Try Twilio
    if TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM:
        result = _send_via_twilio(phone, message)
    else:
        # Fallback: deep link
        import urllib.parse
        body_encoded = urllib.parse.quote(message)
        deep_link = f"sms:{phone}?body={body_encoded}"

        logger.info(f"[SMS] Twilio not configured, returning deep link for {phone}")
        result = {
            "status": "deep_link",
            "deep_link": deep_link,
            "to": phone,
            "message_preview": message[:100],
            "note": "Twilio not configured. Open this link on the device to pre-fill the SMS app.",
        }

    # Update last_contacted for the person associated with this phone number
    if result.get("status") in ("sent", "deep_link"):
        _update_last_contacted_by_phone(phone, user_id)

    return result


def _send_via_twilio(to_phone: str, message: str) -> dict:
    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        msg = client.messages.create(
            body=message,
            from_=TWILIO_FROM,
            to=to_phone,
        )
        logger.info(f"[SMS] Sent via Twilio: sid={msg.sid} to={to_phone}")
        return {
            "status": "sent",
            "message_sid": msg.sid,
            "to": to_phone,
            "message_preview": message[:100],
        }
    except ImportError:
        return {
            "status": "error",
            "error": "twilio package not installed. Add 'twilio' to requirements.txt.",
        }
    except Exception as e:
        logger.error(f"[SMS] Twilio error: {e}")
        return {"status": "error", "error": str(e)}


def lookup_phone_for_person(name_or_relationship: str, user_id: str = "") -> dict:
    """Look up the phone number for a known person by name or relationship.

    Use this before send_sms when the user says 'text my girlfriend' or 'send Maya a message'
    to find their phone number first.

    Args:
        name_or_relationship: Name or relationship string. e.g. "Maya", "my girlfriend", "mom"
        user_id:              Injected automatically.

    Returns:
        dict: {"status": "found", "phone": str, "name": str} or {"status": "not_found"}
    """
    from tools.people import recall_person
    from elora_agent.shared import get_user_id
    uid = user_id or get_user_id()

    result = recall_person(name_or_relationship, user_id=uid)
    if result.get("status") == "found":
        person = result["person"]
        phone = person.get("phone", "")
        email = person.get("email", "")
        if phone:
            return {"status": "found", "phone": phone, "name": person["name"],
                    "relationship": person["relationship"]}
        elif email:
            return {"status": "found_email_only", "email": email, "name": person["name"],
                    "relationship": person["relationship"],
                    "note": f"I have {person['name']}'s email but not their phone number."}
        else:
            return {"status": "no_contact", "name": person["name"],
                    "note": f"I know {person['name']} but don't have their phone number yet. Ask the user for it."}
    return {"status": "not_found", "query": name_or_relationship}


# ── Last-contacted tracking ──────────────────────────────────────────────────

def _update_last_contacted_by_phone(phone: str, user_id: str) -> None:
    """After sending SMS, update the person's last_contacted / last_texted timestamp."""
    try:
        from elora_agent.shared import get_user_id
        uid = user_id or get_user_id()
        from tools.people import _get_all_people, _people_col
        from datetime import datetime, timezone

        people = _get_all_people(uid)
        now_iso = datetime.now(timezone.utc).isoformat()
        phone_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

        for person in people:
            p_phone = (person.get("contact_phone", "") or "").replace(" ", "").replace("-", "")
            if p_phone and p_phone == phone_clean:
                col = _people_col(uid)
                if col:
                    col.document(person["id"]).update({
                        "last_texted": now_iso,
                        "last_contacted": now_iso,
                        "updated_at": now_iso,
                    })
                    logger.info(f"[SMS] Updated last_contacted for '{person.get('name')}' user={uid}")
                break
    except Exception as e:
        logger.debug(f"[SMS] last_contacted update error: {e}")
