"""
src/tools/analyze_image.py · Scale image → call vision model → return text.
Reads an image from an absolute path, scales to max long side (configurable),
sends to the configured vision model with a detailed request, and returns
the model's text response. Depends on: PIL, httpx, settings.vision_model.
"""

import base64
import io
import logging
from pathlib import Path

import httpx
from PIL import Image

log = logging.getLogger("simplex.tools.analyze_image")


def get_visibility() -> dict:
    return {"main_agent": True}


def get_description() -> dict:
    return {
        "description": (
            "Analyze a scanned document, image, or photo using a vision AI model. "
            "Use this when tesseract/pytesseract OCR fails or produces poor results — "
            "handles complex layouts, tables, handwriting, poor-quality scans, and "
            "non-standard fonts. Fall back to this after one failed OCR attempt. "
            "Scale to max 2000px, encode as base64, send to vision model. "
            "Returns descriptive text response."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": (
                        "Absolute path to the image file. "
                        "Must be a valid image path accessible on the filesystem."
                    ),
                },
                "request": {
                    "type": "string",
                    "description": (
                        "Detailed analysis request. Specify what to look for and "
                        "how the description will be used — this helps the vision "
                        "model provide more relevant details."
                    ),
                },
            },
            "required": ["image_path", "request"],
        },
    }


async def execute(image_path: str, request: str) -> str:
    """
    WHAT:    Reads an image, scales it, encodes as base64, and calls the vision API.
    WHY:     The vision agent needs a single tool that handles the full pipeline —
             reading, scaling, encoding, and API call — without exposing API keys
             to the agent sandbox.
    HOW:     1. Opens image with PIL. 2. Scales proportionally if long side >
             vision_max_dimension. 3. Saves as JPEG → base64. 4. Resolves the vision
             model via settings. 5. POSTs to OpenAI-compatible vision endpoint.
             6. Returns the model's text content.
    PARAMS:  image_path: str — absolute path to the image file
             request: str — detailed analysis prompt for the vision model
    RETURNS: str — model's text response, or error description
    ERRORS:  File not found, PIL open failure, API failure, empty response
    """
    if not image_path or not request:
        return (
            "Error: both 'image_path' and 'request' are required."
        )

    target = Path(image_path)
    if not target.exists():
        return f"Error: image file not found: {image_path}"
    if not target.is_file():
        return f"Error: not a file: {image_path}"

    try:
        img = Image.open(target)
    except Exception as e:
        return f"Error: cannot open image '{image_path}': {e}"

    from src.config import settings

    max_dim = settings.vision_max_dimension
    w, h = img.size
    if max(w, h) > max_dim:
        ratio = max_dim / max(w, h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        log.info("Scaled image from %dx%d to %dx%d", w, h, new_w, new_h)

    buffer = io.BytesIO()
    try:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=90)
    except Exception as e:
        return f"Error: cannot encode image: {e}"

    b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
    data_uri = f"data:image/jpeg;base64,{b64_data}"

    litellm_model, api_key, api_base = settings.resolve_model(settings.vision_model)
    if not api_key:
        return (
            "Error: vision model is not configured. "
            "Set SIMPLEX_VISION_MODEL and the corresponding provider API key in .env."
        )

    url = api_base.rstrip("/") + "/chat/completions"

    # Strip LiteLLM routing prefix for direct HTTP call
    model_name = litellm_model
    if model_name.startswith("openai/"):
        model_name = model_name[len("openai/"):]

    SYSTEM = (
        "You are a precise document analyst. "
        "When analyzing an image of a document, ALWAYS include in your response:\n"
        "1. PAGE ORIENTATION — explicitly state \"Portrait\" or \"Landscape\"\n"
        "2. LAYOUT STRUCTURE — sections, columns, margins, headers, footers\n"
        "3. KEY ELEMENTS — tables, images, logos, stamps, signatures, seals\n"
        "4. TABLES — for each: row/column count, headers, content, merged cells\n"
        "5. TEXT — extract verbatim where readable; note font style/size/weight/color\n"
        "6. COLORS — background, text, accents, highlights\n"
         "7. NUMBERS & CODES — extract all numeric values, dates, registration numbers exactly\n"
         "8. CONTENT vs PAGE ORIENTATION — the physical page image may be Portrait while the "
         "text/content is rotated (Landscape). Check if text runs across the short side or reads "
         "vertically. Report BOTH: \"Physical page: Portrait, Content orientation: Landscape (rotated 90°)\".\n\n"
        "Be exhaustive and specific. Do not summarize — describe everything you see."
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": request},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        return "Error: vision API request timed out after 120s."
    except httpx.HTTPStatusError as e:
        body = e.response.text[:500] if e.response.text else "(no body)"
        return f"Error: vision API returned {e.response.status_code}: {body}"
    except Exception as e:
        return f"Error: vision API request failed: {e}"

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        return f"Error: unexpected API response format — missing content: {e}"

    if not text or not text.strip():
        return "Error: vision model returned an empty response."

    return text.strip()
