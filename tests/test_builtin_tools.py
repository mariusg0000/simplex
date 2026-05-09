"""
tests/test_builtin_tools.py · Unit tests for built-in tools · get_current_time.
"""

from src.tools.get_current_time import execute


def test_get_current_time():
    """Returns a string in datetime format."""
    result = execute()
    assert isinstance(result, str)
    parts = result.split(" ")
    assert len(parts) == 2
    assert len(parts[0].split("-")) == 3
    assert len(parts[1].split(":")) == 3
