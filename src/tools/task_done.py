from pathlib import Path


def get_visibility() -> dict:
    return {"main_agent": False}


def get_description() -> dict:
    return {
        "description": "Signal task completion. Call this when your task is finished, passing the result (e.g. file path).",
        "parameters": {
            "type": "object",
            "properties": {
                "result": {
                    "type": "string",
                    "description": "The result of the task, typically a file path or summary.",
                },
            },
            "required": ["result"],
        },
    }


async def execute(result: str, _agent_params: dict = None) -> str:
    if _agent_params and "work_dir" in _agent_params:
        result_path = Path(result)
        if result_path.is_absolute():
            work_dir = _agent_params["work_dir"]
            try:
                result_path.relative_to(Path(work_dir))
            except ValueError:
                return (
                    f"Error: File '{result}' is outside the session folder "
                    f"'{work_dir}'. Create files only inside your workspace."
                )
            if not result_path.is_file():
                return (
                    f"Error: File not found at '{result}'. "
                    f"Verify the file was created successfully before calling task_done."
                )
    return f"_AGENT_DONE_: {result}"
