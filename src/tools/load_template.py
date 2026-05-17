from pathlib import Path

BUILTIN_DIR = Path(__file__).resolve().parent.parent / "templates"
CUSTOM_DIR = Path.home() / ".simplexai" / "templates"


def _list_templates() -> str:
    names: set[str] = set()
    for d in [CUSTOM_DIR, BUILTIN_DIR]:
        if d.is_dir():
            for f in d.iterdir():
                if f.suffix == ".md":
                    names.add(f.stem)
    if not names:
        return "(none)"
    return ", ".join(sorted(names))


def get_description() -> dict:
    available = _list_templates()
    return {
        "description": (
            "Load a document style template by name. Returns the full .md content "
            "with structure, typography, layout, and rules. "
            "Checks ~/.simplexai/templates/ first (custom), then built-in templates. "
            f"Available: {available}."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Template name (without .md extension). "
                        "Choose based on document type. "
                        f"Options: {available}."
                    ),
                },
            },
            "required": ["name"],
        },
    }


async def execute(name: str) -> str:
    if not name or "/" in name or ".." in name:
        return f"Error: invalid template name '{name}'."

    paths = [
        CUSTOM_DIR / f"{name}.md",
        BUILTIN_DIR / f"{name}.md",
    ]

    for path in paths:
        if path.is_file():
            return path.read_text(encoding="utf-8")

    available = _list_templates()
    return (
        f"Error: Template '{name}' not found in ~/.simplexai/templates/ "
        f"or built-in templates. Available: {available}."
    )
