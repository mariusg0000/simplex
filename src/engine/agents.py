"""
src/engine/agents.py · Sub-agent architecture + AgentRegistry + ToolCapableAgent.
Discovers and runs .md-defined agents with session isolation, tool access, and
streaming LLM interaction. Depends on: litellm, ToolRegistry (tools.py), settings (config.py).
"""

import asyncio
import json
import logging
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict, Any, Optional, Set, Callable

import litellm
from src.config import settings
from src.engine.tools import registry, agent_params_ctx

log = logging.getLogger("simplex.engine.agents")

AGENTS_BUILTIN_DIR = Path(__file__).resolve().parent.parent / "agents"
AGENTS_CUSTOM_DIR = Path.home() / ".simplexai" / "agents"

@dataclass
class AgentDef:
    """
    WHAT:    Parsed definition of a single agent from its .md file.
    WHY:     Provides a typed contract between the .md declarative format and
             the runtime logic in AgentRegistry and ToolCapableAgent.
    FIELDS:  name: str — filename stem
             enabled: bool — parsed from ## enabled
             description: str — LLM-facing summary from ## agent_description
             allowed_tools: list[str] — tool names the agent may call
             role_prompt: str — system prompt from ## role_prompt (may contain {work_dir})
             execute_script: str — Python code that creates a session folder (optional)
             done_tool: str — tool name that signals completion (default "task_done")
             model: str — model override for this agent (empty = use default)
    """
    name: str
    enabled: bool
    description: str
    allowed_tools: list[str]
    role_prompt: str
    execute_script: str = ""
    done_tool: str = "task_done"
    model: str = ""


def _parse_agent_md(content: str) -> dict:
    """
    WHAT:    Parses an agent .md file into a dict of section_name → body.
    WHY:     Agents are authored in markdown with ## section headers; this parser
             extracts each section as raw text for structured field extraction.
    HOW:     Iterates lines, matching ## <section> headers. Everything between
             headers belongs to the preceding section. Section names are lowercased.
    PARAMS:  content: str — raw text of the .md file
    RETURNS: dict[str, str] — section name → body (empty dict if no sections)
    """
    sections = {}
    pattern = r'^##\s+(\S+)\s*$'
    lines = content.split('\n')
    current_section = None
    current_lines = []

    for line in lines:
        m = re.match(pattern, line.strip())
        if m:
            if current_section:
                sections[current_section] = '\n'.join(current_lines).strip()
            current_section = m.group(1).lower()
            current_lines = []
        else:
            current_lines.append(line)

    if current_section:
        sections[current_section] = '\n'.join(current_lines).strip()

    return sections


class AgentRegistry:
    """
    WHAT:    Singleton registry that discovers, validates, and runs .md-defined agents.
    WHY:     Centralises agent lifecycle: discovery (from built-in and custom dirs),
             schema generation for the LLM, and invocation with session isolation.
    HOW:     Auto-discovers .md files on init from src/agents/ and ~/.simplexai/agents/.
             Each agent is parsed into an AgentDef. The call() method creates a
             sandboxed ToolCapableAgent that executes the task with its own tool set.
    """
    def __init__(self):
        self._agents: dict[str, AgentDef] = {}
        self._disabled: set[str] = set()
        self._discover(AGENTS_BUILTIN_DIR, "built-in")
        self._discover(AGENTS_CUSTOM_DIR, "custom")

    def _discover(self, directory: Path, source_label: str) -> None:
        """
        WHAT:    Scans a directory for .md agent files and registers valid ones.
        WHY:     Enables the plugin-like agent system: drop a .md file and it's
                 immediately available, without code changes.
        HOW:     Reads each .md, parses sections, validates required fields
                 (enabled, agent_description, allowed_tools, role_prompt), and
                 creates an AgentDef. Malformed files are logged and skipped.
        PARAMS:  directory: Path — folder to scan
                 source_label: str — "built-in" or "custom" (for logging)
        """
        if not directory.exists():
            return
        for filepath in sorted(directory.iterdir()):
            if filepath.suffix != ".md" or filepath.name.lower() == "readme.md":
                continue
            try:
                content = filepath.read_text(encoding="utf-8")
                sections = _parse_agent_md(content)

                required = {"enabled", "agent_description", "allowed_tools", "role_prompt"}
                missing = required - set(sections.keys())
                if missing:
                    log.warning(
                        f"Agent {filepath.name} missing sections: {missing} — skipped"
                    )
                    continue

                name = filepath.stem
                enabled = sections["enabled"].strip().lower() == "enabled"
                description = sections["agent_description"].strip()
                allowed_tools = [
                    line.strip()
                    for line in sections["allowed_tools"].strip().split('\n')
                    if line.strip()
                ]
                role_prompt = sections["role_prompt"].strip()
                execute_script = sections.get("execute_script", "").strip()
                done_tool_raw = sections.get("done_tool", "").strip()
                done_tool = done_tool_raw if done_tool_raw else "task_done"
                model_raw = sections.get("model", "").strip()

                agent_def = AgentDef(
                    name=name,
                    enabled=enabled,
                    description=description,
                    allowed_tools=allowed_tools,
                    role_prompt=role_prompt,
                    execute_script=execute_script,
                    done_tool=done_tool,
                    model=model_raw,
                )

                self._agents[name] = agent_def
                log.info("Loaded agent '%s' from %s (tools=%s, done='%s', has_exec=%s, model='%s')",
                         name, source_label, allowed_tools, done_tool,
                         "yes" if execute_script else "no",
                         model_raw if model_raw else "default")
            except Exception as e:
                log.error(f"Failed to load agent {filepath.name}: {e}")

    def get_descriptions(self) -> str:
        parts = []
        for name, agent in self._agents.items():
            if agent.enabled and name not in self._disabled:
                parts.append(f"[Agent: {name}]\n{agent.description}")
        return "\n\n".join(parts)

    def get_schemas(self) -> list[dict]:
        """
        WHAT:    Builds OpenAI function-calling schemas for all enabled agents.
        WHY:     The main agent's LLM sees these as callable functions; selecting
                 one triggers agent_registry.call(). The work_dir parameter is
                 conditionally exposed for agents with execute_script (workspace reuse).
        PARAMS:  none (uses self._agents, self._disabled)
        RETURNS: list[dict] — OpenAI tool schemas, one per enabled agent
        """
        schemas = []
        for name, agent in self._agents.items():
            if agent.enabled and name not in self._disabled:
                properties = {
                    "task": {
                        "type": "string",
                        "description": f"Task for the {name} agent. Describe what you need in detail."
                    },
                }
                if agent.execute_script:
                    properties["work_dir"] = {
                        "type": "string",
                        "description": (
                            "Existing session folder to reuse. When provided, the agent "
                            "continues working in this folder instead of creating a new one. "
                            "Use this for revisions or corrections to existing work."
                        ),
                    }
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": agent.description,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": ["task"],
                        },
                    },
                })
        return schemas

    async def call(self, name: str, arguments: dict) -> str:
        """
        WHAT:    Invokes a registered agent by name with the given arguments.
        WHY:     Entry point called by the main agent's tool loop. Handles session
                 setup (new or reused), {work_dir} placeholder resolution, sandbox
                 context injection, and result enrichment with session folder info.
        HOW:     1. Resolves work_dir: runs execute_script (new) or reuses existing folder.
                2. Sets agent_params_ctx so bash tool enforces sandbox.
                3. Replaces {work_dir} in the role prompt with the actual path.
                4. Creates a ToolCapableAgent and runs the task with streaming.
                5. Appends [Session folder: ...] to the result for caller reuse.
        PARAMS:  name: str — agent filename stem (e.g. "create_doc")
                 arguments: dict — must contain "task", may contain "work_dir"
        RETURNS: str — the agent's final output (typically a file path or summary)
        ERRORS:  Agent not found → "Error: Agent '...' not found."
                 work_dir invalid → "Error: Specified work_dir ... does not exist"
                 execute_script fails → "Error: Failed to initialize agent workspace: ..."
        """
        agent = self._agents.get(name)
        if not agent:
            return f"Error: Agent '{name}' not found."

        task = arguments.get("task", "")
        log.info("=== Agent '%s' called ===", name)
        log.info("task (first 300): %s", task[:300])

        dynamic_context = ""
        token = None
        params_dict = None
        resolved_prompt = agent.role_prompt

        if agent.execute_script:
            reuse_work_dir = arguments.get("work_dir")

            if reuse_work_dir:
                reuse_path = Path(reuse_work_dir).resolve()
                if not reuse_path.is_dir():
                    return (
                        f"Error: Specified work_dir '{reuse_work_dir}' does not exist "
                        f"or is not a directory."
                    )
                params_dict = {"work_dir": str(reuse_path)}
                token = agent_params_ctx.set(params_dict)
                dynamic_context = (
                    f"SANDBOX: {reuse_path}\n"
                    f"All work happens HERE and ONLY HERE. Scripts, temp files, final document — "
                    f"everything must be created inside this directory. No exceptions. "
                    f"The bash tool enforces this."
                )
                log.info("✓ reusing existing work_dir: %s", reuse_path)
            else:
                log.info("▶ running execute_script for '%s'", name)
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "python3", "-c", agent.execute_script,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await proc.communicate()
                    if proc.returncode == 0 and stdout:
                        output = stdout.decode().strip()
                        log.info("✓ execute_script output: %s", output)
                        params_dict = json.loads(output)
                        token = agent_params_ctx.set(params_dict)
                        wd = params_dict.get("work_dir", "")
                        dynamic_context = (
                            f"SANDBOX: {wd}\n"
                            f"All work happens HERE and ONLY HERE. Scripts, temp files, final document — "
                            f"everything must be created inside this directory. No exceptions. "
                            f"The bash tool enforces this."
                        )
                    else:
                        err_msg = stderr.decode().strip() or f"exit code {proc.returncode}"
                        log.error("✗ execute_script for '%s' failed: %s", name, err_msg)
                        return f"Error: Failed to initialize agent workspace: {err_msg}"
                except Exception as e:
                    log.error("✗ execute_script for '%s' error: %s", name, e)
                    return f"Error: Failed to initialize agent workspace: {e}"

            if params_dict and "work_dir" in params_dict:
                resolved_prompt = agent.role_prompt.replace("{work_dir}", params_dict["work_dir"])

        tc_agent = ToolCapableAgent(
            name=name,
            role_prompt=resolved_prompt,
            allowed_tools=agent.allowed_tools,
            done_tool_name=agent.done_tool,
        )

        model_override = agent.model or None

        on_step = activity_callback.get()
        on_stream = agent_stream_callback.get()
        try:
            log.info("▶ running agent '%s' (max_rounds=%d, done_tool='%s', model='%s')",
                     name, tc_agent.max_rounds, tc_agent.done_tool_name,
                     model_override or "default")
            result = await tc_agent.run(task, model_override=model_override,
                                        on_step=on_step, on_stream=on_stream,
                                        dynamic_context=dynamic_context)
            log.info("=== Agent '%s' done ===", name)
            log.info("result: %s", result[:500])

            # Enrich result with session folder info so caller can reuse it
            if params_dict and "work_dir" in params_dict:
                wd = params_dict["work_dir"]
                session_tag = f"[Session folder: {wd}]"
                if session_tag not in result:
                    result = f"{result}\n{session_tag}"

            return result
        finally:
            if token is not None:
                agent_params_ctx.reset(token)

    def disable(self, name: str):
        self._disabled.add(name)

    def enable(self, name: str):
        self._disabled.discard(name)

    def is_disabled(self, name: str) -> bool:
        return name in self._disabled

    def __contains__(self, name: str) -> bool:
        return name in self._agents


agent_registry = AgentRegistry()


@dataclass
class AgentStep:
    agent_name: str
    round: int
    step_type: str
    content: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M:%S")


activity_callback: ContextVar[Optional[Callable[[AgentStep], None]]] = (
    ContextVar("activity_callback", default=None)
)


@dataclass
class AgentStreamChunk:
    """A chunk of streaming LLM output (reasoning or content) for live display."""
    agent_name: str
    round: int
    chunk_type: str  # "reasoning" or "content"
    content: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M:%S")


agent_stream_callback: ContextVar[Optional[Callable[[AgentStreamChunk], None]]] = (
    ContextVar("agent_stream_callback", default=None)
)


class SubAgent:
    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt

    async def run(self, task_input: str, model_override: Optional[str] = None) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task_input}
        ]

        model_str = model_override or settings.chat_model
        llm_model, llm_api_key, llm_api_base = settings.resolve_model(model_str)
        response = await litellm.acompletion(
            model=llm_model,
            messages=messages,
            api_key=llm_api_key,
            api_base=llm_api_base,
            temperature=0.1
        )

        return response.choices[0].message.content


class RerankerAgent(SubAgent):
    def __init__(self):
        super().__init__(
            name="Reranker",
            system_prompt=(
                "You are an expert File System Analyst. Your task is to look at a list of raw file paths "
                "and select the most relevant ones based on the user's search context.\n"
                "RULES:\n"
                "1. Return a comma-separated list of ONLY the best paths (max 10).\n"
                "2. Prioritize files that look like source documents, code, or data (PDF, DOCX, MD, PY, CSV).\n"
                "3. Ignore temporary, cache, or build-related files if others are available.\n"
                "4. If nothing seems relevant, return 'NONE'.\n"
                "5. Output ONLY the paths, nothing else."
            )
        )

    async def rerank_files(self, query: str, file_paths: List[str]) -> List[str]:
        if not file_paths:
            return []

        task_input = f"User is searching for: '{query}'\nRaw results found:\n" + "\n".join(file_paths)
        result = await self.run(task_input)

        if "NONE" in result:
            return []

        cleaned_paths = [p.strip().strip("'\"") for p in result.replace("\n", ",").split(",") if p.strip()]
        return cleaned_paths[:10]


class ToolCapableAgent:
    """
    WHAT:    Multi-turn LLM agent that calls tools in a loop until done.
    WHY:     Sub-agents (create_doc, etc.) need tool access, streaming output,
             and self-termination without main-agent round-trips. This class
             provides the core loop: LLM → tool call → tool result → repeat.
    HOW:     Maintains its own message history. At each round: calls LLM with
             allowed tool schemas, streams response, executes tool calls via
             ToolRegistry, checks for _AGENT_DONE_ auto-termination, repeats
             up to max_rounds. State is in self.messages (no external DB).
    """
    def __init__(
        self,
        name: str,
        role_prompt: str,
        allowed_tools: Optional[list[str]] = None,
        allowed_cli: Optional[list[str]] = None,
        max_rounds: int = 20,
        done_tool_name: str = "task_done",
    ):
        """
        PARAMS:  name: str — agent identifier (for logging)
                 role_prompt: str — system prompt, may be pre-resolved by AgentRegistry
                 allowed_tools: list[str] or None — tool names the agent may call
                 allowed_cli: list[str] or None — CLI prompt keys for bash context
                 max_rounds: int — max LLM+tool cycles before forced termination
                 done_tool_name: str — tool called to signal completion
        """
        self.name = name
        self.role_prompt = role_prompt
        self.allowed_tools: Set[str] = set(allowed_tools or [])
        self.allowed_cli: Set[str] = set(allowed_cli or [])
        self.max_rounds = max_rounds
        self.done_tool_name = done_tool_name
        self.messages: list[dict] = []

    def _build_system_prompt(self) -> str:
        """
        WHAT:    Assembles the final system prompt by appending CLI docs
                 and accumulated experience from past sessions.
        WHY:     CLI-heavy agents (like create_doc) need explicit docs for
                 bash commands (weasyprint, python3 flags, etc.). These are
                 loaded from cli_prompts.toml and appended to the role prompt.
                 Additionally, per-agent experience files (~/.simplexai/experience/*.md)
                 are loaded so lessons from previous runs are available.
        PARAMS:  none (uses self.allowed_cli, self.role_prompt)
        RETURNS: str — combined system prompt
        """
        from src.prompts import load_cli_prompts
        prompts = load_cli_prompts()
        cli_sections = [prompts[k] for k in self.allowed_cli if k in prompts]
        cli_part = "\n\n".join(cli_sections) if cli_sections else ""
        prompt = self.role_prompt
        if cli_part:
            prompt = self.role_prompt + "\n\n" + cli_part

        # Append accumulated experience from previous sessions
        try:
            from src.engine.learning import load_experience
            exp = load_experience(self.name)
            if exp:
                prompt += f"\n\n## ACCUMULATED EXPERIENCE\n\n{exp}"
        except Exception as e:
            log.warning("Failed to load experience for '%s': %s", self.name, e)

        return prompt

    def _get_allowed_schemas(self) -> list[dict]:
        """
        WHAT:    Filters tool schemas to only those in self.allowed_tools.
        WHY:     Restricts the LLM's tool choice to the agent's permitted set.
                 When allowed_tools is empty/None, all registry tools are exposed.
        PARAMS:  none (uses self.allowed_tools, registry.schemas)
        RETURNS: list[dict] — filtered OpenAI tool schemas
        """
        if not self.allowed_tools:
            return registry.get_schemas()
        return [s for s in registry.schemas if s["function"]["name"] in self.allowed_tools]

    _COALESCE_SEC = 0.3  # Streaming chunk emit interval

    async def run(
        self,
        task_input: str,
        model_override: Optional[str] = None,
        on_step: Optional[Callable[[AgentStep], None]] = None,
        on_stream: Optional[Callable[[AgentStreamChunk], None]] = None,
        dynamic_context: Optional[str] = None,
    ) -> str:
        """
        WHAT:    Main multi-turn tool-calling loop. Calls LLM, streams output,
                 executes tool calls, checks for auto-termination, repeats.
        WHY:     Sub-agents need an autonomous loop without main-agent involvement.
                 The LLM decides when it's done (no tool calls or _AGENT_DONE_).
        HOW:     Per round:
                 1. Calls litellm.acompletion with streaming + tool schemas.
                 2. Consumes the stream: reasoning/content chunks + coalesced emit.
                 3. If no tool calls → agent is done, returns content.
                 4. Otherwise executes each tool call via registry.call().
                 5. _AGENT_DONE_ prefix → auto-terminate with the result.
                 6. max_rounds exceeded → injects a fallback prompt then force-ends.
        PARAMS:  task_input: str — the user's task description
                 model_override: Optional[str] — model name or None for default
                 on_step: Optional[Callable[[AgentStep], None]] — activity log callback
                 on_stream: Optional[Callable[[AgentStreamChunk], None]] — live streaming callback
                 dynamic_context: Optional[str] — extra context appended to system prompt
        RETURNS: str — the agent's final output (file path, summary, or error)
        ERRORS:  CancelledError → "Error: Task cancelled by user."
                 LLM/completion error → "Error: <details>"
                 Streaming error → "Error: Streaming failed: <details>"
                 Max rounds exhausted → "Error: Max rounds reached without final response."
        """
        system_prompt = self._build_system_prompt()
        if dynamic_context:
            system_prompt += "\n\n" + dynamic_context
        self.messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_input},
        ]

        round_num = 1
        gave_fallback = False
        while round_num <= self.max_rounds:
            log.info("┌─ %s round %d/%d", self.name, round_num, self.max_rounds)

            schemas = self._get_allowed_schemas()
            if on_step:
                on_step(AgentStep(self.name, round_num, "llm_call", "Thinking..."))

            response = None
            try:
                model_str = model_override or settings.chat_model
                llm_model, llm_api_key, llm_api_base = settings.resolve_model(model_str)
                response = await litellm.acompletion(
                    model=llm_model,
                    messages=self.messages,
                    api_key=llm_api_key,
                    api_base=llm_api_base,
                    temperature=0.1,
                    tools=schemas if schemas else None,
                    tool_choice="auto" if schemas else None,
                    stream=True,
                )
            except asyncio.CancelledError:
                log.warning("! agent '%s' cancelled by user", self.name)
                if on_step:
                    on_step(AgentStep(self.name, round_num, "error", "Task cancelled by user."))
                return "Error: Task cancelled by user."
            except Exception as e:
                log.error("! agent '%s' LLM error: %s", self.name, e)
                if on_step:
                    on_step(AgentStep(self.name, round_num, "error", str(e)))
                return f"Error: {str(e)}"

            full_reasoning = ""
            full_content = ""
            tool_calls_stream: dict[int, dict] = {}
            buf = {"reasoning": "", "content": ""}
            last_emit = 0.0
            try:
                async for chunk in response:
                    delta = chunk.choices[0].delta

                    r = getattr(delta, "reasoning_content", None)
                    if r:
                        full_reasoning += r
                        buf["reasoning"] += r
                    if delta.content:
                        full_content += delta.content
                        buf["content"] += delta.content
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_stream:
                                tool_calls_stream[idx] = {
                                    "id": "", "function": {"name": "", "arguments": ""},
                                }
                            if tc.id:
                                tool_calls_stream[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_stream[idx]["function"]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_calls_stream[idx]["function"]["arguments"] += tc.function.arguments

                    now = time.monotonic()
                    if (buf["reasoning"] or buf["content"]) and (now - last_emit) >= self._COALESCE_SEC:
                        if on_stream:
                            for ct in ("reasoning", "content"):
                                if buf[ct]:
                                    on_stream(AgentStreamChunk(self.name, round_num, ct, buf[ct]))
                                    buf[ct] = ""
                        last_emit = now

            except asyncio.CancelledError:
                log.warning("! agent '%s' streaming cancelled", self.name)
                if on_step:
                    on_step(AgentStep(self.name, round_num, "error", "Streaming cancelled."))
                return "Error: Task cancelled."
            except Exception as e:
                log.error("! agent '%s' streaming error: %s", self.name, e)
                if on_step:
                    on_step(AgentStep(self.name, round_num, "error", f"Stream error: {e}"))
                return f"Error: Streaming failed: {e}"

            if on_stream:
                for ct in ("reasoning", "content"):
                    if buf[ct]:
                        on_stream(AgentStreamChunk(self.name, round_num, ct, buf[ct]))

            reasoning = full_reasoning or ""
            tc_list = []
            for idx in sorted(tool_calls_stream.keys()):
                tc_data = tool_calls_stream[idx]
                tc_list.append(SimpleNamespace(
                    id=tc_data["id"],
                    function=SimpleNamespace(
                        name=tc_data["function"]["name"],
                        arguments=tc_data["function"]["arguments"],
                    ),
                ))

            has_tool_calls = bool(tc_list)
            log.info("│ %s round %d: reasoning=%d chars, content=%d chars, tool_calls=%d",
                     self.name, round_num, len(full_reasoning), len(full_content), len(tc_list))

            if not has_tool_calls:
                output = full_content or ""
                log.info("└─ %s done (no tool calls, %d chars)", self.name, len(output))
                if on_step:
                    on_step(AgentStep(self.name, round_num, "done", output[:200]))
                return output

            assistant_msg = {"role": "assistant", "content": full_content or None}
            if reasoning:
                assistant_msg["reasoning_content"] = reasoning

            formatted_calls = []
            for tc in tc_list:
                fmt = {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                formatted_calls.append(fmt)
            assistant_msg["tool_calls"] = formatted_calls
            self.messages.append(assistant_msg)

            log.info("│ %s round %d: %d tool call(s)", self.name, round_num, len(formatted_calls))
            if reasoning:
                log.info("│ reasoning: %s...", reasoning[:200])

            for tc in formatted_calls:
                name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]

                if on_step:
                    snippet = raw_args[:200] if name == "bash" else ""
                    label = f"bash: {snippet}..." if snippet else f"{name}(...)"
                    on_step(AgentStep(self.name, round_num, "tool_call", label))

                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    log.warning("! JSON decode error for tool '%s': %s", name, raw_args[:100])
                    args = {}

                log.info("│   %s → calling %s(args=%s)", self.name, name, args)
                result = await registry.call(name, args)
                result_str = str(result)
                log.info("│   %s ← %s", self.name, result_str[:250])

                if on_step:
                    trunc = result_str[:200]
                    on_step(AgentStep(self.name, round_num, "tool_result", trunc))

                # _AGENT_DONE_ prefix signals that the tool has completed the
                # agent's task successfully. Any tool can use this to auto-
                # terminate, eliminating an unnecessary LLM round.
                if result_str.startswith("_AGENT_DONE_:"):
                    done_result = result_str.split(":", 1)[1].strip()
                    log.info("│ %s ← _AGENT_DONE_ from tool '%s': %s",
                             self.name, name, done_result[:300])
                    if on_step:
                        on_step(AgentStep(self.name, round_num, "done", done_result[:200]))
                    log.info("└─ %s finished (_AGENT_DONE_)", self.name)

                    # Learning analysis: extract lessons from this session
                    try:
                        from src.engine.learning import analyze_and_learn
                        log.info("Running learning analysis for '%s' (%d messages)",
                                 self.name, len(self.messages))
                        await analyze_and_learn(self.name, self.messages, done_result)
                    except Exception as e:
                        log.warning("Learning analysis failed for '%s': %s", self.name, e)

                    return done_result

                remaining = self.max_rounds - round_num
                round_tag = f"\n\n[Round {round_num}/{self.max_rounds}"
                if remaining <= 3:
                    round_tag += " 🛑 CRITICAL — finish now!"
                elif remaining <= 6:
                    round_tag += f" ⚠️ only {remaining} left"
                round_tag += "]"
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": result_str + round_tag,
                })

            if round_num == self.max_rounds and not gave_fallback:
                log.warning("! %s hit max_rounds, injecting fallback prompt", self.name)
                self.messages.append({
                    "role": "user",
                    "content": f"Maximum attempts reached. Call {self.done_tool_name}(result='...') with what you have. Do NOT continue working on the task."
                })
                self.max_rounds += 1
                gave_fallback = True

            round_num += 1

        log.error("! %s exhausted all %d rounds", self.name, self.max_rounds)

        last_content = ""
        for m in reversed(self.messages):
            if m["role"] == "assistant" and m.get("content"):
                last_content = m["content"][:300]
                break

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

        # Learning analysis even on failure — failures are the most valuable lessons
        try:
            from src.engine.learning import analyze_and_learn
            log.info("Running learning analysis for '%s' on failure (%d messages)",
                     self.name, len(self.messages))
            await analyze_and_learn(self.name, self.messages, report)
        except Exception as e:
            log.warning("Learning analysis failed for '%s': %s", self.name, e)

        return report
