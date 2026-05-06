"""
tests/test_builtin_tools.py · Unit tests for built-in tools · get_current_time, calculator.
"""

from src.engine.builtin_tools import get_current_time, calculator


def test_get_current_time():
    """Returns a string in datetime format."""
    result = get_current_time()
    assert isinstance(result, str)
    # Format: YYYY-MM-DD HH:MM:SS
    parts = result.split(" ")
    assert len(parts) == 2
    assert len(parts[0].split("-")) == 3
    assert len(parts[1].split(":")) == 3


def test_calculator_simple():
    """Basic arithmetic works."""
    assert calculator("2 + 3") == "5"
    assert calculator("10 / 2") == "5.0"


def test_calculator_invalid():
    """Invalid expression returns error message."""
    result = calculator("undefined_var")
    assert "Error" in result


def test_calculator_no_builtins():
    """Built-in functions are not accessible."""
    result = calculator("__import__('os').system('echo')")
    assert "Error" in result
