"""
Gemini TTS Voice Narration Tool for Elora

Generates natural-sounding voice narration using Gemini's TTS capabilities.
Perfect for:
- Weekly recap voiceovers
- Audio messages
- Narrated presentations
- Personalized voice responses

Usage:
    from tools.tts_narration import generate_narration
    
    result = generate_narration(
        user_id="user_123",
        script="Welcome to your weekly recap...",
        voice="elora"
    )
"""

import os
import logging
import base64
from datetime import datetime
from typing import Optional

logger = logging.getLogger("elora-tools.tts")

# Gemini API client
_genai_client = None
try:
    from google import genai
    _genai_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))
    logger.info("[TTS] Gemini client initialized")
except Exception as e:
    logger.warning(f"[TTS] Gemini client unavailable: {e}")


# Voice configurations
VOICES = {
    "elora": {
        "name": "Elora",
        "description": "Warm, friendly, personal assistant voice",
        "gender": "female",
        "style": "conversational"
    },
    "professional": {
        "name": "Professional",
        "description": "Clear, authoritative business voice",
        "gender": "male",
        "style": "formal"
    },
    "narrator": {
        "name": "Narrator",
        "description": "Documentary-style storytelling voice",
        "gender": "male",
        "style": "narrative"
    },
    "friendly": {
        "name": "Friendly",
        "description": "Casual, upbeat conversational voice",
        "gender": "female",
        "style": "casual"
    }
}

DEFAULT_VOICE = "elora"
DEFAULT_SAMPLE_RATE = 24000


def generate_narration(
    user_id: str,
    script: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    pitch: float = 1.0,
) -> dict:
    """
    Generate voice narration from text script.
    
    Args:
        user_id: User identifier for storage
        script: Text to convert to speech
        voice: Voice profile name (elora, professional, narrator, friendly)
        speed: Speech speed multiplier (0.5-2.0)
        pitch: Pitch multiplier (0.5-2.0)
    
    Returns:
        dict with audio data and metadata
    """
    if not _genai_client:
        return {
            "status": "error",
            "report": "TTS narration unavailable (Gemini API not configured)"
        }
    
    try:
        voice_config = VOICES.get(voice, VOICES[DEFAULT_VOICE])
        
        logger.info(f"[TTS] Generating narration for user={user_id}, voice={voice}")
        
        # Call Gemini TTS API
        # Note: Using generate_content with AUDIO response modality
        response = _genai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Read this aloud in a {voice_config['style']} tone: {script}",
            config={
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voice": voice_config["name"],
                    "speed": max(0.5, min(2.0, speed)),
                    "pitch": max(0.5, min(2.0, pitch)),
                }
            }
        )
        
        # Extract audio from response
        audio_data = _extract_audio_from_response(response)
        
        if not audio_data:
            return {
                "status": "error",
                "report": "TTS generation failed - no audio data returned"
            }
        
        # Convert to base64
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        # Calculate duration (approximate: 24kHz, 16-bit mono)
        duration_seconds = len(audio_data) / (DEFAULT_SAMPLE_RATE * 2)
        
        logger.info(f"[TTS] Narration generated: {duration_seconds:.1f}s")
        
        return {
            "status": "success",
            "audio_base64": audio_base64,
            "duration_seconds": round(duration_seconds, 1),
            "voice": voice,
            "voice_name": voice_config["name"],
            "script_length": len(script),
            "report": f"Generated {duration_seconds:.1f}s narration with {voice_config['name']} voice"
        }
        
    except Exception as e:
        logger.error(f"[TTS] Narration generation failed: {e}")
        return {
            "status": "error",
            "report": f"Narration generation failed: {str(e)[:200]}"
        }


def _extract_audio_from_response(response) -> Optional[bytes]:
    """Extract audio bytes from TTS response."""
    try:
        # Check for audio in response
        if hasattr(response, 'audio') and response.audio:
            return response.audio
        
        # Check candidates
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                for part in candidate.content.parts:
                    if hasattr(part, 'audio') and part.audio:
                        return part.audio
        
        # Check for inline_data
        if hasattr(response, 'text'):
            import re
            base64_matches = re.findall(r'data:audio/wav;base64,([A-Za-z0-9+/=]+)', response.text)
            if base64_matches:
                return base64.b64decode(base64_matches[0])
        
        return None
        
    except Exception as e:
        logger.error(f"[TTS] Failed to extract audio: {e}")
        return None


def list_voices() -> dict:
    """List available voice profiles."""
    return {
        "status": "success",
        "voices": [
            {
                "id": voice_id,
                "name": config["name"],
                "description": config["description"],
                "gender": config["gender"],
                "style": config["style"]
            }
            for voice_id, config in VOICES.items()
        ]
    }


if __name__ == "__main__":
    print("Testing TTS Narration...")
    
    result = generate_narration(
        user_id="demo_user",
        script="Welcome to your weekly recap. This week was amazing!",
        voice="elora"
    )
    
    print(f"Status: {result['status']}")
    print(f"Report: {result.get('report', 'N/A')}")
    if result['status'] == 'success':
        print(f"Duration: {result.get('duration_seconds')}s")
        print(f"Voice: {result.get('voice_name')}")
        print(f"Audio size: {len(result.get('audio_base64', ''))} chars (base64)")
    
    print("\nAvailable voices:")
    voices = list_voices()
    for v in voices.get("voices", []):
        print(f"  - {v['name']}: {v['description']}")
