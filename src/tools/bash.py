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
    cmd_normalized = command.strip().lower()
    reasons = []
    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_normalized):
            reasons.append(description)
    return "; ".join(reasons) if reasons else None


def _truncate_output(text: str) -> str:
    total_chars = len(text)
    if total_chars > MAX_CHARS:
        text = text[:MAX_CHARS]
        text += f"\n[Output truncated: {total_chars - MAX_CHARS} chars removed]"
    return text


def get_description() -> dict:
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


async def execute(command: str, explanation: str, timeout: int = 30, need_confirmation: bool = False, workdir: Optional[str] = None) -> str:
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
