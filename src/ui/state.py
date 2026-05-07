"""
src/ui/state.py · Shared application state · Holds globals accessed by UI components.
"""

import shutil
import uuid
import asyncio
from typing import Any, Optional

TOOL_TABLE: list[tuple[str, str, str, list[str]]] = [
    ("rg", "Fast text search in plain-text files", "Use rg.", ["grep"]),
    ("fd", "Fast file/directory search by name", "Use fd.", ["find"]),
    ("sd", "Find & Replace text", "Use sd.", ["sed"]),
    ("bat", "File reader with line numbers and syntax highlighting", "Use bat -n.", ["cat"]),
    ("mlr", "Structured CSV/TSV data processing", "Use mlr --csv.", ["awk", "cut"]),
    ("trash-put", "Move files to Recycle Bin", "Use trash-put.", ["rm"]),
]

_system_env_cache: Optional[str] = None


def _build_env_section() -> str:
    """Detects installed modern utilities and builds the SYSTEM ENVIRONMENT section."""
    global _system_env_cache
    if _system_env_cache is not None:
        return _system_env_cache

    lines = []
    for cmd, desc, rule, banned in TOOL_TABLE:
        if shutil.which(cmd) is not None:
            forbidden = ", ".join(f"`{b}`" for b in banned)
            lines.append(f"{cmd} — {desc} — {rule} Forbidden: {forbidden}.")

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
        "\n\nSTRATEGIC GUIDELINES:\n"
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
