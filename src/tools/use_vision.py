"""
src/tools/use_vision.py · Scale image → call vision model → write detail file.
Reads an image, scales it, sends to the configured vision model, returns a short
summary inline and writes the full analysis to a file in the session folder.
Depends on: PIL, httpx, settings.vision_model, _agent_params (work_dir).
"""

import base64
import io
import json
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
             2. Sends to the configured vision model with a JSON-format system prompt.
             3. Parses the JSON response for short_description and full_description.
             4. Writes full_description to a .md file in the session folder (work_dir).
             5. Returns short_description + file path to the caller.
    PARAMS:  image_path: str — absolute path to the image file
             request: str — detailed analysis prompt for the vision model
             _agent_params: dict or None — injected by ToolRegistry; carries work_dir
    RETURNS: str — short_description + [DETAIL: filename.md], or error string
    ERRORS:  File not found, PIL open failure, API failure, JSON parse failure
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
        "Return ONLY a valid JSON object with exactly two keys:\n"
        "- short_description: 1-2 sentences summarising what the document IS and its key data "
        "(e.g. \"Romanian invoice from SC Example SRL dated 15.03.2024 — total 1,250 RON, "
        "3 line items\"). Do NOT include meta-commentary like \"The document appears to be...\". "
        "State facts directly.\n"
        "- full_description: exhaustive analysis including: page orientation (Portrait/Landscape "
        "and content rotation if any), layout structure (sections, columns, margins, headers, "
        "footers), key elements (tables, images, logos, stamps, signatures, seals), tables "
        "(row/col counts, headers, content, merged cells), text extracted verbatim with font "
        "style/size/weight/color where readable, background/text/accent colours, all numeric "
        "values, dates, registration numbers, codes extracted exactly. Be exhaustive — "
        "describe everything you see.\n\n"
        "Example format:\n"
        "{\n"
        '  "short_description": "Invoice from SC Example SRL dated 15.03.2024 — total 1,250 RON, 3 items.",\n'
        '  "full_description": "PAGE ORIENTATION: Portrait\\nLAYOUT: ...\\nTABLES: ...\\nTEXT: ..."\n'
        "}\n"
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

    # Extract JSON from response (handle markdown code fences)
    def _extract_json(raw: str) -> dict:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
        return {}

    parsed = _extract_json(text)
    if parsed.get("short_description") and parsed.get("full_description"):
        short = parsed["short_description"].strip()
        full = parsed["full_description"].strip()
    else:
        short = ""
        full = text.strip()

    if not short:
        # Fallback: derive summary from first ~2 sentences
        sentences = full.replace("\n", " ").split(". ")
        short = ". ".join(sentences[:2]).strip()
        if short:
            short += "."
        else:
            short = full[:200].rsplit(" ", 1)[0] + "..."

    if not full:
        full = "(empty analysis)"

    # Write full description to a file in the session folder
    work_dir = Path(work_dir)
    stem = re.sub(r"\s+", "_", target.stem)
    suffix = uuid.uuid4().hex[:8]
    detail_filename = f"{stem}.{suffix}.md"
    detail_path = work_dir / detail_filename

    try:
        detail_path.write_text(full, encoding="utf-8")
    except Exception as e:
        return f"Error: failed to write detail file '{detail_filename}': {e}"

    return f"{short}\n[DETAIL: {detail_path}]"
