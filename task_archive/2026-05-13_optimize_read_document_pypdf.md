# Task: Optimize read_document limit + install pypdf

## Sub-tasks
- Modify read_document: raise char limit from 10K to 50K
- Install pypdf in scripts venv (~/.simplexai/scripts/.venv)

## Summary
Increased `MAX_CHARS` from 10,000 to 50,000 in `read_document.py` so
analyze_doc agent can retrieve full PDF/DOCX text in a single call, avoiding
multi-step Python script workarounds. Installed `pypdf` in the scripts venv
so `run_python` scripts from sub-agents can import it without fallback to PyPDF2.

## Files changed
- `src/tools/read_document.py` — `MAX_CHARS = 10000` → `50000`
- `~/.simplexai/scripts/.venv` — installed `pypdf==6.11.0`
