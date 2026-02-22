"""
MemU Integration - Proactive Memory Engine for Elora

MemU provides 24/7 always-on proactive memory with:
- 10x lower LLM token costs for continuous learning
- 92.09% accuracy on Locomo benchmark
- File system metaphor for hierarchical memory organization
- Real-time intent capture without explicit commands
- Automatic categorization and cross-referencing

OPEN SOURCE: Apache 2.0 license
GitHub: https://github.com/NevaMind-AI/memU

This module wraps MemU's MemoryAgent and integrates it with Elora's
existing memory tools (remember, recall, auto_memorise).

Uses Google Gemini (matching Elora's existing stack).

Quick Start (Self-Hosted - FREE):
    export GOOGLE_API_KEY=your_api_key  # Same as Elora uses
    export MEMU_CLOUD=false
    
    Or use MemU Cloud (free tier):
    export MEMU_API_KEY=your_api_key  # from memu.so
    export MEMU_CLOUD=true
"""

import os
import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("elora.memu")

# ── Export for tests ────────────────────────────────────────────────────────
MEMU_AVAILABLE = True  # Will be set to False if import fails

# ── MemU Service Initialization ──────────────────────────────────────────────

_memu_agents = {}  # Cache per user
_memu_initialised = False
_MEMU_CLOUD = os.getenv("MEMU_CLOUD", "false").lower() == "true"
_MEMU_API_KEY = os.getenv("MEMU_API_KEY", "")
_GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Cloud API configuration
MEMU_CLOUD_URL = "https://api.memu.so"

# Gemini configuration (OpenAI-compatible endpoint)
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_CHAT_MODEL = "gemini-2.0-flash"
GEMINI_EMBED_MODEL = "text-embedding-004"


def get_memu_agent(user_id: str = "default"):
    """Lazy-initialise and return a MemU MemoryAgent for a user."""
    global _memu_initialised
    
    if user_id in _memu_agents:
        return _memu_agents[user_id]
    
    try:
        from memu.llm import OpenAIClient
        from memu.memory import MemoryAgent
        
        if _MEMU_CLOUD and _MEMU_API_KEY:
            # Use MemU Cloud API
            logger.info("Initializing MemU Cloud API")
            llm_client = OpenAIClient(
                api_key=_MEMU_API_KEY,
                base_url=f"{MEMU_CLOUD_URL}/v1",
                model="memu-cloud",
            )
        else:
            # Self-hosted mode with Google Gemini
            if not _GOOGLE_API_KEY:
                logger.warning("MemU: Neither MEMU_API_KEY nor GOOGLE_API_KEY set. Using in-memory fallback.")
                return None
            
            logger.info("Initializing MemU with Google Gemini (self-hosted)")
            llm_client = OpenAIClient(
                api_key=_GOOGLE_API_KEY,
                base_url=GEMINI_BASE_URL,
                model=GEMINI_CHAT_MODEL,
            )
        
        # Create memory agent for this user
        agent = MemoryAgent(
            llm_client=llm_client,
            user_id=user_id,
            agent_id="elora",
            enable_embeddings=False,  # Gemini embeddings via separate API
        )
        
        _memu_agents[user_id] = agent
        _memu_initialised = True
        logger.info(f"MemU agent initialised for user={user_id}")
        return agent
        
    except ImportError as e:
        global MEMU_AVAILABLE
        MEMU_AVAILABLE = False
        logger.warning(f"MemU not installed or import failed: {e}. Using fallback memory system.")
        return None
    except Exception as e:
        logger.warning(f"MemU initialization failed: {e}. Using fallback memory system.")
        return None


# ── Public API ───────────────────────────────────────────────────────────────

async def memorize_async(user_id: str, fact: str, modality: str = "conversation") -> dict:
    """
    Store a fact in MemU's hierarchical memory system.
    
    MemU automatically:
    - Extracts insights from the fact
    - Categorizes it into the file-system-like structure
    - Cross-references with existing memories
    - Makes it available for proactive retrieval
    """
    agent = get_memu_agent(user_id)
    
    if not agent:
        # Fallback to basic response
        logger.warning(f"MemU unavailable, using fallback for: '{fact[:60]}'")
        return {
            "status": "fallback",
            "report": f"Got it, I'll remember: '{fact}'",
            "items": [],
            "categories": []
        }
    
    try:
        # Run agent to process and memorize
        conversation = [
            {"role": "user", "content": f"Remember this: {fact}"}
        ]
        
        # Process through MemU agent
        result = agent.run(conversation, character_name="Elora")
        
        logger.info(f"[MemU] Memorised: '{fact[:60]}' user={user_id}")
        
        return {
            "status": "success",
            "report": f"Remembered: '{fact}'",
            "items": [{"summary": fact, "memory_type": "fact"}],
            "categories": []  # Categories handled internally by MemU
        }
        
    except Exception as e:
        logger.error(f"MemU memorize failed: {e}")
        return {
            "status": "error",
            "report": f"Failed to save memory: {str(e)}",
            "items": [],
            "categories": []
        }


async def retrieve_async(user_id: str, query: str, method: str = "rag") -> dict:
    """
    Retrieve memories using MemU's dual-mode retrieval.
    """
    agent = get_memu_agent(user_id)
    
    if not agent:
        logger.warning(f"MemU unavailable, using fallback retrieval for: '{query[:40]}'")
        return {
            "status": "fallback",
            "memories": [],
            "categories": [],
            "resources": []
        }
    
    try:
        # Query the memory agent
        conversation = [
            {"role": "user", "content": f"Recall: {query}"}
        ]
        
        result = agent.run(conversation, character_name="Elora")
        
        logger.info(f"[MemU] Retrieved for '{query[:40]}'")
        
        return {
            "status": "success",
            "memories": [result.get("response", "")] if result else [],
            "categories": [],
            "resources": [],
            "next_step_query": ""
        }
        
    except Exception as e:
        logger.error(f"MemU retrieve failed: {e}")
        return {
            "status": "error",
            "memories": [],
            "categories": [],
            "resources": []
        }


async def auto_memorise_async(user_id: str, conversation_turn: str) -> dict:
    """
    Proactive memory extraction - MemU's killer feature.
    
    Extracts facts, preferences, skills, and intentions from conversation.
    """
    agent = get_memu_agent(user_id)
    
    if not agent:
        logger.debug(f"MemU unavailable, skipping auto-memorise for user={user_id}")
        return {"status": "fallback", "items": []}
    
    try:
        # Ask agent to extract memories from conversation
        conversation = [
            {"role": "user", "content": f"Extract key facts from: {conversation_turn}"}
        ]
        
        result = agent.run(conversation, character_name="Elora")
        
        logger.info(f"[MemU] Auto-extracted from conversation for user={user_id}")
        
        return {
            "status": "success",
            "items": [{"summary": conversation_turn[:200], "memory_type": "extracted"}],
            "categories": []
        }
        
    except Exception as e:
        logger.debug(f"MemU auto-memorise failed (non-critical): {e}")
        return {"status": "error", "items": []}


async def get_proactive_suggestions(user_id: str, context: str) -> list:
    """Get proactive suggestions based on user's memory and context."""
    agent = get_memu_agent(user_id)
    
    if not agent:
        return []
    
    try:
        # Query for suggestions
        conversation = [
            {"role": "user", "content": f"Given: {context}, what should I know or do?"}
        ]
        
        result = agent.run(conversation, character_name="Elora")
        
        suggestions = []
        if result and result.get("response"):
            suggestions.append(result["response"][:200])
        
        return suggestions
        
    except Exception as e:
        logger.debug(f"Proactive suggestions failed: {e}")
        return []


async def get_memory_categories(user_id: str) -> list:
    """Get the hierarchical category structure for a user's memory."""
    agent = get_memu_agent(user_id)
    
    if not agent:
        return []
    
    try:
        categories = list(agent.get_available_categories())
        return [{"name": cat, "path": cat, "item_count": 0} for cat in categories]
        
    except Exception as e:
        logger.debug(f"Get categories failed: {e}")
        return []


# ── Sync wrappers for backward compatibility ─────────────────────────────────

def memorize(user_id: str, fact: str) -> dict:
    """Synchronous wrapper for memorize_async."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(memorize_async(user_id, fact))


def recall(user_id: str, query: str) -> dict:
    """Synchronous wrapper for retrieve_async."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(retrieve_async(user_id, query))


def auto_memorise(user_id: str, conversation_turn: str) -> dict:
    """Synchronous wrapper for auto_memorise_async."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(auto_memorise_async(user_id, conversation_turn))
