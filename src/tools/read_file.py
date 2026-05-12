from pathlib import Path

MAX_BYTES = 80_000


def get_description() -> dict:
    return {
        "description": "Read a file's contents. Limit: ~80KB (~20k tokens). Defaults to the current working file when no path is given.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file (optional — defaults to current working file).",
                },
            },
            "required": [],
        },
    }


async def execute(path: str = None, _agent_params: dict = None) -> str:
    """Read a file's contents (max ~80KB). Defaults to current agent working file.

    _agent_params (injected by engine via ContextVar):
        html_path (str): Fallback path used when no explicit path is given.
    """
    if _agent_params and not path:
        path = _agent_params.get("html_path")
    if not path:
        return "Error: no path provided and no html_path in agent params"

    fp = Path(path)
    if not fp.exists():
        return f"Error: file not found: {path}"
    if not fp.is_file():
        return f"Error: not a file: {path}"

    stat = fp.stat()
    if stat.st_size > MAX_BYTES:
        return (
            f"Error: file too large ({stat.st_size} bytes, max {MAX_BYTES}). "
            f"File: {path}"
        )

    content = fp.read_bytes()
    return content.decode("utf-8", errors="replace")
