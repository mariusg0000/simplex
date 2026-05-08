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

# Import tool modules to register them with the tool registry
import src.engine.builtin_tools   # noqa: F401
import src.engine.bash_tool       # noqa: F401
import src.engine.pdf_tool        # noqa: F401

# Disable all tools except bash
from src.engine.tools import registry
for tool_name in list(registry.tools.keys()):
    if tool_name != "bash":
        registry.disable(tool_name)

registry.enable("create_pdf")


if __name__ in {"__main__", "__mp_main__"}:
    _cleanup_tmp()
    init_ui()
    ui.run(title="Simplex AI", native=settings.native_mode, window_size=(1200, 800), reload=False)
