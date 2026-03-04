"""
Google Lyria 3 Music Generation Tool for Elora

Generates original music compositions using Google's Lyria 3 model
via the Gemini API. Perfect for:
- Theme songs for weekly recaps
- Background music for presentations
- Personalized melodies based on mood/events
- Soundtracks for photo montages

API Reference: https://ai.google.dev/gemini-api/docs/music-generation

Usage:
    from tools.lyria_music import generate_music
    
    result = generate_music(
        user_id="user_123",
        prompt="Upbeat electronic track with piano and strings, 120 BPM",
        duration_seconds=30,
        style="electronic"
    )
"""

import os
import logging
import base64
from datetime import datetime
from typing import Optional

logger = logging.getLogger("elora-tools.lyria")

# Gemini API client
_genai_client = None
try:
    from google import genai
    _genai_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))
    logger.info("[Lyria] Gemini client initialized")
except Exception as e:
    logger.warning(f"[Lyria] Gemini client unavailable: {e}")


# Lyria 3 model configuration
LYRIA_MODEL = "lyria-3"  # or "lyria-3-fast" for quicker generation
DEFAULT_DURATION = 30  # seconds
MAX_DURATION = 180  # 3 minutes max


def generate_music(
    user_id: str,
    prompt: str,
    duration_seconds: int = DEFAULT_DURATION,
    style: str = "ambient",
    mood: str = "neutral",
    tempo: Optional[str] = None,
    instruments: Optional[list] = None,
) -> dict:
    """
    Generate original music using Lyria 3.
    
    Args:
        user_id: User identifier for storage/retrieval
        prompt: Text description of desired music (e.g., "upbeat jazz piano")
        duration_seconds: Length of track (30-180 seconds)
        style: Music style (ambient, electronic, classical, jazz, pop, cinematic, etc.)
        mood: Emotional tone (happy, sad, energetic, calm, nostalgic, etc.)
        tempo: BPM or description (fast, medium, slow, or specific BPM like "120 BPM")
        instruments: List of instruments to feature
    
    Returns:
        dict with audio_url, base64_audio, duration, and metadata
    """
    if not _genai_client:
        return {
            "status": "error",
            "report": "Lyria music generation unavailable (Gemini API not configured)"
        }
    
    try:
        # Build detailed prompt for Lyria
        full_prompt = _build_lyria_prompt(prompt, style, mood, tempo, instruments)
        
        logger.info(f"[Lyria] Generating music for user={user_id}: {full_prompt[:100]}...")
        
        # Call Lyria 3 API via Gemini
        # Note: Lyria is accessed through the models.generate_content endpoint
        # with special parameters for audio generation
        response = _genai_client.models.generate_content(
            model=LYRIA_MODEL,
            contents=full_prompt,
            config={
                "response_modalities": ["AUDIO"],
                "audio_config": {
                    "duration_seconds": min(duration_seconds, MAX_DURATION),
                    "sample_rate": 44100,
                    "bit_depth": 16,
                }
            }
        )
        
        # Extract audio from response
        audio_data = _extract_audio_from_response(response)
        
        if not audio_data:
            return {
                "status": "error",
                "report": "Lyria generation failed - no audio data returned"
            }
        
        # Save to Cloud Storage for user
        from tools.files import save_to_gcs
        filename = f"users/{user_id}/music/lyria_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        
        # For demo: return base64 directly
        # In production: upload to GCS and return URL
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        logger.info(f"[Lyria] Music generated successfully: {len(audio_data)} bytes")
        
        return {
            "status": "success",
            "audio_base64": audio_base64,
            "audio_url": f"gs://elora-music/{filename}",  # Placeholder
            "duration_seconds": duration_seconds,
            "style": style,
            "mood": mood,
            "prompt": full_prompt,
            "model": LYRIA_MODEL,
            "report": f"Generated {duration_seconds}s {style} track: {prompt[:50]}..."
        }
        
    except Exception as e:
        logger.error(f"[Lyria] Music generation failed: {e}")
        return {
            "status": "error",
            "report": f"Music generation failed: {str(e)[:200]}"
        }


def _build_lyria_prompt(
    prompt: str,
    style: str,
    mood: str,
    tempo: Optional[str],
    instruments: Optional[list]
) -> str:
    """Build a detailed prompt for Lyria 3."""
    
    components = [prompt]
    
    if style:
        components.append(f"Style: {style}")
    
    if mood:
        components.append(f"Mood: {mood}")
    
    if tempo:
        components.append(f"Tempo: {tempo}")
    
    if instruments:
        inst_str = ", ".join(instruments)
        components.append(f"Featured instruments: {inst_str}")
    
    components.append("High quality, professional production, clear mixing")
    
    return " | ".join(components)


def _extract_audio_from_response(response) -> Optional[bytes]:
    """Extract audio bytes from Lyria response."""
    try:
        # Lyria returns audio in the response's audio field
        # Structure depends on API version
        if hasattr(response, 'audio') and response.audio:
            return response.audio
        
        # Alternative: check candidates
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                # Audio might be in content parts
                for part in candidate.content.parts:
                    if hasattr(part, 'audio') and part.audio:
                        return part.audio
        
        # Fallback: check for inline_data
        if hasattr(response, 'text') and response.text:
            # Some APIs return base64 in text field
            import base64
            try:
                return base64.b64decode(response.text)
            except:
                pass
        
        return None
        
    except Exception as e:
        logger.error(f"[Lyria] Failed to extract audio: {e}")
        return None


def create_weekly_theme(
    user_id: str,
    week_highlights: list,
    mood: str = "uplifting"
) -> dict:
    """
    Create a custom theme song for a weekly recap.
    
    Analyzes the week's highlights and generates appropriate music.
    
    Args:
        user_id: User identifier
        week_highlights: List of events/achievements from the week
        mood: Overall mood for the theme
    
    Returns:
        dict with generated music
    """
    # Analyze highlights to determine style
    style = _infer_music_style(week_highlights)
    
    prompt = f"Weekly recap theme song. A {mood} track that captures the essence of this week's journey."
    
    return generate_music(
        user_id=user_id,
        prompt=prompt,
        duration_seconds=45,
        style=style,
        mood=mood,
        tempo="medium",
        instruments=["piano", "strings", "light percussion"]
    )


def _infer_music_style(highlights: list) -> str:
    """Infer music style from week's highlights."""
    if not highlights:
        return "ambient"
    
    highlights_str = " ".join(highlights).lower()
    
    # Keyword-based style inference
    if any(w in highlights_str for w in ["work", "meeting", "project", "deadline"]):
        return "cinematic"
    elif any(w in highlights_str for w in ["party", "friend", "celebration", "fun"]):
        return "electronic"
    elif any(w in highlights_str for w in ["relax", "weekend", "calm", "peaceful"]):
        return "ambient"
    elif any(w in highlights_str for w in ["achievement", "win", "success", "accomplished"]):
        return "orchestral"
    else:
        return "ambient"


# Demo/test function
if __name__ == "__main__":
    print("Testing Lyria 3 Music Generation...")
    
    result = generate_music(
        user_id="demo_user",
        prompt="Upbeat electronic track with piano and strings",
        duration_seconds=30,
        style="electronic",
        mood="energetic"
    )
    
    print(f"Status: {result['status']}")
    print(f"Report: {result.get('report', 'N/A')}")
    if result['status'] == 'success':
        print(f"Duration: {result.get('duration_seconds')}s")
        print(f"Audio size: {len(result.get('audio_base64', ''))} chars (base64)")
