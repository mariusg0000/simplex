"""
src/engine/file_open.py · Open File tool · Opens files/URLs with the default system application.
Cross-platform: Linux (xdg-open), macOS (open), Windows (os.startfile).
Non-blocking — uses subprocess.Popen or os.startfile, returns immediately.
"""

import os
import platform
import subprocess

from src.engine.tools import tool


@tool
def open_file(path: str) -> str:
    """Open a file, directory, or URL with the default system application.
    Use when the user asks to open, view, or launch a file/document/folder/URL.
    This tool is non-blocking and works on all platforms (Linux, macOS, Windows).
    Do NOT use bash for this — use this tool instead."""
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(path)
        elif system == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return f"Opened with default application: {os.path.basename(path)}"
    except Exception as e:
        return f"Error opening {path}: {str(e)}"
