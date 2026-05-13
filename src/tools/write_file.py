"""
src/tools/write_file.py · Write content to a file with sandbox awareness.
When _agent_params contains work_dir, resolves relative filenames against the
session folder and rejects absolute paths. Without work_dir, main agent can
write anywhere.
Depends on: pathlib, _agent_params (ContextVar via ToolRegistry).
"""

from pathlib import Path

MAX_BYTES = 500_000


def get_description() -> dict:
    return {
        "description": (
            "Write content to a file. Sub-agents MUST use relative filenames "
            "(resolved against the session folder). Main agents can use absolute paths."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": (
                        "Relative filename (sub-agent) or absolute path (main agent). "
                        "Sub-agents MUST use relative names only (e.g., 'script.py')."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "The text content to write to the file.",
                },
            },
            "required": ["filename", "content"],
        },
    }


async def execute(filename: str, content: str, _agent_params: dict = None) -> str:
    """
    WHAT:    Writes content to a file with sandbox resolution.
    WHY:     Sub-agents must not see or construct absolute paths. This tool
             resolves relative filenames against work_dir automatically.
    HOW:     If _agent_params has work_dir, joins it with filename. Rejects
             absolute paths from sub-agents. Validates content size. Creates
             parent directories if needed.
    PARAMS:  filename: str — relative name (sub-agent) or absolute path (main agent)
             content: str — text to write
             _agent_params: dict or None — injected by ToolRegistry; carries work_dir
    RETURNS: str — confirmation with filename written
    ERRORS:  Absolute path from sub-agent, content too large, write failure
    """
    if _agent_params and "work_dir" in _agent_params:
        if Path(filename).is_absolute():
            return (
                f"Error: sub-agents cannot use absolute paths. "
                f"Use a relative filename (e.g., 'script.py')."
            )
        target = Path(_agent_params["work_dir"]) / filename
    else:
        target = Path(filename)

    if len(content.encode("utf-8")) > MAX_BYTES:
        return (
            f"Error: content too large ({len(content)} bytes, max {MAX_BYTES}). "
            f"Split into multiple files if needed."
        )

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Written {filename} ({len(content)} bytes)"
    except Exception as e:
        return f"Error writing {filename}: {e}"
