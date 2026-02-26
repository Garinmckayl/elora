"""
Image generation using Gemini and Imagen models.
Supports both gemini-2.0-flash-exp-image-generation and imagen-4.0.
"""

import os
import base64
import logging

logger = logging.getLogger("elora-tools.image_gen")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")


def generate_image(prompt: str, aspect_ratio: str = "1:1") -> dict:
    """Generate an image from a text prompt.

    Args:
        prompt: Detailed description of the image to generate.
        aspect_ratio: Aspect ratio like '1:1', '16:9', '9:16'.

    Returns:
        dict with status, base64 image data, and mime type.
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GOOGLE_API_KEY)

        # Primary: use gemini-2.0-flash-exp-image-generation (multimodal output)
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash-exp-image-generation",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    image_data = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/png"
                    b64 = base64.b64encode(image_data).decode("utf-8")
                    return {
                        "status": "success",
                        "image_base64": b64,
                        "mime_type": mime_type,
                        "report": f"Image generated successfully for: {prompt[:100]}",
                    }
        except Exception as e:
            logger.warning(f"Gemini image gen failed, trying Imagen: {e}")

        # Fallback: use Imagen 4.0
        try:
            result = client.models.generate_images(
                model="imagen-4.0-generate-001",
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio=aspect_ratio,
                ),
            )

            if result.generated_images:
                img = result.generated_images[0]
                b64 = base64.b64encode(img.image.image_bytes).decode("utf-8")
                return {
                    "status": "success",
                    "image_base64": b64,
                    "mime_type": "image/png",
                    "report": f"Image generated successfully for: {prompt[:100]}",
                }
        except Exception as e2:
            logger.warning(f"Imagen 4.0 also failed: {e2}")

        return {
            "status": "error",
            "report": "Image generation failed with all available models.",
        }

    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return {
            "status": "error",
            "report": f"Image generation failed: {str(e)[:200]}",
        }
