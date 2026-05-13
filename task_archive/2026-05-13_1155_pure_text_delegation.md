# Fix: create_doc becomes pure text-to-document generator

## Subtasks
- Rewrite agent_description — only inline text, no file paths
- Rewrite role_prompt — pure generator, 3 bash calls max
- Rewrite WORKFLOW — 3 steps: WRITE→WEASYPRINT→DONE
- Rewrite LIBRARY REFERENCE — only weasyprint + docx + xlsx
- Update state.py rule #5 — no file paths
- Commit, push

## Summary
Fundamental architecture change. Previously the main agent passed file paths to
reference documents, which made create_doc re-analyze them with fitz. Now:

- Main agent extracts ALL text and layout info itself (using its own analysis)
- Main agent passes ONLY inline text (description + content) to create_doc
- NO file paths anywhere
- create_doc is a PURE GENERATOR: receives inline text, writes HTML, weasyprint, done
- Max 3 bash calls
- Same pattern for DOCX and XLSX

### Files changed
- src/agents/create_doc.md: Complete rewrite (91 lines from 123, -32)
- src/ui/state.py:233-235: Simplified rule #5
