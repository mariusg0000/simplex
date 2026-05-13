"""
src/tools/bash.py · Shell command execution tool with sandbox enforcement.
Executes shell commands, enforces working directory restrictions for sub-agents,
detects dangerous patterns, and supports user confirmation for destructive ops.
Depends on: asyncio.subprocess, ToolRegistry, storage (for working_directories config).
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

from src.engine.tools import registry

SCRIPTS_VENV = Path.home() / ".simplexai" / "scripts" / ".venv"
SCRIPTS_VENV_BIN = str(SCRIPTS_VENV / "bin")

log = logging.getLogger("simplex.tools.bash")

MAX_LINES = 500
MAX_CHARS = 50 * 1024
SENTINEL = "___EXEC_RESULTS___"

DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # (regex pattern, human-readable description of the risk)

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
    WHAT:    Scans a shell command against known dangerous patterns.
    WHY:     Prevents accidental data loss or system damage by flagging
             destructive operations (rm, dd, mkfs, fork bombs, etc.) in
             the DANGEROUS_PATTERNS list.
    HOW:     Normalises the command to lowercase, then regex-searches each
             pattern. Returns a concatenated description of all matches,
             or None if the command appears safe.
    PARAMS:  command: str — the raw shell command string
    RETURNS: Optional[str] — semicolon-joined descriptions of matched risks, or None
    """
    cmd_normalized = command.strip().lower()
    reasons = []
    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_normalized):
            reasons.append(description)
    return "; ".join(reasons) if reasons else None


def _truncate_output(text: str) -> str:
    """
    WHAT:    Truncates tool output to MAX_CHARS (50 KiB) with a notice.
    WHY:     LLM context windows are limited; unbounded command output would
             consume tokens and risk exceeding the model's limit.
    PARAMS:  text: str — raw command output
    RETURNS: str — truncated text (if needed) with truncation notice appended
    """
    total_chars = len(text)
    if total_chars > MAX_CHARS:
        text = text[:MAX_CHARS]
        text += f"\n[Output truncated: {total_chars - MAX_CHARS} chars removed]"
    return text


def get_description() -> dict:
    """
    WHAT:    Returns the OpenAI tool schema for the bash tool.
    WHY:     Required by ToolRegistry for dynamic discovery; defines the
             parameters the LLM may supply (command, explanation, timeout,
             workdir, need_confirmation).
    PARAMS:  none
    RETURNS: dict — tool schema with "command" and "explanation" as required
    """
    return {
        "description": "Execute a shell command and return its output (stdout + stderr combined). Output is truncated at 500 lines or 50 KB. Use this to run terminal commands, scripts, or system operations. Set need_confirmation=True for destructive commands.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "explanation": {
                    "type": "string",
                    "description": "Plain-language explanation of what this command does.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum execution time in seconds (default: 30, max: 120).",
                },
                "need_confirmation": {
                    "type": "boolean",
                    "description": "Set to True if the command could be destructive.",
                },
                "workdir": {
                    "type": "string",
                    "description": "Working directory for the command.",
                },
            },
            "required": ["command", "explanation"],
        },
    }


async def execute(command: str, explanation: str, timeout: int = 30, need_confirmation: bool = False, workdir: Optional[str] = None, _agent_params: dict = None) -> str:
    """
    WHAT:    Executes a shell command with sandbox enforcement and danger detection.
    WHY:     The LLM needs general-purpose shell access for file manipulation, code
             execution, and system operations. This tool provides that access while
             preventing damage via three layers: workdir sandboxing (sub-agents) or
             working_directories config (main agent), dangerous-command patterns, and
             optional user confirmation for destructive operations.
    HOW:     1. Resolves allowed directories from _agent_params (sub-agent) or
               storage.prefs.working_directories (main agent).
             2. Validates the requested workdir and detects > / >> redirects to
               absolute paths outside the allowed directories.
             3. Clamps timeout to [1, 120] seconds.
             4. Runs _check_dangerous() on the command; if matches are found or
               need_confirmation=True, fires the UI confirmation callback.
             5. Executes via asyncio.create_subprocess_shell with the custom venv
               PATH and a sentinel (___EXEC_RESULTS___) to capture exit codes.
             6. Decodes output, strips the sentinel line, truncates if needed.
    PARAMS:  command: str — the shell command to execute
             explanation: str — plain-language description (for user confirmation UI)
             timeout: int — max seconds (clamped to 1-120, default 30)
             need_confirmation: bool — if True, requires user approval before running
             workdir: str or None — working directory (must be within allowed dirs)
             _agent_params: dict or None — injected by ToolRegistry; carries work_dir
    RETURNS: str — stdout+stderr output, or error message, or success notice
    ERRORS:  workdir outside sandbox → "Error: workdir '...' is outside the allowed..."
             command writes outside sandbox → "Error: command writes to '...' outside..."
             command timed out → "Error: Command timed out..."
             command not found → "Error: Command not found — ..."
             user rejects → "User did not approve this operation..."
             execute exception → "Error executing command: {details}"
    """
    allowed_dirs: set[Path] | None = None
    is_sub_agent = _agent_params is not None

    if is_sub_agent:
        sub_work_dir = Path(_agent_params["work_dir"]).resolve()
        allowed_dirs = {sub_work_dir}
    else:
        from src.storage import storage
        raw_dirs = storage.prefs.working_directories
        if raw_dirs:
            allowed_dirs = {Path(d).expanduser().resolve() for d in raw_dirs}

    def _check_in_allowed(target: Path, label: str) -> str | None:
        """
        WHAT:    Checks whether a Path is inside any of the allowed directories.
        WHY:     Core of the sandbox enforcement — both workdir validation and
                 redirect-path inspection call this to reject out-of-bounds paths.
        HOW:     Uses Path.relative_to() against each allowed dir. If any returns
                 a relative path (no ValueError), the target is contained.
        PARAMS:  target: Path — the path to check
                 label: str — human-readable label for the error message
        RETURNS: str (error message) if outside, None if within allowed dirs
        """
        for ad in allowed_dirs:
            try:
                target.relative_to(ad)
                return None
            except ValueError:
                continue
        dirs_str = ", ".join(str(d) for d in allowed_dirs)
        return (
            f"Error: {label} '{target}' is outside the allowed "
            f"directory/directories ({dirs_str}). "
            f"{'All files must stay inside your session folder (' + str(list(allowed_dirs)[0]) + '). Use a relative path (e.g., cat > script.py << ...) or write to ' + str(list(allowed_dirs)[0]) + '/filename.' if is_sub_agent else 'Configure working directories in Settings.'}"
        )

    if allowed_dirs is not None:
        if workdir:
            requested = Path(workdir).resolve()
            err = _check_in_allowed(requested, "workdir")
            if err:
                return err
            workdir = str(requested)
        elif is_sub_agent:
            workdir = str(list(allowed_dirs)[0])

        def _inspect_path(target: str) -> str | None:
            """
            WHAT:    Detects if a file redirect target writes outside allowed dirs.
            WHY:     Best-effort sandbox enforcement — the LLM could bypass this
                     by using Python open() or mv inside a script, but catching
                     obvious shell-level redirects (> / >>) prevents the most
                     common escape vector.
            HOW:     Strips quotes, expands ~/, resolves absolute paths, and
                     checks containment via _check_in_allowed.
            PARAMS:  target: str — the argument after > or >>
            RETURNS: str (the offending path) if outside allowed dirs, else None
            """
            t = target.strip().strip("\"'")
            if t.startswith("~/"):
                t = str(Path.home() / t[2:])
            if t.startswith("/"):
                p = Path(t).resolve()
                err = _check_in_allowed(p, "command writes to")
                if err:
                    return str(p)
            return None

        parts = command.split()
        for i, token in enumerate(parts):
            if token in (">", ">>") and i + 1 < len(parts):
                off_limit = _inspect_path(parts[i + 1])
                if off_limit:
                    return (
                        f"Error: command writes to '{off_limit}' which is outside the "
                        f"allowed directory/directories ({', '.join(str(d) for d in allowed_dirs)}). "
                        f"{'All files must stay inside your session folder.' if is_sub_agent else 'Configure working directories in Settings.'}"
                    )
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
            return "User did not approve this operation. Stop and ask the user how to proceed."

    log.debug("Executing bash command (timeout=%ds): %s", timeout, command[:200])

    full_command = f"( {command} ); printf '\\n{SENTINEL}:%s\\n' \"$?\""

    try:
        env = os.environ.copy()
        env["PATH"] = f"{SCRIPTS_VENV_BIN}:{env['PATH']}"

        process = await asyncio.create_subprocess_shell(
            full_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
            cwd=workdir,
            env=env,
        )

        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return "Error: Command timed out. Avoid long-running or interactive commands."

        output = stdout.decode("utf-8", errors="replace").strip()

        sentinel_marker = f"{SENTINEL}:"
        if sentinel_marker not in output:
            return _truncate_output(output) if output else "Success: Command finished with no output."

        lines = output.rsplit("\n", 1)
        if len(lines) == 2:
            actual_output = lines[0].strip()
            exit_code_line = lines[1]
        else:
            actual_output = ""
            exit_code_line = lines[0]

        exit_code = exit_code_line.replace(sentinel_marker, "").strip()

        if not actual_output:
            if exit_code == "0":
                return "Success: Command finished with no output."
            return f"Command failed with exit code {exit_code}."

        return _truncate_output(actual_output)

    except FileNotFoundError as e:
        return f"Error: Command not found — {str(e)}"
    except Exception as e:
        log.exception("Unexpected error in bash tool")
        return f"Error executing command: {str(e)}"
