"""
src/engine/chat.py · LLM streaming engine · Handles async communication with LiteLLM.
"""

import json
from typing import AsyncIterable, List, Dict, Any
import litellm
from src.config import settings
from src.engine.tools import registry

# Configure litellm to use the custom base URL if provided
if settings.openai_api_base:
    litellm.api_base = settings.openai_api_base

async def stream_chat(messages: List[Dict[str, str]]) -> AsyncIterable[Dict[str, str]]:
    """
    WHAT:    Streams reasoning, tools, and content from the LLM.
    WHY:     Supports multi-turn tool execution loop.
    HOW:     Iteratively calls LLM until a final response is generated.
    """
    while True:
        tools = registry.get_schemas()
        
        # Use litellm.acompletion with tools if available
        response = await litellm.acompletion(
            model=settings.model,
            messages=messages,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            stream=True,
            api_key=settings.openai_api_key,
            api_base=settings.openai_api_base,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None
        )

        full_content = ""
        full_reasoning = ""
        tool_calls_stream = {} # Track tool calls being streamed

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
        # 1. Add assistant's message with tool calls to history
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
            
            yield {"type": "tool", "content": f"Executing {name}({args})..."}
            
            result = await registry.call(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": name,
                "content": str(result)
            })
        
        # Continue loop to get next LLM response after tool results
