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


async def execute(result: str) -> str:
    return result
