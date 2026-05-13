"""
src/tools/task_done.py · Sub-agent task completion signal.
Terminates a sub-agent loop with an optional result, used exclusively by sub-agents.
Depends on: agent_params_ctx (ContextVar) for sandbox validation.
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
    """
    WHAT:    Validates the result path (if sub-agent) and signals completion.
    WHY:     Prevents LLM from hallucinating file paths; sandbox enforcement is
             checked before declaring the agent done. The _AGENT_DONE_ prefix is
             the contract that ToolCapableAgent.run() recognises as auto-terminate.
    HOW:     When _agent_params is present (sub-agent context), verifies the path
             is absolute, inside the session folder, and the file actually exists.
             On success returns _AGENT_DONE_:<result> to trigger auto-termination.
    PARAMS:  result: str — file path or summary of completed work
             _agent_params: dict or None — injected by ToolRegistry; carries work_dir
    RETURNS: str — _AGENT_DONE_:<result> on success, or an error message on failure
    ERRORS:  File outside session folder → plain error string (agent can retry)
             File not found → plain error string (agent can retry)
    """
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
