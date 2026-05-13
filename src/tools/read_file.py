"""
src/tools/read_file.py · Read file contents with sandbox awareness.
When _agent_params contains work_dir, accepts relative filenames and resolves
them against the session folder. Without work_dir, requires an absolute path.
Depends on: pathlib, _agent_params (ContextVar via ToolRegistry).
"""

from pathlib import Path

MAX_BYTES = 80_000


def get_description() -> dict:
    return {
        "description": (
            "Read a file's contents. Limit: ~80KB (~20k tokens). "
            "When called by a sub-agent, accepts a relative filename "
            "(resolved against the session folder). Otherwise requires an absolute path."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": (
                        "Relative filename (sub-agent) or absolute path (main agent). "
                        "Sub-agents MUST use relative names only."
                    ),
                },
            },
            "required": ["filename"],
        },
    }


async def execute(filename: str, _agent_params: dict = None) -> str:
    """
    WHAT:    Reads file contents with sandbox resolution.
    WHY:     Sub-agents must not see absolute paths; this tool resolves
             relative filenames against work_dir when _agent_params is present.
             Main agents use absolute paths directly.
    HOW:     If _agent_params has work_dir, joins it with filename to get the
             absolute path. Otherwise treats filename as an absolute path.
             Validates existence, type, and size before reading.
    PARAMS:  filename: str — relative name (sub-agent) or absolute path (main agent)
             _agent_params: dict or None — injected by ToolRegistry; carries work_dir
    RETURNS: str — file content (UTF-8) or error message
    ERRORS:  File not found, not a file, too large, or no path provided
    """
    if _agent_params and "work_dir" in _agent_params:
        target = Path(_agent_params["work_dir"]) / filename
    else:
        target = Path(filename)

    if not target.exists():
        return f"Error: file not found: {filename}"
    if not target.is_file():
        return f"Error: not a file: {filename}"

    stat = target.stat()
    if stat.st_size > MAX_BYTES:
        return (
            f"Error: file too large ({stat.st_size} bytes, max {MAX_BYTES}). "
            f"File: {filename}"
        )

    content = target.read_bytes()
    return content.decode("utf-8", errors="replace")
