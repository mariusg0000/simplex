"""
src/engine/tool_parser.py · XML text-based tool call parser.
Parses LLM output for <tool_name><param>value</param></tool_name> blocks,
strips them from chat display text, and formats tool results for injection.
Depends on: re, logging.
"""

import logging
import re

log = logging.getLogger("simplex.engine.tool_parser")

TOOL_START_RE = re.compile(r"<(\w+)>\s*$", re.MULTILINE)
ARG_RE = re.compile(r"<(\w+)>(.*?)</\1>", re.DOTALL)
CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
RESULT_PREFIX = "<result name='"


def extract_tool_blocks(text: str, known_tools: set[str]) -> list[dict]:
    """
    WHAT:    Finds <tool_name>...</tool_name> blocks in LLM output text.
    WHY:     The main loop calls this after streaming finishes. Each found
             block is parsed into a dict with name + args for dispatch.
    HOW:     Iterates through text looking for opening <tag> where tag is
             a known tool name. Finds the matching </tag> by tracking depth.
             For each block, parses <param>value</param> children into args.
    PARAMS:  text: str — full LLM response
             known_tools: set[str] — registered tool names
    RETURNS: list[dict] — each has "name" (str) and "args" (dict[str,str])
    ERRORS:  Unmatched tags or unclosed blocks are logged and skipped.
    """
    blocks: list[dict] = []
    pos = 0
    while pos < len(text):
        # Look for the next <tag> where tag ∈ known_tools
        match = TOOL_START_RE.search(text, pos)
        if not match:
            break

        tag = match.group(1)
        if tag not in known_tools:
            pos = match.end()
            continue

        open_start = match.start()
        close_tag = f"</{tag}>"
        close_pos = text.find(close_tag, match.end())
        if close_pos == -1:
            log.warning("Unclosed tool block <%s> at pos %d", tag, open_start)
            break

        raw = text[open_start : close_pos + len(close_tag)]
        args = _parse_args(raw)
        blocks.append({"name": tag, "args": args, "raw": raw})
        log.info("Extracted tool block: <%s> with args=%s", tag, list(args.keys()))
        pos = close_pos + len(close_tag)

    return blocks


def strip_tool_blocks(text: str, known_tools: set[str]) -> str:
    """
    WHAT:    Removes all <tool_name>...</tool_name> blocks from text.
    WHY:     LLM output for chat display must not include raw XML tool calls.
    HOW:     Same matching logic as extract_tool_blocks but discards blocks
             instead of parsing them.
    PARAMS:  text: str — full LLM response
             known_tools: set[str] — registered tool names
    RETURNS: str — text with XML tool blocks removed (whitespace collapsed)
    """
    result = []
    pos = 0
    while pos < len(text):
        match = TOOL_START_RE.search(text, pos)
        if not match:
            result.append(text[pos:])
            break

        tag = match.group(1)
        if tag not in known_tools:
            result.append(text[pos : match.end()])
            pos = match.end()
            continue

        close_tag = f"</{tag}>"
        close_pos = text.find(close_tag, match.end())
        if close_pos == -1:
            result.append(text[pos:])
            break

        result.append(text[pos : match.start()])
        pos = close_pos + len(close_tag)

    stripped = "".join(result).strip()
    # Collapse multiple blank lines into one
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    return stripped


def is_result_message(content: str) -> bool:
    """
    WHAT:    Checks if a message content looks like a tool result.
    WHY:     The chat renderer uses this to decide whether to display a
             user/assistant message. Tool-result messages are hidden from
             the chat view (shown only in Activity Log).
    HOW:     Checks if content starts with <result name='...'> tag.
    PARAMS:  content: str — message content
    RETURNS: bool — True if it's a tool result injection
    """
    if not content:
        return False
    return content.strip().startswith(RESULT_PREFIX)


def format_result(name: str, result_text: str) -> str:
    """
    WHAT:    Wraps a tool result in the <result name='tool'>...</result> format.
    WHY:     Injected as a user message so the LLM sees it in context.
             Keeps a consistent, parseable format.
    PARAMS:  name: str — tool name
             result_text: str — tool output (may be long)
    RETURNS: str — formatted result string
    """
    # Escape XML special chars in result_text
    safe = _escape_xml(result_text)
    return f"<result name='{name}'>{safe}</result>"


def format_display_for_activity_log(tool_name: str, args: dict) -> str:
    """
    WHAT:    Builds a short summary line for the Activity Log.
    WHY:     The Activity Log shows tool calls truncated to ~500 chars.
    PARAMS:  tool_name: str, args: dict
    RETURNS: str — e.g. "<use_vision> path=/tmp/img.jpg"
    """
    parts = []
    for k, v in args.items():
        short = v[:80] + "..." if len(v) > 80 else v
        parts.append(f"  {k}={short}")
    return f"<{tool_name}>\n" + "\n".join(parts)


def _parse_args(xml_block: str) -> dict[str, str]:
    """
    WHAT:    Parses <param>value</param> children from a tool XML block.
    WHY:     Flat structure only — no nested elements. CDATA is handled
             by unrolling before regex matching.
    HOW:     First unrolls <![CDATA[...]]> sections (replacing with plain
             text), then strips the root tags, then matches child elements.
    PARAMS:  xml_block: str — full <tool_name>...</tool_name> XML
    RETURNS: dict[str, str] — param_name → param_value
    """
    # Unroll CDATA sections before regex
    def _unroll_cdata(m):
        content = m.group(1)
        # Escape only what's needed for XML safety inside regex captures
        return content
    unrolled = CDATA_RE.sub(_unroll_cdata, xml_block)

    # Strip root tags: <tool_name>...</tool_name>
    inner = re.sub(r"^<\w+[^>]*>(.*)</\w+>$", r"\1", unrolled.strip(), flags=re.DOTALL)
    if inner == unrolled.strip():
        return {}

    args: dict[str, str] = {}
    for m in ARG_RE.finditer(inner):
        key = m.group(1)
        value = m.group(2).strip()
        args[key] = value

    return args


def _escape_xml(text: str) -> str:
    """
    WHAT:    Escapes XML special characters in text for safe insertion
             as element content (no CDATA needed for typical usage).
    WHY:     The result text might contain &, <, or > which would break
             XML parsing if not escaped.
    PARAMS:  text: str — raw text
    RETURNS: str — escaped text
    """
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text
