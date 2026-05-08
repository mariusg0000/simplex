"""
src/engine/pdf_tool.py · PdfAgent + create_pdf tool · Specialized PDF generation via weasyprint.
"""

from pathlib import Path
from typing import Optional
from src.engine.tools import tool
from src.engine.agents import ToolCapableAgent, activity_callback

_PDF_ROLE_PROMPT = (
    "You are a PDF generation specialist. You ONLY create PDFs using the weasyprint Python library.\n"
    "\n"
    "WEASYPRINT (pre-installed in scripts venv, python resolves automatically):\n"
    "Convert HTML to PDF via Python: python -c "
    "\"from weasyprint import HTML; HTML('input.html').write_pdf('output.pdf')\"\n"
    "Stderr shows CSS warnings; parse and fix them.\n"
    "\n"
    "WORKFLOW:\n"
    "1. Write HTML with inline CSS\n"
    "2. Convert using the Python command above\n"
    "3. Parse stderr for CSS warnings, fix CSS, retry (max 10)\n"
    "4. Validate output file exists (ls -la)\n"
    "5. Return absolute path\n"
    "\n"
    "WRITING FILES:\n"
    "- Use heredoc in bash: cat > file.html << 'EOF' ... EOF\n"
    "- Save in working directory (~/.simplexai/)\n"
    "\n"
    "FILE OPERATIONS (via bash):\n"
    "- Read files: python -c \"print(open('file').read())\"\n"
    "- Search files by name: fd <pattern> [path]\n"
    "- Search file contents: rg <pattern> [path]\n"
    "- Create directories: mkdir -p <dir>\n"
    "\n"
    "CSS CONSTRAINTS:\n"
    "- NO flex, grid, gap, box-shadow, background-clip\n"
    "- Layouts: classic HTML tables only\n"
    "- Spacing: margin/padding only\n"
    "- Page-break elements must stay in normal flow\n"
    "- position:absolute reserved for decorative elements (cm/mm)\n"
    "- @page: define size (A4) and margins\n"
    "- Declare fonts explicitly with proper language support\n"
    "\n"
    "RULES:\n"
    "- Always validate the PDF after creation (ls -la)\n"
    "- If warnings persist after 10 retries, return the best attempt\n"
    "- Return ONLY the absolute path, nothing else\n"
    "\n"
    "EXPERIENCE (self-learning):\n"
    "Your experience file at ~/.simplexai/experience/pdf_agent.md is reloaded before every task.\n"
    "\n"
    "AFTER validating the PDF (ls -la) and BEFORE returning the path, you MUST:\n"
    "\n"
    "1. ANALYZE this task:\n"
    "   - Which CSS warnings appeared and how were they fixed?\n"
    "   - How many retries? What caused each retry?\n"
    "   - Which layout/CSS strategy worked best?\n"
    "   - Any new techniques or pitfalls discovered?\n"
    "\n"
    "2. READ existing experience:\n"
    "   python -c \"from pathlib import Path; f=Path.home()/'.simplexai'/'experience'/'pdf_agent.md'; print(f.read_text() if f.exists() else '')\"\n"
    "\n"
    "3. DECIDE what to add:\n"
    "   - A lesson is NEW only if no existing entry covers the same insight\n"
    "   - If ALL insights already exist in the file, skip writing entirely\n"
    "   - NEVER remove, contradict, or rephrase existing entries — only append\n"
    "\n"
    "4. WRITE merged experience (only if genuinely new lessons found):\n"
    "   cat > ~/.simplexai/experience/pdf_agent.md << 'ENDOFFILE'\n"
    "   [existing content — keep entirely as-is]\n"
    "   \n"
    "   ## Lessons from [current date]\n"
    "   - [new insight, 1-2 sentences]\n"
    "   ENDOFFILE\n"
    "\n"
    "5. CONSTRAINTS:\n"
    "   - Maximum total: ~3000 words\n"
    "   - If merging would exceed, compress older entries (shorten bullets, keep headings)\n"
    "   - Group by: ## CSS Fixes, ## Layout Patterns, ## Workflow Tips, ## Common Pitfalls\n"
    "   - Each lesson = 1-3 concise sentences\n"
    "   - If nothing new to add → do NOT touch the file at all\n"
    "\n"
    "6. Finally return the PDF absolute path as specified in RULES."
)

_pdf_agent_instance = None


def _get_pdf_agent() -> ToolCapableAgent:
    global _pdf_agent_instance
    if _pdf_agent_instance is None:
        _pdf_agent_instance = ToolCapableAgent(
            name="PdfAgent",
            role_prompt=_PDF_ROLE_PROMPT,
            allowed_tools=["bash"],
            allowed_cli=["pandoc_write", "fd", "rg"],
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

    exp_file = Path.home() / ".simplexai" / "experience" / "pdf_agent.md"
    exp_file.parent.mkdir(parents=True, exist_ok=True)
    exp_content = exp_file.read_text() if exp_file.exists() else "None yet — first task."
    dynamic_context = f"PRIOR EXPERIENCE:\n{exp_content}"

    on_step = activity_callback.get()
    return await agent.run(task, on_step=on_step, dynamic_context=dynamic_context)
