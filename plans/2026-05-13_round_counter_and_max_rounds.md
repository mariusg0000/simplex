# Round Counter Tag & Max-Rounds Safety Net

## Problem

1. **Sub-agents** hit the hard `max_rounds=20` limit (`agents.py:446`) and return a useless error string `"Error: Max rounds reached without final response."` — the main agent/user gets no insight into what was attempted.
2. **Both agents** give the LLM zero visibility into how many LLM+tool cycles remain, so the LLM cannot pace its decisions.
3. **Main agent** has no max-rounds limit at all (`chat.py:159`: `while True:`), making it vulnerable to infinite loops.

## Solution

**A.** Append a round-counter tag to every tool result so the LLM sees its progress toward the limit.
**B.** For sub-agents: when max_rooms is exhausted, return a structured summary of what was attempted, not a generic error.
**C.** For main agent: add a configurable `max_rounds` parameter + structured fallback exit.

---

## 1. The Round Tag Format

```
\n\n[Round {current}/{max}]
```

Minimal, single line, low token cost. Appended to the tool result's `content` field before it enters the conversation history.

### Question: why `content` and not the field `round_tag`?

The LLM only sees `content` in tool messages. A separate field would be stripped by `sanitize_messages()`. Appending to `content` is the only way to make it visible to the model.

---

## 2. Sub-Agent Changes — `src/engine/agents.py`

### 2a. Append round tag (line 697-702)

**Current:**
```python
self.messages.append({
    "role": "tool",
    "tool_call_id": tc["id"],
    "name": name,
    "content": result_str,
})
```

**New:**
```python
round_tag = f"\n\n[Round {round_num}/{self.max_rounds}]"
self.messages.append({
    "role": "tool",
    "tool_call_id": tc["id"],
    "name": name,
    "content": result_str + round_tag,
})
```

No change to the `_AGENT_DONE_` early‑return path (line 695) — the tag is intentionally excluded because the agent is signalling completion, not continuing.

The fallback prompt at lines 706-708 increments `self.max_rounds` to 21, so after that point the tag reads `[Round X/21]`.

### 2b. Structured fallback when max_rounds exhausted (line 715-718)

**Current:**
```python
log.error("! %s exhausted all %d rounds", self.name, self.max_rounds)
msg = "Error: Max rounds reached without final response."
if on_step:
    on_step(AgentStep(self.name, self.max_rounds, "error", msg))
return msg
```

**New:** build a report from the conversation history:
```python
log.error("! %s exhausted all %d rounds", self.name, self.max_rounds)

# Extract last assistant content
last_content = ""
for m in reversed(self.messages):
    if m["role"] == "assistant" and m.get("content"):
        last_content = m["content"][:300]
        break

# Count tool calls by name
tool_counts: dict[str, int] = {}
for m in self.messages:
    if m["role"] == "assistant" and m.get("tool_calls"):
        for tc in m["tool_calls"]:
            name = tc["function"]["name"]
            tool_counts[name] = tool_counts.get(name, 0) + 1

tool_summary = ", ".join(f"{k} x{v}" for k, v in tool_counts.items()) or "(none)"

report = (
    f"[AGENT: {self.name}] Max rounds ({self.max_rounds}) reached. "
    f"Tool calls made: {tool_summary}. "
    f"Last response: {last_content or '(empty)'}. "
    f"[Partial results may exist in the session folder.]"
)
if on_step:
    on_step(AgentStep(self.name, self.max_rounds, "error", report))
return report
```

---

## 3. Main Agent Changes — `src/engine/chat.py`

### 3a. Add `max_rounds` parameter (line 126)

**Current:**
```python
async def stream_chat(messages: List[Dict[str, str]]) -> AsyncIterable[Dict[str, str]]:
```

**New:**
```python
async def stream_chat(messages: List[Dict[str, str]], max_rounds: int = 50) -> AsyncIterable[Dict[str, str]]:
```

Default 50 — reasonable for the main agent which may delegate to sub-agents (each round can contain many tool calls). The caller in `chat_view.py:209` is unchanged.

### 3b. Track round number (line 159-160)

Already tracked as `round_num` at line 150-160.

### 3c. Append round tag to tool results (line 323-328)

**Current:**
```python
messages.append({
    "role": "tool",
    "tool_call_id": tc["id"],
    "name": name,
    "content": str(result)
})
```

**New:**
```python
round_tag = f"\n\n[Round {round_num}/{max_rounds}]"
messages.append({
    "role": "tool",
    "tool_call_id": tc["id"],
    "name": name,
    "content": str(result) + round_tag,
})
```

### 3d. Add max rounds check after tool execution (line 329, before yield)

After executing all tool calls for a round, check if we've exceeded max_rounds:

```python
# After tool execution loop, before round increment
if round_num >= max_rounds:
    yield {"type": "status", "value": "error",
           "content": f"Max rounds ({max_rounds}) reached."}
    yield {"type": "content",
           "content": f"\n\n**Max rounds ({max_rounds}) reached.** The main agent attempted {tool_count} tool calls. Consider asking the user how to proceed or re-invoking with a different strategy."}
    break
```

Wait — the main agent loop increments `round_num` at line 160 before the LLM call, and tool execution happens later. So when the check fires, `round_num` is the current completed round. If `max_rounds` is 50 and we've just completed round 50, we break.

But actually, looking at the code more carefully: `round_num` starts at 0 and is incremented at the top of the while loop (line 160). So on the first iteration, `round_num = 1`. After 50 rounds, `round_num = 50`. If `round_num >= max_rounds`, we break after executing tools.

But wait, what about the final turn where the LLM produces content without tool calls? That round also counts. If the LLM is at round 50 and produces content (no tools), the loop breaks at line 280 with a successful return. Good — the max_rounds check should only be triggered after tool calls (because if the LLM produced content without tools, it finished successfully).

So the check should be: after processing tool calls (if there were any), if `round_num >= max_rounds`, break.

### 3e. Safety: also add the check at the top of the while loop

To prevent entering another round after max_rounds:

```python
while True:
    round_num += 1
    if round_num > max_rounds:
        yield {"type": "content",
               "content": f"\n\n**Max rounds ({max_rounds}) reached.** ..."}
        break
```

But this could conflict with the round counter tag — if we break before the LLM call, we never give the LLM a chance to wrap up. Better to check **after** the current round's tool calls. If the LLM at round 50 produces content without tools (success), we break normally. If it produces tool calls, we execute them, append the round tag, then break after.

So only one check point: after tool execution, if `round_num >= max_rounds`, break.

---

## 4. Files Summary

| File | Lines | Change |
|---|---|---|
| `src/engine/agents.py` | 697-702 | Append `[Round X/Y]` tag to tool result content |
| `src/engine/agents.py` | 715-718 | Replace generic error with structured report |
| `src/engine/chat.py` | 126 | Add `max_rounds: int = 50` parameter |
| `src/engine/chat.py` | 323-328 | Append `[Round X/Y]` tag to tool result content |
| `src/engine/chat.py` | ≈330 | Add `if round_num >= max_rounds: break` after tool execution |

---

## 5. Edge Cases

| Case | Behavior |
|---|---|
| Sub-agent calls `task_done` before max_rounds | Normal return (no tag emitted for the final tool call because it early‑returns at `_AGENT_DONE_`) |
| Sub-agent ignores fallback prompt | Structured report returned — main agent sees what was attempted, can re-invoke with `work_dir=` |
| Main agent at round 50 produces content (no tools) | Normal success — the check only triggers if tools were called |
| Main agent round counter tag shows `[Round 50/50]` at limit | LLM sees it's at the limit and should wrap up on next round |
| Main agent exceeded max -> break yields error event | `_process_response` in `chat_view.py` gets a content event with the error message, then continues to save partial state |
