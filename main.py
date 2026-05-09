"""
main.py · Entry Point · Initializes and runs the Simplex AI application.
"""

import os
import sys
import subprocess
from pathlib import Path

SIMPLEx_DIR = Path.home() / ".simplexai"
TMP_DIR = SIMPLEx_DIR / ".tmp"
SCRIPTS_DIR = SIMPLEx_DIR / "scripts"
SCRIPTS_VENV = SCRIPTS_DIR / ".venv"
SCRIPTS_CATALOG = SCRIPTS_DIR / "scripts.md"

SIMPLEx_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)
SCRIPTS_DIR.mkdir(exist_ok=True)

if not SCRIPTS_VENV.exists():
    subprocess.run([sys.executable, "-m", "venv", str(SCRIPTS_VENV)])

_SCRIPTS_PIP = SCRIPTS_VENV / "bin" / "pip"
if _SCRIPTS_PIP.exists():
    for _pkg in ["weasyprint", "pandas", "openpyxl", "pymupdf"]:
        r = subprocess.run([str(_SCRIPTS_PIP), "show", _pkg], capture_output=True)
        if r.returncode != 0:
            subprocess.run([str(_SCRIPTS_PIP), "install", _pkg], capture_output=True)

if not SCRIPTS_CATALOG.exists():
    SCRIPTS_CATALOG.write_text("# Scripts Catalog\n\nReusable Python scripts. Created/maintained by the Python Runner agent.\n")


def _cleanup_tmp():
    """Sterge toate fisierele din .tmp la pornire."""
    for f in TMP_DIR.iterdir():
        if f.is_file():
            f.unlink()


from nicegui import ui
from src.config import settings
from src.ui.app import init_ui

# Tool modules are auto-discovered by ToolRegistry from src/tools/

from src.engine.tools import registry

registry.disable("read_document")
registry.disable("generate_pdf")
registry.disable("get_current_time")
registry.disable("task_done")


if __name__ in {"__main__", "__mp_main__"}:
    _cleanup_tmp()
    init_ui()
    ui.run(title="Simplex AI", native=settings.native_mode, window_size=(1200, 800), reload=False)
