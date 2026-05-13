# Document Python source files (docstrings + cleanup)

## Sub-tasks
- Document tools.py
- Document bash.py
- Document chat.py (+ cleanup inline *what* comments)
- Archive, commit, push

## Summary
Added structured WHAT/WHY/HOW/PARAMS/RETURNS/ERRORS docstrings to 4 Python files and cleaned up inline *what* comments.

### src/engine/tools.py
- File header with dependencies
- agent_params_ctx ContextVar documented
- _make_async_wrapper(), ToolRegistry (class + all methods), tool() decorator — all with full docstrings
- _discover() docstring replaces inline "Optional per-tool visibility declaration" comment

### src/tools/bash.py
- File header with dependencies
- DANGEROUS_PATTERNS list header comment
- _check_dangerous(), _truncate_output(), get_description(), execute() — all with full docstrings
- Inner functions _check_in_allowed() and _inspect_path() documented
- Removed 1 *what* comment ("Determine allowed directories for write operations")

### src/engine/chat.py
- File header with dependencies
- _debug(), _truncate_json() docstrings updated
- stream_chat() full WHAT/WHY/HOW/PARAMS/RETURNS/ERRORS docstring
- Removed 8 inline *what* comments from stream_chat (section markers like "Handle reasoning", "Count input tokens", etc.)
- Kept 2 *why* comments (finish_reason API behavior, provider content-null requirement)
- Cleaned up sanitize_messages() inline comments (removed 3 *what* markers, condensed the provider note)

### src/tools/task_done.py
- Already partially documented in previous commit; minor polish added.
