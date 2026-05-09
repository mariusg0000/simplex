"""
tests/test_doc_reader.py · Unit tests for document reader · Verifies format support.
"""

import pytest
from pathlib import Path
from src.tools.read_document import execute


def test_read_txt_file(tmp_path):
    """Reads a .txt file."""
    f = tmp_path / "test.txt"
    f.write_text("Hello world")
    result = execute(str(f))
    assert "Hello world" in result
    assert "Content of test.txt" in result


def test_read_md_file(tmp_path):
    """Reads a .md file."""
    f = tmp_path / "readme.md"
    f.write_text("# Title\nContent")
    result = execute(str(f))
    assert "# Title" in result


def test_read_python_file(tmp_path):
    """Reads a .py file."""
    f = tmp_path / "script.py"
    f.write_text("print('hello')")
    result = execute(str(f))
    assert "print('hello')" in result


def test_file_not_found():
    """Non-existent file returns error."""
    result = execute("/nonexistent/file.txt")
    assert "Error: File not found" in result


def test_empty_file(tmp_path):
    """Empty file returns appropriate message."""
    f = tmp_path / "empty.txt"
    f.write_text("")
    result = execute(str(f))
    assert "empty" in result.lower()


def test_unsupported_format(tmp_path):
    """Unsupported format returns error."""
    f = tmp_path / "image.png"
    f.write_text("fake binary")
    result = execute(str(f))
    assert "unsupported" in result.lower()
