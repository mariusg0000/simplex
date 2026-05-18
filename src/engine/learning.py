"""
src/engine/learning.py · Experience management and continuous learning.
Loads/saves per-agent experience files and triggers LLM analysis after
task completion to extract lessons from mistakes and corrections.
Depends on: pathlib, litellm, settings (config.py).
"""

import json
import logging
from pathlib import Path
from typing import Optional

import litellm
from src.config import settings

log = logging.getLogger("simplex.engine.learning")

EXPERIENCE_DIR = Path.home() / ".simplexai" / "experience"


def get_experience_path(agent_name: str) -> Path:
    """
    WHAT:    Returns the filesystem path for an agent's experience file.
    WHY:     Centralises path resolution so all callers use the same location.
    PARAMS:  agent_name: str — filename stem (e.g. "create_doc")
    RETURNS: Path to ~/.simplexai/experience/{agent_name}.md
    """
    return EXPERIENCE_DIR / f"{agent_name}.md"


def load_experience(agent_name: str) -> Optional[str]:
    """
    WHAT:    Reads the experience file for a given agent, if it exists.
    WHY:     Used by ToolCapableAgent._build_system_prompt() to append
             accumulated wisdom to the system prompt.
    PARAMS:  agent_name: str — agent filename stem
    RETURNS: str or None — file content stripped, or None if no file
    """
    path = get_experience_path(agent_name)
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return None


def save_experience(agent_name: str, content: str) -> None:
    """
    WHAT:    Writes experience content to disk atomically (temp file + rename).
    WHY:     Prevents partial writes if the process is interrupted mid-write.
    PARAMS:  agent_name: str — agent filename stem
             content: str — new markdown content for the experience file
    """
    path = get_experience_path(agent_name)
    EXPERIENCE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    log.info("Experience saved for '%s' (%d bytes)", agent_name, len(content))


def format_session_for_analysis(messages: list[dict]) -> str:
    """
    WHAT:    Formats the agent's message history into a readable transcript.
    WHY:     The LLM needs a clean, structured view of the session to
             identify mistakes, patterns, and lessons.
    HOW:     Each message is rendered as ROLE: content. Tool calls are
             exploded with their arguments; reasoning is included inline.
    PARAMS:  messages: list[dict] — raw message list from ToolCapableAgent
    RETURNS: str — formatted transcript
    """
    lines = []
    for i, msg in enumerate(messages):
        role = msg["role"].upper()
        if role == "SYSTEM":
            lines.append(f"--- SYSTEM PROMPT (message {i}) ---")
            lines.append(msg.get("content", ""))
            lines.append("")
        elif role == "USER":
            lines.append(f"--- USER TASK (message {i}) ---")
            lines.append(msg.get("content", ""))
            lines.append("")
        elif role == "ASSISTANT":
            content = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""
            tool_calls = msg.get("tool_calls", []) or []

            if reasoning:
                lines.append(f"--- ASSISTANT REASONING (message {i}) ---")
                lines.append(reasoning)

            if content:
                lines.append(f"--- ASSISTANT RESPONSE (message {i}) ---")
                lines.append(content)

            for tc in tool_calls:
                name = tc.get("function", {}).get("name", "?")
                args_raw = tc.get("function", {}).get("arguments", "{}")
                try:
                    args_fmt = json.dumps(json.loads(args_raw), indent=2)
                except (json.JSONDecodeError, ValueError):
                    args_fmt = args_raw
                lines.append(f"--- TOOL CALL: {name} (message {i}) ---")
                lines.append(args_fmt)

            lines.append("")
        elif role == "TOOL":
            name = msg.get("name", "?")
            content = msg.get("content", "")
            lines.append(f"--- TOOL RESULT: {name} (message {i}) ---")
            if len(content) > 2000:
                lines.append(content[:2000] + "\n...[truncated]")
            else:
                lines.append(content)
            lines.append("")

    return "\n".join(lines)


ANALYSIS_PROMPT_TEMPLATE = """\
You are an expert at extracting lessons from agent sessions.

## INSTRUCTIONS
Review the session transcript below. Identify:
1. Mistakes the agent made (wrong approach, incorrect assumptions, etc.)
2. Tool errors or failed attempts (API errors, file not found, permissions, etc.)
3. Inefficient or suboptimal approaches
4. Patterns to avoid in the future

The system prompt (first message) may already contain accumulated experience.
Compare any new lessons against it.

CRITICAL RULE: If there is NO existing experience file (no "## ACCUMULATED EXPERIENCE"
section in the system prompt), you MUST create one. Never respond NO_CHANGE when
the file doesn't exist yet.

If the existing experience already covers everything (and it exists), respond
with exactly:

NO_CHANGE

Otherwise, output the COMPLETE updated experience file content in markdown
format. Include ALL existing experience (do not remove anything) plus any new
lessons. Use these sections:

## Pitfalls
## Best Practices
## Common Errors

## SESSION TRANSCRIPT
{transcript}
"""


async def analyze_and_learn(agent_name: str, messages: list[dict], result: str) -> None:
    """
    WHAT:    Sends the session transcript to the LLM for analysis and
             optionally updates the agent's experience file.
    WHY:     Continuous learning: after each task completion, the LLM reviews
             what happened and extracts reusable lessons (mistakes, patterns).
    HOW:     1. Formats messages into a transcript.
             2. Calls LLM with ANALYSIS_PROMPT_TEMPLATE.
             3. If response is not "NO_CHANGE", saves it as the new experience.
             4. Existing experience is already in message[0] (system prompt),
                so the LLM can compare without a separate load.
    PARAMS:  agent_name: str — which agent ran
             messages: list[dict] — full message history from the session
             result: str — the agent's final output (for logging)
    """
    if not messages:
        log.debug("No messages to analyze for '%s' — skipping", agent_name)
        return

    transcript = format_session_for_analysis(messages)
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(transcript=transcript)

    log.info("Analyzing session for '%s' (%d messages, %d chars transcript)...",
             agent_name, len(messages), len(transcript))

    try:
        llm_model, llm_api_key, llm_api_base = settings.resolve_model()
        response = await litellm.acompletion(
            model=llm_model,
            messages=[
                {"role": "system", "content": "You analyze agent performance and extract lessons. Be concise and specific."},
                {"role": "user", "content": prompt},
            ],
            api_key=llm_api_key,
            api_base=llm_api_base,
            temperature=0.1,
            max_tokens=4096,
        )
        analysis = response.choices[0].message.content.strip()
        log.info("Learning LLM response for '%s' (%d chars): %s",
                 agent_name, len(analysis), analysis[:300])
    except Exception as e:
        log.warning("Learning analysis LLM call failed for '%s': %s", agent_name, e)
        return

    if not analysis or analysis == "NO_CHANGE":
        log.info("No new lessons for '%s'", agent_name)
        return

    save_experience(agent_name, analysis)
