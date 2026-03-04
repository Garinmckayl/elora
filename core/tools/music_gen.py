"""
Music generation using Lyria RealTime (lyria-realtime-exp).

Based on: https://github.com/google-gemini/cookbook/blob/main/quickstarts/Get_started_LyriaRealTime.py

Key facts:
  - Model: "models/lyria-realtime-exp"
  - API version: v1alpha
  - receive() and play() MUST run as concurrent asyncio tasks
  - Output is stereo 16-bit PCM at 48000 Hz
  - chunk.data is already raw bytes
"""

import os
import base64
import logging
import asyncio
import struct

logger = logging.getLogger("elora-tools.music_gen")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

LYRIA_MODEL = "models/lyria-realtime-exp"

# Lyria outputs stereo 48kHz 16-bit PCM (from official cookbook)
SAMPLE_RATE = 48000
CHANNELS = 2
BITS_PER_SAMPLE = 16
BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * (BITS_PER_SAMPLE // 8)

MIN_DURATION = 5
MAX_DURATION = 30


def _pcm_to_wav(pcm_data: bytes) -> bytes:
    """Convert raw PCM audio to WAV. Stereo 48kHz 16-bit."""
    data_size = len(pcm_data)
    block_align = CHANNELS * BITS_PER_SAMPLE // 8
    byte_rate = SAMPLE_RATE * block_align

    wav_header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        CHANNELS,
        SAMPLE_RATE,
        byte_rate,
        block_align,
        BITS_PER_SAMPLE,
        b"data",
        data_size,
    )
    return wav_header + pcm_data


def generate_music(prompt: str, duration_seconds: int = 15) -> dict:
    """Generate music from a text prompt using Lyria RealTime.

    Args:
        prompt: Description of the music (mood, genre, instruments, tempo).
        duration_seconds: Approximate duration in seconds (clamped 5-30).

    Returns:
        dict with audio_base64 (WAV), mime_type, duration_seconds, report.
    """
    try:
        from google import genai
        from google.genai import types

        if not GOOGLE_API_KEY:
            return {
                "status": "error",
                "report": "GOOGLE_API_KEY is not set. Cannot generate music.",
            }

        client = genai.Client(
            api_key=GOOGLE_API_KEY,
            http_options={"api_version": "v1alpha"},
        )

        duration_seconds = max(MIN_DURATION, min(MAX_DURATION, duration_seconds))
        target_bytes = duration_seconds * BYTES_PER_SECOND

        async def _generate() -> bytes | None:
            audio_chunks: list[bytes] = []
            total_bytes = 0
            done = asyncio.Event()

            async with client.aio.live.music.connect(model=LYRIA_MODEL) as session:

                # Receiver task — must be running before play()
                async def receive():
                    nonlocal total_bytes
                    async for message in session.receive():
                        if message.server_content and message.server_content.audio_chunks:
                            audio_data = message.server_content.audio_chunks[0].data
                            if audio_data:
                                audio_chunks.append(audio_data)
                                total_bytes += len(audio_data)
                                if total_bytes >= target_bytes:
                                    done.set()
                                    return
                        elif message.filtered_prompt:
                            logger.warning(f"Prompt filtered: {message.filtered_prompt}")
                            done.set()
                            return
                        await asyncio.sleep(10**-12)

                # Set prompt
                await session.set_weighted_prompts(
                    prompts=[types.WeightedPrompt(text=prompt, weight=1.0)]
                )

                # Set config
                config = types.LiveMusicGenerationConfig()
                config.bpm = 120
                await session.set_music_generation_config(config=config)

                # Start receiver BEFORE play — exactly like the cookbook
                receive_task = asyncio.create_task(receive())

                # Start playback
                await session.play()

                # Wait until enough audio collected or timeout
                try:
                    await asyncio.wait_for(done.wait(), timeout=duration_seconds + 20)
                except asyncio.TimeoutError:
                    logger.warning("Music generation timed out, using collected audio")

                # Stop and clean up
                try:
                    await session.stop()
                except Exception:
                    pass

                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass

            if not audio_chunks:
                return None
            return b"".join(audio_chunks)

        # Run async, handling existing event loops
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pcm_data = pool.submit(
                    lambda: asyncio.run(_generate())
                ).result(timeout=120)
        else:
            pcm_data = asyncio.run(_generate())

        if pcm_data is None:
            return {
                "status": "error",
                "report": (
                    "Music generation produced no audio. "
                    "Lyria RealTime may be unavailable or the prompt was filtered."
                ),
            }

        wav_data = _pcm_to_wav(pcm_data)
        actual_duration = round(len(pcm_data) / BYTES_PER_SECOND, 1)
        b64 = base64.b64encode(wav_data).decode("utf-8")

        logger.info(
            f"Music generation complete: {actual_duration}s, "
            f"{len(wav_data)} bytes WAV"
        )

        return {
            "status": "success",
            "audio_base64": b64,
            "mime_type": "audio/wav",
            "duration_seconds": actual_duration,
            "report": f"Generated {actual_duration}s music track for: {prompt[:100]}",
        }

    except Exception as e:
        logger.error(f"Music generation failed: {e}", exc_info=True)
        return {
            "status": "error",
            "report": f"Music generation failed: {str(e)[:200]}",
        }
