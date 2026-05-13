# Fix: Hard STOP on create_doc re-analyzing PDFs with fitz

## Subtasks
- Hard rule in role_prompt: ABSOLUTELY FORBIDDEN to use fitz
- Removed fitz from library reference entirely
- agent_description now tells main agent to prepend FORBIDDEN line in task
- state.py regula #5 updated with prepend instruction

## Summary
Previous fix was insufficient — create_doc agent still analyzed PDFs with fitz
despite being told "do not re-analyze". The prompt instruction was too weak.

### Changes
1. **agent_description** (create_doc.md:14-15): Now tells main agent to
   prepend "FORBIDDEN: do NOT use fitz/python3/bash to read or analyze any
   PDF file." at the start of every task.

2. **role_prompt** (create_doc.md:26-34): Added RIGID RULE box at very top:
   "ABSOLUTELY FORBIDDEN — Do NOT use fitz, pymupdf, python3, or any bash
   command to read/analyze/extract/verify any PDF file."

3. **TOOL SELECTION** (create_doc.md:36-39): Removed fitz from priority list.
   Only weasyprint, python-docx, openpyxl remain.

4. **LIBRARY REFERENCE** (create_doc.md:67-99): Removed entire pymupdf/fitz
   section. Only weasyprint, python-docx, openpyxl shown.

5. **RULES** (create_doc.md:101-107): Added "FORBIDDEN: any use of fitz,
   pymupdf, or `python3 -c "import fitz"`." Reduced max calls from 8 to 6.

6. **state.py:233-237**: Updated strategic guideline #5 to include the
   prepend instruction that main agent must put in every create_doc task.

### Key decisions
- Agent sees fitz ONLY in prohibition contexts — no code example, no
  library section, no usage pattern
- Main agent is told to prepend a direct prohibition command in the task
  itself (not just in the system prompt)
- Task-level instructions override general role_prompt guidelines
