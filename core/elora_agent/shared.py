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


def get_user_id() -> str:
    return current_user_id.get()
