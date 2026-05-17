from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def get_description() -> dict:
    return {
        "description": (
            "Load a document style template by name. Returns the full .md content "
            "with structure, typography, layout, and rules. "
            "Use this at the start of PDF/doc creation to set the document style. "
            "Available templates: invoice, report, letter, certificate, simple."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Template name (without .md extension). "
                        "Choose based on document type. "
                        "Options: invoice, report, letter, certificate, simple."
                    ),
                },
            },
            "required": ["name"],
        },
    }


async def execute(name: str) -> str:
    path = TEMPLATES_DIR / f"{name}.md"
    if not path.exists():
        return (
            f"Error: Template '{name}' not found. "
            f"Available: invoice, report, letter, certificate, simple."
        )
    if not path.is_file():
        return f"Error: '{name}' is not a file."

    content = path.read_text(encoding="utf-8")
    return content
