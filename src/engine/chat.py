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
from src.engine.tool_parser import (
    extract_tool_blocks, strip_tool_blocks, is_result_message,
    format_result, format_display_for_activity_log,
)
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
    WHY:     Different providers have strict requirements for message fields.
    HOW:     Filters keys to an allow-list, handles empty/null content, and
             discards old-format tool role messages.
    PARAMS:  messages: List[Dict[str, Any]] — The raw chat history.
    RETURNS: List[Dict[str, Any]] — A sanitized copy ready for the LLM.
    """
    allowed_keys = {"role", "content", "name"}
    temp_messages = []
    for m in messages:
        role = m.get("role")
        if role not in ("system", "user", "assistant"):
            continue  # discard old-format tool role messages
        clean_m = {k: v for k, v in m.items() if k in allowed_keys}
        if role == "assistant" and not clean_m.get("content"):
            clean_m["content"] = ""
        elif clean_m.get("content") is None:
            clean_m["content"] = ""
        temp_messages.append(clean_m)
    return temp_messages

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
             "content", "tool", "status", "usage"
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

    # Known tool names for XML parsing
    _known_tools: set[str] = set()
    for s in tool_registry.get_schemas():
        _known_tools.add(s["function"]["name"])
    for s in agent_registry.get_schemas():
        _known_tools.add(s["function"]["name"])
    for s in skill_registry.get_schemas():
        _known_tools.add(s["function"]["name"])

    while True:
        round_num += 1
        api_messages = sanitize_messages(messages)
        tool_count = len([m for m in messages if m.get("role") == "assistant"])
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

        for i, m in enumerate(api_messages):
            r = m.get("role", "?")
            c_len = len(m.get("content", "") or "") if isinstance(m.get("content"), str) else 0
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

            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                yield {"type": "reasoning", "content": delta.reasoning_content}

            content = delta.content
            if content:
                full_content += content
                yield {"type": "content", "content": content}

            if chunk.choices[0].finish_reason in ("stop",):
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

        # --- XML-based tool call detection ---
        tool_blocks = extract_tool_blocks(full_content, _known_tools)

        if not tool_blocks:
            _debug(f"LLM FINISHED — no tool calls. final_content_len={len(full_content)}")
            break

        _debug(f"LLM REQUESTED {len(tool_blocks)} XML tool block(s): {[b['name'] for b in tool_blocks]}")

        # Strip XML from content for chat display
        safe_content = strip_tool_blocks(full_content, _known_tools)

        # Replace displayed content with XML-stripped version
        yield {"type": "content_reset", "content": safe_content}

        # Append the assistant message (without XML)
        assistant_msg = {"role": "assistant", "content": safe_content or None}
        messages.append(assistant_msg)

        # Execute each tool block (ALWAYS exactly one per round)
        for block in tool_blocks[:1]:  # safeguard: only first block
            name = block["name"]
            args = block["args"]

            display_line = format_display_for_activity_log(name, args)
            yield {"type": "tool", "content": display_line}
            yield {"type": "status", "value": "tool_run", "content": f"Running: {name}..."}

            t0 = time.time()
            if name in tool_registry:
                result = await tool_registry.call(name, args)
            elif name in agent_registry:
                result = await agent_registry.call(name, args, session_folder=state.session_folder)
            else:
                result = await skill_registry.call(name, args)
            elapsed = time.time() - t0
            result_str = str(result)
            _debug(f"TOOL RESULT [{name}]: len={len(result_str)}, elapsed={elapsed:.2f}s")

            yield {"type": "status", "value": "tool_done", "content": f"Done: {name} ({elapsed:.1f}s)"}

            # Inject result as a user message (hidden from chat display)
            result_user_msg = {
                "role": "user",
                "content": format_result(name, result_str),
            }
            messages.append(result_user_msg)
            _debug(f"Appended result for '{name}'. messages count: {len(messages)}")

        if round_num >= max_rounds:
            yield {"type": "status", "value": "error",
                   "content": f"Max rounds ({max_rounds}) reached."}
            yield {"type": "content",
                   "content": f"\n\n**Max rounds ({max_rounds}) reached.** The main agent attempted {tool_count} tool calls. Consider asking the user how to proceed or re-invoking with a different strategy."}
            break
