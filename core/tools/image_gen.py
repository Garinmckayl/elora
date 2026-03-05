"""
Image generation using Nano Banana 2 (gemini-3.1-flash-image-preview).

Generates images from text prompts with configurable aspect ratio and resolution.
"""

import os
import base64
import logging

logger = logging.getLogger("elora-tools.image_gen")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Supported aspect ratios for Nano Banana 2
SUPPORTED_ASPECT_RATIOS = {
    "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9",
}

# Default image resolution
DEFAULT_IMAGE_SIZE = "1K"


def generate_image(prompt: str, aspect_ratio: str = "1:1") -> dict:
    """Generate an image from a text prompt using Nano Banana 2.

    Uses the gemini-3.1-flash-image-preview model with IMAGE-only output
    modality for high-quality image generation.

    Args:
        prompt: Detailed description of the image to generate.
        aspect_ratio: Aspect ratio string (e.g. '1:1', '16:9', '9:16', '3:2').
            Defaults to '1:1'. Unsupported values fall back to '1:1'.

    Returns:
        dict with keys:
            - status: 'success' or 'error'
            - image_base64: base64-encoded image data (on success)
            - mime_type: MIME type of the image (on success)
            - report: human-readable summary
    """
    try:
        from google import genai
        from google.genai import types

        if not GOOGLE_API_KEY:
            return {
                "status": "error",
                "report": "GOOGLE_API_KEY is not set. Cannot generate images.",
            }

        # Validate and normalize aspect ratio
        if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
            logger.warning(
                f"Unsupported aspect ratio '{aspect_ratio}', falling back to '1:1'. "
                f"Supported: {SUPPORTED_ASPECT_RATIOS}"
            )
            aspect_ratio = "1:1"

        client = genai.Client(api_key=GOOGLE_API_KEY)

        # Generate image using Nano Banana 2
        response = client.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=DEFAULT_IMAGE_SIZE,
                ),
            ),
        )

        # Extract image data from the response
        if not response.candidates:
            return {
                "status": "error",
                "report": "Image generation returned no candidates.",
            }

        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_bytes = part.inline_data.data
                mime_type = part.inline_data.mime_type or "image/png"
                b64 = base64.b64encode(image_bytes).decode("utf-8")

                logger.info(
                    f"Image generated: {len(image_bytes)} bytes, "
                    f"mime={mime_type}, ratio={aspect_ratio}"
                )

                return {
                    "status": "success",
                    "image_base64": b64,
                    "mime_type": mime_type,
                    "report": (
                        f"Image generated successfully ({aspect_ratio}, "
                        f"{DEFAULT_IMAGE_SIZE}) for: {prompt[:100]}"
                    ),
                }

        return {
            "status": "error",
            "report": "Image generation response contained no image data.",
        }

    except Exception as e:
        logger.error(f"Image generation failed: {e}", exc_info=True)
        return {
            "status": "error",
            "report": f"Image generation failed: {str(e)[:200]}",
        }
