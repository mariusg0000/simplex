"""
src/ui/state.py · Shared application state · Holds globals accessed by UI components.
"""

import os
import shutil
import tomllib
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.config import settings

_CLI_PROMPTS_PATH = Path(__file__).resolve().parent.parent.parent / "cli_prompts.toml"
_cli_prompts_cache: Optional[dict[str, str]] = None
_system_env_cache: Optional[str] = None
active_task: Optional[asyncio.Task] = None
chat_title: str = "New Chat"
current_session_id: str = ""
status_label: Any = None
usage_label: Any = None

TOOL_ALIASES: dict[str, list[str]] = {
    "fd": ["fdfind"],
    "bat": ["batcat"],
}

TOOL_PACKAGES: dict[str, str] = {
    "rg": "ripgrep",
    "fd": "fd-find",
    "sd": "",
    "bat": "bat",
    "mlr": "miller",
    "trash-put": "trash-cli",
    "exiftool": "libimage-exiftool-perl",
    "pdftotext": "poppler-utils",
    "pdfinfo": "poppler-utils",
    "pdfunite": "poppler-utils",
    "pdfseparate": "poppler-utils",
    "pdftoppm": "poppler-utils",
    "pdffonts": "poppler-utils",
    "pdfimages": "poppler-utils",
    "pandoc": "pandoc",
    "tesseract": "tesseract-ocr",
    "weasyprint": "weasyprint",
}


def load_cli_prompts() -> dict[str, str]:
    """Load CLI tool prompts from cli_prompts.toml. Cached after first read."""
    global _cli_prompts_cache
    if _cli_prompts_cache is not None:
        return _cli_prompts_cache
    try:
        with open(_CLI_PROMPTS_PATH, "rb") as f:
            data = tomllib.load(f)
        _cli_prompts_cache = {k: v["prompt"] for k, v in data.items()}
    except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError):
        _cli_prompts_cache = {}
    return _cli_prompts_cache


def find_tool(cmd: str) -> str | None:
    """Check if a tool is installed, trying aliases if the primary name is not found."""
    path = shutil.which(cmd)
    if path:
        return path
    for alias in TOOL_ALIASES.get(cmd, []):
        path = shutil.which(alias)
        if path:
            return path
    return None


def build_install_command() -> str:
    """Generate a sudo apt install command for all missing tools."""
    packages: set[str] = set()
    for cmd, pkg in TOOL_PACKAGES.items():
        if find_tool(cmd) is None and pkg:
            packages.add(pkg)
    if not packages:
        return ""
    sorted_pkgs = sorted(packages)
    return f"for pkg in {' '.join(sorted_pkgs)}; do sudo apt install -y \"$pkg\" 2>&1 | tail -2; done"


def _build_env_section() -> str:
    """Detects installed modern utilities and builds the SYSTEM ENVIRONMENT section."""
    global _system_env_cache
    if _system_env_cache is not None:
        return _system_env_cache

    prompts = load_cli_prompts()
    lines = []
    for cmd, prompt in prompts.items():
        if find_tool(cmd) is not None:
            lines.append(prompt)

    section = "\n".join(lines) if lines else ""
    _system_env_cache = section
    return section


def get_system_prompt() -> dict:
    """Returns the current system prompt with env info and strategic guidelines."""
    env_section = _build_env_section()
    content = settings.system_prompt
    if env_section:
        content += f"\n\nSYSTEM ENVIRONMENT:\n{env_section}"
    content += (
        f"\n\nCWD: {os.getcwd()}\n"
        f"Current time: {datetime.now().strftime('%Y-%m-%d %H:00 (%B, %A)')}\n"
    )
    content += (
        "\nSTRATEGIC GUIDELINES:\n"
        "1. BE EFFICIENT: Do not perform more than 2 search attempts for the same request.\n"
        "2. TRUST THE TOOLS: If a search tool returns results, those are the best matches. Present them immediately.\n"
        "3. NO REDUNDANCY: Do not call the same tool with slightly different parameters if you already have relevant data.\n"
        "4. RERANKER TRUST: The file search tool uses an internal Reranker. The top results it returns are the final candidates."
    )
    return {"role": "system", "content": content}


def init_messages():
    """Initializes messages with the dynamic system prompt."""
    import src.ui.state as state
    state.messages = [get_system_prompt()]
