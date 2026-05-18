"""
src/engine/context.py · Context compression engine ·
Summarizes old conversation turns when the context window exceeds thresholds.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import litellm
from src.config import settings

log = logging.getLogger("simplex.engine.context")


def _count_tokens(messages: List[Dict], model: str) -> int:
    try:
        return litellm.token_counter(model=model, messages=messages)
    except Exception:
        text = ""
        for m in messages:
            text += m.get("content") or ""
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    text += tc.get("function", {}).get("arguments", "")
            if m.get("role") == "tool":
                text += m.get("content") or ""
        return max(1, len(text) // 3)


def _is_safe_split(messages: List[Dict], cut_idx: int) -> bool:
    """
    Checks that no tool_response in the "keep" set (messages[cut_idx:])
    references a tool_call_id from the "remove" set (messages[1:cut_idx]).
    """
    removed_call_ids: set = set()
    for i in range(1, cut_idx):
        m = messages[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                cid = tc.get("id") or tc.get("function", {}).get("id", "")
                removed_call_ids.add(cid)

    if not removed_call_ids:
        return True

    for i in range(cut_idx, len(messages)):
        m = messages[i]
        if m.get("role") == "tool" and m.get("tool_call_id") in removed_call_ids:
            return False

    return True


def find_safe_cut(messages: List[Dict], max_context: int, min_context: int, model: str) -> Optional[int]:
    """
    Scans from oldest messages forward to find the earliest safe cut
    point where the remaining (uncompressed) messages fit under min_context.

    Returns cut_idx (compress messages[1:cut_idx], keep messages[cut_idx:]),
    or None if no compression is needed.
    """
    chat_msgs = messages[1:]
    if not chat_msgs:
        return None

    total = _count_tokens(chat_msgs, model)
    if total <= max_context:
        return None

    # Approximate per-message token counts
    per_msg = []
    for m in chat_msgs:
        per_msg.append(_count_tokens([m], model))

    removed = 0
    for i, t in enumerate(per_msg):
        removed += t
        remaining = total - removed
        cut_idx = i + 2

        if remaining <= min_context and cut_idx >= 2:
            if _is_safe_split(messages, cut_idx):
                log.info("context: safe cut at idx=%d (compress %d messages, keep %d, ~%d tokens remaining)",
                         cut_idx, cut_idx - 1, len(messages) - cut_idx, remaining)
                return cut_idx

    log.warning("context: no safe cut point found for target min_context=%d", min_context)
    return None


def _format_messages_for_summary(messages: List[Dict]) -> str:
    """Format a list of messages as plain text for the LLM summarizer."""
    lines = []
    for m in messages:
        role = m.get("role", "unknown")
        content = m.get("content") or ""
        ts = ""

        if role == "user":
            ts = f"[User]: {content}"
        elif role == "assistant":
            ts = f"[Assistant]: {content}"
            if m.get("tool_calls"):
                tc_names = [tc.get("function", {}).get("name", "?") for tc in m["tool_calls"]]
                ts += f"\n  (called tools: {', '.join(tc_names)})"
        elif role == "tool":
            name = m.get("name", "?")
            trunc = content[:200] + "..." if len(content) > 200 else content
            ts = f"[Tool: {name}]: {trunc}"

        if ts:
            lines.append(ts)

    return "\n\n".join(lines)


async def compress_with_llm(messages: List[Dict]) -> str:
    """Send messages to the LLM and return a concise summary."""
    formatted = _format_messages_for_summary(messages)

    prompt = (
        "You are a conversation compression assistant. "
        "Summarize the following conversation messages into a concise but information-dense summary. "
        "Preserve ALL critical information including:\n"
        "- User requests, questions, and preferences\n"
        "- Code or content that was created or modified, including file paths\n"
        "- Key decisions, data, errors, and their resolutions\n"
        "- Any information the assistant needs to continue the conversation coherently\n\n"
        "The summary will replace these messages in the conversation context.\n\n"
        "Messages to compress:\n"
        "--- begin ---\n"
        f"{formatted}\n"
        "--- end ---\n\n"
        "Output only the summary, nothing else."
    )

    log.info("context: compressing %d messages (~%d chars) with LLM", len(messages), len(formatted))

    try:
        llm_model, llm_api_key, llm_api_base = settings.resolve_model(settings.chat_model)
        response = await litellm.acompletion(
            model=llm_model,
            messages=[{"role": "user", "content": prompt}],
            api_key=llm_api_key,
            api_base=llm_api_base,
            temperature=0.1,
            max_tokens=2048,
        )
        summary = response.choices[0].message.content.strip()
        log.info("context: compression complete — summary is %d chars", len(summary))
        return summary
    except Exception as e:
        log.error("context: LLM compression failed: %s", e)
        # Fallback: basic truncation summary
        fallback = formatted[:1500] + "\n\n[Conversation truncated due to compression failure]"
        return fallback


async def compress_messages(messages: List[Dict]) -> List[Dict]:
    """
    Main entry point.
    Checks if context exceeds max_context, finds a safe cut,
    compresses the old messages, and returns the new message list.
    If no compression is needed, returns the original list unchanged.
    """
    max_ctx = settings.max_context
    min_ctx = settings.min_context
    model = settings.model

    cut_idx = find_safe_cut(messages, max_ctx, min_ctx, model)
    if cut_idx is None:
        return messages

    msgs_to_compress = messages[1:cut_idx]
    msgs_to_keep = messages[cut_idx:]

    summary = await compress_with_llm(msgs_to_compress)

    compressed_summary_msg = {
        "role": "user",
        "content": (
            "This is a summary of older messages that were compressed to optimize context. "
            f"Messages from the beginning of the conversation up to this point have been summarized:\n\n{summary}"
        ),
    }

    new_messages = [messages[0], compressed_summary_msg] + msgs_to_keep
    log.info("context: compressed %d messages into 1 summary — total messages: %d -> %d",
             len(msgs_to_compress), len(messages), len(new_messages))

    return new_messages
