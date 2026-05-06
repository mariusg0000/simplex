"""
src/engine/chat.py · LLM streaming engine · Handles async communication with LiteLLM.
"""

import json
import logging
from typing import AsyncIterable, List, Dict, Any, Optional
import litellm
from src.config import settings, logger
from src.engine.tools import registry

log = logging.getLogger("simplex.engine.chat")

# Configure litellm
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
        # Filter allowed fields
        if role == "tool":
            clean_m = {k: v for k, v in m.items() if k in ["role", "content", "tool_call_id", "name"]}
        else:
            clean_m = {k: v for k, v in m.items() if k in ["role", "content", "tool_calls", "name", "reasoning_content"]}
        
        # MANDATORY: Content must NOT be null/None EXCEPT for assistant tool calls
        # In fact, some strict proxies reject content entirely if tool_calls is present.
        if role == "assistant" and "tool_calls" in clean_m:
            if not clean_m.get("content"):
                clean_m.pop("content", None)
            else:
                # If content exists, keep it as is
                pass
        elif clean_m.get("content") is None:
            clean_m["content"] = ""
            
        # Ensure tool_calls is a list if it exists and is not empty
        if "tool_calls" in clean_m and not clean_m["tool_calls"]:
            del clean_m["tool_calls"]
            
        temp_messages.append(clean_m)
    
    # Step 2: Enforce sequence integrity (Assistant Call -> Tool Response)
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

async def stream_chat(messages: List[Dict[str, str]]) -> AsyncIterable[Dict[str, str]]:
    """
    Streams reasoning, tools, and content from the LLM.
    Handles the multi-turn tool execution loop.
    """
    while True:
        tools = registry.get_schemas()
        api_messages = sanitize_messages(messages)
        
        log.debug("Sending %d messages to LLM", len(api_messages))
        
        try:
            # Use litellm.acompletion
            response = await litellm.acompletion(
                model=settings.model,
                messages=api_messages,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                stream=True,
                api_key=settings.openai_api_key,
                api_base=settings.openai_api_base,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None
            )
        except Exception as e:
            log.error("LiteLLM error: %s", str(e))
            yield {"type": "content", "content": f"\n\n**LiteLLM Error:** {str(e)}"}
            break

        full_content = ""
        full_reasoning = ""
        tool_calls_stream = {}

        async for chunk in response:
            delta = chunk.choices[0].delta
            
            # Handle reasoning
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                full_reasoning += reasoning
                yield {"type": "reasoning", "content": reasoning}
                
            # Handle content
            content = delta.content
            if content:
                full_content += content
                yield {"type": "content", "content": content}

            # Handle tool calls streaming
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_stream:
                        tool_calls_stream[idx] = {"id": tc.id, "name": "", "arguments": ""}
                    
                    if tc.id: tool_calls_stream[idx]["id"] = tc.id
                    if tc.function.name: tool_calls_stream[idx]["name"] += tc.function.name
                    if tc.function.arguments: tool_calls_stream[idx]["arguments"] += tc.function.arguments

        # If we have content but no tool calls, we are done
        if not tool_calls_stream:
            break

        # Process tool calls
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

        # 2. Execute tools and add results
        for tc in formatted_tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            
            yield {"type": "tool", "content": f"Executing {name}..."}
            
            result = await registry.call(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": name,
                "content": str(result)
            })
