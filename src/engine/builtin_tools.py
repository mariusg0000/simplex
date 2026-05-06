"""
src/engine/builtin_tools.py · Built-in utility tools · Time and calculator for the LLM.
"""

from src.engine.tools import tool


@tool
def get_current_time():
    """Returns the current server time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
def calculator(expression: str):
    """Evaluates a simple mathematical expression."""
    try:
        return str(eval(expression, {"__builtins__": None}, {}))
    except Exception as e:
        return f"Error: {str(e)}"
