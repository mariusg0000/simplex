"""
src/prompts.py · CLI prompt loading · Separated from UI state for reuse by agents.
"""

import tomllib
from pathlib import Path
from typing import Optional

_CLI_PROMPTS_PATH = Path(__file__).resolve().parent.parent / "cli_prompts.toml"
_cli_prompts_cache: Optional[dict[str, str]] = None


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
