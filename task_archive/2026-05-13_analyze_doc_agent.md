# Task: Implement analyze_doc agent

## Sub-tasks
- Create analyze_doc agent definition file
- Update agent description references if needed
- Archive task

## Summary
Created a new `analyze_doc` agent specialized in document analysis — summarization, data extraction, inspection, and querying of PDF, DOCX, XLSX, TXT, MD files. It receives the absolute file path in the task from the main agent, uses `read_document` for initial 10K char reading, and falls back to `run_python` with pypdf/python-docx/pandas for deeper analysis.

### Key decisions
- Named `analyze_doc` (not `extract_doc`) to cover both extraction and summarization use cases
- Receives absolute path in task description; `read_document` works with absolute paths (no work_dir support needed)
- Falls back to `run_python` for documents larger than 10K chars
- Auto-discovered by AgentRegistry from src/agents/ — no code changes needed

### Files changed
- src/agents/analyze_doc.md — new agent
