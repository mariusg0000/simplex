# Fix: agent stuck on PDF creation / delegation

## Subtasks
- Analiză root cause — de ce s-a blocat agentul
- Fix: json.loads() neprotejat în chat.py (JSONDecodeError)
- Fix: regulă delegare în system prompt (state.py)
- Archive, commit, push

## Summary

Investigated why the agent got stuck ("s-a blocat") when asked to create a fictional CV PDF. Found two root causes:

1. **Crash on malformed tool call JSON** (`chat.py:305`): The main agent tried to create the PDF directly using `bash` with a massive heredoc containing the Python script. The heredoc JSON arguments were malformed (unescaped quotes/backslashes in the Python code), causing `json.loads()` to throw `JSONDecodeError`. Unlike the sub-agent (`agents.py:670-674`), `chat.py` had NO try/except around `json.loads()`, so the exception crashed `stream_chat()` silently — no error logged, no tool result returned.

2. **No delegation instruction** (`state.py`): The main agent had `create_doc` available as a callable function but chose to use `bash` directly because the system prompt didn't explicitly instruct it to delegate document creation tasks.

## Key decisions
- Added try/except JSONDecodeError around `json.loads()` in `chat.py:305-310` (mirrors `agents.py:670-674`)
- Added strategic guideline #5 in `state.py:233-234`: "DELEGATE TO AGENTS: ... use `create_doc` for any DOCX/XLSX/PDF document generation — do NOT create documents directly with bash/Python"
