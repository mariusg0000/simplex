# Fix create_doc agent bugs

## Sub-tasks
- Fix 1: Replace {work_dir} placeholder in role_prompt (agents.py)
- Fix 2: Fail fast if execute_script fails (agents.py)
- Fix 3: Validate result file exists in task_done + remove done_tool shortcut (task_done.py, agents.py)
- Fix 4: Remove stale read_file/read_document reference (create_doc.md)
- Verify: run tests

## Summary
Analyzed the create_doc agent's full execution flow and identified 8 issues. Fixed the 4 most impactful:

1. **{work_dir} not replaced**: The role_prompt had literal `{work_dir}` placeholders that were never substituted. Added resolution logic in `agents.py:call()` — after execute_script sets up the session folder, `{work_dir}` is replaced with the actual path via `str.replace()`, and the resolved prompt is passed to `ToolCapableAgent`.

2. **Execute_script failure → no sandbox**: When the subprocess failed, `params_dict` stayed None and the agent ran without `_agent_params` → bash tool had no sandbox enforcement. Added early return of `"Error: Failed to initialize agent workspace: ..."` in both the non-zero exit and exception branches.

3. **task_done didn't validate output**: Removed the special-case done_tool interception in `ToolCapableAgent.run()` that short-circuited before `registry.call()`. Now `task_done` goes through the normal tool execution path. Added file existence and work_dir containment validation in `task_done.execute()`. On success it returns `_AGENT_DONE_: <path>` to auto-terminate via the existing `_AGENT_DONE_` handler.

4. **Stale tool reference in role_prompt**: `create_doc.md` line 84 told the agent to use `read_file`/`read_document` which aren't in `allowed_tools`. Replaced with bash-native alternatives (`cat`, `python3` one-liner).

All 64 tests pass.
