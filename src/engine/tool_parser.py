"""
src/engine/tool_parser.py · XML text-based tool call parser.
Parses LLM output for <tool_name><param>value</param></tool_name> blocks,
strips them from chat display text, and formats tool results for injection.

StreamingToolParser: incremental detection during LLM streaming — only yields
non-tool text for display, so XML never appears in chat (no content_reset needed).

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
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    return stripped


class StreamingToolParser:
    """
    WHAT:    Incremental XML tool block detection during LLM streaming.
    WHY:     Prevents tool call XML from appearing in chat display. Instead of
             streaming everything then doing content_reset, this detects tool
             blocks on-the-fly and only yields non-tool text for display.
    HOW:     State machine per character: NORMAL → MAYBE_TOOL (saw '<') →
             IN_TOOL (matched '<tool_name>') → NORMAL (saw '</tool_name>').
             Unknown tags are flushed as text. Incomplete blocks at flush()
             are also emitted as text.
    """

    def __init__(self, known_tools: set[str]):
        self.known_tools = known_tools
        self._state = "normal"
        self._buf = ""
        self._display = ""
        self._tools: list[dict] = []
        self._tool_name: str | None = None

    def feed(self, chunk: str):
        """
        WHAT:    Process a chunk of streamed text.
        WHY:     Called for each delta.content chunk from the LLM stream.
        HOW:     Character-by-character state machine. Yields content events
                 for non-tool text. Accumulates tool blocks internally.
        PARAMS:  chunk: str — new text from LLM stream
        YIELDS:  dict — {"type": "content", "content": "..."}
        """
        for c in chunk:
            if self._state == "normal":
                if c == "<":
                    self._state = "maybe"
                    self._buf = "<"
                else:
                    self._display += c

            elif self._state == "maybe":
                potential = self._buf + c
                matched = any(
                    f"<{t}".startswith(potential) for t in self.known_tools
                )
                is_complete = potential in (f"<{t}>" for t in self.known_tools)

                if is_complete:
                    self._tool_name = potential[1:-1]
                    self._state = "intool"
                    self._buf = ""
                elif not matched:
                    self._display += self._buf
                    self._buf = ""
                    self._state = "normal"
                    if c == "<":
                        self._state = "maybe"
                        self._buf = "<"
                    else:
                        self._display += c
                else:
                    self._buf = potential

            elif self._state == "intool":
                self._buf += c
                close_tag = f"</{self._tool_name}>"
                if self._buf.endswith(close_tag):
                    raw = f"<{self._tool_name}>{self._buf}"
                    args = _parse_args(raw)
                    self._tools.append(
                        {"name": self._tool_name, "args": args, "raw": raw}
                    )
                    self._buf = ""
                    self._tool_name = None
                    self._state = "normal"

        if self._display:
            yield {"type": "content", "content": self._display}
            self._display = ""

    def flush(self):
        """
        WHAT:    Flush any remaining buffered content as text.
        WHY:     Called after the stream ends. Incomplete tool blocks are
                 treated as plain text.
        YIELDS:  dict — {"type": "content", "content": "..."}
        """
        if self._state == "maybe":
            self._display += self._buf
        elif self._state == "intool":
            self._display += f"<{self._tool_name}>{self._buf}"
        self._state = "normal"
        self._buf = ""
        self._tool_name = None
        if self._display:
            yield {"type": "content", "content": self._display}
            self._display = ""

    @property
    def tool_blocks(self) -> list[dict]:
        return self._tools

    def reset(self):
        self._state = "normal"
        self._buf = ""
        self._display = ""
        self._tools = []
        self._tool_name = None


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
    def _unroll_cdata(m):
        content = m.group(1)
        return content
    unrolled = CDATA_RE.sub(_unroll_cdata, xml_block)

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
