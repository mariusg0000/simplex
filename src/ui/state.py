"""
src/ui/state.py · Shared application state · Holds globals accessed by UI components.
"""

import os
import shutil
import uuid
import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Callable

from nicegui import ui
from src.engine.agents import AgentStep

from src.config import settings
from src.prompts import load_cli_prompts

_system_env_cache: Optional[str] = None

EXCLUDED_CLI: set[str] = {
    "pandoc_write",
}
active_task: Optional[asyncio.Task] = None

# Sub-agent activity log
sub_agent_log: list[AgentStep] = []
sub_agent_panel: Optional[ui.expansion] = None
sub_agent_content: Optional[ui.column] = None


def clear_sub_agent_log():
    """Adaugă separator între run-uri — nu șterge nimic."""
    if sub_agent_content:
        with sub_agent_content:
            ui.separator().classes("my-0.5 opacity-30")


def make_sub_agent_callback() -> Callable[[AgentStep], None]:
    """Creates a callback that appends to sub_agent_log and updates the UI."""
    def _on_step(step: AgentStep):
        sub_agent_log.append(step)
        if sub_agent_panel and not sub_agent_panel.value:
            sub_agent_panel.value = True
        if sub_agent_content:
            with sub_agent_content:
                icon = {
                    "llm_call": "🤔",
                    "tool_call": "⚡",
                    "tool_result": "✅",
                    "error": "❌",
                    "done": "🏁",
                }.get(step.step_type, "•")
                max_chars = 200 if step.step_type == "tool_call" else 150
                content = step.content[:max_chars]
                line = f"[{step.timestamp}] {icon} [{step.agent_name}] R{step.round}: {content}"
                ui.label(line).classes("text-[11px] font-mono text-gray-600 leading-5 py-0.5")
                try:
                    sub_agent_content.client.run_javascript("""
                        const el = document.querySelector('.sub-agent-expansion .q-expansion-item__content');
                        if (el) el.scrollTop = el.scrollHeight;
                    """)
                except Exception:
                    pass
    return _on_step
chat_title: str = "New Chat"
current_session_id: str = ""
status_label: Any = None
usage_label: Any = None

TOOL_ALIASES: dict[str, list[str]] = {
    "fd": ["fdfind"],
    "bat": ["batcat"],
    "pandoc_read": ["pandoc"],
    "pandoc_write": ["pandoc"],
}

TOOL_PACKAGES: dict[str, str] = {
    "rg": "ripgrep",
    "fd": "fd-find",
    "sd": "",
    "pandoc_read": "pandoc",
    "pandoc_write": "pandoc",
    "pandas": "",
    "tesseract": "tesseract-ocr",
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


def _python_package_available(package: str) -> bool:
    """Check if a Python package is importable in the scripts venv."""
    venv_python = Path.home() / ".simplexai" / "scripts" / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable
    try:
        subprocess.run(
            [python, "-c", f"import {package}"],
            capture_output=True, timeout=5,
        )
        return True
    except Exception:
        return False


def _build_env_section() -> str:
    """Detects installed modern utilities and builds the SYSTEM ENVIRONMENT section."""
    global _system_env_cache
    if _system_env_cache is not None:
        return _system_env_cache

    prompts = load_cli_prompts()
    lines = []
    for cmd, prompt in prompts.items():
        if cmd in EXCLUDED_CLI:
            continue
        if cmd == "pandas":
            if _python_package_available("pandas"):
                lines.append(prompt)
        elif find_tool(cmd) is not None:
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
        f"Current time: {datetime.now().strftime('%Y-%m-%d %H:00 (%B, %A)')}\n\n"
        f"Working directory: ~/.simplexai\n"
        f"  - .tmp/     -> temporary/intermediate files (auto-cleaned after 30 min)\n"
        f"  - scripts/  -> reusable Python scripts (see catalog below)\n"
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
