"""
src/tools/task_done.py · Sub-agent task completion signal.
Terminates a sub-agent loop with an optional result. When _agent_params contains
work_dir, resolves relative filenames against the session folder and validates
the file exists. Without work_dir, accepts any result string.
Depends on: pathlib, _agent_params (ContextVar via ToolRegistry).
"""

from pathlib import Path


def get_visibility() -> dict:
    return {"main_agent": False}


def get_description() -> dict:
    """
    WHAT:    Returns the OpenAI tool schema for the LLM.
    WHY:     Required by ToolRegistry for dynamic discovery; the LLM uses the schema to
             understand when and how to call task_done.
    PARAMS:  none
    RETURNS: dict — tool schema with "result" parameter
    """
    return {
        "description": (
            "Signal task completion. Call this when your task is finished, "
            "passing the result filename (relative, e.g., 'output.pdf')."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "result": {
                    "type": "string",
                    "description": (
                        "The result of the task — a relative filename "
                        "(e.g., 'output.pdf') or a short summary."
                    ),
                },
            },
            "required": ["result"],
        },
    }


async def execute(result: str, _agent_params: dict = None) -> str:
    """
    WHAT:    Validates the result file (if sub-agent) and signals completion.
    WHY:     Prevents LLM from hallucinating file paths. When _agent_params is
             present (sub-agent context), resolves the relative filename against
             work_dir and verifies the file exists. On success returns
             _AGENT_DONE_:<result> to trigger auto-termination.
    HOW:     If _agent_params has work_dir, joins it with result to get the
             absolute path. Validates the file exists inside the session folder.
             Without work_dir, accepts any result string.
    PARAMS:  result: str — relative filename or summary of completed work
             _agent_params: dict or None — injected by ToolRegistry; carries work_dir
    RETURNS: str — _AGENT_DONE_:<result> on success, or an error message on failure
    ERRORS:  File outside session folder → plain error string (agent can retry)
             File not found → plain error string (agent can retry)
    """
    if _agent_params and "work_dir" in _agent_params:
        result_path = Path(result)

        if result_path.is_absolute():
            return (
                f"Error: sub-agents must use relative filenames. "
                f"Use just the filename (e.g., 'output.pdf')."
            )

        work_dir = _agent_params["work_dir"]
        full_path = Path(work_dir) / result_path

        try:
            full_path.relative_to(Path(work_dir))
        except ValueError:
            return (
                f"Error: File '{result}' resolves outside the session folder "
                f"'{work_dir}'. Create files only inside your workspace."
            )

        if not full_path.is_file():
            return (
                f"Error: File not found at '{result}'. "
                f"Verify the file was created successfully before calling task_done."
            )

    return f"_AGENT_DONE_: {result}"
