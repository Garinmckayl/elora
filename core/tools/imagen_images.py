"""
Google Imagen 3 Image Generation Tool for Elora

Generates images and photo montages using Google's Imagen 3 model
via the Gemini API. Perfect for:
- Weekly recap photo montages
- Highlight collages from memories
- Visual summaries of events
- Personalized artwork

API Reference: https://ai.google.dev/gemini-api/docs/image-generation
Model: imagen-3.0-generate-001 or imagen-4.0-generate-001

Usage:
    from tools.imagen_images import generate_image
    
    result = generate_image(
        user_id="user_123",
        prompt="Beautiful sunset over mountains, photorealistic",
        style="photographic"
    )
"""

import os
import logging
import base64
from datetime import datetime
from typing import Optional, List

logger = logging.getLogger("elora-tools.imagen")

# Gemini API client
_genai_client = None
try:
    from google import genai
    _genai_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))
    logger.info("[Imagen] Gemini client initialized")
except Exception as e:
    logger.warning(f"[Imagen] Gemini client unavailable: {e}")


# Imagen model configuration
IMAGEN_MODEL = "imagen-3.0-generate-001"
DEFAULT_SIZE = "1024x1024"
SUPPORTED_SIZES = ["1024x1024", "1024x768", "768x1024", "1536x1024", "1024x1536"]


def generate_image(
    user_id: str,
    prompt: str,
    size: str = DEFAULT_SIZE,
    style: str = "photographic",
    negative_prompt: Optional[str] = None,
    num_images: int = 1,
) -> dict:
    """
    Generate images using Imagen 3.
    
    Args:
        user_id: User identifier for storage
        prompt: Text description of desired image
        size: Image dimensions (1024x1024, 1024x768, etc.)
        style: Image style (photographic, digital-art, painting, cinematic, etc.)
        negative_prompt: What to avoid in the image
        num_images: Number of variations to generate (1-4)
    
    Returns:
        dict with image URLs/base64 and metadata
    """
    if not _genai_client:
        return {
            "status": "error",
            "report": "Imagen image generation unavailable (Gemini API not configured)"
        }
    
    try:
        logger.info(f"[Imagen] Generating image for user={user_id}: {prompt[:100]}...")
        
        # Build generation config
        config = {
            "response_modalities": ["IMAGE"],
            "image_config": {
                "size": size,
                "num_images": min(num_images, 4),
            }
        }
        
        # Add style guidance to prompt
        full_prompt = f"{prompt}. Style: {style}. High quality, professional."
        
        if negative_prompt:
            full_prompt += f" Avoid: {negative_prompt}"
        
        # Call Imagen API
        response = _genai_client.models.generate_content(
            model=IMAGEN_MODEL,
            contents=full_prompt,
            config=config
        )
        
        # Extract images from response
        images = _extract_images_from_response(response)
        
        if not images:
            return {
                "status": "error",
                "report": "Imagen generation failed - no image data returned"
            }
        
        # Convert to base64 for client
        image_base64_list = [base64.b64encode(img).decode('utf-8') for img in images]
        
        logger.info(f"[Imagen] Generated {len(images)} image(s) successfully")
        
        return {
            "status": "success",
            "images_base64": image_base64_list,
            "count": len(images),
            "size": size,
            "style": style,
            "prompt": full_prompt,
            "model": IMAGEN_MODEL,
            "report": f"Generated {len(images)} image(s): {prompt[:50]}..."
        }
        
    except Exception as e:
        logger.error(f"[Imagen] Image generation failed: {e}")
        return {
            "status": "error",
            "report": f"Image generation failed: {str(e)[:200]}"
        }


def create_photo_montage(
    user_id: str,
    week_highlights: List[dict],
    theme: str = "weekly recap"
) -> dict:
    """
    Create a photo montage from the week's highlights.
    
    Generates a collage-style image representing key moments.
    
    Args:
        user_id: User identifier
        week_highlights: List of highlight dicts with descriptions
        theme: Overall theme for the montage
    
    Returns:
        dict with generated montage image
    """
    if not week_highlights:
        return {
            "status": "error",
            "report": "No highlights provided for montage"
        }
    
    # Build prompt from highlights
    highlight_descriptions = [h.get("description", "") for h in week_highlights[:5]]
    
    prompt = f"""
    Create a beautiful photo montage collage representing {theme}.
    Include visual elements representing: {", ".join(highlight_descriptions)}.
    
    Style: Modern, vibrant, professional photo collage with smooth transitions.
    Layout: Multiple panels blending together harmoniously.
    Mood: Celebratory and nostalgic.
    """
    
    return generate_image(
        user_id=user_id,
        prompt=prompt,
        size="1536x1024",  # Landscape for montage
        style="photographic",
        num_images=1
    )


def create_highlight_image(
    user_id: str,
    highlight: dict,
    style: str = "cinematic"
) -> dict:
    """
    Create an artistic representation of a single highlight.
    
    Args:
        user_id: User identifier
        highlight: Highlight dict with description, type, etc.
        style: Visual style
    
    Returns:
        dict with generated image
    """
    description = highlight.get("description", "Special moment")
    highlight_type = highlight.get("type", "memory")
    
    prompt = f"""
    Artistic representation of: {description}.
    Type: {highlight_type}.
    
    Style: {style}, high quality, emotionally evocative.
    """
    
    return generate_image(
        user_id=user_id,
        prompt=prompt,
        size="1024x1024",
        style=style
    )


def _extract_images_from_response(response) -> List[bytes]:
    """Extract image bytes from Imagen response."""
    images = []
    
    try:
        # Imagen returns images in the response
        if hasattr(response, 'images') and response.images:
            for img in response.images:
                if hasattr(img, 'image_bytes') and img.image_bytes:
                    images.append(img.image_bytes)
                elif isinstance(img, bytes):
                    images.append(img)
        
        # Alternative: check candidates
        if not images and hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                for part in candidate.content.parts:
                    if hasattr(part, 'image') and part.image:
                        if hasattr(part.image, 'image_bytes'):
                            images.append(part.image.image_bytes)
                        elif isinstance(part.image, bytes):
                            images.append(part.image)
        
        # Fallback: check for inline_data with MIME type
        if not images and hasattr(response, 'text'):
            # Some APIs return base64 in text field
            import re
            base64_matches = re.findall(r'data:image/png;base64,([A-Za-z0-9+/=]+)', response.text)
            for b64 in base64_matches:
                try:
                    images.append(base64.b64decode(b64))
                except:
                    pass
        
        return images
        
    except Exception as e:
        logger.error(f"[Imagen] Failed to extract images: {e}")
        return []


# Demo/test function
if __name__ == "__main__":
    print("Testing Imagen 3 Image Generation...")
    
    result = generate_image(
        user_id="demo_user",
        prompt="Beautiful sunset over mountains, photorealistic",
        size="1024x1024",
        style="photographic"
    )
    
    print(f"Status: {result['status']}")
    print(f"Report: {result.get('report', 'N/A')}")
    if result['status'] == 'success':
        print(f"Images generated: {result.get('count')}")
        print(f"Image size: {result.get('size')}")
        if result.get('images_base64'):
            print(f"First image: {len(result['images_base64'][0])} chars (base64)")
