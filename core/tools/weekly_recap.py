"""
Weekly Recap Generator for Elora

Creates a comprehensive weekly recap with:
1. Voice narration (TTS) - Gemini TTS
2. Photo montage (Image) - Imagen 3
3. Theme song (Music) - Lyria 3

This is Elora's signature "wow" feature for demos.

Usage:
    from tools.weekly_recap import generate_weekly_recap
    
    result = generate_weekly_recap(
        user_id="user_123",
        days=7,
        include_music=True,
        include_montage=True
    )
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict

logger = logging.getLogger("elora-tools.weekly-recap")


def generate_weekly_recap(
    user_id: str,
    days: int = 7,
    include_music: bool = True,
    include_montage: bool = True,
    include_narration: bool = True,
) -> dict:
    """
    Generate a complete weekly recap with multimedia.
    
    Args:
        user_id: User identifier
        days: Number of days to include (default 7)
        include_music: Generate Lyria 3 theme song
        include_montage: Generate Imagen 3 photo montage
        include_narration: Generate Gemini TTS voice narration
    
    Returns:
        dict with all recap components
    """
    logger.info(f"[WeeklyRecap] Starting recap for user={user_id}, days={days}")
    
    # 1. Gather week's highlights from memory
    highlights = _gather_week_highlights(user_id, days)
    
    if not highlights:
        return {
            "status": "partial",
            "report": "No highlights found for this week. Try interacting more with Elora!",
            "highlights": [],
        }
    
    recap = {
        "status": "success",
        "user_id": user_id,
        "period": f"Last {days} days",
        "generated_at": datetime.now().isoformat(),
        "highlights": highlights,
        "music": None,
        "montage": None,
        "narration": None,
    }
    
    # 2. Generate theme music with Lyria 3
    if include_music:
        logger.info("[WeeklyRecap] Generating theme music with Lyria 3...")
        from tools.lyria_music import create_weekly_theme
        
        music_result = create_weekly_theme(
            user_id=user_id,
            week_highlights=highlights,
            mood="uplifting"
        )
        
        if music_result["status"] == "success":
            recap["music"] = music_result
            logger.info("[WeeklyRecap] ✓ Music generated")
        else:
            logger.warning(f"[WeeklyRecap] Music failed: {music_result.get('report')}")
    
    # 3. Generate photo montage with Imagen 3
    if include_montage:
        logger.info("[WeeklyRecap] Generating photo montage with Imagen 3...")
        from tools.imagen_images import create_photo_montage
        
        montage_result = create_photo_montage(
            user_id=user_id,
            week_highlights=highlights,
            theme="weekly recap"
        )
        
        if montage_result["status"] == "success":
            recap["montage"] = montage_result
            logger.info("[WeeklyRecap] ✓ Montage generated")
        else:
            logger.warning(f"[WeeklyRecap] Montage failed: {montage_result.get('report')}")
    
    # 4. Generate voice narration with Gemini TTS
    if include_narration:
        logger.info("[WeeklyRecap] Generating voice narration...")
        from tools.tts_narration import generate_narration
        
        narration_script = _build_narration_script(highlights)
        
        narration_result = generate_narration(
            user_id=user_id,
            script=narration_script,
            voice="elora"  # Elora's signature voice
        )
        
        if narration_result["status"] == "success":
            recap["narration"] = narration_result
            logger.info("[WeeklyRecap] ✓ Narration generated")
        else:
            logger.warning(f"[WeeklyRecap] Narration failed: {narration_result.get('report')}")
    
    # Build summary report
    components = []
    if recap["music"]:
        components.append(f"🎵 {recap['music'].get('duration_seconds', 0)}s theme song")
    if recap["montage"]:
        components.append(f"🖼️ Photo montage ({recap['montage'].get('count', 0)} images)")
    if recap["narration"]:
        components.append(f"🎙️ Voice narration ({recap['narration'].get('duration_seconds', 0)}s)")
    
    recap["report"] = (
        f"Weekly recap generated with {len(highlights)} highlights. "
        f"Components: {', '.join(components) if components else 'highlights only'}"
    )
    
    logger.info(f"[WeeklyRecap] ✓ Recap complete for user={user_id}")
    
    return recap


def _gather_week_highlights(user_id: str, days: int) -> List[dict]:
    """
    Gather highlights from the user's memory for the past N days.
    
    Sources:
    - MemU memory items
    - Calendar events
    - Conversations
    - Achievements mentioned
    """
    highlights = []
    
    try:
        # Get memories from MemU
        from tools.memory import search_memory
        
        # Search for different types of highlights
        queries = [
            "accomplishments achievements wins successes",
            "meetings events appointments",
            "fun activities hobbies entertainment",
            "learning new skills knowledge",
            "social friends family relationships"
        ]
        
        for query in queries:
            result = search_memory(user_id, query, top_k=3)
            
            if result.get("status") == "success" and result.get("memories"):
                for memory in result["memories"]:
                    highlights.append({
                        "type": "memory",
                        "description": memory,
                        "category": _categorize_highlight(memory),
                    })
        
        # Get calendar events from the past week
        try:
            from tools.calendar import list_events
            start_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            calendar_result = list_events(user_id, start_date=start_date)
            
            if calendar_result.get("status") == "success":
                for event in calendar_result.get("events", [])[:5]:
                    highlights.append({
                        "type": "calendar",
                        "description": f"Event: {event.get('summary', 'Calendar event')}",
                        "category": "work" if "meeting" in event.get("summary", "").lower() else "personal",
                        "date": event.get("start", {}).get("dateTime", ""),
                    })
        except Exception as e:
            logger.debug(f"[WeeklyRecap] Calendar fetch failed: {e}")
        
        # Deduplicate and limit
        seen = set()
        unique_highlights = []
        for h in highlights:
            key = h["description"][:50]
            if key not in seen:
                seen.add(key)
                unique_highlights.append(h)
        
        return unique_highlights[:10]  # Top 10 highlights
        
    except Exception as e:
        logger.error(f"[WeeklyRecap] Failed to gather highlights: {e}")
        return []


def _categorize_highlight(description: str) -> str:
    """Categorize a highlight based on its content."""
    desc_lower = description.lower()
    
    if any(w in desc_lower for w in ["work", "meeting", "project", "deadline"]):
        return "work"
    elif any(w in desc_lower for w in ["friend", "family", "party", "social"]):
        return "social"
    elif any(w in desc_lower for w in ["learn", "study", "course", "skill"]):
        return "learning"
    elif any(w in desc_lower for w in ["fun", "hobby", "game", "entertainment"]):
        return "entertainment"
    elif any(w in desc_lower for w in ["health", "workout", "exercise", "fitness"]):
        return "health"
    else:
        return "general"


def _build_narration_script(highlights: List[dict]) -> str:
    """Build a natural-sounding narration script from highlights."""
    
    if not highlights:
        return "This week was quiet. Next week will be even better!"
    
    # Group by category
    by_category = {}
    for h in highlights:
        cat = h.get("category", "general")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(h["description"])
    
    # Build script
    script_parts = ["Here's your weekly recap...\n\n"]
    
    for category, items in by_category.items():
        script_parts.append(f"In {category}: ")
        script_parts.append(", ".join(items[:3]))
        script_parts.append(".\n\n")
    
    script_parts.append("What a week! Looking forward to next week's adventures.")
    
    return "".join(script_parts)


# Demo endpoint for main.py
def weekly_recap_endpoint(user_id: str) -> dict:
    """
    HTTP endpoint wrapper for weekly recap generation.
    
    Returns immediately with status; client polls for completion.
    """
    try:
        # Start async generation
        import asyncio
        
        async def generate():
            return generate_weekly_recap(
                user_id=user_id,
                days=7,
                include_music=True,
                include_montage=True,
                include_narration=True
            )
        
        # For demo: run synchronously (in production, use background task)
        result = asyncio.get_event_loop().run_until_complete(generate())
        
        return result
        
    except Exception as e:
        logger.error(f"[WeeklyRecap] Endpoint failed: {e}")
        return {
            "status": "error",
            "report": f"Recap generation failed: {str(e)[:200]}"
        }


if __name__ == "__main__":
    print("Testing Weekly Recap Generator...")
    
    result = generate_weekly_recap(
        user_id="demo_user",
        days=7,
        include_music=True,
        include_montage=True,
        include_narration=True
    )
    
    print(f"\nStatus: {result['status']}")
    print(f"Report: {result.get('report', 'N/A')}")
    print(f"Highlights: {len(result.get('highlights', []))}")
    
    if result.get("music"):
        print(f"\n🎵 Music:")
        print(f"   Duration: {result['music'].get('duration_seconds')}s")
        print(f"   Style: {result['music'].get('style')}")
    
    if result.get("montage"):
        print(f"\n🖼️ Montage:")
        print(f"   Images: {result['montage'].get('count')}")
        print(f"   Size: {result['montage'].get('size')}")
    
    if result.get("narration"):
        print(f"\n🎙️ Narration:")
        print(f"   Duration: {result['narration'].get('duration_seconds')}s")
        print(f"   Voice: {result['narration'].get('voice')}")
