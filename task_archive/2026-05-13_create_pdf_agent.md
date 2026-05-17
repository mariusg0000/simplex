# Task: Create create_pdf agent with generate_pdf auto-terminating tool

## Sub-tasks
- Create generate_pdf.py tool with auto-termination on success
- Create create_pdf.md agent with strict 4-step flow
- Verify tool exports and syntax

## Summary
Split PDF generation into a dedicated create_pdf agent with a generate_pdf
tool that auto-terminates on success, eliminating the excessive planning/
thinking rounds consumed by the original create_doc agent.

### Key decisions
- generate_pdf returns _AGENT_DONE_ with JSON on success — no task_done needed
- On failure, returns error details so agent can fix and retry once
- Agent has list_files and read_file for revision scenarios
- create_doc.md left unchanged (only trailing newline cleanup)

### Files changed
- src/agents/create_pdf.md — new agent
- src/tools/generate_pdf.py — new tool
- src/agents/create_doc.md — minor whitespace cleanup

### Commit
c71ee0e — feat: add create_pdf agent with generate_pdf auto-terminating tool
