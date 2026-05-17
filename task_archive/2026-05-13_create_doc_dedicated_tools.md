# Task: Replace bash with dedicated tools for create_doc agent

## Sub-tasks
- Modify read_file.py to accept relative filenames when work_dir is present
- Create write_file.py tool
- Create list_files.py tool
- Create run_python.py tool
- Create html_to_pdf.py tool
- Update create_doc.md with new allowed_tools and workflow
- Update task_done.py to handle relative filenames from sub-agents
- Verify linting and consistency

## Summary
Replaced the bash tool with 6 dedicated, sandbox-aware tools for the create_doc
sub-agent. The agent now works exclusively with relative filenames and never
sees absolute paths.

### Key decisions
- All new tools follow the _agent_params pattern: when work_dir is present,
  resolve relative filenames against it; when absent, allow absolute paths
  for the main agent
- html_to_pdf resolves weasyprint from ~/.simplexai/scripts/.venv via sys.path
  instead of using subprocess — no system installation needed
- Removed fitz restriction from RULES — agent may use fitz/pymupdf if needed
- task_done validates relative filenames against work_dir and verifies file
  exists before completing

### Files changed
- src/agents/create_doc.md — rewritten with new allowed_tools, workflow, rules
- src/tools/read_file.py — modified to support relative filenames with work_dir
- src/tools/task_done.py — modified to validate relative filenames
- src/tools/write_file.py — new tool
- src/tools/list_files.py — new tool
- src/tools/run_python.py — new tool
- src/tools/html_to_pdf.py — new tool

### Commit
e794da4 — feat: replace bash with dedicated tools for create_doc agent
