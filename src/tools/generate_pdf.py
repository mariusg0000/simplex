"""
src/tools/generate_pdf.py · Convert HTML to PDF with auto-termination on success.
Takes a relative HTML filename, converts to PDF in the same session folder.
On success: returns _AGENT_DONE_ with the PDF filename (auto-exits agent).
On failure: returns error string so the agent can retry.
Depends on: weasyprint (from scripts venv), pathlib, _agent_params (ContextVar).
"""

import sys
from pathlib import Path


SCRIPTS_VENV = Path.home() / ".simplexai" / "scripts" / ".venv"


def _ensure_weasyprint_in_path():
    """Adds scripts venv site-packages to sys.path if not present."""
    site_pkgs = SCRIPTS_VENV / "lib"
    if site_pkgs.exists():
        for d in sorted(site_pkgs.iterdir()):
            if d.is_dir() and d.name.startswith("python"):
                sp = d / "site-packages"
                if sp.exists() and str(sp) not in sys.path:
                    sys.path.insert(0, str(sp))
                    return


def get_visibility() -> dict:
    return {"main_agent": False}


def get_description() -> dict:
    return {
        "description": (
            "Convert an HTML file to PDF. On success, auto-terminates the agent "
            "with the session folder and PDF filename. On failure, returns errors."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": (
                        "Relative HTML filename to convert (e.g., 'index.html'). "
                        "Must be inside the session folder."
                    ),
                },
            },
            "required": ["filename"],
        },
    }


async def execute(filename: str, _agent_params: dict = None) -> str:
    """
    WHAT:    Converts an HTML file to PDF. Auto-terminates agent on success.
    WHY:     Single-step PDF generation for create_pdf agent. No retries needed
             from the tool — on success it exits; on failure it returns errors
             so the agent can fix and retry.
    HOW:     Resolves filename against work_dir. Uses weasyprint to convert.
             On success returns _AGENT_DONE_:<pdf_filename> to auto-terminate.
             On failure returns a plain error string so the agent can retry.
    PARAMS:  filename: str — relative HTML filename
             _agent_params: dict — injected by ToolRegistry; carries work_dir
    RETURNS: str — _AGENT_DONE_:<pdf_filename> on success,
                   or error string on failure
    """
    if not _agent_params or "work_dir" not in _agent_params:
        return "Error: generate_pdf requires a session folder (work_dir)."

    work_dir = _agent_params["work_dir"]
    html_path = Path(work_dir) / filename

    if not html_path.exists():
        return f"Error: HTML file not found: {filename}"
    if not html_path.is_file():
        return f"Error: not a file: {filename}"

    pdf_filename = html_path.with_suffix(".pdf").name
    pdf_path = Path(work_dir) / pdf_filename

    _ensure_weasyprint_in_path()

    try:
        from weasyprint import HTML
        HTML(str(html_path)).write_pdf(str(pdf_path))
    except ImportError:
        return (
            "Error: weasyprint is not installed in the scripts environment. "
            "Install with: pip install weasyprint"
        )
    except Exception as e:
        return f"Error converting {filename} to PDF: {e}"

    size = pdf_path.stat().st_size
    if size < 500:
        return (
            f"Error: generated PDF is only {size} bytes — likely empty or broken. "
            f"Fix the HTML/CSS and retry."
        )

    return f"_AGENT_DONE_: {pdf_filename}"
