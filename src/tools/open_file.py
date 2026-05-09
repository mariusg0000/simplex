import os
import platform
import subprocess


def get_description() -> dict:
    return {
        "description": "Open a file, directory, or URL with the default system application. Use when the user asks to open, view, or launch a file/document/folder/URL. Non-blocking, cross-platform.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file, directory, or URL to open.",
                },
            },
            "required": ["path"],
        },
    }


def execute(path: str) -> str:
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
