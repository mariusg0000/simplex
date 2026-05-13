"""
src/ui/state.py · Shared application state · Holds globals accessed by UI components.
"""

import os
import re
import shutil
import uuid
import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Callable

from nicegui import ui
from src.engine.agents import AgentStep, AgentStreamChunk

from src.config import settings
from src.prompts import load_cli_prompts
from src.engine.agents import agent_registry

_system_env_cache: Optional[str] = None

EXCLUDED_CLI: set[str] = {
    "pandoc_write",
}
active_task: Optional[asyncio.Task] = None

# Sub-agent raw output panel
sub_agent_panel: Optional[ui.expansion] = None
sub_agent_content: Optional[ui.column] = None
sub_agent_dismissed: bool = False
_sub_agent_closing: bool = False
_console = None  # single console label


def _collapse_newlines(text: str) -> str:
    return re.sub(r'\n+', '\n', text)


def log_activity(text: str):
    """Append text to the Activity Log console panel."""
    global _console
    if sub_agent_panel and not sub_agent_panel.value and not sub_agent_dismissed:
        sub_agent_panel.value = True
    if sub_agent_content:
        if _console is None:
            with sub_agent_content:
                _console = ui.label("").classes(
                    "text-[11px] font-mono text-black leading-5 py-0.5 whitespace-pre-wrap"
                )
        _console.set_text((_console.text or "") + _collapse_newlines(text))
        _scroll_sub_agent()


def close_activity_log():
    """Close the Activity Log panel and reset dismiss flag."""
    global _console
    if sub_agent_panel:
        global _sub_agent_closing
        _sub_agent_closing = True
        sub_agent_panel.value = False
        _sub_agent_closing = False
    global sub_agent_dismissed
    sub_agent_dismissed = False
    _console = None


def make_sub_agent_callback():
    """Creates (on_step, on_stream) callbacks that append to the console label.

    on_step: tool calls + results, raw terminal style.
    on_stream: raw LLM text appended verbatim — like a terminal.
    Both feed into the same single console label to preserve chronology.
    """

    def _on_stream(chunk: AgentStreamChunk):
        if sub_agent_panel and not sub_agent_panel.value and not sub_agent_dismissed:
            sub_agent_panel.value = True
        if sub_agent_content:
            global _console
            if _console is None:
                with sub_agent_content:
                    _console = ui.label("").classes(
                        "text-[11px] font-mono text-black leading-5 py-0.5 whitespace-pre-wrap"
                    )
            _console.set_text((_console.text or "") + _collapse_newlines(f"[{chunk.agent_name}] {chunk.content}"))
            _scroll_sub_agent()

    def _on_step(step: AgentStep):
        global _console, sub_agent_dismissed, _sub_agent_closing
        if step.step_type == "done":
            _console = None
            if sub_agent_panel:
                _sub_agent_closing = True
                sub_agent_panel.value = False
                _sub_agent_closing = False
            sub_agent_dismissed = False
            return
        if sub_agent_panel and not sub_agent_panel.value and not sub_agent_dismissed:
            sub_agent_panel.value = True
        if sub_agent_content:
            if _console is None:
                with sub_agent_content:
                    _console = ui.label("").classes(
                        "text-[11px] font-mono text-black leading-5 py-0.5 whitespace-pre-wrap"
                    )
            text = ""
            if step.step_type == "tool_call":
                text = f"[{step.agent_name}] $ {step.content[:500]}"
            elif step.step_type == "tool_result":
                text = f"[{step.agent_name}] {step.content[:500]}"
            if text:
                _console.set_text((_console.text or "") + "\n" + _collapse_newlines(text))
                _scroll_sub_agent()
    return _on_step, _on_stream


def _scroll_sub_agent():
    try:
        sub_agent_content.client.run_javascript("""
            const el = document.querySelector('.sub-agent-expansion .q-expansion-item__content');
            if (el) el.scrollTop = el.scrollHeight;
        """)
    except Exception:
        pass
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
    agent_descs = agent_registry.get_descriptions()
    if agent_descs:
        content += f"\n\nAVAILABLE AGENTS:\n{agent_descs}"
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
        "4. RERANKER TRUST: The file search tool uses an internal Reranker. The top results it returns are the final candidates.\n"
        "5. DELEGATE TO AGENTS: When a task matches an AVAILABLE AGENT description, delegate it to that agent. "
        "For `create_doc`: first analyze reference documents yourself, then call the agent with ALL layout specs (colors, fonts, sizes, spacing, structure) and full text content. "
        "CRITICAL: prepend the task with: 'FORBIDDEN: do NOT use fitz/python/bash to read any PDF file. Generate directly from specs.' "
        "The sub-agent generates directly from your description — it does NOT re-analyze. "
        "Never create documents directly with bash/Python yourself.\n"
    )
    return {"role": "system", "content": content}


def init_messages():
    """Initializes messages with the dynamic system prompt."""
    import src.ui.state as state
    state.messages = [get_system_prompt()]
