"""
src/tools/use_vision.py · Scale image → call vision model → write detail file.
Reads an image, scales it, sends to the configured vision model, splits response
on the ===FULL=== marker: short summary returned inline, full analysis written
to a .md file in the session folder.
Depends on: PIL, httpx, settings.vision_model, _agent_params (work_dir).
"""

import base64
import io
import logging
import re
import uuid
from pathlib import Path

import httpx
from PIL import Image

log = logging.getLogger("simplex.tools.use_vision")


def get_visibility() -> dict:
    return {"main_agent": True}


def get_description() -> dict:
    return {
        "description": (
            "Analyze a scanned document, image, or photo using a vision AI model. "
            "Use this when tesseract/pytesseract OCR fails or produces poor results — "
            "handles complex layouts, tables, handwriting, poor-quality scans, and "
            "non-standard fonts. Fall back to this after one failed OCR attempt. "
            "Returns a short summary inline and writes the full analysis to a .md "
            "file in the session folder."
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


async def execute(image_path: str, request: str, _agent_params: dict = None) -> str:
    """
    WHAT:    Reads an image, calls the vision API, returns short summary inline
             and writes full analysis to a file in the session folder.
    WHY:     The vision tool needs to keep the main agent's context lean — only a
             short summary flows back; the full detailed analysis persists on disk
             in the session folder for later reference.
    HOW:     1. Opens image with PIL, scales if needed, encodes as base64 JPEG.
              2. Sends to the configured vision model with a marker-based system prompt.
              3. Splits response on the ===FULL=== marker into short + full sections.
              4. Writes full analysis to a .md file in the session folder (work_dir).
              5. Returns short summary + file path to the caller.
    PARAMS:  image_path: str — absolute path to the image file
             request: str — detailed analysis prompt for the vision model
             _agent_params: dict or None — injected by ToolRegistry; carries work_dir
    RETURNS: str — short_description + [DETAIL: filename.md], or error string
    ERRORS:  File not found, PIL open failure, API failure, marker not found
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

    if _agent_params and "work_dir" in _agent_params:
        work_dir = _agent_params["work_dir"]
    else:
        from src.ui import state
        if state.session_folder:
            work_dir = state.session_folder
        else:
            return (
                "Error: use_vision requires a session folder to write the detail file. "
                "No session folder is set."
            )

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
        "Respond with exactly TWO sections separated by a line containing ONLY the word `===FULL===`.\n"
        "\n"
        "First section: SHORT DESCRIPTION — exactly 1-2 sentences summarising what the document IS "
        "and its key data (e.g. \"Romanian invoice from SC Example SRL dated 15.03.2024 — total "
        "1,250 RON, 3 line items\"). Do NOT include meta-commentary like \"The document appears "
        "to be...\". State facts directly. Do NOT prefix with any label or marker.\n"
        "\n"
        "Second section (after `===FULL===`): FULL DETAILED ANALYSIS — provide the exhaustive "
        "analysis exactly as requested by the user.\n"
        "\n"
        "Respond exactly like this:\n"
        "Audit report page (page 4) analyzing accounting irregularities.\n"
        "===FULL===\n"
        "PAGE ORIENTATION: Portrait\n"
        "LAYOUT: ...\n"
        "...\n"
        "\n"
        "Do NOT use markdown code fences (```). Do NOT output a JSON object. "
        "Do NOT include any text before the short description or after the full analysis.\n"
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

    # Split response on the ===FULL=== marker
    cleaned = text.strip()
    # Strip markdown code fences if the model wraps the response anyway
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json|markdown)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    parts = re.split(r"\n\s*===FULL===\s*\n", cleaned, maxsplit=1)
    if len(parts) == 2:
        short = parts[0].strip()
        full = parts[1].strip()
    else:
        log.warning("vision model response missing ===FULL=== marker — using full text as both")
        short = ""
        full = cleaned

    if not short:
        sentences = full.replace("\n", " ").split(". ")
        short = ". ".join(sentences[:2]).strip()
        if short:
            short += "."
        else:
            short = full[:200].rsplit(" ", 1)[0] + "..."

    if not full:
        full = "(empty analysis)"

    work_dir = Path(work_dir)
    stem = re.sub(r"\s+", "_", target.stem)
    suffix = uuid.uuid4().hex[:8]
    detail_filename = f"{stem}.{suffix}.md"
    detail_path = work_dir / detail_filename

    md_content = (
        f"===REQUEST===\n{request}\n\n===SHORT_DESCRIPTION===\n{short}\n\n===FULL_DESCRIPTION===\n{full}\n"
    )
    try:
        detail_path.write_text(md_content, encoding="utf-8")
    except Exception as e:
        return f"Error: failed to write detail file '{detail_filename}': {e}"

    return f"{short}\n[DETAIL: {detail_path}]"
