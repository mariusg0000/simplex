"""
src/engine/builtin_tools.py · Built-in utility tools · Time utility for the LLM.
"""

from src.engine.tools import tool


@tool
def get_current_time():
    """Returns the current server time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
