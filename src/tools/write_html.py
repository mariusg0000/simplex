from pathlib import Path


def get_visibility() -> dict:
    return {"main_agent": False}


def get_description() -> dict:
    return {
        "description": "Write HTML content to the working file. Overwrites the existing file each time. Path is auto-managed via agent context.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The full HTML content with inline CSS to write.",
                },
            },
            "required": ["content"],
        },
    }


async def execute(content: str, _agent_params: dict = None) -> str:
    """Write HTML content to the agent-managed working file.
    
    _agent_params (injected by engine via ContextVar):
        html_path (str): Path to write the HTML file to.
    """
    html_path = _agent_params.get("html_path") if _agent_params else None
    if not html_path:
        return "Error: no html_path in agent params"

    fp = Path(html_path)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    return f"HTML written: {fp.name} ({len(content)} bytes)"
