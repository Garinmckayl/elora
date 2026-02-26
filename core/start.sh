#!/bin/bash
# Start FastAPI server and optionally the LiveKit agent (if deps are installed).

# Try to start the LiveKit agent in the background (fails gracefully if deps missing)
python livekit_agent.py start &>/dev/null &

# Start the FastAPI server in the foreground (Cloud Run health checks hit this)
exec uvicorn main:app --host 0.0.0.0 --port 8080
