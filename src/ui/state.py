"""
src/ui/state.py · Shared application state · Holds globals accessed by UI components.
"""

import os
import shutil
import uuid
import asyncio
from datetime import datetime
from typing import Any, Optional

from src.config import settings

# Prepend bundled tools directory to PATH so shutil.which() finds them.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BIN_DIR = os.path.join(_PROJECT_ROOT, "bin")
if os.path.isdir(_BIN_DIR):
    os.environ["PATH"] = f"{_BIN_DIR}:{os.environ.get('PATH', '')}"

TOOL_TABLE: list[tuple[str, str, str, list[str]]] = [
    ("rg", "Fast text search in plain-text files", "Use rg.", ["grep"]),
    ("fd", "Fast file/directory search by name", "Use fd.", ["find"]),
    ("sd", "Find & Replace text", "Use sd.", ["sed"]),
    ("bat", "File reader with line numbers and syntax highlighting", "Use bat -n.", ["cat"]),
    ("mlr", "Structured CSV/TSV data processing", "Use mlr --csv.", ["awk", "cut"]),
    ("trash-put", "Move files to Recycle Bin", "Use trash-put.", ["rm"]),
    ("exiftool", "Extract file metadata (creator, dates, camera info)", "Use exiftool.", []),
    ("pdftotext", "Extract text from PDFs (preserve layout with -layout flag)", "Use pdftotext -layout.", []),
    ("pdfinfo", "Display PDF metadata (pages, author, dimensions, security)", "Use pdfinfo.", []),
    ("pdfunite", "Merge multiple PDFs into one", "Use pdfunite.", []),
    ("pdfseparate", "Extract individual pages from a PDF", "Use pdfseparate.", []),
    ("pdftoppm", "Convert PDF pages to images (PNG, JPEG, TIFF)", "Use pdftoppm.", []),
    ("pdffonts", "List fonts used in a PDF", "Use pdffonts.", []),
    ("pdfimages", "Extract embedded images from a PDF", "Use pdfimages.", []),
    ("pandoc", "Convert between document formats (.md, .docx, etc.)", "Use pandoc.", []),
    ("tesseract", "OCR text from images and scanned PDFs", "Use tesseract.", []),
    ("xdg-open", "Open files/directories/URLs with the system default application", "When user asks to open a file, use xdg-open.", []),
    ("ddgr", "Search DuckDuckGo from the terminal", "Use ddgr.", []),
    ("reader", "Extract main content from web pages and EML files as clean text/markdown", "Use reader -o for markdown output.", []),
]

_system_env_cache: Optional[str] = None
active_task: Optional[asyncio.Task] = None
chat_title: str = "New Chat"
current_session_id: str = ""

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
    "ddgr": "ddgr",
    "reader": "",
}


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

    lines = []
    for cmd, desc, rule, banned in TOOL_TABLE:
        if shutil.which(cmd) is not None:
            if banned:
                forbidden = ", ".join(f"`{b}`" for b in banned)
                lines.append(f"{cmd} — {desc} — {rule} Forbidden: {forbidden}.")
            else:
                lines.append(f"{cmd} — {desc} — {rule}")

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
