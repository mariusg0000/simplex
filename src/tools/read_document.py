from pathlib import Path
from pypdf import PdfReader
from docx import Document
import pandas as pd

MAX_CHARS = 50000


def _read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read(MAX_CHARS)


def _read_pdf(path: Path) -> str:
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
        if len(text) > MAX_CHARS:
            break
    return text[:MAX_CHARS]


def _read_docx(path: Path) -> str:
    doc = Document(path)
    text = "\n".join([para.text for para in doc.paragraphs])
    return text[:MAX_CHARS]


def _read_excel(path: Path) -> str:
    df = pd.read_excel(path, nrows=50)
    return df.to_string()


def get_description() -> dict:
    return {
        "description": "Reads the text content of a document. Supports .txt, .md, .pdf, .docx, .xlsx. Use this to understand the content of a file. Sub-agents MUST use relative filenames (resolved against the session folder). Main agents can use absolute paths.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative filename (sub-agent) or absolute path (main agent). Sub-agents MUST use relative names only.",
                },
            },
            "required": ["file_path"],
        },
    }


async def execute(file_path: str, _agent_params: dict = None) -> str:
    if _agent_params and "work_dir" in _agent_params:
        if Path(file_path).is_absolute():
            return (
                f"Error: sub-agents cannot use absolute paths. "
                f"Use a relative filename (e.g., 'contract.docx')."
            )
        path = Path(_agent_params["work_dir"]) / file_path
    else:
        path = Path(file_path)

    if not path.exists():
        return f"Error: File not found at {file_path}"

    ext = path.suffix.lower()
    try:
        if ext in (".txt", ".md", ".py", ".json", ".yaml", ".yml"):
            content = _read_text(path)
        elif ext == ".pdf":
            content = _read_pdf(path)
        elif ext == ".docx":
            content = _read_docx(path)
        elif ext in (".xlsx", ".xls"):
            content = _read_excel(path)
        else:
            return f"Error: Unsupported file format '{ext}'"

        if not content.strip():
            return "The file appears to be empty."

        return f"--- Content of {path.name} ---\n{content}\n--- End of Content ---"

    except Exception as e:
        return f"Error reading file {path.name}: {str(e)}"
