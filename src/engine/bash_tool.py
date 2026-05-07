"""
src/engine/bash_tool.py · Bash Tool · Executes shell commands and returns output.

WARNING: This tool can execute arbitrary shell commands. Use with caution.
"""

import asyncio
import logging
import re
from typing import Optional

from src.engine.tools import tool, registry

log = logging.getLogger("simplex.engine.bash_tool")

MAX_LINES = 500
MAX_CHARS = 50 * 1024  # 50 KB

DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\b", "Deletes files/folders permanently."),
    (r"rmdir\b", "Deletes directories."),
    (r"git\s+clean\s+-[a-z]*[f]", "Deletes untracked files permanently."),
    (r"dd\s+.*of=/dev/\w", "Can overwrite/destroy disk partitions."),
    (r"mkfs\.", "Formats disk partitions (destroys all data)."),
    (r"(curl|wget).*\|.*(bash|sh|python|perl|ruby)", "Downloads and executes code from the internet."),
    (r"chmod\s+-[rR]?\s*777", "Gives write access to everyone — security risk."),
    (r">\s*/dev/sd[a-z]", "Redirects output to a block device — can corrupt disks."),
    (r"shutdown\b", "Shuts down the computer."),
    (r"reboot\b", "Restarts the computer."),
    (r"halt\b", "Halts the system."),
    (r"poweroff\b", "Powers off the computer."),
    (r"init\s+[06]\b", "Changes system runlevel (shutdown/reboot)."),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Fork bomb — can freeze/crash the computer."),
    (r"sudo\s+", "Runs with administrator (root) privileges."),
    (r"\beval\b", "Evaluates arbitrary string as a command — bypass risk."),
    (r"(bash|sh)\s+-c\b", "Executes arbitrary string as a command — bypass risk."),
    (r"\bexec\b", "Replaces the shell process with a new command."),
]


def _check_dangerous(command: str) -> Optional[str]:
    """
    Checks if a command matches known dangerous patterns.
    Returns a human-readable danger description, or None if safe.
    """
    cmd_normalized = command.strip().lower()
    reasons = []
    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_normalized):
            reasons.append(description)
    return "; ".join(reasons) if reasons else None


@tool
async def bash(command: str, explanation: str, timeout: int = 30, need_confirmation: bool = False) -> str:
    """
    Execute a shell command and return its output (stdout + stderr combined).
    Output is truncated at 500 lines or 50 KB to avoid context overflow.
    Use this to run terminal commands, scripts, or system operations.

    PREFERRED TOOLS (faster & safer than classic Unix tools):
    - For file/content search, use `rg` (ripgrep) instead of `grep`.
    - For file editing / find-and-replace, use `sd` instead of `sed`.
    - Chain commands with `&&` for sequential execution; use `;` only if failures are acceptable.

    SAFETY:
    - Set `need_confirmation` to `True` for ANY command that could be destructive
      (deleting files, modifying system settings, affecting disk/network, etc.).
      The user will see a confirmation dialog before execution.
    - Dangerous commands (rm -rf, dd, chmod 777, shutdown, curl|bash, etc.)
      are automatically detected and will ALWAYS require confirmation, even
      if `need_confirmation` is `False`.

    PARAMS:
    command: str - The shell command to execute.
    explanation: str - Plain-language explanation of what this command does (shown to the user).
    timeout: int - Maximum execution time in seconds (default: 30, max: 120).
    need_confirmation: bool - Set to True if the command could be destructive (default: False).
    """
    if timeout < 1:
        timeout = 1
    if timeout > 120:
        timeout = 120

    danger_reason = _check_dangerous(command)

    if need_confirmation or danger_reason:
        if registry.on_confirmation_required is None:
            return "Confirmation required but no UI handler is registered."

        approved = await registry.on_confirmation_required(
            command, explanation, danger_reason or ""
        )
        if not approved:
            return "Command cancelled by user."

    log.debug("Executing bash command (timeout=%ds): %s", timeout, command[:200])

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return (
                f"Exit code: -1\n"
                f"Command timed out after {timeout} seconds.\n"
                f"Command: {command[:500]}"
            )

        exit_code = process.returncode or 0
        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

        output_parts = [f"Exit code: {exit_code}"]

        if stdout:
            output_parts.append(_truncate_output(stdout, "stdout"))
        if stderr:
            output_parts.append(_truncate_output(stderr, "stderr"))

        return "\n".join(output_parts)

    except FileNotFoundError as e:
        return f"Error: Command not found — {str(e)}"
    except Exception as e:
        log.exception("Unexpected error in bash tool")
        return f"Error executing command: {str(e)}"


def _truncate_output(text: str, label: str) -> str:
    """
    Truncate output to MAX_LINES lines or MAX_CHARS characters.
    """
    lines = text.splitlines()
    total_lines = len(lines)
    total_chars = len(text)

    truncated_lines = False
    truncated_chars = False

    if total_chars > MAX_CHARS:
        text = text[:MAX_CHARS]
        truncated_chars = True

    if total_lines > MAX_LINES:
        lines = text.splitlines()[:MAX_LINES]
        text = "\n".join(lines)
        truncated_lines = True

    result = f"--- {label} ({total_lines} lines, {total_chars} chars) ---\n{text}"

    if truncated_lines or truncated_chars:
        reasons = []
        if truncated_lines:
            reasons.append(f"{total_lines - MAX_LINES} lines removed")
        if truncated_chars:
            reasons.append(f"{total_chars - MAX_CHARS} chars removed")
        result += f"\n[Output truncated: {', '.join(reasons)}]"

    return result
