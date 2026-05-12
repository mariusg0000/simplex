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
TOOLS_DIR = SIMPLEx_DIR / "tools"
AGENTS_DIR = SIMPLEx_DIR / "agents"
SKILLS_DIR = SIMPLEx_DIR / "skills"

SIMPLEx_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)
SCRIPTS_DIR.mkdir(exist_ok=True)
TOOLS_DIR.mkdir(exist_ok=True)
AGENTS_DIR.mkdir(exist_ok=True)
SKILLS_DIR.mkdir(exist_ok=True)

_BUNDLED_TOOLS_README = Path(__file__).resolve().parent / "src" / "tools" / "README.md"
_BUNDLED_AGENTS_README = Path(__file__).resolve().parent / "src" / "agents" / "README.md"
_BUNDLED_SKILLS_README = Path(__file__).resolve().parent / "src" / "skills" / "README.md"

_TOOLS_README = TOOLS_DIR / "README.md"
_AGENTS_README = AGENTS_DIR / "README.md"
_SKILLS_README = SKILLS_DIR / "README.md"

# Sync bundled READMEs to custom directories on every startup (overwrite)
for src, dst in [(_BUNDLED_TOOLS_README, _TOOLS_README),
                 (_BUNDLED_AGENTS_README, _AGENTS_README),
                 (_BUNDLED_SKILLS_README, _SKILLS_README)]:
    if src.exists():
        dst.write_bytes(src.read_bytes())



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
from src.engine.skills import skill_registry

registry.disable("read_document")
registry.disable("generate_pdf")
registry.disable("get_current_time")
registry.disable("task_done")


if __name__ in {"__main__", "__mp_main__"}:
    _cleanup_tmp()
    init_ui()
    ui.run(title="Simplex AI", native=settings.native_mode, window_size=(1200, 800), reload=False)
