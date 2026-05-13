# Round Counter Tag & Max-Rounds Safety Net

## Sub-tasks
- Read current code in src/engine/agents.py (lines ~690-720) and src/engine/chat.py (lines ~120-340)
- Propose changes for agents.py: round tag (2a) + structured fallback (2b)
- Propose changes for chat.py: max_rounds param (3a) + round tag (3c) + max rounds check (3d/3e)
- Execute approved changes
- Verify with lint/typecheck
- Archive task

## Summary
Implemented plan `plans/2026-05-13_round_counter_and_max_rounds.md`:

### `src/engine/agents.py`
- **Round tag**: Appends `[Round X/Y]` to every tool result content (line 697-703), skipped on `_AGENT_DONE_` early-return path.
- **Structured fallback**: Replaced generic `"Error: Max rounds reached without final response."` with a detailed report including last assistant content, tool call counts per type, and a pointer to session folder.

### `src/engine/chat.py`
- **`max_rounds` parameter**: Added `max_rounds: int = 50` to `stream_chat()` signature (default 50, backward compatible).
- **Round tag**: Appends `[Round X/Y]` to tool result content (line 323-329).
- **Max rounds check**: After tool execution loop, if `round_num >= max_rounds`, yields error status + content events and breaks the loop.

### Verification
- All 64 existing tests pass.
- mypy shows no new errors (only pre-existing unrelated issues).
