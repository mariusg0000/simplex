"""
tests/test_builtin_tools.py · Unit tests for built-in tools · get_current_time.
"""

from src.engine.builtin_tools import get_current_time


def test_get_current_time():
    """Returns a string in datetime format."""
    result = get_current_time()
    assert isinstance(result, str)
    parts = result.split(" ")
    assert len(parts) == 2
    assert len(parts[0].split("-")) == 3
    assert len(parts[1].split(":")) == 3
