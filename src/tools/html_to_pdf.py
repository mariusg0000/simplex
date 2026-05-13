"""
src/tools/html_to_pdf.py · Convert HTML to PDF using weasyprint with sandbox awareness.
When _agent_params contains work_dir, resolves filenames against the session folder.
Without work_dir, main agent can use any paths.
Resolves weasyprint from scripts venv (~/.simplexai/scripts/.venv) via sys.path
so it works without installing in the app environment.
Depends on: weasyprint (in scripts venv), pathlib, _agent_params (ContextVar via ToolRegistry).
"""

import sys
from pathlib import Path


SCRIPTS_VENV = Path.home() / ".simplexai" / "scripts" / ".venv"


def _ensure_weasyprint_in_path():
    """
    WHAT:    Adds scripts venv site-packages to sys.path if not already present.
    WHY:     weasyprint is installed in ~/.simplexai/scripts/.venv, not in the
             app environment. This allows importing it without subprocess or
             system-wide installation.
    HOW:     Finds the site-packages directory inside the scripts venv and
             prepends it to sys.path. Skips if already present.
    """
    site_pkgs = SCRIPTS_VENV / "lib"
    if site_pkgs.exists():
        for d in sorted(site_pkgs.iterdir()):
            if d.is_dir() and d.name.startswith("python"):
                sp = d / "site-packages"
                if sp.exists() and str(sp) not in sys.path:
                    sys.path.insert(0, str(sp))
                    return


def get_description() -> dict:
    return {
        "description": (
            "Convert an HTML file to PDF using weasyprint. Sub-agents MUST use "
            "relative filenames. Main agents can use absolute paths."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_html": {
                    "type": "string",
                    "description": (
                        "Source HTML filename. Sub-agents MUST use relative names "
                        "(e.g., 'index.html')."
                    ),
                },
                "output_pdf": {
                    "type": "string",
                    "description": (
                        "Destination PDF filename. Sub-agents MUST use relative names "
                        "(e.g., 'output.pdf')."
                    ),
                },
            },
            "required": ["input_html", "output_pdf"],
        },
    }


async def execute(input_html: str, output_pdf: str, _agent_params: dict = None) -> str:
    """
    WHAT:    Converts an HTML file to PDF using weasyprint.
    WHY:     Provides a clean, path-agnostic way for sub-agents to generate PDFs
             without ever seeing absolute paths or invoking shell commands.
    HOW:     If _agent_params has work_dir, resolves both filenames against it.
             Uses weasyprint.HTML to read the HTML and write_pdf to generate PDF.
             Catches import errors (weasyprint not installed) and conversion errors.
    PARAMS:  input_html: str — source HTML filename (relative for sub-agents)
             output_pdf: str — destination PDF filename (relative for sub-agents)
             _agent_params: dict or None — injected by ToolRegistry; carries work_dir
    RETURNS: str — confirmation with output filename and size, or error message
    ERRORS:  Absolute path from sub-agent, input not found, weasyprint not installed,
             conversion failure
    """
    if _agent_params and "work_dir" in _agent_params:
        if Path(input_html).is_absolute() or Path(output_pdf).is_absolute():
            return (
                f"Error: sub-agents cannot use absolute paths. "
                f"Use relative filenames."
            )
        html_path = Path(_agent_params["work_dir"]) / input_html
        pdf_path = Path(_agent_params["work_dir"]) / output_pdf
    else:
        html_path = Path(input_html)
        pdf_path = Path(output_pdf)

    if not html_path.exists():
        return f"Error: HTML file not found: {input_html}"
    if not html_path.is_file():
        return f"Error: not a file: {input_html}"

    _ensure_weasyprint_in_path()

    try:
        from weasyprint import HTML
        HTML(str(html_path)).write_pdf(str(pdf_path))
    except ImportError:
        return (
            "Error: weasyprint is not installed. "
            "Install with: pip install weasyprint"
        )
    except Exception as e:
        return f"Error converting {input_html} to PDF: {e}"

    size = pdf_path.stat().st_size
    return f"Created {output_pdf} ({size:,} bytes)"
