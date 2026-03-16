"""
Shared constants and context vars for Elora agent.
This module has NO heavy dependencies (no google-adk, no livekit-agents).
Both the ADK agent (elora_agent/agent.py) and the LiveKit agent (livekit_agent.py)
import from here.
"""

import threading
from contextvars import ContextVar

# Per-request user ID context var
current_user_id: ContextVar[str] = ContextVar("current_user_id", default="anonymous")

# Async callback for streaming browser screenshots
current_browser_callback: ContextVar = ContextVar("current_browser_callback", default=None)

# Side-channel for large binary payloads (audio_base64, image_base64).
# Tool wrapper functions stash binary data here so it never enters the ADK
# session history (which would blow up Gemini's context window on next turn).
# The WebSocket handler retrieves and forwards the data to the client.
#
# NOTE: We use a thread-safe global dict instead of ContextVar because ADK
# may run tool functions in a thread pool, which creates a new context copy.
# The ContextVar approach silently loses stashed data across context boundaries.
_binary_lock = threading.Lock()
_binary_payloads: dict[str, list] = {}  # user_id -> [payloads]


def stash_binary_payload(payload: dict) -> None:
    """Stash a binary payload for the WebSocket handler to pick up."""
    uid = current_user_id.get()
    with _binary_lock:
        if uid not in _binary_payloads:
            _binary_payloads[uid] = []
        _binary_payloads[uid].append(payload)


def drain_binary_payloads() -> list:
    """Retrieve and clear all pending binary payloads."""
    uid = current_user_id.get()
    with _binary_lock:
        bucket = _binary_payloads.pop(uid, [])
    return bucket


def get_user_id() -> str:
    return current_user_id.get()
