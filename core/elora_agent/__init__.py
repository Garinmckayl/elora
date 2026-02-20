# Lazy imports -- avoid triggering heavy ADK loads at package import time.
# The main Cloud Run server explicitly imports elora_agent.agent when needed.
# The LiveKit agent only imports elora_agent.shared.
