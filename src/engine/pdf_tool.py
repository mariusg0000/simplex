"""
src/engine/pdf_tool.py · PdfAgent + create_pdf tool · Specialized PDF generation via weasyprint.
"""

from typing import Optional
from src.engine.tools import tool
from src.engine.agents import ToolCapableAgent, activity_callback

_PDF_ROLE_PROMPT = (
    "You are a PDF generation specialist. You ONLY create PDFs using weasyprint.\n"
    "\n"
    "WORKFLOW:\n"
    "1. Write HTML with inline CSS\n"
    "2. Convert: weasyprint input.html output.pdf\n"
    "3. Parse stderr for warnings, fix CSS, retry (max 10)\n"
    "4. Validate output file exists (ls -la)\n"
    "5. Return absolute path\n"
    "\n"
    "WRITING FILES:\n"
    "- Use heredoc in bash: cat > file.html << 'EOF' ... EOF\n"
    "- Save in working directory (~/.simplexai/)\n"
    "\n"
    "INSTALLING:\n"
    "- pip via scripts/.venv/bin/pip\n"
    "\n"
    "RULES:\n"
    "- Always validate the PDF after creation (ls -la)\n"
    "- If warnings persist after 10 retries, return the best attempt\n"
    "- Return ONLY the absolute path, nothing else"
)

_pdf_agent_instance = None


def _get_pdf_agent() -> ToolCapableAgent:
    global _pdf_agent_instance
    if _pdf_agent_instance is None:
        _pdf_agent_instance = ToolCapableAgent(
            name="PdfAgent",
            role_prompt=_PDF_ROLE_PROMPT,
            allowed_tools=["bash"],
            allowed_cli=["weasyprint", "pandoc_write"],
        )
    return _pdf_agent_instance


@tool
async def create_pdf(description: str, reference_pdf: Optional[str] = None) -> str:
    """
    Generate a PDF document. Uses weasyprint internally.
    Args:
        description: Detailed description of the PDF content, layout, and formatting.
        reference_pdf: Optional path to a previously generated PDF for revision.
    Returns:
        Absolute path to the generated PDF file.
    """
    agent = _get_pdf_agent()
    task = description
    if reference_pdf:
        task = f"{description}\n\nPrevious attempt was at {reference_pdf}. Read the file and fix the issues."

    on_step = activity_callback.get()
    return await agent.run(task, on_step=on_step)
