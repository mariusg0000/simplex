"""
src/tools/list_files.py · List files in the session folder with sandbox awareness.
When _agent_params contains work_dir, lists files in that directory. Without
work_dir, main agent can list any directory.
Depends on: pathlib, _agent_params (ContextVar via ToolRegistry).
"""

from pathlib import Path


def get_description() -> dict:
    return {
        "description": (
            "List files in a directory. Sub-agents see only their session folder. "
            "Main agents can specify any directory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Directory to list. Sub-agents MUST use '.' or omit this "
                        "(defaults to session folder). Main agents can use any path."
                    ),
                },
                "detail": {
                    "type": "boolean",
                    "description": (
                        "If True, include file sizes. Default: False (names only)."
                    ),
                },
            },
            "required": [],
        },
    }


async def execute(path: str = ".", detail: bool = False, _agent_params: dict = None) -> str:
    """
    WHAT:    Lists files in a directory with sandbox resolution.
    WHY:     Sub-agents must only see their session folder. This tool enforces
             that by ignoring any path argument from sub-agents.
    HOW:     If _agent_params has work_dir, forces listing of that directory
             regardless of the path argument. Otherwise uses the provided path.
             Returns filenames or filenames with sizes based on detail flag.
    PARAMS:  path: str — directory to list (ignored for sub-agents)
             detail: bool — include file sizes
             _agent_params: dict or None — injected by ToolRegistry; carries work_dir
    RETURNS: str — newline-separated file listing or error message
    ERRORS:  Directory not found, not a directory, listing failure
    """
    if _agent_params and "work_dir" in _agent_params:
        target = Path(_agent_params["work_dir"])
    else:
        target = Path(path)

    if not target.exists():
        return f"Error: directory not found: {path}"
    if not target.is_dir():
        return f"Error: not a directory: {path}"

    try:
        entries = sorted(target.iterdir())
        if not entries:
            return "(empty directory)"

        lines = []
        for entry in entries:
            if detail:
                size = entry.stat().st_size if entry.is_file() else 0
                lines.append(f"{'[dir]' if entry.is_dir() else '[file]':5s} {size:>10,}  {entry.name}")
            else:
                prefix = "d " if entry.is_dir() else "  "
                lines.append(f"{prefix}{entry.name}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error listing {path}: {e}"
