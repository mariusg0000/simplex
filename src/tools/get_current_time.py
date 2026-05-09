from datetime import datetime


def get_description() -> dict:
    return {
        "description": "Returns the current server time.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    }


def execute() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
