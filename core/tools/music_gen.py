"""
Music generation using Gemini Native Audio (Live API).
Generates vocal/hummed melodies from text prompts describing mood and style.
Falls back gracefully if the live audio API is unavailable.
"""

import os
import base64
import logging
import asyncio
import struct

logger = logging.getLogger("elora-tools.music_gen")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")


def generate_music(
    prompt: str,
    duration_seconds: int = 15,
) -> dict:
    """Generate music/audio from a text prompt using Gemini Native Audio.

    Args:
        prompt: Description of the music (mood, genre, instruments, tempo).
        duration_seconds: Approximate duration (10-30 seconds).

    Returns:
        dict with status, base64 audio data, and mime type.
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GOOGLE_API_KEY)
        duration_seconds = max(10, min(30, duration_seconds))

        async def _generate():
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
            )
            async with client.aio.live.connect(
                model="gemini-2.5-flash-native-audio-preview-12-2025",
                config=config,
            ) as session:
                await session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text=(
                            f"Generate a {duration_seconds}-second musical piece: {prompt}. "
                            f"Hum, sing, or vocalize the melody. No spoken words, just music/melody. "
                            f"Make it expressive and emotional."
                        ))],
                    )
                )

                audio_chunks = []
                # PCM at 24000Hz, 16-bit mono = 48000 bytes/sec
                target_bytes = duration_seconds * 48000

                async for msg in session.receive():
                    if msg.server_content and msg.server_content.model_turn:
                        for part in msg.server_content.model_turn.parts:
                            if part.inline_data:
                                audio_chunks.append(part.inline_data.data)
                    if msg.server_content and msg.server_content.turn_complete:
                        break
                    total = sum(len(c) for c in audio_chunks)
                    if total >= target_bytes:
                        break

                if not audio_chunks:
                    return None

                # Combine PCM chunks into WAV
                pcm_data = b"".join(audio_chunks)
                sample_rate = 24000
                channels = 1
                bits_per_sample = 16
                data_size = len(pcm_data)
                wav_header = struct.pack(
                    "<4sI4s4sIHHIIHH4sI",
                    b"RIFF",
                    36 + data_size,
                    b"WAVE",
                    b"fmt ",
                    16,
                    1,  # PCM format
                    channels,
                    sample_rate,
                    sample_rate * channels * bits_per_sample // 8,
                    channels * bits_per_sample // 8,
                    bits_per_sample,
                    b"data",
                    data_size,
                )
                return wav_header + pcm_data

        # Run the async generation
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                wav_data = pool.submit(lambda: asyncio.run(_generate())).result(timeout=90)
        else:
            wav_data = asyncio.run(_generate())

        if wav_data is None:
            return {
                "status": "error",
                "report": "Music generation produced no audio output.",
            }

        b64 = base64.b64encode(wav_data).decode("utf-8")
        actual_duration = (len(wav_data) - 44) / (24000 * 2)  # minus header, 24kHz 16-bit mono

        return {
            "status": "success",
            "audio_base64": b64,
            "mime_type": "audio/wav",
            "duration_seconds": round(actual_duration, 1),
            "report": f"Generated {round(actual_duration, 1)}s audio track: {prompt[:100]}",
        }

    except Exception as e:
        logger.error(f"Music generation failed: {e}")
        return {
            "status": "error",
            "report": f"Music generation failed: {str(e)[:200]}",
        }
