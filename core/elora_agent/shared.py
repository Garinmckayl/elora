"""
Shared constants and context vars for Elora agent.
This module has NO heavy dependencies (no google-adk, no livekit-agents).
Both the ADK agent (elora_agent/agent.py) and the LiveKit agent (livekit_agent.py)
import from here.
"""

from contextvars import ContextVar

# Per-request user ID context var
current_user_id: ContextVar[str] = ContextVar("current_user_id", default="anonymous")

# Async callback for streaming browser screenshots
current_browser_callback: ContextVar = ContextVar("current_browser_callback", default=None)

# Side-channel for large binary payloads (audio_base64, image_base64).
# Tool wrapper functions stash binary data here so it never enters the ADK
# session history (which would blow up Gemini's context window on next turn).
# The WebSocket handler retrieves and forwards the data to the client.
pending_binary_payloads: ContextVar[list] = ContextVar("pending_binary_payloads", default=None)


def stash_binary_payload(payload: dict) -> None:
    """Stash a binary payload for the WebSocket handler to pick up."""
    bucket = pending_binary_payloads.get()
    if bucket is None:
        bucket = []
        pending_binary_payloads.set(bucket)
    bucket.append(payload)


def drain_binary_payloads() -> list:
    """Retrieve and clear all pending binary payloads."""
    bucket = pending_binary_payloads.get()
    if bucket:
        pending_binary_payloads.set([])
        return bucket
    return []


def get_user_id() -> str:
    return current_user_id.get()
