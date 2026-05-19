"""
src/engine/chat.py · Main LLM streaming loop · multi-turn tool execution.
The core chat engine: sanitises messages, calls LiteLLM with streaming,
yields reasoning/content/tool events, dispatches tool/agent/skill calls,
and repeats until done. Depends on: litellm, ToolRegistry, AgentRegistry, SkillRegistry.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import AsyncIterable, List, Dict, Any, Optional
import litellm
from src.config import settings, logger
from src.engine.tools import registry as tool_registry
from src.engine.agents import agent_registry
from src.engine.skills import skill_registry
from src.ui import state

log = logging.getLogger("simplex.engine.chat")

_LOG_FILE = Path("/tmp/simplex_debug.log")


def _debug(msg: str) -> None:
    """
    WHAT:    Writes a timestamped debug line to stderr and /tmp/simplex_debug.log.
    WHY:     Persistent debug log that survives terminal restarts; used for
             diagnosing LLM round contents without relying on the UI.
    PARAMS:  msg: str — the debug message to write
    """
    line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [CHAT_DEBUG] {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        with open(_LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _truncate_json(obj: Any, max_len: int = 500) -> str:
    """
    WHAT:    JSON-dumps an object, truncating string values longer than max_len.
    WHY:     Debug logging of full API payloads would flood the log; this keeps
             the structure visible while limiting each string field's size.
    PARAMS:  obj: Any — object to serialise
             max_len: int — max char length per string value (default 500)
    RETURNS: str — pretty-printed JSON with truncated strings
    """
    def _shorten(v):
        if isinstance(v, str) and len(v) > max_len:
            return v[:max_len] + f"...<truncated {len(v)-max_len} chars>"
        return v
    truncated = _shorten(json.dumps(obj, indent=2, ensure_ascii=False))
    return truncated

if settings.openai_api_base:
    litellm.api_base = settings.openai_api_base
litellm.drop_params = True # Standardize non-OpenAI responses

def sanitize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    WHAT:    Cleans and validates the message history for API compatibility.
    WHY:     Different providers (OpenAI, DeepSeek, Anthropic via LiteLLM) have strict, 
             often conflicting requirements for message structures, tool response 
             sequences, and mandatory fields.
    HOW:     1. Filters keys to an allow-list (including 'reasoning_content' for DeepSeek).
             2. Handles the 'empty content' requirement for assistant tool calls.
             3. Enforces sequence integrity: an assistant 'tool_calls' message MUST be 
                immediately followed by the corresponding 'tool' response messages. 
                Incomplete turns are discarded to prevent API 400 errors.
    PARAMS:  messages: List[Dict[str, Any]] — The raw chat history.
    RETURNS: List[Dict[str, Any]] — A sanitized copy of the history ready for the LLM.
    """
    temp_messages = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            clean_m = {k: v for k, v in m.items() if k in ["role", "content", "tool_call_id", "name"]}
        else:
            clean_m = {k: v for k, v in m.items() if k in ["role", "content", "tool_calls", "name", "reasoning_content"]}
        
        # Mandatory: some providers reject content entirely when tool_calls is present
        if role == "assistant" and "tool_calls" in clean_m:
            if not clean_m.get("content"):
                clean_m.pop("content", None)
        elif clean_m.get("content") is None:
            clean_m["content"] = ""
            
        if "tool_calls" in clean_m and not clean_m["tool_calls"]:
            del clean_m["tool_calls"]
            
        temp_messages.append(clean_m)
    
    final_sanitized = []
    i = 0
    while i < len(temp_messages):
        msg = temp_messages[i]
        
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            num_calls = len(msg["tool_calls"])
            call_ids = [tc.get("id") for tc in msg["tool_calls"]]
            
            responses = []
            j = i + 1
            while j < len(temp_messages) and temp_messages[j].get("role") == "tool":
                if temp_messages[j].get("tool_call_id") in call_ids:
                    responses.append(temp_messages[j])
                j += 1
            
            if len(responses) == num_calls:
                final_sanitized.append(msg)
                final_sanitized.extend(responses)
                i = j
            else:
                i = j # Discard incomplete turn
        elif msg.get("role") == "tool":
            i += 1 # Discard orphaned response
        else:
            final_sanitized.append(msg)
            i += 1
            
    return final_sanitized

async def stream_chat(messages: List[Dict[str, str]], max_rounds: int = 50) -> AsyncIterable[Dict[str, str]]:
    """
    WHAT:    Main AI loop: LLM streaming + multi-turn tool execution.
    WHY:     The highest-level engine — orchestrates the full conversation:
             sanitises messages → calls LLM (streaming) → dispatches tools,
             agents, and skills → repeats until the LLM produces content
             without tool calls.
    HOW:     1. Combines tool/agent/skill schemas into a single tool list.
             2. Sanitises messages for API compatibility.
             3. Calls litellm.acompletion with streaming.
             4. Consumes the stream: yields reasoning/content chunks in real
                time, accumulates tool_calls.
             5. On finish_reason="stop": yields usage stats + cost, breaks.
             6. On tool_calls: assembles the assistant message, dispatches
                each call to the appropriate registry (tool → AgentRegistry /
                ToolRegistry / SkillRegistry), appends results to messages,
                and continues the while loop.
    PARAMS:  messages: List[Dict[str, str]] — the mutable chat history; new
                        assistant + tool messages are appended in-place.
             max_rounds: int = 50 — max LLM+tool cycles before forced exit.
    RETURNS: AsyncIterable[Dict[str, str]] — event stream with types:
             "content", "reasoning", "tool", "status", "usage"
    ERRORS:  litellm exception → yields error status + content, then breaks
             stream timeout (120s) → yields timeout error status, breaks
    """
    round_num = 0
    total_assistant = 0
    import time
    llm_model, llm_api_key, llm_api_base = settings.resolve_model()
    try:
        mi = litellm.model_cost.get(llm_model, {})
        max_input_tokens = mi.get("max_input_tokens") or mi.get("max_tokens", 131072)
    except:
        max_input_tokens = 131072
    cumulative_cost = 0.0
    while True:
        round_num += 1
        tools = tool_registry.get_main_agent_schemas() + agent_registry.get_schemas() + skill_registry.get_schemas()
        api_messages = sanitize_messages(messages)
        tool_count = len([m for m in messages if m.get("role") == "assistant" and m.get("tool_calls")])
        total_chars = sum(len(m.get("content", "") or "") for m in api_messages)
        try:
            input_tokens = litellm.token_counter(model=llm_model, messages=api_messages)
        except:
            input_tokens = total_chars // 4
        context_pct = (input_tokens / max_input_tokens * 100) if max_input_tokens else 0

        yield {"type": "usage", "context_tokens": input_tokens, "context_pct": context_pct, "cost": cumulative_cost}

        _debug(f"=== LLM ROUND #{tool_count} ===")
        _debug(f"Sending {len(api_messages)} messages to LLM ({len(messages)} raw)")
        
        yield {"type": "status", "value": "request", "content": f"Round {tool_count + 1}: Sending {len(api_messages)} messages (~{input_tokens} tokens)..."}
        
        _debug(f"Sending {len(api_messages)} messages to LLM ({len(messages)} raw)")
        for i, m in enumerate(api_messages):
            r = m.get("role", "?")
            c_len = len(m.get("content", "") or "") if isinstance(m.get("content"), str) else 0
            tc = m.get("tool_calls")
            if tc:
                names = [t["function"]["name"] for t in tc]
                _debug(f"  msg[{i}] role={r} content_len={c_len} tool_calls={names}")
            else:
                _debug(f"  msg[{i}] role={r} content_len={c_len}")
        _debug(f"RAW JSON to LLM:\n{_truncate_json(api_messages)}")
        
        yield {"type": "status", "value": "connecting", "content": f"Connecting to LLM..."}
        _debug("=== BEFORE litellm.acompletion() ===")

        try:
            response = await litellm.acompletion(
                model=llm_model,
                messages=api_messages,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                stream=True,
                api_key=llm_api_key,
                api_base=llm_api_base,
                timeout=60,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None
            )
        except Exception as e:
            _debug(f"LiteLLM EXCEPTION: {type(e).__name__}: {str(e)}")
            log.error("LiteLLM error: %s", str(e))
            yield {"type": "status", "value": "error", "content": f"Error: {str(e)}"}
            yield {"type": "content", "content": f"\n\n**LiteLLM Error:** {str(e)}"}
            break
        
        _debug("=== AFTER litellm.acompletion(), starting stream ===")
        yield {"type": "status", "value": "streaming", "content": "Receiving response..."}

        full_content = ""
        full_reasoning = ""
        tool_calls_stream = {}
        CHUNK_TIMEOUT = 120

        stream_iter = response.__aiter__()
        while True:
            try:
                chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=CHUNK_TIMEOUT)
            except StopAsyncIteration:
                _debug("Stream ended via StopAsyncIteration")
                break
            except asyncio.TimeoutError:
                _debug(f"Stream timeout — no chunk in {CHUNK_TIMEOUT}s")
                yield {"type": "status", "value": "error", "content": f"Stream timeout ({CHUNK_TIMEOUT}s). Check connection."}
                break

            delta = chunk.choices[0].delta

            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                full_reasoning += reasoning
                yield {"type": "reasoning", "content": reasoning}

            content = delta.content
            if content:
                full_content += content
                yield {"type": "content", "content": content}

            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_stream:
                        tool_calls_stream[idx] = {"id": tc.id, "name": "", "arguments": ""}
                    if tc.id: tool_calls_stream[idx]["id"] = tc.id
                    if tc.function.name: tool_calls_stream[idx]["name"] += tc.function.name
                    if tc.function.arguments: tool_calls_stream[idx]["arguments"] += tc.function.arguments

            # Finish reason — API signals stream end without [DONE]
            if chunk.choices[0].finish_reason in ("stop", "tool_calls"):
                _debug(f"Stream finished via finish_reason={chunk.choices[0].finish_reason}")
                break

        output_tokens = 0
        if full_content:
            try:
                output_tokens = litellm.token_counter(model=llm_model, text=full_content)
            except:
                output_tokens = len(full_content) // 4
        if output_tokens > 0:
            try:
                prompt_cost, completion_cost = litellm.cost_per_token(
                    model=llm_model,
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens
                )
                cumulative_cost += prompt_cost + completion_cost
            except:
                pass

        yield {"type": "usage", "context_tokens": input_tokens, "context_pct": context_pct, "cost": cumulative_cost}

        if not tool_calls_stream:
            _debug(f"LLM FINISHED — no tool calls. final_content_len={len(full_content)}, final_reasoning_len={len(full_reasoning)}")
            break

        _debug(f"LLM REQUESTED {len(tool_calls_stream)} tool call(s)")
        for idx in sorted(tool_calls_stream.keys()):
            tc = tool_calls_stream[idx]
            _debug(f"  tool_call[{idx}]: {tc['name']}({tc['arguments'][:200]})")

        assistant_msg = {"role": "assistant", "content": full_content or None}
        if full_reasoning:
            assistant_msg["reasoning_content"] = full_reasoning
        
        formatted_tool_calls = []
        for idx in sorted(tool_calls_stream.keys()):
            tc = tool_calls_stream[idx]
            formatted_tool_calls.append({
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]}
            })
        assistant_msg["tool_calls"] = formatted_tool_calls
        messages.append(assistant_msg)

        for tc in formatted_tool_calls:
            name = tc["function"]["name"]
            raw_args = tc["function"]["arguments"]
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError as e:
                log.warning("! JSON decode error for tool '%s': %s (pos=%s)", name, raw_args[:200], e.pos)
                error_msg = (
                    f"Error: Tool arguments are not valid JSON (position {e.pos}). "
                    f"String values may contain unescaped quotes or backslashes. "
                    f"Put document content in files and pass filenames, not inline text."
                )
                yield {"type": "tool", "content": f"⚠ {error_msg}"}
                remaining = max_rounds - round_num
                round_tag = f"\n\n[Round {round_num}/{max_rounds}"
                if remaining <= 3:
                    round_tag += " 🛑 CRITICAL — finish now!"
                elif remaining <= 6:
                    round_tag += f" ⚠️ only {remaining} left"
                round_tag += "]"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": error_msg + round_tag,
                })
                continue
            
            cmd_snippet = ""
            if "command" in args:
                cmd = args["command"]
                cmd_snippet = cmd[:50] + ("..." if len(cmd) > 50 else "")
            yield {"type": "tool", "content": f"Executing {name}" + (f": {cmd_snippet}" if cmd_snippet else " ...")}
            yield {"type": "status", "value": "tool_run", "content": f"Running: {name}" + (f" {cmd_snippet}" if cmd_snippet else "") + "..."}
            
            t0 = time.time()
            if name in tool_registry:
                result = await tool_registry.call(name, args)
            elif name in agent_registry:
                result = await agent_registry.call(name, args, session_folder=state.session_folder)
            else:
                result = await skill_registry.call(name, args)
            elapsed = time.time() - t0
            result_summary = str(result)[:60]
            _debug(f"TOOL RESULT [{name}]: result_len={len(str(result))}, preview={result_summary}, elapsed={elapsed:.2f}s")
            remaining = max_rounds - round_num
            round_tag = f"\n\n[Round {round_num}/{max_rounds}"
            if remaining <= 3:
                round_tag += " 🛑 CRITICAL — finish now!"
            elif remaining <= 6:
                round_tag += f" ⚠️ only {remaining} left"
            round_tag += "]"
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": name,
                "content": str(result) + round_tag
            })
            _debug(f"Appended tool response. messages count now: {len(messages)}")
            yield {"type": "status", "value": "tool_done", "content": f"Done: {name} ({elapsed:.1f}s)"}

        if round_num >= max_rounds:
            yield {"type": "status", "value": "error",
                   "content": f"Max rounds ({max_rounds}) reached."}
            yield {"type": "content",
                   "content": f"\n\n**Max rounds ({max_rounds}) reached.** The main agent attempted {tool_count} tool calls. Consider asking the user how to proceed or re-invoking with a different strategy."}
            break
